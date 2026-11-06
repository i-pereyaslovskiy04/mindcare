"""
ADR-037, этап 4: версии методики и исправление текстов.

  - новая версия: тот же lineage, version+1, черновик, копия вопросов/правил;
    вторая неопубликованная версия — 409; событие test_version_created;
  - публикация новой версии ставит прежней superseded_at: её нет в каталоге
    студента и в выборе методики кампании; прежние результаты и кампании
    остаются на своей версии;
  - исправление текстов при наличии результатов: только тексты, состав — 422,
    устаревший updated_at — 409, ничего не изменилось — без события;
  - психолог: новая версия и тексты только своей методики; опубликованная при
    исправлении текстов снимается с публикации.

Требует disposable PostgreSQL (Stage 1 isolated runner).
"""
import uuid

import pytest

from app.db.models import AuditLog, TestCampaign, TestResult
from app.db.models import Test as TestModel
from app.db.session import SessionLocal
from tests.integration.assignments_helpers import user
from tests.integration.staff_results_helpers import auth

ADMIN = "/api/admin/tests"
PSY = "/api/psychologist/tests"
RULES = {"version": 1, "scales": [{"code": "A", "label": "Тревога", "main": True}],
         "levels": [{"code": "low", "label": "Низкий", "min": 0, "max": 2}]}


def _q(order):
    return {"question_text": f"Вопрос {order}", "question_order": order,
            "question_type": "single_choice", "is_required": True,
            "config": {"scale": "A"},
            "options": [{"option_text": "Да", "option_order": 0, "value_score": 1},
                        {"option_text": "Нет", "option_order": 1, "value_score": 0}]}


@pytest.fixture
def cleanup():
    lineages = []
    yield lineages
    with SessionLocal() as db:
        for lin in lineages:
            ids = [t.id for t in db.query(TestModel.id).filter(
                TestModel.lineage_uuid == uuid.UUID(lin))]
            db.query(TestCampaign).filter(TestCampaign.test_id.in_(ids)).delete(
                synchronize_session=False)
            db.query(TestResult).filter(TestResult.test_id.in_(ids)).delete(
                synchronize_session=False)
            for t in db.query(TestModel).filter(TestModel.id.in_(ids)).all():
                db.delete(t)
        db.commit()


