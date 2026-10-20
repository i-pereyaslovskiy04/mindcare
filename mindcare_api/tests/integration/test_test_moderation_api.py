"""
Integration: moderation workflow тестов (Этап F, ADR-016).

Покрывает:
  - видимость студенту = status='published' AND is_active=True (draft/in_review
    не видны ни в списке, ни при попытке пройти);
  - admin публикует draft → студент видит и может пройти; пишет test_published;
  - admin возвращает in_review → needs_changes; пишет test_returned_for_changes;
  - psychologist-автор отправляет свой draft на модерацию (in_review); пишет
    test_submitted_for_review;
  - psychologist НЕ может отправить чужой draft → 403, без audit;
  - нелегальный переход состояния → 409 (не 403), без audit.

Требует dev/disposable PostgreSQL (Stage 1 isolated runner).
"""
import uuid as _uuid

import bcrypt
import pytest

from app.auth import storage as auth_storage
from app.db.session import SessionLocal
from app.db.models import AuditLog, Test as TestModel
from app.tests import storage as tests_storage
from tests.integration.conftest import create_test_user

PASSWORD = "SecurePass42!"


def _staff(client, role: str):
    user = auth_storage.save_user({
        "name": f"Moderation {role} {_uuid.uuid4().hex[:6]}",
        "email": f"integ_moder_{role}_{_uuid.uuid4().hex[:10]}@example.com",
        "hashed_password": bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode(),
        "role": role,
    })
    r = client.post("/api/auth/login", json={"email": user["email"], "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['session_token']}"}, int(user["id"])


def _student_headers(client):
    email = f"integ_moder_student_{_uuid.uuid4().hex[:10]}@example.com"
    create_test_user(email, PASSWORD)
    r = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['session_token']}"}


def _payload(title, status="draft"):
    return {
        "title": title, "description": "d", "scoring": "sum",
        "time_limit_min": None, "is_active": True, "status": status,
        "category_ids": [], "tag_uuids": [],
        "questions": [
            {"question_text": "Q1", "question_order": 1, "question_type": "single_choice",
             "is_required": True, "config": {},
             "options": [{"option_text": "нет", "option_order": 0, "value_score": 0},
                         {"option_text": "да", "option_order": 1, "value_score": 3}]},
        ],
        "interpretations": [],
    }


def _make_test(admin_id, status="draft"):
    """Тест напрямую через storage (обходит /admin/tests, чтобы задать произвольный
    status — Pydantic на HTTP-границе допускает при создании только draft/published)."""
    data = _payload(f"MODER {_uuid.uuid4().hex[:6]}", status="published")
    test = tests_storage.create_test(data, created_by=admin_id, actor_role="admin")
    if status != "published":
        with SessionLocal() as db:
            db.query(TestModel).filter(
                TestModel.uuid == _uuid.UUID(test["uuid"])
            ).update({"status": status})
            db.commit()
        test["status"] = status
    return test


def _reassign_author(test_uuid: str, new_author_id: int):
    """Тестовый фикстур-хелпер: подменяет created_by (симулирует, что черновик
    создал именно этот психолог — F1 не даёт HTTP-пути создания психологом)."""
    with SessionLocal() as db:
        db.query(TestModel).filter(
            TestModel.uuid == _uuid.UUID(test_uuid)
        ).update({"created_by": new_author_id})
        db.commit()


def _hard_delete_test(test_uuid):
    with SessionLocal() as db:
        t = db.query(TestModel).filter(TestModel.uuid == _uuid.UUID(test_uuid)).first()
        if t:
            db.delete(t)
            db.commit()


def _audit_rows(event_type: str, entity_id: int):
    with SessionLocal() as db:
        return (
            db.query(AuditLog)
            .filter(AuditLog.event_type == event_type, AuditLog.entity_id == entity_id)
            .all()
        )


def _internal_id(test_uuid: str) -> int:
    with SessionLocal() as db:
        return db.query(TestModel).filter(TestModel.uuid == _uuid.UUID(test_uuid)).first().id


# ── видимость: draft/in_review невидимы студенту ───────────────────────────────

@pytest.mark.parametrize("status", ["draft", "in_review", "needs_changes"])
def test_student_does_not_see_unpublished_test(client, status):
    admin, admin_id = _staff(client, "admin")
    test = _make_test(admin_id, status=status)
    try:
        headers = _student_headers(client)
        r = client.get("/api/tests?page=1&size=50", headers=headers)
        assert r.status_code == 200, r.text
        assert all(it["uuid"] != test["uuid"] for it in r.json()["items"])

        r = client.get(f"/api/tests/{test['uuid']}", headers=headers)
        assert r.status_code == 404, r.text
    finally:
        _hard_delete_test(test["uuid"])


# ── admin публикует draft → видим студенту, пишет test_published ──────────────

def test_admin_publishes_draft_and_student_sees_it(client):
    admin, admin_id = _staff(client, "admin")
    test = _make_test(admin_id, status="draft")
    try:
        r = client.post(f"/api/admin/tests/{test['uuid']}/publish", headers=admin)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "published"

        rows = _audit_rows("test_published", _internal_id(test["uuid"]))
        assert len(rows) == 1
        assert rows[0].user_id == admin_id

        headers = _student_headers(client)
        r = client.get(f"/api/tests/{test['uuid']}", headers=headers)
        assert r.status_code == 200, r.text
    finally:
        _hard_delete_test(test["uuid"])


