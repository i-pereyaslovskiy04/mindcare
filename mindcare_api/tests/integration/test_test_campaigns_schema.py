"""
Схема тестовых кампаний (ADR-036, миграция a3e7c1f9d5b2): ограничения БД.

Покрывает только схему, без API (API — этапы 3–4):
  - валидная строка кампании/ответа/шкал/ответов создаётся;
  - ФИО и токен ссылки — только `enc:v1:` (открытый текст отвергается CHECK);
  - формат хеша токена, статус и closed_at, пустое название;
  - возраст 14..100, пол male/female, непустая специальность;
  - идемпотентность: submission_key уникален в пределах кампании;
  - удаление кампании каскадно удаляет ответы, шкалы, ответы на вопросы;
    запись согласия остаётся (её удаляет service — ADR-036);
  - согласие, вопрос и вариант с ответами удалить нельзя (RESTRICT);
  - tests.campaign_only = false по умолчанию; scoring_rules NULL, lineage_uuid задан (ADR-037)
    по умолчанию.

Каждый тест убирает свои строки сам (фикстура `campaign_env`).
"""
import hashlib
import secrets
import uuid as _uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.encryption import encrypt_text
from app.db.models import (
    CampaignResponse, CampaignResponseAnswer, CampaignResponseScale, Consent,
    ConsentRecord, Option, Question, Test, TestCampaign,
)
from app.db.session import SessionLocal


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _token_pair() -> tuple[str, str]:
    raw = secrets.token_urlsafe(32)
    return hashlib.sha256(raw.encode()).hexdigest(), encrypt_text(raw)


def _make_test(db) -> Test:
    test = Test(title=f"integ_campaign_test_{_uuid.uuid4().hex[:8]}")
    db.add(test)
    db.flush()
    q = Question(test_id=test.id, question_text="Q1", question_order=1,
                 question_type="single_choice")
    db.add(q)
    db.flush()
    db.add_all([
        Option(question_id=q.id, option_text="Да", option_order=1, value_score=1),
        Option(question_id=q.id, option_text="Нет", option_order=2, value_score=0),
    ])
    db.flush()
    return test


def _make_campaign(db, test_id: int, **overrides) -> TestCampaign:
    token_hash, token_enc = _token_pair()
    values = {
        "test_id": test_id,
        "title": "integ_campaign",
        "link_token_hash": token_hash,
        "link_token_enc": token_enc,
    }
    values.update(overrides)
    campaign = TestCampaign(**values)
    db.add(campaign)
    db.flush()
    return campaign


def _make_consent_record(db) -> ConsentRecord:
    consent = db.query(Consent).filter(Consent.policy_type == "test_consent").first()
    assert consent is not None, "seed test_consent отсутствует"
    rec = ConsentRecord(user_id=None, consent_id=consent.id, accepted=True,
                        ip_address="127.0.0.1", user_agent="integ-campaign")
    db.add(rec)
    db.flush()
    return rec


def _make_response(db, campaign_id: int, **overrides) -> CampaignResponse:
    values = {
        "campaign_id": campaign_id,
        "submission_key": _uuid.uuid4(),
        "test_version": 1,
        "full_name_enc": encrypt_text("Иванов Иван Иванович"),
        "faculty_code": "accounting_finance",
        "specialty": "Бизнес-информатика",
        "age": 18,
        "gender": "female",
    }
    values.update(overrides)
    if "consent_record_id" not in values:
        values["consent_record_id"] = _make_consent_record(db).id
    resp = CampaignResponse(**values)
    db.add(resp)
    db.flush()
    return resp


@pytest.fixture()
def campaign_env(client):
    """Тест с вопросом; после теста — удаление всех созданных строк.

    `client` (session-scoped) запускает lifespan приложения — он создаёт seed
    согласий (test_consent), на которые ссылаются записи согласия.
    """
    created = {"test_ids": [], "consent_ids": []}
    with SessionLocal() as db:
        test = _make_test(db)
        db.commit()
        created["test_ids"].append(test.id)
    yield created
    with SessionLocal() as db:
        campaign_ids = [
            c.id for c in db.query(TestCampaign.id)
            .filter(TestCampaign.test_id.in_(created["test_ids"])).all()
        ]
        consent_ids = set(created["consent_ids"])
        if campaign_ids:
            consent_ids |= {
                r.consent_record_id for r in db.query(CampaignResponse)
                .filter(CampaignResponse.campaign_id.in_(campaign_ids)).all()
            }
            db.query(TestCampaign).filter(TestCampaign.id.in_(campaign_ids)) \
                .delete(synchronize_session=False)
        db.query(ConsentRecord).filter(
            (ConsentRecord.id.in_(consent_ids))
            | (ConsentRecord.user_agent == "integ-campaign")
        ).delete(synchronize_session=False)
        db.query(Test).filter(Test.id.in_(created["test_ids"])) \
            .delete(synchronize_session=False)
        db.commit()


