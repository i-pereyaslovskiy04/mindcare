"""
Integration: публичный API кампании (ADR-036, этап 3).

  GET  /api/public/campaigns/{token}
  POST /api/public/campaigns/{token}/submit

Покрывает: 404 (кривой/неизвестный токен, закрытая кампания, удалённый тест);
DTO без ключа методики; успешная отправка (ФИО `enc:v1:`, согласие без
user_id с IP/UA, баллы шкал, анонимное событие аудита, test_results не
тронут); повтор submission_key → 200 без дублей; 422 без эха ФИО и без строк;
устаревшая версия согласия → 409; 429; сбой аудита → 503 без строк;
Cache-Control: no-store на всех исходах.
"""
import uuid as _uuid
from datetime import datetime, timezone

import pytest

from app.audit import AuditError
from app.campaigns import storage as campaign_storage
from app.campaigns import tokens
from app.core import rate_limit
from app.core.encryption import decrypt_text, encrypt_text
from app.db.models import (
    AuditLog, CampaignResponse, CampaignResponseAnswer, CampaignResponseScale,
    ConsentRecord, Test as TestModel, TestCampaign, TestResult,
)
from app.db.session import SessionLocal
from app.tests.profiles.ito_seed import ensure_ito_test

FULL_NAME = "Иванова   Мария Петровна"


# ─── fixtures / helpers ───────────────────────────────────────────────────────

@pytest.fixture()
def campaign(client):
    """Тест ИТО + открытая кампания с известным токеном; полная уборка."""
    with SessionLocal() as db:
        test, created = ensure_ito_test(db)
        token = tokens.generate_token()
        camp = TestCampaign(
            test_id=test.id, title="integ Кампания 1 курс",
            link_token_hash=tokens.hash_token(token),
            link_token_enc=encrypt_text(token),
        )
        db.add(camp)
        db.commit()
        info = {"token": token, "campaign_id": camp.id, "test_id": test.id}
    yield info
    with SessionLocal() as db:
        consent_ids = [r.consent_record_id for r in db.query(CampaignResponse)
                       .filter(CampaignResponse.campaign_id == info["campaign_id"])]
        response_ids = [r.id for r in db.query(CampaignResponse.id)
                        .filter(CampaignResponse.campaign_id == info["campaign_id"])]
        if response_ids:
            db.query(AuditLog).filter(
                AuditLog.event_type == "campaign_response_submitted",
                AuditLog.entity_id.in_(response_ids),
            ).delete(synchronize_session=False)
        db.query(TestCampaign).filter(TestCampaign.id == info["campaign_id"]) \
            .delete(synchronize_session=False)
        if consent_ids:
            db.query(ConsentRecord).filter(ConsentRecord.id.in_(consent_ids)) \
                .delete(synchronize_session=False)
        if created:
            db.query(TestModel).filter(TestModel.id == info["test_id"]) \
                .delete(synchronize_session=False)
        db.commit()


def _url(token: str, submit: bool = False) -> str:
    return f"/api/public/campaigns/{token}" + ("/submit" if submit else "")


def _payload(client, token: str, yes: set[int] = frozenset(), **overrides) -> dict:
    data = client.get(_url(token)).json()
    answers = []
    for q in data["questions"]:
        opts = {o["text"]: o["id"] for o in q["options"]}
        answers.append({"question_id": q["id"],
                        "option_id": opts["Да" if q["number"] in yes else "Нет"]})
    body = {
        "submission_key": str(_uuid.uuid4()),
        "full_name": FULL_NAME,
        "faculty_code": "accounting_finance",
        "specialty": "Бизнес-информатика",
        "age": 18,
        "gender": "female",
        "consent_accepted": True,
        "consent_version": data["consent"]["version"],
        "answers": answers,
    }
    body.update(overrides)
    return body


def _counts(campaign_id: int) -> tuple[int, int]:
    with SessionLocal() as db:
        responses = db.query(CampaignResponse) \
            .filter(CampaignResponse.campaign_id == campaign_id).count()
        consents = db.query(ConsentRecord).filter(
            ConsentRecord.user_id.is_(None),
            ConsentRecord.id.in_(
                db.query(CampaignResponse.consent_record_id)
                .filter(CampaignResponse.campaign_id == campaign_id)
            ),
        ).count()
        return responses, consents


