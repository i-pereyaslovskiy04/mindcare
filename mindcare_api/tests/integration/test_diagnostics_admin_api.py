"""
API/integration-тесты admin-эндпоинтов психодиагностики.

Закрывают дефект: PATCH /api/admin/tests/{uuid} с вопросами теста, по которому
уже есть результаты, отдавал HTTP 500 (IntegrityError на FK student_answers →
questions, ON DELETE RESTRICT). Теперь — 409 с понятным текстом, а штатный путь
правки — POST /api/admin/tests/{uuid}/duplicate.

Требования: dev PostgreSQL на alembic head с seed (incl. test_consent v1).
"""

import uuid as _uuid
from unittest.mock import patch

import bcrypt
import pytest

from app.auth import storage as auth_storage
from app.db.session import SessionLocal
from app.db.models import Test as TestModel, TestResult as TestResultModel
from app.tests import storage as tests_storage
from tests.integration.conftest import create_test_user

PASSWORD = "SecurePass42!"


# ── helpers ───────────────────────────────────────────────────────────────────

def _admin_headers(client):
    admin = auth_storage.save_user({
        "name": "Integ Tests Admin",
        "email": f"integ_testsadmin_{_uuid.uuid4().hex[:10]}@example.com",
        "hashed_password": bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode(),
        "role": "admin",
    })
    r = client.post("/api/auth/login", json={"email": admin["email"], "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['session_token']}"}, int(admin["id"])


def _student_headers(client, email):
    create_test_user(email, PASSWORD)
    r = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['session_token']}"}


def _test_payload(title):
    return {
        "title": title, "description": "d", "scoring": "sum",
        "time_limit_min": None, "is_active": True,
        "category_ids": [], "tag_uuids": [],
        "questions": [
            {"question_text": "Q1", "question_order": 1, "question_type": "single_choice",
             "is_required": True, "config": {},
             "options": [{"option_text": "нет", "option_order": 0, "value_score": 0},
                         {"option_text": "да", "option_order": 1, "value_score": 3}]},
        ],
        "interpretations": [
            {"scale_name": None, "min_score": 0, "max_score": 3,
             "label": "Низкий", "recommendation": "ok"},
        ],
    }


def _hard_delete_test(test_uuid):
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
def admin(client):
    headers, _ = _admin_headers(client)
    return headers


@pytest.fixture
def created_test(client, admin):
    r = client.post(
        "/api/admin/tests",
        json=_test_payload(f"INTEG API {_uuid.uuid4().hex[:6]}"),
        headers=admin,
    )
    assert r.status_code == 201, r.text
    test = r.json()
    try:
        yield test
    finally:
        _hard_delete_test(test["uuid"])


def _submit_result(client, test_email, test):
    """Студент проходит тест → у теста появляются результаты."""
    headers = _student_headers(client, test_email)
    client.post("/api/tests/consent/accept", headers=headers)
    q = test["questions"][0]
    r = client.post(
        f"/api/tests/{test['uuid']}/submit",
        json={"answers": [{"question_id": q["id"], "option_id": q["options"][1]["id"]}]},
        headers=headers,
    )
    assert r.status_code == 201, r.text


# ── PATCH: вопросы заблокированы, метаданные — нет ────────────────────────────

def test_patch_questions_without_results_ok(client, admin, created_test):
    payload = _test_payload("x")
    payload["questions"][0]["question_text"] = "Q1 изменён"
    r = client.patch(
        f"/api/admin/tests/{created_test['uuid']}",
        json={"questions": payload["questions"]}, headers=admin,
    )
    assert r.status_code == 200, r.text
    assert r.json()["questions"][0]["question_text"] == "Q1 изменён"


def test_patch_questions_with_results_returns_409(client, admin, test_email, created_test):
    """Раньше здесь был HTTP 500 (IntegrityError наружу)."""
    _submit_result(client, test_email, created_test)

    payload = _test_payload("x")
    payload["questions"][0]["question_text"] = "Q1 изменён"
    r = client.patch(
        f"/api/admin/tests/{created_test['uuid']}",
        json={"questions": payload["questions"]}, headers=admin,
    )
    assert r.status_code == 409, r.text
    assert "результаты" in r.json()["detail"]

    # вопрос не изменился
    r = client.get(f"/api/admin/tests/{created_test['uuid']}", headers=admin)
    assert r.json()["questions"][0]["question_text"] == "Q1"


def test_patch_title_with_results_returns_200(client, admin, test_email, created_test):
    """Переименование теста с результатами обязано проходить."""
    _submit_result(client, test_email, created_test)
    r = client.patch(
        f"/api/admin/tests/{created_test['uuid']}",
        json={"title": "Переименован"}, headers=admin,
    )
    assert r.status_code == 200, r.text
    assert r.json()["title"] == "Переименован"