def _expect_integrity_error(build) -> None:
    with SessionLocal() as db:
        with pytest.raises(IntegrityError):
            build(db)
            db.flush()
        db.rollback()


# ─── Валидные строки ──────────────────────────────────────────────────────────

def test_valid_campaign_response_scales_answers(campaign_env):
    test_id = campaign_env["test_ids"][0]
    with SessionLocal() as db:
        campaign = _make_campaign(db, test_id)
        resp = _make_response(db, campaign.id)
        q = db.query(Question).filter(Question.test_id == test_id).one()
        opt = db.query(Option).filter(Option.question_id == q.id).first()
        db.add(CampaignResponseScale(response_id=resp.id, scale_name="L",
                                     score=3, max_score=9))
        db.add(CampaignResponseAnswer(response_id=resp.id, question_id=q.id,
                                      option_id=opt.id))
        db.commit()
        db.refresh(campaign)
        db.refresh(resp)
        assert campaign.status == "open"
        assert campaign.closed_at is None
        assert campaign.uuid is not None and resp.uuid is not None
        assert resp.submitted_at is not None


def test_tests_flags_defaults(campaign_env):
    """ADR-037: CHECK на scoring_profile снят (код его не читает); правила —
    scoring_rules, у каждого теста есть lineage_uuid."""
    test_id = campaign_env["test_ids"][0]
    with SessionLocal() as db:
        test = db.get(Test, test_id)
        assert test.campaign_only is False
        assert test.scoring_profile is None
        assert test.scoring_rules is None
        assert test.superseded_at is None
        assert test.lineage_uuid is not None
        test.campaign_only = True
        db.commit()


# ─── Шифрование и формат ссылки ───────────────────────────────────────────────

def test_plaintext_full_name_rejected(campaign_env):
    test_id = campaign_env["test_ids"][0]
    _expect_integrity_error(lambda db: _make_response(
        db, _make_campaign(db, test_id).id, full_name_enc="Иванов Иван",
    ))


def test_plaintext_link_token_rejected(campaign_env):
    test_id = campaign_env["test_ids"][0]
    _expect_integrity_error(lambda db: _make_campaign(
        db, test_id, link_token_enc="raw-token",
    ))


def test_link_token_hash_format_and_uniqueness(campaign_env):
    test_id = campaign_env["test_ids"][0]
    _expect_integrity_error(lambda db: _make_campaign(
        db, test_id, link_token_hash="NOT-A-HASH",
    ))

    def duplicate(db):
        first = _make_campaign(db, test_id)
        _make_campaign(db, test_id, link_token_hash=first.link_token_hash)
    _expect_integrity_error(duplicate)


def test_status_closed_at_consistency_and_blank_title(campaign_env):
    test_id = campaign_env["test_ids"][0]
    _expect_integrity_error(lambda db: _make_campaign(db, test_id, status="closed"))
    _expect_integrity_error(lambda db: _make_campaign(
        db, test_id, closed_at=datetime.now(timezone.utc),
    ))
    _expect_integrity_error(lambda db: _make_campaign(db, test_id, status="paused"))
    _expect_integrity_error(lambda db: _make_campaign(db, test_id, title="   "))
    with SessionLocal() as db:
        _make_campaign(db, test_id, status="closed",
                       closed_at=datetime.now(timezone.utc))
        db.commit()


# ─── Анкета ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("field,value", [
    ("age", 13), ("age", 101), ("gender", "other"), ("specialty", "  "),
])
def test_respondent_field_checks(campaign_env, field, value):
    test_id = campaign_env["test_ids"][0]
    _expect_integrity_error(lambda db: _make_response(
        db, _make_campaign(db, test_id).id, **{field: value},
    ))


