"""
ADR-037: правила обработки у обычного теста каталога.

При отправке студентом достоверность и типы снимком пишутся в
test_results.rule_summary. Психолог и супервизор (Этап E) видят снимок и
подписи шкал; студент — нет (ни в ответе submit, ни в своей истории).
Снимок не меняется при последующей правке правил.

Требует disposable PostgreSQL (Stage 1 isolated runner).
"""
import uuid

import pytest

from app.db.models import Test as TestModel
from app.db.models import TestResult
from app.db.session import SessionLocal
from app.tests import storage as tests_storage
from tests.integration.assignments_helpers import engage, user
from tests.integration.staff_results_helpers import auth, cleanup_test

RULES = {
    "version": 1,
    "scales": [{"code": "L", "label": "L Ложь"},
               {"code": "A", "label": "А Тревога", "main": True}],
    "levels": [{"code": "low", "label": "Низкий", "min": 0, "max": 1},
               {"code": "high", "label": "Высокий", "min": 2, "max": 2}],
    "validity": {"scales": [{"code": "L", "max_valid": 0}]},
    "types": {"threshold": 2, "items": [{"name": "Тревожный", "scales": ["A"]}]},
}


def _yes_no(order, scale):
    return {"question_text": f"Вопрос {order}", "question_order": order,
            "question_type": "single_choice", "is_required": True,
            "config": {"scale": scale},
            "options": [{"option_text": "Да", "option_order": 0, "value_score": 1},
                        {"option_text": "Нет", "option_order": 1, "value_score": 0}]}


@pytest.fixture
def rules_test(client):
    admin_id, _ = user(client, ["admin"])
    test = tests_storage.create_test({
        "title": f"integ_RULES {uuid.uuid4().hex[:6]}", "description": "d",
        "scoring": "sum", "max_score": None, "time_limit_min": None, "is_active": True,
        "category_ids": [], "tag_uuids": [],
        "questions": [_yes_no(1, "L"), _yes_no(2, "A"), _yes_no(3, "A")],
        "interpretations": [],
    }, created_by=admin_id, actor_role="admin")
    with SessionLocal() as db:
        t = db.query(TestModel).filter(TestModel.uuid == uuid.UUID(test["uuid"])).one()
        t.scoring_rules = RULES
        t.status = "published"
        db.commit()
    yield test
    cleanup_test(test)


def _submit_all_yes(client, token, test):
    client.post("/api/tests/consent/accept", headers=auth(token))
    answers = [{"question_id": q["id"], "option_id": q["options"][0]["id"]}
               for q in test["questions"]]
    return client.post(f"/api/tests/{test['uuid']}/submit",
                       json={"answers": answers}, headers=auth(token))


def test_snapshot_staff_only(client, rules_test):
    sid, stoken = user(client, ["student"])
    pid, ptoken = user(client, ["psychologist", "student"])
    engage(pid, sid)

    r = _submit_all_yes(client, stoken, rules_test)
    assert r.status_code == 201, r.text
    body = r.json()
    assert "rule_summary" not in body and "scale_labels" not in body
    r_uuid = body["uuid"]

    with SessionLocal() as db:
        stored = db.query(TestResult.rule_summary).filter(
            TestResult.uuid == uuid.UUID(r_uuid)).scalar()
    assert stored == {"is_valid": False, "types": ["Тревожный (недостоверно)"]}

    own = client.get(f"/api/tests/results/{r_uuid}", headers=auth(stoken))
    assert own.status_code == 200
    assert "rule_summary" not in own.json()
    listed = client.get("/api/tests/results", headers=auth(stoken)).json()
    assert all("rule_summary" not in i for i in listed["items"])

    staff = client.get(f"/api/staff/test-results/{r_uuid}", headers=auth(ptoken))
    assert staff.status_code == 200, staff.text
    data = staff.json()
    assert data["rule_summary"] == stored
    assert data["scale_labels"] == {"L": "L Ложь", "A": "А Тревога"}

    # Снимок не пересчитывается при правке правил.
    with SessionLocal() as db:
        t = db.query(TestModel).filter(
            TestModel.uuid == uuid.UUID(rules_test["uuid"])).one()
        t.scoring_rules = {**RULES, "validity": None, "types": None}
        db.commit()
    again = client.get(f"/api/staff/test-results/{r_uuid}", headers=auth(ptoken)).json()
    assert again["rule_summary"] == stored


def test_without_rules_no_snapshot(client, rules_test):
    with SessionLocal() as db:
        t = db.query(TestModel).filter(
            TestModel.uuid == uuid.UUID(rules_test["uuid"])).one()
        t.scoring_rules = None
        db.commit()
    sid, stoken = user(client, ["student"])
    pid, ptoken = user(client, ["psychologist", "student"])
    engage(pid, sid)
    r_uuid = _submit_all_yes(client, stoken, rules_test).json()["uuid"]
    data = client.get(f"/api/staff/test-results/{r_uuid}", headers=auth(ptoken)).json()
    assert data["rule_summary"] is None and data["scale_labels"] == {}
