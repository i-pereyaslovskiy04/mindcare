"""
Integration-тесты прохождения теста (Этап B) на реальной dev-БД.

Покрывают:
  - ФЗ-152 consent-gate: submit без согласия → 403; accept → submit ок;
  - корректность подсчёта и сохранения результата (sum + интерпретация);
  - изоляцию value_score в выдаче для прохождения (GET /tests/{uuid});
  - приватность результата: чужой пользователь не видит результат (404);
  - валидацию обязательных вопросов (422).

Требует запущенный dev PostgreSQL на alembic head с seed (incl. test_consent v1).
"""

import uuid as _uuid

import pytest

from app.db.session import SessionLocal
from app.db.models import Test as TestModel, TestResult as TestResultModel
from app.tests import storage as tests_storage
from tests.integration.conftest import create_test_user


# ── helpers ───────────────────────────────────────────────────────────────────

def _login(client, email, password="SecurePass42!"):
    create_test_user(email, password)
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['session_token']}"}


def _make_test(created_by_email):
    """Создаёт активный тест (single_choice, sum) напрямую через storage."""
    with SessionLocal() as db:
        from app.db.models import User
        uid = db.query(User.id).filter(User.email == created_by_email).scalar()
    data = {
        "title": f"INTEG Тест {_uuid.uuid4().hex[:6]}",
        "description": "d", "scoring": "sum", "max_score": 6,
        "time_limit_min": None, "is_active": True,
        "category_ids": [], "tag_uuids": [],
        "questions": [
            {"question_text": "Q1", "question_order": 1, "question_type": "single_choice",
             "is_required": True, "config": {},
             "options": [{"option_text": "нет", "option_order": 0, "value_score": 0},
                         {"option_text": "да", "option_order": 1, "value_score": 3}]},
            {"question_text": "Q2", "question_order": 2, "question_type": "single_choice",
             "is_required": True, "config": {},
             "options": [{"option_text": "нет", "option_order": 0, "value_score": 0},
                         {"option_text": "да", "option_order": 1, "value_score": 3}]},
        ],
        "interpretations": [
            {"scale_name": None, "min_score": 0, "max_score": 2, "label": "Низкий", "recommendation": "ok"},
            {"scale_name": None, "min_score": 3, "max_score": 6, "label": "Высокий", "recommendation": "к специалисту"},
        ],
    }
    return tests_storage.create_test(data, created_by=uid)


def _hard_delete_test(test_uuid):
    """Подчищает созданный тест и его результаты (RESTRICT на test_results → удалять первыми)."""
    with SessionLocal() as db:
        t = db.query(TestModel).filter(TestModel.uuid == _uuid.UUID(test_uuid)).first()
        if not t:
            return
        db.query(TestResultModel).filter(
            TestResultModel.test_id == t.id
        ).delete(synchronize_session=False)
        db.delete(t)
        db.commit()


@pytest.fixture
def made_test(test_email):
    headers = None
    test = _make_test(test_email)  # автор = тот же integ-пользователь (cleanup удалит его)
    try:
        yield test
    finally:
        _hard_delete_test(test["uuid"])


# ── тесты ─────────────────────────────────────────────────────────────────────

def test_submit_requires_consent(client, test_email, made_test):
    headers = _login(client, test_email)
    answers = {"answers": [
        {"question_id": made_test["questions"][0]["id"], "option_id": made_test["questions"][0]["options"][1]["id"]},
        {"question_id": made_test["questions"][1]["id"], "option_id": made_test["questions"][1]["options"][0]["id"]},
    ]}
    r = client.post(f"/api/tests/{made_test['uuid']}/submit", json=answers, headers=headers)
    assert r.status_code == 403, r.text


def test_consent_flow_and_scoring(client, test_email, made_test):
    headers = _login(client, test_email)

    # consent status — изначально не принято
    r = client.get("/api/tests/consent", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["accepted"] is False

    # принять согласие
    r = client.post("/api/tests/consent/accept", headers=headers)
    assert r.status_code == 200 and r.json()["accepted"] is True

    # submit: Q1=да(3), Q2=да(3) → total 6 → «Высокий»
    q1, q2 = made_test["questions"]
    answers = {"answers": [
        {"question_id": q1["id"], "option_id": q1["options"][1]["id"]},
        {"question_id": q2["id"], "option_id": q2["options"][1]["id"]},
    ]}
    r = client.post(f"/api/tests/{made_test['uuid']}/submit", json=answers, headers=headers)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["total_score"] == 6
    assert body["max_possible"] == 6
    assert "Высокий" in (body["recommendations"] or "")
    result_uuid = body["uuid"]

    # результат виден в своём списке и по uuid
    r = client.get("/api/tests/results", headers=headers)
    assert r.status_code == 200 and r.json()["total"] >= 1
    r = client.get(f"/api/tests/results/{result_uuid}", headers=headers)
    assert r.status_code == 200 and r.json()["total_score"] == 6


def test_take_payload_hides_value_score(client, test_email, made_test):
    headers = _login(client, test_email)
    r = client.get(f"/api/tests/{made_test['uuid']}", headers=headers)
    assert r.status_code == 200, r.text
    for q in r.json()["questions"]:
        for o in q["options"]:
            assert "value_score" not in o


def test_required_question_missing_returns_422(client, test_email, made_test):
    headers = _login(client, test_email)
    client.post("/api/tests/consent/accept", headers=headers)
    q1 = made_test["questions"][0]
    answers = {"answers": [{"question_id": q1["id"], "option_id": q1["options"][1]["id"]}]}  # Q2 пропущен
    r = client.post(f"/api/tests/{made_test['uuid']}/submit", json=answers, headers=headers)
    assert r.status_code == 422, r.text


def test_result_is_private_to_owner(client, test_email, made_test):
    owner_headers = _login(client, test_email)
    client.post("/api/tests/consent/accept", headers=owner_headers)
    q1, q2 = made_test["questions"]
    answers = {"answers": [
        {"question_id": q1["id"], "option_id": q1["options"][1]["id"]},
        {"question_id": q2["id"], "option_id": q2["options"][0]["id"]},
    ]}
    r = client.post(f"/api/tests/{made_test['uuid']}/submit", json=answers, headers=owner_headers)
    assert r.status_code == 201, r.text
    result_uuid = r.json()["uuid"]

    # другой студент не видит чужой результат
    other_headers = _login(client, f"integ_other_{_uuid.uuid4().hex[:8]}@example.com")
    r = client.get(f"/api/tests/results/{result_uuid}", headers=other_headers)
    assert r.status_code == 404, r.text
