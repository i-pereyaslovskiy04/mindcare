"""
ADR-037, этап 3: правила обработки в конструкторе тестов.

  - admin/supervisor и психолог создают и правят тест с scoring_rules и
    campaign_only; правила возвращаются в TestRead в каноничной форме;
  - analyze отдаёт rule_issues (несогласованность с вопросами), preview-score —
    уровни основных шкал, достоверность и типы;
  - публикация и отправка на проверку с несогласованными правилами — 422,
    статус не меняется; согласованные — проходят;
  - после первых результатов правила не меняются (409), а метаданные — да.

Требует disposable PostgreSQL (Stage 1 isolated runner).
"""
import uuid

import pytest

from app.db.models import Test as TestModel
from app.db.models import TestResult
from app.db.session import SessionLocal
from tests.integration.assignments_helpers import user
from tests.integration.staff_results_helpers import auth

ADMIN = "/api/admin/tests"
PSY = "/api/psychologist/tests"

RULES = {
    "version": 1,
    "instruction": "  Отвечайте честно.  ",
    "scales": [{"code": "L", "label": "  L   Ложь "},
               {"code": "A", "label": "Тревога", "main": True}],
    "levels": [{"code": "low", "label": "Низкий", "min": 0, "max": 1},
               {"code": "high", "label": "Высокий", "min": 2, "max": 2}],
    "validity": {"scales": [{"code": "L", "max_valid": 0}]},
    "types": {"threshold": 2, "items": [{"name": "Тревожный", "scales": ["A"]}]},
}


def _q(order, scale):
    return {"question_text": f"Вопрос {order}", "question_order": order,
            "question_type": "single_choice", "is_required": True,
            "config": {"scale": scale},
            "options": [{"option_text": "Да", "option_order": 0, "value_score": 1},
                        {"option_text": "Нет", "option_order": 1, "value_score": 0}]}


def _body(**over):
    body = {"title": f"integ_RULESAPI {uuid.uuid4().hex[:6]}", "status": "draft",
            "questions": [_q(1, "L"), _q(2, "A"), _q(3, "A")],
            "scoring_rules": RULES, "campaign_only": True}
    body.update(over)
    return body


@pytest.fixture
def created():
    uuids = []
    yield uuids
    with SessionLocal() as db:
        for u in uuids:
            t = db.query(TestModel).filter(TestModel.uuid == uuid.UUID(u)).first()
            if t is not None:
                db.query(TestResult).filter(TestResult.test_id == t.id).delete(
                    synchronize_session=False)
                db.delete(t)
        db.commit()


def _publish(client, token, test):
    return client.post(f"{ADMIN}/{test['uuid']}/publish", headers=auth(token), json={
        "expected_status": test["status"], "expected_updated_at": test["updated_at"]})


def test_admin_create_read_and_canonical_rules(client, created):
    _, token = user(client, ["admin"])
    r = client.post(ADMIN, headers=auth(token), json=_body())
    assert r.status_code == 201, r.text
    test = r.json()
    created.append(test["uuid"])
    assert test["campaign_only"] is True
    assert test["scoring_rules"]["scales"][0] == {"code": "L", "label": "L Ложь", "main": False}
    assert test["scoring_rules"]["instruction"] == "Отвечайте честно."
    got = client.get(f"{ADMIN}/{test['uuid']}", headers=auth(token)).json()
    assert got["scoring_rules"] == test["scoring_rules"]


def test_invalid_rules_422(client):
    _, token = user(client, ["admin"])
    bad = {**RULES, "types": {"threshold": 2, "items": [{"name": "Т", "scales": ["Z"]}]}}
    r = client.post(ADMIN, headers=auth(token), json=_body(scoring_rules=bad))
    assert r.status_code == 422


