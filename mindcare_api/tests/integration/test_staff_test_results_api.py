"""
Integration: staff-доступ к результатам психодиагностики (Этап E, ADR-016).

Покрывает:
  - supervisor читает результат любого студента → 200 + audit test_result_content_read;
  - psychologist своего студента (active/past engagement) → 200 + audit(psychologist);
  - psychologist чужого студента (без engagement) → 403 БЕЗ audit;
  - admin → 403 (роль вне роутера);
  - список — metadata-only (без total_score/scales), тоже под scope;
  - staff НЕ читает результаты другого staff (resolve_student_id: только чистый student).

Требует dev/disposable PostgreSQL (Stage 1 isolated runner).
"""
import uuid as _uuid

import bcrypt
import pytest

from app.auth import storage as auth_storage
from app.db.session import SessionLocal
from app.db.models import AuditLog, TherapyEngagement, TestResult, User, Test as TestModel
from app.tests import storage as tests_storage
from tests.integration.conftest import create_test_user

PASSWORD = "SecurePass42!"


def _staff(client, role: str):
    user = auth_storage.save_user({
        "name": f"StaffRes {role} {_uuid.uuid4().hex[:6]}",
        "email": f"integ_staffres_{role}_{_uuid.uuid4().hex[:10]}@example.com",
        "hashed_password": bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode(),
        "role": role,
    })
    r = client.post("/api/auth/login", json={"email": user["email"], "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['session_token']}"}, int(user["id"])


def _student(client):
    email = f"integ_staffres_student_{_uuid.uuid4().hex[:10]}@example.com"
    create_test_user(email, PASSWORD)
    with SessionLocal() as db:
        u = db.query(User).filter(User.email == email).first()
        sid, suuid = u.id, str(u.uuid)
    r = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    return {"Authorization": f"Bearer {r.json()['session_token']}"}, sid, suuid


def _make_test(admin_id):
    data = {
        "title": f"STAFFRES {_uuid.uuid4().hex[:6]}", "description": "d",
        "scoring": "sum", "max_score": 3, "time_limit_min": None, "is_active": True,
        "category_ids": [], "tag_uuids": [],
        "questions": [
            {"question_text": "Q1", "question_order": 1, "question_type": "single_choice",
             "is_required": True, "config": {},
             "options": [{"option_text": "нет", "option_order": 0, "value_score": 0},
                         {"option_text": "да", "option_order": 1, "value_score": 3}]},
        ],
        "interpretations": [
            {"scale_name": None, "min_score": 0, "max_score": 3, "label": "L", "recommendation": "r"},
        ],
    }
    return tests_storage.create_test(data, created_by=admin_id, actor_role="admin")


def _submit_result(client, student_headers, test) -> str:
    client.post("/api/tests/consent/accept", headers=student_headers)
    q = test["questions"][0]
    r = client.post(
        f"/api/tests/{test['uuid']}/submit",
        json={"answers": [{"question_id": q["id"], "option_id": q["options"][1]["id"]}]},
        headers=student_headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["uuid"]


def _engagement(psych_id, client_id, status="active"):
    with SessionLocal() as db:
        eng = TherapyEngagement(psychologist_id=psych_id, client_id=client_id, status=status)
        db.add(eng)
        db.commit()


def _result_db_id(result_uuid):
    with SessionLocal() as db:
        return db.query(TestResult).filter(TestResult.uuid == _uuid.UUID(result_uuid)).first().id


def _content_read_rows(result_id):
    with SessionLocal() as db:
        return (
            db.query(AuditLog)
            .filter(AuditLog.event_type == "test_result_content_read",
                    AuditLog.entity_id == result_id)
            .all()
        )


def _cleanup_test(test_uuid):
    with SessionLocal() as db:
        t = db.query(TestModel).filter(TestModel.uuid == _uuid.UUID(test_uuid)).first()
        if not t:
            return
        db.query(TestResult).filter(TestResult.test_id == t.id).delete(synchronize_session=False)
        db.delete(t)
        db.commit()


@pytest.fixture
def scenario(client):
    admin_headers, admin_id = _staff(client, "admin")
    student_headers, student_id, student_uuid = _student(client)
    test = _make_test(admin_id)
    result_uuid = _submit_result(client, student_headers, test)
    try:
        yield {
            "student_id": student_id, "student_uuid": student_uuid,
            "result_uuid": result_uuid, "result_id": _result_db_id(result_uuid),
        }
    finally:
        _cleanup_test(test["uuid"])


# ── detail: supervisor любой ──────────────────────────────────────────────────

def test_supervisor_reads_any_result_and_audits(client, scenario):
    headers, _ = _staff(client, "supervisor")
    r = client.get(f"/api/staff/test-results/{scenario['result_uuid']}", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["total_score"] == 3
    rows = _content_read_rows(scenario["result_id"])
    assert len(rows) == 1
    assert rows[0].user_role == "supervisor"


# ── detail: psychologist по engagement ────────────────────────────────────────

def test_psychologist_reads_own_student_result(client, scenario):
    headers, psych_id = _staff(client, "psychologist")
    _engagement(psych_id, scenario["student_id"])
    r = client.get(f"/api/staff/test-results/{scenario['result_uuid']}", headers=headers)
    assert r.status_code == 200, r.text
    rows = _content_read_rows(scenario["result_id"])
    assert len(rows) == 1 and rows[0].user_role == "psychologist"


def test_psychologist_denied_without_engagement_and_no_audit(client, scenario):
    headers, _ = _staff(client, "psychologist")   # без engagement
    r = client.get(f"/api/staff/test-results/{scenario['result_uuid']}", headers=headers)
    assert r.status_code == 403, r.text
    assert _content_read_rows(scenario["result_id"]) == []


# ── admin исключён ────────────────────────────────────────────────────────────

def test_admin_has_no_access(client, scenario):
    headers, _ = _staff(client, "admin")
    r = client.get(f"/api/staff/test-results/{scenario['result_uuid']}", headers=headers)
    assert r.status_code == 403, r.text


# ── список metadata-only ──────────────────────────────────────────────────────

def test_supervisor_list_is_metadata_only(client, scenario):
    headers, _ = _staff(client, "supervisor")
    r = client.get(
        f"/api/staff/test-results?student_uuid={scenario['student_uuid']}", headers=headers,
    )
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert len(items) == 1
    assert set(items[0].keys()) == {"uuid", "test_title", "submitted_at"}


def test_psychologist_list_denied_without_engagement(client, scenario):
    headers, _ = _staff(client, "psychologist")
    r = client.get(
        f"/api/staff/test-results?student_uuid={scenario['student_uuid']}", headers=headers,
    )
    assert r.status_code == 403, r.text


# ── staff-на-staff запрещён (resolve_student_id: только чистый student) ────────

def test_supervisor_cannot_list_by_staff_uuid(client, scenario):
    headers, _ = _staff(client, "supervisor")
    # uuid другого supervisor'а — не чистый student → 404 (не найден как студент)
    _, other_id = _staff(client, "supervisor")
    with SessionLocal() as db:
        other_uuid = str(db.query(User).filter(User.id == other_id).first().uuid)
    r = client.get(f"/api/staff/test-results?student_uuid={other_uuid}", headers=headers)
    assert r.status_code == 404, r.text
