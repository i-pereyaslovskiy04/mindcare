"""
Integration: сроки и кодовое слово ссылки кампании (ТЗ редактора методик,
этап 2, §6; миграция c2a5f7d9e3b1).

  PATCH  /api/supervisor/campaigns/{uuid}/schedule
  PUT    /api/supervisor/campaigns/{uuid}/access-code
  DELETE /api/supervisor/campaigns/{uuid}/access-code
  GET    /api/public/campaigns/{token}         (замок / 409 до начала / 404 после)
  POST   /api/public/campaigns/{token}/unlock
  POST   /api/public/campaigns/{token}/submit  (access_code)

Покрывает: до начала — 409 campaign_not_started с датой, анкета не
отдаётся; после окончания — 404, как закрытая; кодовое слово — замок без
вопросов, unlock с верным словом (регистр и пробелы не важны), неверное —
403 без сохранения; слово сменили во время прохождения — 403; хеш — только
bcrypt, слово не попадает в ответы API и журнал; события аудита и no-op без
события; порядок дат — 422; лимит попыток — 429.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.core import rate_limit
from app.db.models import AuditLog, CampaignResponse, TestCampaign
from app.db.session import SessionLocal
from tests.integration.test_campaign_supervisor_api import (  # noqa: F401  (fixture env)
    BASE, _campaign_id, _create, _events, _token, env,
)

CODE = "Весна  2026"


def _public(token: str, suffix: str = "") -> str:
    return f"/api/public/campaigns/{token}{suffix}"


def _body(client, token: str, code=None, **over) -> dict:
    data = (client.post(_public(token, "/unlock"), json={"access_code": code}).json()
            if code else client.get(_public(token)).json())
    answers = [{"question_id": q["id"], "option_id": q["options"][1]["id"]}
               for q in data["questions"]]
    import uuid as _uuid
    body = {"submission_key": str(_uuid.uuid4()), "full_name": "Сидоров Сидор",
            "faculty_code": "accounting_finance", "specialty": "Экономика", "age": 19,
            "gender": "male", "consent_accepted": True,
            "consent_version": data["consent"]["version"], "answers": answers}
    body.update(over)
    return body


def _responses(campaign_id: int) -> int:
    with SessionLocal() as db:
        return db.query(CampaignResponse).filter(
            CampaignResponse.campaign_id == campaign_id).count()


def _iso(dt: datetime) -> str:
    return dt.isoformat()


# ─── сроки ────────────────────────────────────────────────────────────────────

def test_schedule_not_started_expired_and_events(client, env):
    c = _create(client, env)
    cid, token = _campaign_id(c["uuid"]), _token(c)
    now = datetime.now(timezone.utc)
    url = f"{BASE}/{c['uuid']}/schedule"

    r = client.patch(url, headers=env["headers"], json={
        "opens_at": _iso(now + timedelta(days=1)), "closes_at": _iso(now + timedelta(days=2))})
    assert r.status_code == 200, r.text
    assert r.json()["link_state"] == "scheduled"
    assert _events("test_campaign_schedule_changed", cid) == 1
    g = client.get(_public(token))
    assert g.status_code == 409
    assert g.json()["code"] == "campaign_not_started" and g.json()["opens_at"]
    assert "questions" not in g.json()
    assert g.headers.get("cache-control") == "no-store, private"

    # те же значения — без события
    same = r.json()
    client.patch(url, headers=env["headers"],
                 json={"opens_at": same["opens_at"], "closes_at": same["closes_at"]})
    assert _events("test_campaign_schedule_changed", cid) == 1

    # срок истёк — как закрытая кампания
    with SessionLocal() as db:
        db.query(TestCampaign).filter(TestCampaign.id == cid).update({
            "opens_at": now - timedelta(days=2), "closes_at": now - timedelta(minutes=1)})
        db.commit()
    assert client.get(_public(token)).status_code == 404
    assert client.get(f"{BASE}/{c['uuid']}", headers=env["headers"]).json()["link_state"] == "expired"

    # снять сроки — снова открыта
    r = client.patch(url, headers=env["headers"], json={"opens_at": None, "closes_at": None})
    assert r.json()["link_state"] == "open"
    assert client.get(_public(token)).status_code == 200
    assert _events("test_campaign_schedule_changed", cid) == 2


@pytest.mark.parametrize("body", [
    {"opens_at": "2026-12-01T10:00:00+03:00", "closes_at": "2026-12-01T10:00:00+03:00"},
    {"opens_at": "2026-12-02T10:00:00+03:00", "closes_at": "2026-12-01T10:00:00+03:00"},
    {"opens_at": "2026-12-01T10:00:00", "closes_at": None},
    {"opens_at": None},
])
def test_schedule_validation_422(client, env, body):
    c = _create(client, env)
    r = client.patch(f"{BASE}/{c['uuid']}/schedule", headers=env["headers"], json=body)
    assert r.status_code == 422


def test_submit_after_close_time_rejected(client, env):
    c = _create(client, env)
    cid, token = _campaign_id(c["uuid"]), _token(c)
    body = _body(client, token)
    with SessionLocal() as db:
        db.query(TestCampaign).filter(TestCampaign.id == cid).update(
            {"closes_at": datetime.now(timezone.utc) - timedelta(seconds=1)})
        db.commit()
    assert client.post(_public(token, "/submit"), json=body).status_code == 404
    assert _responses(cid) == 0


# ─── кодовое слово ────────────────────────────────────────────────────────────

def test_access_code_flow(client, env):
    c = _create(client, env)
    cid, token = _campaign_id(c["uuid"]), _token(c)
    r = client.put(f"{BASE}/{c['uuid']}/access-code", headers=env["headers"],
                   json={"access_code": CODE})
    assert r.status_code == 200, r.text
    assert r.json()["access_code_set"] is True
    assert CODE not in r.text and "весна" not in r.text.lower()
    with SessionLocal() as db:
        stored = db.query(TestCampaign.access_code_hash).filter(TestCampaign.id == cid).scalar()
        meta = [e.log_metadata for e in db.query(AuditLog).filter(
            AuditLog.event_type == "test_campaign_access_code_changed",
            AuditLog.entity_id == cid)]
    assert stored.startswith("$2") and "весна" not in stored
    assert meta == [{}]

    locked = client.get(_public(token)).json()
    assert locked["access_code_required"] is True
    assert locked["questions"] == [] and locked["consent"] is None

    wrong = client.post(_public(token, "/unlock"), json={"access_code": "осень 2026"})
    assert wrong.status_code == 403 and wrong.json()["code"] == "access_code_invalid"
    assert "осень" not in wrong.text

    opened = client.post(_public(token, "/unlock"), json={"access_code": " весна 2026 "})
    assert opened.status_code == 200 and len(opened.json()["questions"]) == 91

    body = _body(client, token, code=CODE)
    no_code = dict(body)
    no_code.pop("access_code", None)
    assert client.post(_public(token, "/submit"), json=no_code).status_code == 403
    bad = client.post(_public(token, "/submit"), json={**body, "access_code": "нет-нет"})
    assert bad.status_code == 403
    assert _responses(cid) == 0
    ok = client.post(_public(token, "/submit"), json={**body, "access_code": "ВЕСНА 2026"})
    assert ok.status_code == 201, ok.text
    assert _responses(cid) == 1


def test_code_changed_during_attempt_and_cleared(client, env):
    c = _create(client, env)
    cid, token = _campaign_id(c["uuid"]), _token(c)
    url = f"{BASE}/{c['uuid']}/access-code"
    client.put(url, headers=env["headers"], json={"access_code": CODE})
    body = _body(client, token, code=CODE)
    client.put(url, headers=env["headers"], json={"access_code": "новое слово"})
    r = client.post(_public(token, "/submit"), json={**body, "access_code": CODE})
    assert r.status_code == 403
    assert _events("test_campaign_access_code_changed", cid) == 2

    r = client.delete(url, headers=env["headers"])
    assert r.status_code == 200 and r.json()["access_code_set"] is False
    assert _events("test_campaign_access_code_changed", cid) == 3
    client.delete(url, headers=env["headers"])                 # снимать нечего
    assert _events("test_campaign_access_code_changed", cid) == 3
    assert client.get(_public(token)).json()["access_code_required"] is False


@pytest.mark.parametrize("code", ["abc", "x" * 65, "ab\tc\x01d"])
def test_access_code_rules_422(client, env, code):
    c = _create(client, env)
    r = client.put(f"{BASE}/{c['uuid']}/access-code", headers=env["headers"],
                   json={"access_code": code})
    assert r.status_code == 422
    assert code not in r.text


def test_unlock_rate_limit_429(client, env, monkeypatch):
    c = _create(client, env)
    client.put(f"{BASE}/{c['uuid']}/access-code", headers=env["headers"],
               json={"access_code": CODE})
    monkeypatch.setitem(rate_limit.RULES, "campaign_code:ip", (2, 600))
    rate_limit.reset()
    url = _public(_token(c), "/unlock")
    assert client.post(url, json={"access_code": "x1x1"}).status_code == 403
    assert client.post(url, json={"access_code": "x1x1"}).status_code == 403
    assert client.post(url, json={"access_code": CODE}).status_code == 429
    rate_limit.reset()


def test_other_staff_cannot_set_code_or_schedule(client, env):
    from tests.integration.test_campaign_supervisor_api import _login
    c = _create(client, env)
    headers, _ = _login(client, "psychologist")
    assert client.put(f"{BASE}/{c['uuid']}/access-code", headers=headers,
                      json={"access_code": CODE}).status_code == 403
    assert client.patch(f"{BASE}/{c['uuid']}/schedule", headers=headers,
                        json={"opens_at": None, "closes_at": None}).status_code == 403


def test_long_cyrillic_code(client, env):
    """64 кириллических символа (128 байт) — больше лимита bcrypt в 72 байта."""
    c = _create(client, env)
    word = "ж" * 64
    r = client.put(f"{BASE}/{c['uuid']}/access-code", headers=env["headers"],
                   json={"access_code": word})
    assert r.status_code == 200, r.text
    url = _public(_token(c), "/unlock")
    assert client.post(url, json={"access_code": word}).status_code == 200
    assert client.post(url, json={"access_code": "ж" * 63 + "з"}).status_code == 403
