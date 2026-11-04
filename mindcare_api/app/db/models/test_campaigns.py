"""
Модели: тестовые кампании по публичной ссылке (ADR-036).

  TestCampaign            — кампания супервизора: один тест, одна ссылка на всех.
  CampaignResponse        — одно прохождение по ссылке без аккаунта: анкета
                            (ФИО, факультет, специальность, возраст, пол) и
                            ссылка на запись согласия.
  CampaignResponseScale   — баллы шкал, снимок на момент отправки.
  CampaignResponseAnswer  — ответы (вопрос → выбранный вариант).

Изоляция: ответы кампаний НЕ пишутся в test_results/student_answers — ни один
существующий путь чтения результатов (история студента, staff-результаты,
карточка клиента) их структурно не видит.

Ссылка: link_token_hash (SHA-256 hex) — поиск по входящему токену;
link_token_enc (`enc:v1:`) — чтобы супервизор мог снова скопировать ссылку.
Перевыпуск ссылки меняет оба поля.

IP / User-Agent респондента хранятся ТОЛЬКО в consent_records (как при
регистрации). Достоверность и типы профиля НЕ хранятся — вычисляются из баллов
шкал при выгрузке.

Удаление — физическое (исключение из правила soft delete, ADR-036): ответ
удаляется вместе со шкалами и ответами (CASCADE), запись согласия — тем же
service-вызовом в той же транзакции (сначала ответ, затем согласие).

SECURITY: full_name_enc и link_token_enc — ТОЛЬКО Fernet `enc:v1:`
(app/core/encryption.py), закреплено CHECK. Не логировать, не копировать в
audit/data_change_log.
"""
import uuid as _uuid

from sqlalchemy import (
    CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, SmallInteger,
    String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.db.base import Base

CAMPAIGN_STATUSES = ("open", "closed")
RESPONDENT_GENDERS = ("male", "female")
RESPONDENT_AGE_MIN = 14
RESPONDENT_AGE_MAX = 100


class TestCampaign(Base):
    __tablename__ = "test_campaigns"
    __test__ = False  # не pytest-класс, несмотря на префикс Test
    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'closed')", name="ck_test_campaigns_status",
        ),
        CheckConstraint(
            "(status = 'open' AND closed_at IS NULL)"
            " OR (status = 'closed' AND closed_at IS NOT NULL)",
            name="ck_test_campaigns_status_closed_at",
        ),
        CheckConstraint(
            "link_token_hash ~ '^[0-9a-f]{64}$'",
            name="ck_test_campaigns_link_token_hash_format",
        ),
        CheckConstraint(
            "link_token_enc LIKE 'enc:v1:%'",
            name="ck_test_campaigns_link_token_enc_format",
        ),
        CheckConstraint(
            "length(btrim(title)) > 0", name="ck_test_campaigns_title_not_blank",
        ),
        # Список кампаний супервизора — keyset по (created_at, id).
        Index("ix_test_campaigns_created", "created_at", "id"),
        # Проверка RESTRICT при удалении теста.
        Index("ix_test_campaigns_test_id", "test_id"),
    )

    id              = Column(Integer, primary_key=True)
    uuid            = Column(
        UUID(as_uuid=True), unique=True, nullable=False, default=_uuid.uuid4
    )
    test_id         = Column(
        Integer, ForeignKey("tests.id", ondelete="RESTRICT"), nullable=False
    )
    title           = Column(String(255), nullable=False)
    status          = Column(String(20), nullable=False, server_default="open")
    link_token_hash = Column(String(64), nullable=False, unique=True)
    link_token_enc  = Column(Text, nullable=False)        # ТОЛЬКО enc:v1:
    created_by      = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at      = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at      = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    closed_at       = Column(DateTime(timezone=True), nullable=True)


class CampaignResponse(Base):
    __tablename__ = "campaign_responses"
    __table_args__ = (
        UniqueConstraint(
            "campaign_id", "submission_key",
            name="uq_campaign_responses_submission_key",
        ),
        CheckConstraint(
            "full_name_enc LIKE 'enc:v1:%'",
            name="ck_campaign_responses_full_name_enc_format",
        ),
        CheckConstraint(
            "length(btrim(specialty)) > 0",
            name="ck_campaign_responses_specialty_not_blank",
        ),
        CheckConstraint(
            "age BETWEEN 14 AND 100", name="ck_campaign_responses_age_range",
        ),
        CheckConstraint(
            "gender IN ('male', 'female')", name="ck_campaign_responses_gender",
        ),
        # Таблица респондентов и выгрузка — keyset по (submitted_at, id).
        Index("ix_campaign_responses_campaign_submitted",
              "campaign_id", "submitted_at", "id"),
    )

    id                = Column(Integer, primary_key=True)
    uuid              = Column(
        UUID(as_uuid=True), unique=True, nullable=False, default=_uuid.uuid4
    )
    campaign_id       = Column(
        Integer, ForeignKey("test_campaigns.id", ondelete="CASCADE"),
        nullable=False,
    )
    submission_key    = Column(UUID(as_uuid=True), nullable=False)
    test_version      = Column(Integer, nullable=False)
    full_name_enc     = Column(Text, nullable=False)      # ТОЛЬКО enc:v1:
    faculty_code      = Column(String(64), nullable=False)
    specialty         = Column(String(255), nullable=False)
    age               = Column(SmallInteger, nullable=False)
    gender            = Column(String(10), nullable=False)
    consent_record_id = Column(
        Integer, ForeignKey("consent_records.id", ondelete="RESTRICT"),
        nullable=False, unique=True,
    )
    submitted_at      = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CampaignResponseScale(Base):
    __tablename__ = "campaign_response_scales"
    __table_args__ = (
        UniqueConstraint(
            "response_id", "scale_name",
            name="uq_campaign_response_scales_response_scale",
        ),
    )

    id          = Column(Integer, primary_key=True)
    response_id = Column(
        Integer, ForeignKey("campaign_responses.id", ondelete="CASCADE"),
        nullable=False,
    )
    scale_name  = Column(String(100), nullable=False)
    score       = Column(Integer, nullable=False)
    max_score   = Column(Integer, nullable=False)


class CampaignResponseAnswer(Base):
    __tablename__ = "campaign_response_answers"
    __table_args__ = (
        UniqueConstraint(
            "response_id", "question_id",
            name="uq_campaign_response_answers_response_question",
        ),
        # Проверки RESTRICT при удалении вопросов/вариантов.
        Index("ix_campaign_response_answers_question_id", "question_id"),
        Index("ix_campaign_response_answers_option_id", "option_id"),
    )

    id          = Column(Integer, primary_key=True)
    response_id = Column(
        Integer, ForeignKey("campaign_responses.id", ondelete="CASCADE"),
        nullable=False,
    )
    question_id = Column(
        Integer, ForeignKey("questions.id", ondelete="RESTRICT"), nullable=False
    )
    option_id   = Column(
        Integer, ForeignKey("options.id", ondelete="RESTRICT"), nullable=False
    )
