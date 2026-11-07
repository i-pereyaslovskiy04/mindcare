"""
Хранилище публичной части кампаний (ADR-036).

Отправка — одна транзакция: строка кампании под FOR SHARE (сериализация с
закрытием/удалением кампании супервизором под FOR UPDATE, этап 4) →
повтор по submission_key → проверка открытости и теста → согласие
(consent_records, user_id NULL, IP/UA) → ответ → шкалы → ответы →
campaign_response_submitted (ATOMIC/RAISE) → commit. Сбой аудита — rollback,
в БД ничего не остаётся.

SECURITY: ФИО — только `enc:v1:`; токен и его хеш не логируются и в аудит не
попадают; IP/UA — только в consent_records и контексте аудита.
"""
from typing import Optional

from sqlalchemy.exc import IntegrityError

from app.audit import Actor, Outcome, Target, record_event
from app.campaigns import access
from app.audit.request_context import build_request_context
from app.campaigns.answers import compute, validate_answers
from app.core.encryption import encrypt_text
from app.db.models import (
    CampaignResponse, CampaignResponseAnswer, CampaignResponseScale, Consent,
    ConsentRecord, Option, Question, Test, TestCampaign,
)
from app.db.session import SessionLocal

CONSENT_POLICY = "campaign_consent"
SUBMISSION_KEY_CONSTRAINT = "uq_campaign_responses_submission_key"


class CampaignNotFound(Exception):
    """Нет кампании по токену, она закрыта или её тест удалён (→ 404)."""


class ConsentOutdated(Exception):
    """Клиент принял не последнюю версию согласия (→ 409)."""


class CampaignNotStarted(Exception):
    """Срок начала кампании ещё не наступил (→ 409 с датой начала)."""

    def __init__(self, opens_at):
        super().__init__("campaign_not_started")
        self.opens_at = opens_at


class AccessCodeWrong(Exception):
    """Кодовое слово не указано, неверно или сменилось во время прохождения (→ 403)."""


# ── чтение ────────────────────────────────────────────────────────────────────

def _latest_consent(db) -> Consent:
    consent = (
        db.query(Consent).filter(Consent.policy_type == CONSENT_POLICY)
        .order_by(Consent.version.desc()).first()
    )
    if consent is None:   # seed согласий выполняется при старте приложения
        raise RuntimeError("campaign_consent is not seeded")
    return consent


def _test_structure(db, test: Test) -> dict:
    """Тест в формате общего движка подсчёта + тексты для отдачи респонденту."""
    questions = []
    for q in (db.query(Question).filter(Question.test_id == test.id)
              .order_by(Question.question_order, Question.id).all()):
        options = (db.query(Option).filter(Option.question_id == q.id)
                   .order_by(Option.option_order, Option.id).all())
        questions.append({
            "id": q.id,
            "number": q.question_order,
            "text": q.question_text,
            "question_type": q.question_type,
            "config": q.config or {},
            "options": [{"id": o.id, "text": o.option_text,
                         "value_score": o.value_score or 0} for o in options],
        })
    return {
        "id": test.id,
        "title": test.title,
        "description": test.description,
        "version": test.version or 1,
        "scoring": test.scoring or "sum",
        "scoring_rules": test.scoring_rules,
        "questions": questions,
        "interpretations": [],
    }


def _open_campaign_and_test(db, campaign: Optional[TestCampaign]) -> tuple:
    """Кампания открыта и в сроках; иначе CampaignNotFound (закрыта, срок
    истёк) или CampaignNotStarted. Время — сервера."""
    if campaign is None:
        raise CampaignNotFound()
    state = access.state(campaign.status, campaign.opens_at, campaign.closes_at)
    if state == "scheduled":
        raise CampaignNotStarted(campaign.opens_at)
    if state != "open":
        raise CampaignNotFound()
    test = db.get(Test, campaign.test_id)
    if test is None or test.deleted_at is not None:
        raise CampaignNotFound()
    return campaign, test