def _orphan_campaign_consents() -> int:
    """Записи согласия кампании без ответа — признак частичной записи."""
    with SessionLocal() as db:
        used = db.query(CampaignResponse.consent_record_id)
        return db.query(ConsentRecord).filter(
            ConsentRecord.user_id.is_(None),
            ConsentRecord.id.notin_(used),
            ConsentRecord.user_agent == "integ-campaign-ua",
        ).count()


def _no_store(r) -> None:
    assert r.headers.get("cache-control") == "no-store, private", r.headers


# ─── GET ──────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("token", ["short", "x" * 43, "Z" * 43])
def test_unknown_or_malformed_token_404(client, token):
    r = client.get(_url(token))
    assert r.status_code == 404
    _no_store(r)


def test_get_returns_form_without_key(client, campaign):
    r = client.get(_url(campaign["token"]))
    assert r.status_code == 200, r.text
    _no_store(r)
    data = r.json()
    assert data["title"] == "integ Кампания 1 курс"
    assert len(data["questions"]) == 91
    assert [q["number"] for q in data["questions"]] == list(range(1, 92))
    assert data["consent"]["version"] >= 1 and data["consent"]["content"]
    assert {f["code"] for f in data["faculties"]} >= {"law", "accounting_finance"}
    raw = r.text
    for forbidden in ("value_score", "config", "scale", "Спонтанность"):
        assert forbidden not in raw, forbidden
    q = data["questions"][0]
    assert set(q) == {"id", "number", "text", "options"}
    assert set(q["options"][0]) == {"id", "text"}


def test_closed_campaign_404(client, campaign):
    with SessionLocal() as db:
        camp = db.get(TestCampaign, campaign["campaign_id"])
        camp.status, camp.closed_at = "closed", datetime.now(timezone.utc)
        db.commit()
    assert client.get(_url(campaign["token"])).status_code == 404


def test_deleted_test_404(client, campaign):
    with SessionLocal() as db:
        db.get(TestModel, campaign["test_id"]).deleted_at = datetime.now(timezone.utc)
        db.commit()
    try:
        assert client.get(_url(campaign["token"])).status_code == 404
    finally:
        with SessionLocal() as db:
            db.get(TestModel, campaign["test_id"]).deleted_at = None
            db.commit()


# ─── POST: успех ──────────────────────────────────────────────────────────────

def test_submit_success_persists_everything(client, campaign):
    results_before = _test_results_count()
    body = _payload(client, campaign["token"], yes={49, 40})
    r = client.post(_url(campaign["token"], True), json=body,
                    headers={"User-Agent": "integ-campaign-ua"})
    assert r.status_code == 201, r.text
    assert r.json() == {"status": "accepted"}
    _no_store(r)

    with SessionLocal() as db:
        resp = db.query(CampaignResponse) \
            .filter(CampaignResponse.campaign_id == campaign["campaign_id"]).one()
        assert resp.full_name_enc.startswith("enc:v1:")
        assert decrypt_text(resp.full_name_enc) == "Иванова Мария Петровна"
        assert (resp.faculty_code, resp.specialty, resp.age, resp.gender) == (
            "accounting_finance", "Бизнес-информатика", 18, "female")
        consent = db.get(ConsentRecord, resp.consent_record_id)
        assert consent.user_id is None and consent.accepted is True
        assert consent.ip_address is not None
        assert consent.user_agent == "integ-campaign-ua"

        scores = {s.scale_name: s.score for s in db.query(CampaignResponseScale)
                  .filter(CampaignResponseScale.response_id == resp.id)}
        # Все «Нет», кроме 49 (II) и 40 (VIII): обратные пункты + по 1 в II и VIII.
        assert scores == {"L": 0, "F": 0, "I": 3, "II": 4, "III": 2, "IV": 3,
                          "V": 3, "VI": 4, "VII": 2, "VIII": 5}
        assert db.query(CampaignResponseAnswer) \
            .filter(CampaignResponseAnswer.response_id == resp.id).count() == 91

        event = db.query(AuditLog).filter(
            AuditLog.event_type == "campaign_response_submitted",
            AuditLog.entity_id == resp.id,
        ).one()
        assert event.user_id is None and event.user_role is None
        assert event.entity_type == "campaign_response"
        assert not event.log_metadata
    assert _test_results_count() == results_before