def test_patch_interpretations_with_results_returns_200(client, admin, test_email, created_test):
    """Пороги не связаны FK с результатами: расшифровка снапшотится при submit."""
    _submit_result(client, test_email, created_test)
    r = client.patch(
        f"/api/admin/tests/{created_test['uuid']}",
        json={"interpretations": [
            {"scale_name": None, "min_score": 0, "max_score": 3,
             "label": "Обновлённый", "recommendation": None},
        ]}, headers=admin,
    )
    assert r.status_code == 200, r.text
    assert r.json()["interpretations"][0]["label"] == "Обновлённый"


def test_integrity_error_also_maps_to_409(client, admin, created_test):
    """
    Defense-in-depth: если результат появится между проверкой has_results и
    заменой вопросов, FK (RESTRICT) поднимет IntegrityError — наружу всё равно
    409, а не 500. Гонку воспроизводим, отключив service-guard.
    """
    from sqlalchemy.exc import IntegrityError

    with patch("app.tests.service.storage.test_has_results", return_value=False), \
         patch("app.tests.storage.has_results", return_value=False), \
         patch("app.tests.storage._replace_questions",
               side_effect=IntegrityError("stmt", {}, Exception("FK"))):
        r = client.patch(
            f"/api/admin/tests/{created_test['uuid']}",
            json={"questions": _test_payload("x")["questions"]}, headers=admin,
        )
    assert r.status_code == 409, r.text


# ── валидация шкал на уровне API ──────────────────────────────────────────────

def test_partial_scales_rejected_by_api(client, admin):
    payload = _test_payload(f"INTEG scales {_uuid.uuid4().hex[:6]}")
    payload["questions"].append({
        "question_text": "Q2", "question_order": 2, "question_type": "single_choice",
        "is_required": True, "config": {"scale": "Тревога"},
        "options": [{"option_text": "нет", "option_order": 0, "value_score": 0},
                    {"option_text": "да", "option_order": 1, "value_score": 1}],
    })
    r = client.post("/api/admin/tests", json=payload, headers=admin)
    assert r.status_code == 422, r.text
    assert "Шкала указана не у всех" in r.json()["detail"]


# ── duplicate ─────────────────────────────────────────────────────────────────

def test_duplicate_returns_draft_copy(client, admin, test_email, created_test):
    _submit_result(client, test_email, created_test)   # оригинал заблокирован

    r = client.post(f"/api/admin/tests/{created_test['uuid']}/duplicate", headers=admin)
    assert r.status_code == 201, r.text
    copy = r.json()
    try:
        assert copy["uuid"] != created_test["uuid"]
        assert copy["is_active"] is False
        assert copy["version"] == 1
        assert copy["title"].endswith("(копия)")
        assert len(copy["questions"]) == 1
        assert len(copy["interpretations"]) == 1

        # копию можно править: у неё нет результатов
        edited = client.patch(
            f"/api/admin/tests/{copy['uuid']}",
            json={"questions": [{
                "question_text": "Новый Q", "question_order": 1,
                "question_type": "single_choice", "is_required": True, "config": {},
                "options": [{"option_text": "a", "option_order": 0, "value_score": 0},
                            {"option_text": "b", "option_order": 1, "value_score": 2}],
            }]}, headers=admin,
        )
        assert edited.status_code == 200, edited.text
        assert edited.json()["questions"][0]["question_text"] == "Новый Q"
    finally:
        _hard_delete_test(copy["uuid"])


def test_duplicate_unknown_uuid_returns_404(client, admin):
    r = client.post(f"/api/admin/tests/{_uuid.uuid4()}/duplicate", headers=admin)
    assert r.status_code == 404, r.text


def test_duplicate_requires_staff_role(client, test_email, created_test):
    headers = _student_headers(client, test_email)
    r = client.post(f"/api/admin/tests/{created_test['uuid']}/duplicate", headers=headers)
    assert r.status_code == 403, r.text


# ── POST /api/admin/tests/analyze ─────────────────────────────────────────────

def _analyze_body(scores_per_question, interpretations, scoring="sum"):
    return {
        "scoring": scoring,
        "questions": [
            {"question_text": f"Q{n}", "question_order": n,
             "question_type": "single_choice", "is_required": True, "config": {},
             "options": [{"option_text": str(s), "option_order": i, "value_score": s}
                         for i, s in enumerate(scores)]}
            for n, scores in enumerate(scores_per_question, start=1)
        ],
        "interpretations": interpretations,
    }


def test_analyze_reports_gap(client, admin):
    body = _analyze_body(
        [[0, 3], [0, 3]],
        [{"scale_name": None, "min_score": 0, "max_score": 2, "label": "Низкий",
          "recommendation": None},
         {"scale_name": None, "min_score": 5, "max_score": 6, "label": "Высокий",
          "recommendation": None}],
    )
    r = client.post("/api/admin/tests/analyze", json=body, headers=admin)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["score_bounds"] == [{"scale_name": None, "min_score": 0, "max_score": 6}]
    assert [i["kind"] for i in data["issues"]] == ["gap"]
    assert (data["issues"][0]["min_score"], data["issues"][0]["max_score"]) == (3, 4)