def load_public(token_hash: str) -> dict:
    with SessionLocal() as db:
        campaign = (db.query(TestCampaign)
                    .filter(TestCampaign.link_token_hash == token_hash).first())
        campaign, test = _open_campaign_and_test(db, campaign)
        consent = _latest_consent(db)
        return {
            "title": campaign.title,
            "closes_at": campaign.closes_at,
            # Только для проверки вне транзакции (service); наружу не отдаётся.
            "access_code_hash": campaign.access_code_hash,
            "test": _test_structure(db, test),
            "consent": {"version": consent.version, "title": consent.title,
                        "content": consent.content},
        }


def access_code_hash(token_hash: str) -> Optional[str]:
    """Хеш кодового слова открытой кампании в сроках (для проверки до
    транзакции отправки)."""
    with SessionLocal() as db:
        campaign = (db.query(TestCampaign)
                    .filter(TestCampaign.link_token_hash == token_hash).first())
        campaign, _ = _open_campaign_and_test(db, campaign)
        return campaign.access_code_hash


# ── отправка ──────────────────────────────────────────────────────────────────

def _is_submission_key_conflict(exc: IntegrityError) -> bool:
    diag = getattr(getattr(exc, "orig", None), "diag", None)
    return getattr(diag, "constraint_name", None) == SUBMISSION_KEY_CONSTRAINT


def _existing(db, campaign_id: int, submission_key) -> bool:
    return db.query(
        db.query(CampaignResponse.id).filter(
            CampaignResponse.campaign_id == campaign_id,
            CampaignResponse.submission_key == submission_key,
        ).exists()
    ).scalar()


def submit(token_hash: str, payload: dict, *, ip: Optional[str],
           user_agent: Optional[str], verified_code_hash: Optional[str] = None) -> str:
    """'created' — сохранено; 'replay' — этот submission_key уже принят.

    verified_code_hash — хеш кодового слова, с которым service уже сверил
    присланное слово (bcrypt — вне транзакции). Под блокировкой строки он
    обязан совпасть с текущим: слово сменили или задали во время прохождения
    → AccessCodeWrong.

    Исключения: CampaignNotFound, CampaignNotStarted, AccessCodeWrong,
    ConsentOutdated, AnswersInvalid, AuditError (сбой обязательного аудита —
    ничего не сохранено).
    """
    safe_ctx = build_request_context(ip=ip, user_agent=user_agent)
    with SessionLocal() as db:
        campaign = (
            db.query(TestCampaign)
            .filter(TestCampaign.link_token_hash == token_hash)
            .with_for_update(read=True)
            .populate_existing()
            .first()
        )
        if campaign is not None and _existing(db, campaign.id,
                                              payload["submission_key"]):
            return "replay"
        campaign, test = _open_campaign_and_test(db, campaign)
        if campaign.access_code_hash != verified_code_hash:
            raise AccessCodeWrong()

        consent = _latest_consent(db)
        if payload["consent_version"] != consent.version:
            raise ConsentOutdated()

        structure = _test_structure(db, test)
        answers = validate_answers(structure, payload["answers"])
        scales = compute(structure, answers)

        record = ConsentRecord(
            user_id=None, consent_id=consent.id, accepted=True,
            ip_address=safe_ctx.ip_address, user_agent=safe_ctx.user_agent,
        )
        db.add(record)
        db.flush()

        response = CampaignResponse(
            campaign_id=campaign.id,
            submission_key=payload["submission_key"],
            test_version=structure["version"],
            full_name_enc=encrypt_text(payload["full_name"]),
            faculty_code=payload["faculty_code"],
            specialty=payload["specialty"],
            age=payload["age"],
            gender=payload["gender"],
            consent_record_id=record.id,
        )
        db.add(response)
        try:
            db.flush()
        except IntegrityError as exc:
            # Гонка двух одинаковых отправок: вторая — повтор, не ошибка.
            db.rollback()
            if _is_submission_key_conflict(exc):
                return "replay"
            raise

        db.add_all(
            CampaignResponseScale(response_id=response.id, **s) for s in scales
        )
        db.add_all(
            CampaignResponseAnswer(response_id=response.id, **a) for a in answers
        )
        record_event(
            event="campaign_response_submitted",
            actor=Actor.anonymous(),
            target=Target("campaign_response", response.id),
            outcome=Outcome.SUCCESS,
            metadata={},
            context=safe_ctx,
            db=db,
        )
        db.commit()
    return "created"