def test_supervisor_publishes_draft(client):
    admin, admin_id = _staff(client, "admin")
    supervisor, _ = _staff(client, "supervisor")
    test = _make_test(admin_id, status="draft")
    try:
        r = client.post(f"/api/admin/tests/{test['uuid']}/publish", headers=supervisor)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "published"
    finally:
        _hard_delete_test(test["uuid"])


# ── admin/supervisor возвращают in_review → needs_changes ──────────────────────

def test_admin_returns_in_review_for_changes(client):
    admin, admin_id = _staff(client, "admin")
    test = _make_test(admin_id, status="in_review")
    try:
        r = client.post(
            f"/api/admin/tests/{test['uuid']}/return",
            json={"reason": "нужно уточнить формулировку"}, headers=admin,
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "needs_changes"

        rows = _audit_rows("test_returned_for_changes", _internal_id(test["uuid"]))
        assert len(rows) == 1
        # reason — свободный текст, в audit НЕ попадает (metadata пустая)
        assert (rows[0].log_metadata or {}) == {}
    finally:
        _hard_delete_test(test["uuid"])


# ── psychologist-автор отправляет свой тест на модерацию ──────────────────────

def test_psychologist_submits_own_draft_for_review(client):
    admin, admin_id = _staff(client, "admin")
    psych, psych_id = _staff(client, "psychologist")
    test = _make_test(admin_id, status="draft")
    _reassign_author(test["uuid"], psych_id)
    try:
        r = client.post(
            f"/api/psychologist/tests/{test['uuid']}/submit-for-review", headers=psych,
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "in_review"

        rows = _audit_rows("test_submitted_for_review", _internal_id(test["uuid"]))
        assert len(rows) == 1
        assert rows[0].user_id == psych_id
    finally:
        _hard_delete_test(test["uuid"])


def test_psychologist_submits_own_needs_changes_for_review(client):
    admin, admin_id = _staff(client, "admin")
    psych, psych_id = _staff(client, "psychologist")
    test = _make_test(admin_id, status="needs_changes")
    _reassign_author(test["uuid"], psych_id)
    try:
        r = client.post(
            f"/api/psychologist/tests/{test['uuid']}/submit-for-review", headers=psych,
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "in_review"
    finally:
        _hard_delete_test(test["uuid"])


def test_psychologist_cannot_submit_others_draft(client):
    admin, admin_id = _staff(client, "admin")
    psych, _ = _staff(client, "psychologist")   # НЕ автор
    test = _make_test(admin_id, status="draft")   # created_by = admin_id
    try:
        r = client.post(
            f"/api/psychologist/tests/{test['uuid']}/submit-for-review", headers=psych,
        )
        assert r.status_code == 403, r.text
        assert _audit_rows("test_submitted_for_review", _internal_id(test["uuid"])) == []
        # статус не изменился
        r2 = client.get(f"/api/admin/tests/{test['uuid']}", headers=admin)
        assert r2.json()["status"] == "draft"
    finally:
        _hard_delete_test(test["uuid"])


def test_student_cannot_submit_for_review(client):
    admin, admin_id = _staff(client, "admin")
    test = _make_test(admin_id, status="draft")
    _reassign_author(test["uuid"], admin_id)
    try:
        headers = _student_headers(client)
        r = client.post(
            f"/api/psychologist/tests/{test['uuid']}/submit-for-review", headers=headers,
        )
        assert r.status_code == 403, r.text   # require_role("psychologist") на роутере
    finally:
        _hard_delete_test(test["uuid"])


# ── нелегальные переходы → 409, без audit ───────────────────────────────────────

def test_publish_already_published_returns_409(client):
    admin, admin_id = _staff(client, "admin")
    test = _make_test(admin_id, status="published")
    try:
        r = client.post(f"/api/admin/tests/{test['uuid']}/publish", headers=admin)
        assert r.status_code == 409, r.text
        assert _audit_rows("test_published", _internal_id(test["uuid"])) == []
    finally:
        _hard_delete_test(test["uuid"])


def test_return_draft_returns_409(client):
    # return легален только из in_review
    admin, admin_id = _staff(client, "admin")
    test = _make_test(admin_id, status="draft")
    try:
        r = client.post(
            f"/api/admin/tests/{test['uuid']}/return", json={}, headers=admin,
        )
        assert r.status_code == 409, r.text
    finally:
        _hard_delete_test(test["uuid"])


def test_admin_tests_list_shows_all_statuses_by_default(client):
    """Критично после data-миграции: список НЕ фильтрует по status без query —
    иначе мигрированные-в-draft тесты пропали бы из вида админа."""
    admin, admin_id = _staff(client, "admin")
    draft = _make_test(admin_id, status="draft")
    try:
        r = client.get("/api/admin/tests?page=1&size=100", headers=admin)
        assert r.status_code == 200, r.text
        assert any(it["uuid"] == draft["uuid"] for it in r.json()["items"])

        r = client.get("/api/admin/tests?page=1&size=100&status=published", headers=admin)
        assert all(it["uuid"] != draft["uuid"] for it in r.json()["items"])
    finally:
        _hard_delete_test(draft["uuid"])