def test_analyze_full_coverage_is_clean(client, admin):
    body = _analyze_body(
        [[0, 3]],
        [{"scale_name": None, "min_score": 0, "max_score": 3, "label": "ok",
          "recommendation": None}],
    )
    r = client.post("/api/admin/tests/analyze", json=body, headers=admin)
    assert r.status_code == 200, r.text
    assert r.json()["issues"] == []


def test_analyze_does_not_persist_anything(client, admin):
    before = client.get("/api/admin/tests?page=1&size=1", headers=admin).json()["total"]
    client.post("/api/admin/tests/analyze", json=_analyze_body([[0, 1]], []), headers=admin)
    after = client.get("/api/admin/tests?page=1&size=1", headers=admin).json()["total"]
    assert before == after


def test_analyze_route_not_shadowed_by_uuid_route(client, admin):
    """`analyze` не должен попасть в `/{uuid}` — иначе был бы 404/422."""
    r = client.post("/api/admin/tests/analyze", json=_analyze_body([], []), headers=admin)
    assert r.status_code == 200, r.text
    assert r.json() == {"score_bounds": [], "issues": []}


def test_analyze_requires_staff_role(client, test_email):
    headers = _student_headers(client, test_email)
    r = client.post("/api/admin/tests/analyze", json=_analyze_body([[0, 1]], []), headers=headers)
    assert r.status_code == 403, r.text


# ── POST /api/admin/tests/preview-score ───────────────────────────────────────

def _preview_body(answers, scoring="sum"):
    return {
        "scoring": scoring,
        "questions": [
            {"question_text": "Q1", "question_order": 0, "question_type": "single_choice",
             "is_required": True, "config": {},
             "options": [{"option_text": "нет", "option_order": 0, "value_score": 0},
                         {"option_text": "да", "option_order": 1, "value_score": 3}]},
            {"question_text": "Q2", "question_order": 1, "question_type": "single_choice",
             "is_required": True, "config": {},
             "options": [{"option_text": "нет", "option_order": 0, "value_score": 0},
                         {"option_text": "да", "option_order": 1, "value_score": 3}]},
        ],
        "interpretations": [
            {"scale_name": None, "min_score": 0, "max_score": 2, "label": "Низкий",
             "recommendation": "ок"},
            {"scale_name": None, "min_score": 3, "max_score": 6, "label": "Высокий",
             "recommendation": "к специалисту"},
        ],
        "answers": answers,
    }


def test_preview_score_matches_real_scoring(client, admin):
    r = client.post(
        "/api/admin/tests/preview-score",
        json=_preview_body([{"question_order": 0, "option_order": 1},
                            {"question_order": 1, "option_order": 1}]),
        headers=admin,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total_score"] == 6
    assert body["max_possible"] == 6
    assert "Высокий" in body["recommendations"]


def test_preview_score_partial_answers_allowed(client, admin):
    """Автор пробует частичный набор — обязательность в предпросмотре не проверяется."""
    r = client.post(
        "/api/admin/tests/preview-score",
        json=_preview_body([{"question_order": 0, "option_order": 1}]),
        headers=admin,
    )
    assert r.status_code == 200, r.text
    assert r.json()["total_score"] == 3


def test_preview_score_multi_scale(client, admin):
    body = _preview_body([{"question_order": 0, "option_order": 1},
                          {"question_order": 1, "option_order": 1}])
    body["questions"][0]["config"] = {"scale": "Тревога"}
    body["questions"][1]["config"] = {"scale": "Депрессия"}
    body["interpretations"] = [
        {"scale_name": "Тревога", "min_score": 0, "max_score": 3, "label": "Т-высокий",
         "recommendation": None},
    ]
    r = client.post("/api/admin/tests/preview-score", json=body, headers=admin)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total_score"] is None            # многошкальный → итога нет
    scales = {s["scale_name"]: s for s in data["scales"]}
    assert scales["Тревога"]["score"] == 3
    assert scales["Тревога"]["label"] == "Т-высокий"
    assert scales["Депрессия"]["score"] == 3


def test_preview_score_persists_nothing(client, admin):
    before = client.get("/api/admin/tests?page=1&size=1", headers=admin).json()["total"]
    with SessionLocal() as db:
        results_before = db.query(TestResultModel).count()

    client.post(
        "/api/admin/tests/preview-score",
        json=_preview_body([{"question_order": 0, "option_order": 1}]),
        headers=admin,
    )

    after = client.get("/api/admin/tests?page=1&size=1", headers=admin).json()["total"]
    with SessionLocal() as db:
        results_after = db.query(TestResultModel).count()
    assert (before, results_before) == (after, results_after)


def test_preview_score_requires_staff_role(client, test_email):
    headers = _student_headers(client, test_email)
    r = client.post(
        "/api/admin/tests/preview-score",
        json=_preview_body([]), headers=headers,
    )
    assert r.status_code == 403, r.text


def test_preview_score_ignores_unknown_question_order(client, admin):
    r = client.post(
        "/api/admin/tests/preview-score",
        json=_preview_body([{"question_order": 99, "option_order": 1}]),
        headers=admin,
    )
    assert r.status_code == 200, r.text
    assert r.json()["total_score"] == 0
