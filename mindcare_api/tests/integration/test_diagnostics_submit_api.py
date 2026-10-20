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
from app.db.models import (
    Test as TestModel, TestResult as TestResultModel, User,
)
from app.tests import storage as tests_storage
from tests.integration.conftest import create_test_user


# ── helpers ───────────────────────────────────────────────────────────────────

def _ensure_user(email, password="SecurePass42!") -> int:
    """Возвращает id пользователя, создавая его ТОЛЬКО при отсутствии.

    Фикстура made_test выполняется до логина, а `create_test` теперь
    fail-closed требует actor context — раньше в неё уходил `created_by=None`,
    который storage молча принимал. Поэтому автора нужно завести заранее, а
    логин не должен создавать его повторно.
    """
    with SessionLocal() as db:
        uid = db.query(User.id).filter(User.email == email).scalar()
    if uid is not None:
        return int(uid)
    return int(create_test_user(email, password)["id"])


def _login(client, email, password="SecurePass42!"):
    _ensure_user(email, password)
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['session_token']}"}


def _make_test(created_by_email):
    """Создаёт активный тест (single_choice, sum) напрямую через storage."""
    uid = _ensure_user(created_by_email)
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
    # Stage 4B-5: create_test пишет ATOMIC audit → нужен actor context.
    return tests_storage.create_test(data, created_by=uid, actor_role="admin")


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


def test_timed_out_submit_accepts_partial_answers(client, test_email, made_test):
    """Тайм-лимит (клиентский): авто-submit с пропущенными обязательными → 201,
    неотвеченный вопрос даёт 0 (а не 422 с потерей ответов)."""
    headers = _login(client, test_email)
    client.post("/api/tests/consent/accept", headers=headers)
    q1 = made_test["questions"][0]
    body = {
        "answers": [{"question_id": q1["id"], "option_id": q1["options"][1]["id"]}],
        "timed_out": True,   # Q2 пропущен намеренно
    }
    r = client.post(f"/api/tests/{made_test['uuid']}/submit", json=body, headers=headers)
    assert r.status_code == 201, r.text
    # только Q1 (3 балла) засчитан, Q2 = 0
    assert r.json()["total_score"] == 3


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


# ══════════════════════════════════════════════════════════════════════════════
# P0-1: правка теста с результатами · P0-3: шифрование свободного текста
# ══════════════════════════════════════════════════════════════════════════════

from app.core.encryption import ENCRYPTION_PREFIX, decrypt_text  # noqa: E402
from app.db.models import Question as QuestionModel, StudentAnswer  # noqa: E402
from app.tests import service as tests_service  # noqa: E402


def _make_test_with_free_text(created_by_email):
    uid = _ensure_user(created_by_email)
    data = {
        "title": f"INTEG FreeText {_uuid.uuid4().hex[:6]}",
        "description": None, "scoring": "sum", "max_score": None,
        "time_limit_min": None, "is_active": True,
        "category_ids": [], "tag_uuids": [],
        "questions": [
            {"question_text": "Q1", "question_order": 1, "question_type": "single_choice",
             "is_required": True, "config": {},
             "options": [{"option_text": "нет", "option_order": 0, "value_score": 0},
                         {"option_text": "да", "option_order": 1, "value_score": 3}]},
            {"question_text": "Опишите состояние", "question_order": 2,
             "question_type": "free_text", "is_required": True, "config": {}, "options": []},
        ],
        "interpretations": [],
    }
    return tests_storage.create_test(data, created_by=uid, actor_role="admin")


@pytest.fixture
def free_text_test(test_email):
    test = _make_test_with_free_text(test_email)
    try:
        yield test
    finally:
        _hard_delete_test(test["uuid"])


def test_free_text_answer_stored_encrypted(client, test_email, free_text_test):
    """Свободный текст ответа не должен лежать в БД открытым (ФЗ-152)."""
    headers = _login(client, test_email)
    client.post("/api/tests/consent/accept", headers=headers)

    secret = f"мне тревожно {_uuid.uuid4().hex[:8]}"
    q1, q2 = free_text_test["questions"]
    r = client.post(
        f"/api/tests/{free_text_test['uuid']}/submit",
        json={"answers": [
            {"question_id": q1["id"], "option_id": q1["options"][1]["id"]},
            {"question_id": q2["id"], "free_text_answer": secret},
        ]},
        headers=headers,
    )
    assert r.status_code == 201, r.text

    with SessionLocal() as db:
        stored = (
            db.query(StudentAnswer.free_text_answer_enc)
            .filter(StudentAnswer.question_id == q2["id"])
            .scalar()
        )
    assert stored, "свободный ответ не сохранился"
    assert stored.startswith(ENCRYPTION_PREFIX)
    assert secret not in stored
    assert decrypt_text(stored) == secret


