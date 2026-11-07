"""
Подсказки интерфейса методик: has_results и campaigns_count в карточке и
списке /api/admin/tests (видны сразу, до попытки правки).
"""
from tests.integration.test_campaign_supervisor_api import (  # noqa: F401  (fixture env)
    _create, _submit, _token, env,
)

ADMIN = "/api/admin/tests"


def _item(client, headers, uuid):
    items = client.get(ADMIN, headers=headers, params={"size": 100}).json()["items"]
    return next(i for i in items if i["uuid"] == uuid)


def test_usage_flags(client, env):
    h, uuid = env["headers"], env["test_uuid"]
    before = client.get(f"{ADMIN}/{uuid}", headers=h).json()["campaigns_count"]
    c = _create(client, env)
    got = client.get(f"{ADMIN}/{uuid}", headers=h).json()
    assert got["campaigns_count"] == before + 1
    _submit(client, _token(c))
    got = client.get(f"{ADMIN}/{uuid}", headers=h).json()
    assert got["has_results"] is True
    item = _item(client, h, uuid)
    assert item["has_results"] is True and item["campaigns_count"] == before + 1


def test_new_test_has_no_usage(client, env):
    r = client.post(ADMIN, headers=env["headers"], json={
        "title": "integ usage", "status": "draft",
        "questions": [{"question_text": "q", "question_order": 1, "question_type": "single_choice",
                       "is_required": True, "config": {},
                       "options": [{"option_text": "да", "option_order": 0, "value_score": 1},
                                   {"option_text": "нет", "option_order": 1, "value_score": 0}]}]})
    assert r.status_code == 201, r.text
    body = r.json()
    try:
        assert body["has_results"] is False and body["campaigns_count"] == 0
    finally:
        client.delete(f"{ADMIN}/{body['uuid']}", headers=env["headers"])