def test_analyze_and_preview(client):
    _, token = user(client, ["supervisor"])
    rules = {**RULES, "scales": [*RULES["scales"], {"code": "X", "label": "Лишняя"}],
             "levels": [{"code": "low", "label": "Низкий", "min": 0, "max": 0}]}
    r = client.post(f"{ADMIN}/analyze", headers=auth(token), json={
        "questions": [_q(1, "L"), _q(2, "A"), _q(3, "A")], "scoring_rules": rules})
    assert r.status_code == 200, r.text
    kinds = {(i["kind"], i["scale_name"]) for i in r.json()["rule_issues"]}
    assert kinds == {("scale_unused", "X"), ("level_gap", "A")}
    assert all(i["message"] for i in r.json()["rule_issues"])

    r = client.post(f"{ADMIN}/preview-score", headers=auth(token), json={
        "questions": [_q(1, "L"), _q(2, "A"), _q(3, "A")], "scoring_rules": RULES,
        "answers": [{"question_order": n, "option_order": 0} for n in (1, 2, 3)]})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["levels"] == {"A": "high"}
    assert data["rule_summary"] == {"is_valid": False, "types": ["Тревожный (недостоверно)"]}


def test_publish_blocked_by_inconsistent_rules(client, created):
    _, token = user(client, ["admin"])
    rules = {**RULES, "scales": [{"code": "L", "label": "L"}]}   # нет шкалы A
    test = client.post(ADMIN, headers=auth(token), json=_body(
        scoring_rules={k: v for k, v in rules.items() if k not in ("levels", "types")})).json()
    created.append(test["uuid"])
    r = _publish(client, token, test)
    assert r.status_code == 422
    assert "не согласованы" in r.json()["detail"]
    assert client.get(f"{ADMIN}/{test['uuid']}", headers=auth(token)).json()["status"] == "draft"

    fixed = client.patch(f"{ADMIN}/{test['uuid']}", headers=auth(token),
                         json={"scoring_rules": RULES}).json()
    assert _publish(client, token, fixed).status_code == 200


def test_psychologist_submit_blocked_then_ok(client, created):
    _, token = user(client, ["psychologist"])
    rules = {**RULES, "levels": [{"code": "low", "label": "Низкий", "min": 0, "max": 0}]}
    r = client.post(PSY, headers=auth(token), json=_body(scoring_rules=rules, status="published"))
    assert r.status_code == 201, r.text
    test = r.json()
    created.append(test["uuid"])
    assert test["status"] == "draft" and test["campaign_only"] is True
    assert client.post(f"{PSY}/{test['uuid']}/submit-for-review",
                       headers=auth(token)).status_code == 422
    client.patch(f"{PSY}/{test['uuid']}", headers=auth(token), json={"scoring_rules": RULES})
    r = client.post(f"{PSY}/{test['uuid']}/submit-for-review", headers=auth(token))
    assert r.status_code == 200 and r.json()["status"] == "in_review"


def test_rules_frozen_after_results(client, created):
    _, token = user(client, ["admin"])
    test = client.post(ADMIN, headers=auth(token), json=_body(
        status="published", campaign_only=False)).json()
    created.append(test["uuid"])
    sid, stoken = user(client, ["student"])
    client.post("/api/tests/consent/accept", headers=auth(stoken))
    answers = [{"question_id": q["id"], "option_id": q["options"][1]["id"]}
               for q in test["questions"]]
    r = client.post(f"/api/tests/{test['uuid']}/submit", json={"answers": answers},
                    headers=auth(stoken))
    assert r.status_code == 201, r.text

    r = client.patch(f"{ADMIN}/{test['uuid']}", headers=auth(token),
                     json={"scoring_rules": {**RULES, "instruction": "Другая"}})
    assert r.status_code == 409
    r = client.patch(f"{ADMIN}/{test['uuid']}", headers=auth(token),
                     json={"scoring_rules": None})
    assert r.status_code == 409
    # То же значение и метаданные — можно.
    r = client.patch(f"{ADMIN}/{test['uuid']}", headers=auth(token),
                     json={"scoring_rules": test["scoring_rules"], "title": "integ_RULESAPI ok"})
    assert r.status_code == 200, r.text