def test_blank_required_free_text_rejected(client, test_email, free_text_test):
    headers = _login(client, test_email)
    client.post("/api/tests/consent/accept", headers=headers)
    q1, q2 = free_text_test["questions"]
    r = client.post(
        f"/api/tests/{free_text_test['uuid']}/submit",
        json={"answers": [
            {"question_id": q1["id"], "option_id": q1["options"][1]["id"]},
            {"question_id": q2["id"], "free_text_answer": "   "},
        ]},
        headers=headers,
    )
    assert r.status_code == 422, r.text


def _submit_once(client, test_email, made_test):
    headers = _login(client, test_email)
    client.post("/api/tests/consent/accept", headers=headers)
    q1, q2 = made_test["questions"]
    r = client.post(
        f"/api/tests/{made_test['uuid']}/submit",
        json={"answers": [
            {"question_id": q1["id"], "option_id": q1["options"][1]["id"]},
            {"question_id": q2["id"], "option_id": q2["options"][0]["id"]},
        ]},
        headers=headers,
    )
    assert r.status_code == 201, r.text


def test_editing_questions_with_results_raises_not_500(client, test_email, made_test):
    """
    До фикса замена вопросов упиралась в FK student_answers→questions (RESTRICT)
    и вылетала IntegrityError → HTTP 500. Теперь — доменная ошибка (HTTP 409).
    """
    _submit_once(client, test_email, made_test)

    new_questions = [{
        "question_text": "Изменённый вопрос", "question_order": 1,
        "question_type": "single_choice", "is_required": True, "config": {},
        "options": [{"option_text": "a", "option_order": 0, "value_score": 0},
                    {"option_text": "b", "option_order": 1, "value_score": 1}],
    }]
    with pytest.raises(tests_service.TestHasResults):
        tests_service.update_test(made_test["uuid"], {"questions": new_questions})

    # вопросы остались нетронутыми
    with SessionLocal() as db:
        t = db.query(TestModel).filter(
            TestModel.uuid == _uuid.UUID(made_test["uuid"])
        ).first()
        texts = [
            q.question_text for q in
            db.query(QuestionModel).filter(QuestionModel.test_id == t.id).all()
        ]
    assert sorted(texts) == ["Q1", "Q2"]


def test_metadata_edit_allowed_when_results_exist(client, test_email, made_test):
    """Переименование теста с результатами обязано проходить: FK держит вопросы, не заголовок."""
    _submit_once(client, test_email, made_test)
    with SessionLocal() as db:
        from app.db.models import User
        uid = db.query(User.id).filter(User.email == test_email).scalar()
    updated = tests_service.update_test(
        made_test["uuid"], {"title": "Переименованный INTEG тест"},
        actor_id=uid, actor_role="admin",
    )
    assert updated["title"] == "Переименованный INTEG тест"
    assert len(updated["questions"]) == 2


def test_duplicate_test_copies_tree_as_draft(test_email, made_test):
    with SessionLocal() as db:
        from app.db.models import User
        uid = db.query(User.id).filter(User.email == test_email).scalar()

    copy = tests_service.duplicate_test(
        made_test["uuid"], created_by=uid, actor_role="admin",
    )
    try:
        assert copy["uuid"] != made_test["uuid"]
        assert copy["is_active"] is False          # копия — черновик
        assert copy["version"] == 1
        assert copy["title"].endswith("(копия)")
        assert len(copy["questions"]) == 2
        assert [o["value_score"] for o in copy["questions"][0]["options"]] == [0, 3]
        assert len(copy["interpretations"]) == 2

        # у копии нет результатов → её вопросы редактируются свободно
        edited = tests_service.update_test(copy["uuid"], {"questions": [{
            "question_text": "Новый Q", "question_order": 1,
            "question_type": "single_choice", "is_required": True, "config": {},
            "options": [{"option_text": "a", "option_order": 0, "value_score": 0},
                        {"option_text": "b", "option_order": 1, "value_score": 2}],
        }]}, actor_id=uid, actor_role="admin")
        assert [q["question_text"] for q in edited["questions"]] == ["Новый Q"]
    finally:
        _hard_delete_test(copy["uuid"])