def _test_results_count() -> int:
    with SessionLocal() as db:
        return db.query(TestResult).count()


def test_replay_same_key_returns_200_without_duplicates(client, campaign):
    body = _payload(client, campaign["token"])
    assert client.post(_url(campaign["token"], True), json=body).status_code == 201
    r = client.post(_url(campaign["token"], True), json=body)
    assert r.status_code == 200, r.text
    assert r.json() == {"status": "accepted"}
    assert _counts(campaign["campaign_id"]) == (1, 1)


def test_replay_accepted_even_after_close(client, campaign):
    body = _payload(client, campaign["token"])
    assert client.post(_url(campaign["token"], True), json=body).status_code == 201
    with SessionLocal() as db:
        camp = db.get(TestCampaign, campaign["campaign_id"])
        camp.status, camp.closed_at = "closed", datetime.now(timezone.utc)
        db.commit()
    assert client.post(_url(campaign["token"], True), json=body).status_code == 200
    new = dict(body, submission_key=str(_uuid.uuid4()))
    assert client.post(_url(campaign["token"], True), json=new).status_code == 404


# ─── POST: отказы ─────────────────────────────────────────────────────────────

def test_missing_answer_422_no_rows(client, campaign):
    body = _payload(client, campaign["token"])
    body["answers"] = body["answers"][:-1]
    r = client.post(_url(campaign["token"], True), json=body)
    assert r.status_code == 422 and r.json()["code"] == "missing_answers"
    _no_store(r)
    assert _counts(campaign["campaign_id"]) == (0, 0)


def test_foreign_option_and_duplicate_422(client, campaign):
    body = _payload(client, campaign["token"])
    a0, a1 = body["answers"][0], body["answers"][1]
    body["answers"][0] = {"question_id": a0["question_id"], "option_id": a1["option_id"]}
    r = client.post(_url(campaign["token"], True), json=body)
    assert r.status_code == 422 and r.json()["code"] == "foreign_option"

    body = _payload(client, campaign["token"])
    body["answers"][1] = dict(body["answers"][0])
    r = client.post(_url(campaign["token"], True), json=body)
    assert r.status_code == 422 and r.json()["code"] == "duplicate_question"
    assert _counts(campaign["campaign_id"]) == (0, 0)


@pytest.mark.parametrize("override", [
    {"consent_accepted": False},
    {"age": 13}, {"age": "18"}, {"gender": "other"},
    {"faculty_code": "nope"}, {"specialty": " "}, {"full_name": "A\x00B"},
    {"extra_field": 1},
])
def test_invalid_fields_422_without_echo(client, campaign, override):
    body = _payload(client, campaign["token"], **override)
    r = client.post(_url(campaign["token"], True), json=body)
    assert r.status_code == 422, r.text
    _no_store(r)
    assert "Иванова" not in r.text
    assert _counts(campaign["campaign_id"]) == (0, 0)


def test_outdated_consent_version_409(client, campaign):
    body = _payload(client, campaign["token"])
    body["consent_version"] += 1
    r = client.post(_url(campaign["token"], True), json=body)
    assert r.status_code == 409 and r.json()["code"] == "consent_outdated"
    _no_store(r)
    assert _counts(campaign["campaign_id"]) == (0, 0)


def test_rate_limit_429(client, campaign, monkeypatch):
    monkeypatch.setitem(rate_limit.RULES, "campaign_read:ip", (2, 600))
    assert client.get(_url(campaign["token"])).status_code == 200
    assert client.get(_url(campaign["token"])).status_code == 200
    r = client.get(_url(campaign["token"]))
    assert r.status_code == 429
    _no_store(r)


def test_audit_failure_503_and_nothing_saved(client, campaign, monkeypatch):
    body = _payload(client, campaign["token"])

    def boom(**_kwargs):
        raise AuditError("injected")

    monkeypatch.setattr(campaign_storage, "record_event", boom)
    r = client.post(_url(campaign["token"], True), json=body,
                    headers={"User-Agent": "integ-campaign-ua"})
    assert r.status_code == 503
    _no_store(r)
    assert _counts(campaign["campaign_id"]) == (0, 0)
    assert _orphan_campaign_consents() == 0