def _create(client, token, base=ADMIN, **over):
    body = {"title": f"integ_VER {uuid.uuid4().hex[:6]}", "status": "published",
            "questions": [_q(1), _q(2)], "scoring_rules": RULES}
    body.update(over)
    r = client.post(base, headers=auth(token), json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _publish(client, token, test):
    r = client.post(f"{ADMIN}/{test['uuid']}/publish", headers=auth(token), json={
        "expected_status": test["status"], "expected_updated_at": test["updated_at"]})
    assert r.status_code == 200, r.text
    return r.json()


def _submit(client, test):
    _, stoken = user(client, ["student"])
    client.post("/api/tests/consent/accept", headers=auth(stoken))
    answers = [{"question_id": q["id"], "option_id": q["options"][0]["id"]}
               for q in test["questions"]]
    r = client.post(f"/api/tests/{test['uuid']}/submit", json={"answers": answers},
                    headers=auth(stoken))
    return r


def _events(name, test_uuid):
    with SessionLocal() as db:
        tid = db.query(TestModel.id).filter(TestModel.uuid == uuid.UUID(test_uuid)).scalar()
        return db.query(AuditLog).filter(AuditLog.event_type == name,
                                         AuditLog.entity_id == tid).count()


def test_new_version_supersedes_on_publish(client, cleanup):
    _, token = user(client, ["supervisor"])
    v1 = _create(client, token)
    cleanup.append(v1["lineage_uuid"])
    assert _submit(client, v1).status_code == 201

    r = client.post(f"{ADMIN}/{v1['uuid']}/new-version", headers=auth(token))
    assert r.status_code == 201, r.text
    v2 = r.json()
    assert v2["lineage_uuid"] == v1["lineage_uuid"] and v2["version"] == 2
    assert v2["status"] == "draft" and v2["title"] == v1["title"]
    assert v2["scoring_rules"] == v1["scoring_rules"]
    assert [q["question_text"] for q in v2["questions"]] == ["Вопрос 1", "Вопрос 2"]
    assert _events("test_version_created", v2["uuid"]) == 1
    # Вторая неопубликованная версия — нет.
    assert client.post(f"{ADMIN}/{v1['uuid']}/new-version",
                       headers=auth(token)).status_code == 409

    # До публикации v2 каталог и выбор кампании — v1.
    _, stoken = user(client, ["student"])
    catalog = {t["uuid"] for t in client.get("/api/tests?size=100", headers=auth(stoken)).json()["items"]}
    assert v1["uuid"] in catalog and v2["uuid"] not in catalog

    # В новой версии можно менять правила и вопросы (у неё нет результатов).
    r = client.patch(f"{ADMIN}/{v2['uuid']}", headers=auth(token),
                     json={"scoring_rules": {**RULES, "instruction": "v2"}})
    assert r.status_code == 200, r.text
    v2 = _publish(client, token, r.json())

    old = client.get(f"{ADMIN}/{v1['uuid']}", headers=auth(token)).json()
    assert old["superseded_at"] is not None and old["status"] == "published"
    catalog = {t["uuid"] for t in client.get("/api/tests?size=100", headers=auth(stoken)).json()["items"]}
    assert v2["uuid"] in catalog and v1["uuid"] not in catalog
    choice = {t["uuid"] for t in client.get("/api/supervisor/campaigns/tests",
                                            headers=auth(token)).json()}
    assert v2["uuid"] in choice and v1["uuid"] not in choice
    # Прохождение заменённой версии — 404, новой — да.
    assert _submit(client, v1).status_code == 404
    assert _submit(client, v2).status_code == 201
    listed = client.get(f"{ADMIN}?size=100", headers=auth(token)).json()["items"]
    flags = {i["uuid"]: i["superseded_at"] for i in listed}
    assert flags.get(v1["uuid"]) is not None and flags.get(v2["uuid"]) is None


def test_correct_texts_with_results(client, cleanup):
    _, token = user(client, ["admin"])
    test = _create(client, token)
    cleanup.append(test["lineage_uuid"])
    assert _submit(client, test).status_code == 201
    url = f"{ADMIN}/{test['uuid']}/texts"

    def body(**over):
        data = {"expected_updated_at": test["updated_at"],
                "questions": [{"question_order": q["question_order"],
                               "question_text": q["question_text"],
                               "options": [{"option_order": o["option_order"],
                                            "option_text": o["option_text"]}
                                           for o in q["options"]]}
                              for q in test["questions"]]}
        data.update(over)
        return data

    # Ничего не изменилось — 200 без события.
    assert client.patch(url, headers=auth(token), json=body()).status_code == 200
    assert _events("test_texts_corrected", test["uuid"]) == 0

    fixed = body()
    fixed["questions"][0]["question_text"] = "  Вопрос 1 (исправлено) "
    fixed["questions"][1]["options"][1]["option_text"] = "Нет, не согласен"
    r = client.patch(url, headers=auth(token), json={**fixed, "instruction": "Новая инструкция"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["questions"][0]["question_text"] == "Вопрос 1 (исправлено)"
    assert data["questions"][1]["options"][1]["option_text"] == "Нет, не согласен"
    assert data["questions"][1]["options"][1]["value_score"] == 0
    assert data["scoring_rules"]["instruction"] == "Новая инструкция"
    assert data["status"] == "published"
    assert _events("test_texts_corrected", test["uuid"]) == 1

    # Старый updated_at — 409; другой состав — 422.
    assert client.patch(url, headers=auth(token), json=fixed).status_code == 409
    fresh = body(expected_updated_at=data["updated_at"])
    fresh["questions"] = fresh["questions"][:1]
    assert client.patch(url, headers=auth(token), json=fresh).status_code == 422
    extra = body(expected_updated_at=data["updated_at"])
    extra["questions"][0]["options"].append({"option_order": 9, "option_text": "Лишний"})
    assert client.patch(url, headers=auth(token), json=extra).status_code == 422
    # Баллы через этот путь не передать.
    bad = body(expected_updated_at=data["updated_at"])
    bad["questions"][0]["options"][0]["value_score"] = 5
    assert client.patch(url, headers=auth(token), json=bad).status_code == 422


def test_psychologist_own_only_and_unpublish(client, cleanup):
    _, ptoken = user(client, ["psychologist"])
    _, other = user(client, ["psychologist"])
    _, stoken = user(client, ["supervisor"])
    draft = _create(client, ptoken, base=PSY)
    cleanup.append(draft["lineage_uuid"])
    r = client.post(f"{PSY}/{draft['uuid']}/submit-for-review", headers=auth(ptoken))
    assert r.status_code == 200, r.text
    published = _publish(client, stoken, r.json())

    assert client.post(f"{PSY}/{published['uuid']}/new-version",
                       headers=auth(other)).status_code == 404
    texts = {"expected_updated_at": published["updated_at"],
             "questions": [{"question_order": q["question_order"],
                            "question_text": q["question_text"] + "!",
                            "options": [{"option_order": o["option_order"],
                                         "option_text": o["option_text"]}
                                        for o in q["options"]]}
                           for q in published["questions"]]}
    assert client.patch(f"{PSY}/{published['uuid']}/texts", headers=auth(other),
                        json=texts).status_code == 404
    r = client.patch(f"{PSY}/{published['uuid']}/texts", headers=auth(ptoken), json=texts)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "draft"          # повторная модерация
    assert _events("test_unpublished_for_edit", published["uuid"]) == 1

    r = client.post(f"{PSY}/{published['uuid']}/new-version", headers=auth(ptoken))
    assert r.status_code == 409                   # своя версия ещё не опубликована