def test_age_bounds_accepted(campaign_env):
    test_id = campaign_env["test_ids"][0]
    with SessionLocal() as db:
        campaign = _make_campaign(db, test_id)
        _make_response(db, campaign.id, age=14, gender="male")
        _make_response(db, campaign.id, age=100)
        db.commit()


# ─── Идемпотентность ──────────────────────────────────────────────────────────

def test_submission_key_unique_per_campaign(campaign_env):
    test_id = campaign_env["test_ids"][0]
    key = _uuid.uuid4()

    def duplicate(db):
        campaign = _make_campaign(db, test_id)
        _make_response(db, campaign.id, submission_key=key)
        _make_response(db, campaign.id, submission_key=key)
    _expect_integrity_error(duplicate)

    with SessionLocal() as db:  # тот же ключ в разных кампаниях допустим
        _make_response(db, _make_campaign(db, test_id).id, submission_key=key)
        _make_response(db, _make_campaign(db, test_id).id, submission_key=key)
        db.commit()


def test_consent_record_used_once(campaign_env):
    test_id = campaign_env["test_ids"][0]

    def reuse(db):
        campaign = _make_campaign(db, test_id)
        first = _make_response(db, campaign.id)
        _make_response(db, campaign.id, consent_record_id=first.consent_record_id)
    _expect_integrity_error(reuse)


# ─── Удаление ─────────────────────────────────────────────────────────────────

def test_campaign_delete_cascades_but_keeps_consent(campaign_env):
    test_id = campaign_env["test_ids"][0]
    with SessionLocal() as db:
        campaign = _make_campaign(db, test_id)
        resp = _make_response(db, campaign.id)
        q = db.query(Question).filter(Question.test_id == test_id).one()
        opt = db.query(Option).filter(Option.question_id == q.id).first()
        db.add(CampaignResponseScale(response_id=resp.id, scale_name="L",
                                     score=1, max_score=9))
        db.add(CampaignResponseAnswer(response_id=resp.id, question_id=q.id,
                                      option_id=opt.id))
        db.commit()
        campaign_id, resp_id, consent_id = campaign.id, resp.id, resp.consent_record_id
        campaign_env["consent_ids"].append(consent_id)

    with SessionLocal() as db:
        db.query(TestCampaign).filter(TestCampaign.id == campaign_id) \
            .delete(synchronize_session=False)
        db.commit()
        assert db.query(CampaignResponse).filter_by(id=resp_id).count() == 0
        assert db.query(CampaignResponseScale).filter_by(response_id=resp_id).count() == 0
        assert db.query(CampaignResponseAnswer).filter_by(response_id=resp_id).count() == 0
        # Согласие БД не трогает — удаляет service той же транзакцией (ADR-036).
        assert db.query(ConsentRecord).filter_by(id=consent_id).count() == 1


def test_consent_record_restricted_while_response_exists(campaign_env):
    test_id = campaign_env["test_ids"][0]
    with SessionLocal() as db:
        resp = _make_response(db, _make_campaign(db, test_id).id)
        db.commit()
        consent_id = resp.consent_record_id

    _expect_integrity_error(
        lambda db: db.query(ConsentRecord).filter_by(id=consent_id)
        .delete(synchronize_session=False)
    )


def test_question_and_option_restricted_by_answers(campaign_env):
    test_id = campaign_env["test_ids"][0]
    with SessionLocal() as db:
        resp = _make_response(db, _make_campaign(db, test_id).id)
        q = db.query(Question).filter(Question.test_id == test_id).one()
        opt = db.query(Option).filter(Option.question_id == q.id).first()
        db.add(CampaignResponseAnswer(response_id=resp.id, question_id=q.id,
                                      option_id=opt.id))
        db.commit()
        q_id, opt_id = q.id, opt.id

    _expect_integrity_error(
        lambda db: db.query(Option).filter_by(id=opt_id)
        .delete(synchronize_session=False)
    )
    _expect_integrity_error(
        lambda db: db.query(Question).filter_by(id=q_id)
        .delete(synchronize_session=False)
    )


def test_test_restricted_by_campaign(campaign_env):
    test_id = campaign_env["test_ids"][0]
    with SessionLocal() as db:
        _make_campaign(db, test_id)
        db.commit()
    _expect_integrity_error(
        lambda db: db.query(Test).filter_by(id=test_id)
        .delete(synchronize_session=False)
    )
