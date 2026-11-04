"""add_test_campaigns

ADR-036: тестовые кампании по публичной ссылке без аккаунта (ИТО Собчик).

tests:
  - scoring_profile VARCHAR(30) NULL + CHECK (NULL | 'ito_sobchik') —
    пост-обработка результата методики (достоверность, типы);
  - campaign_only BOOLEAN NOT NULL DEFAULT false — тест только для кампаний.

test_campaigns — кампания: test_id → tests RESTRICT, title, status open/closed
  + closed_at (CHECK согласованности), link_token_hash (SHA-256 hex, UNIQUE,
  CHECK формата) и link_token_enc (только `enc:v1:`), created_by → users
  SET NULL, created_at/updated_at.

campaign_responses — прохождение по ссылке: campaign_id → CASCADE,
  submission_key (UNIQUE с campaign_id — идемпотентность), test_version,
  full_name_enc (только `enc:v1:`), faculty_code, specialty (не пустая),
  age 14..100, gender male/female, consent_record_id → consent_records
  RESTRICT (UNIQUE), submitted_at. IP/UA — только в consent_records.

campaign_response_scales — баллы шкал (UNIQUE response+scale), CASCADE.
campaign_response_answers — ответы (UNIQUE response+question), CASCADE от
  ответа, RESTRICT на questions/options.

test_results / student_answers НЕ меняются: ответы кампаний изолированы от
существующих путей чтения результатов структурно.

Backfill НЕТ. downgrade — fail-closed при наличии кампаний (иначе необратимо
теряются ответы респондентов) или тестов с профилем/признаком кампании.
STRICT, без IF EXISTS.

Revision ID: a3e7c1f9d5b2
Revises: d0ee44dc2527
Create Date: 2026-11-04
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a3e7c1f9d5b2"
down_revision: Union[str, Sequence[str], None] = "d0ee44dc2527"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _timestamps():
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
    ]


def upgrade() -> None:
    # ── tests ────────────────────────────────────────────────────────────────
    op.add_column(
        "tests", sa.Column("scoring_profile", sa.String(length=30), nullable=True),
    )
    op.add_column(
        "tests",
        sa.Column(
            "campaign_only", sa.Boolean(), nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_check_constraint(
        "ck_tests_scoring_profile", "tests",
        "scoring_profile IS NULL OR scoring_profile IN ('ito_sobchik')",
    )

    # ── test_campaigns ───────────────────────────────────────────────────────
    op.create_table(
        "test_campaigns",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("test_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="open",
        ),
        sa.Column("link_token_hash", sa.String(length=64), nullable=False),
        sa.Column("link_token_enc", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        *_timestamps(),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="test_campaigns_pkey"),
        sa.UniqueConstraint("uuid", name="test_campaigns_uuid_key"),
        sa.UniqueConstraint(
            "link_token_hash", name="test_campaigns_link_token_hash_key",
        ),
        sa.ForeignKeyConstraint(
            ["test_id"], ["tests.id"], ondelete="RESTRICT",
            name="test_campaigns_test_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], ondelete="SET NULL",
            name="test_campaigns_created_by_fkey",
        ),
        sa.CheckConstraint(
            "status IN ('open', 'closed')", name="ck_test_campaigns_status",
        ),
        sa.CheckConstraint(
            "(status = 'open' AND closed_at IS NULL)"
            " OR (status = 'closed' AND closed_at IS NOT NULL)",
            name="ck_test_campaigns_status_closed_at",
        ),
        sa.CheckConstraint(
            "link_token_hash ~ '^[0-9a-f]{64}$'",
            name="ck_test_campaigns_link_token_hash_format",
        ),
        sa.CheckConstraint(
            "link_token_enc LIKE 'enc:v1:%'",
            name="ck_test_campaigns_link_token_enc_format",
        ),
        sa.CheckConstraint(
            "length(btrim(title)) > 0", name="ck_test_campaigns_title_not_blank",
        ),
    )
    op.create_index(
        "ix_test_campaigns_created", "test_campaigns", ["created_at", "id"],
    )
    op.create_index("ix_test_campaigns_test_id", "test_campaigns", ["test_id"])

    # ── campaign_responses ───────────────────────────────────────────────────
    op.create_table(
        "campaign_responses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("campaign_id", sa.Integer(), nullable=False),
        sa.Column("submission_key", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("test_version", sa.Integer(), nullable=False),
        sa.Column("full_name_enc", sa.Text(), nullable=False),
        sa.Column("faculty_code", sa.String(length=64), nullable=False),
        sa.Column("specialty", sa.String(length=255), nullable=False),
        sa.Column("age", sa.SmallInteger(), nullable=False),
        sa.Column("gender", sa.String(length=10), nullable=False),
        sa.Column("consent_record_id", sa.Integer(), nullable=False),
        sa.Column(
            "submitted_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="campaign_responses_pkey"),
        sa.UniqueConstraint("uuid", name="campaign_responses_uuid_key"),
        sa.UniqueConstraint(
            "consent_record_id", name="campaign_responses_consent_record_id_key",
        ),
        sa.UniqueConstraint(
            "campaign_id", "submission_key",
            name="uq_campaign_responses_submission_key",
        ),
        sa.ForeignKeyConstraint(
            ["campaign_id"], ["test_campaigns.id"], ondelete="CASCADE",
            name="campaign_responses_campaign_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["consent_record_id"], ["consent_records.id"], ondelete="RESTRICT",
            name="campaign_responses_consent_record_id_fkey",
        ),
        sa.CheckConstraint(
            "full_name_enc LIKE 'enc:v1:%'",
            name="ck_campaign_responses_full_name_enc_format",
        ),
        sa.CheckConstraint(
            "length(btrim(specialty)) > 0",
            name="ck_campaign_responses_specialty_not_blank",
        ),
        sa.CheckConstraint(
            "age BETWEEN 14 AND 100", name="ck_campaign_responses_age_range",
        ),
        sa.CheckConstraint(
            "gender IN ('male', 'female')", name="ck_campaign_responses_gender",
        ),
    )
    op.create_index(
        "ix_campaign_responses_campaign_submitted", "campaign_responses",
        ["campaign_id", "submitted_at", "id"],
    )

    # ── campaign_response_scales ─────────────────────────────────────────────
    op.create_table(
        "campaign_response_scales",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("response_id", sa.Integer(), nullable=False),
        sa.Column("scale_name", sa.String(length=100), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("max_score", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="campaign_response_scales_pkey"),
        sa.UniqueConstraint(
            "response_id", "scale_name",
            name="uq_campaign_response_scales_response_scale",
        ),
        sa.ForeignKeyConstraint(
            ["response_id"], ["campaign_responses.id"], ondelete="CASCADE",
            name="campaign_response_scales_response_id_fkey",
        ),
    )

    # ── campaign_response_answers ────────────────────────────────────────────
    op.create_table(
        "campaign_response_answers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("response_id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("option_id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="campaign_response_answers_pkey"),
        sa.UniqueConstraint(
            "response_id", "question_id",
            name="uq_campaign_response_answers_response_question",
        ),
        sa.ForeignKeyConstraint(
            ["response_id"], ["campaign_responses.id"], ondelete="CASCADE",
            name="campaign_response_answers_response_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["question_id"], ["questions.id"], ondelete="RESTRICT",
            name="campaign_response_answers_question_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["option_id"], ["options.id"], ondelete="RESTRICT",
            name="campaign_response_answers_option_id_fkey",
        ),
    )
    op.create_index(
        "ix_campaign_response_answers_question_id", "campaign_response_answers",
        ["question_id"],
    )
    op.create_index(
        "ix_campaign_response_answers_option_id", "campaign_response_answers",
        ["option_id"],
    )


def downgrade() -> None:
    conn = op.get_context().connection

    # Fail-closed ДО любых изменений. Только количество — без id/содержимого.
    campaigns = conn.execute(sa.text("SELECT COUNT(*) FROM test_campaigns")).scalar()
    if campaigns:
        raise RuntimeError(
            "Cannot downgrade a3e7c1f9d5b2: "
            f"{campaigns} test campaign row(s) exist. Dropping the tables would "
            "irreversibly erase campaign responses; export and delete them first."
        )
    flagged = conn.execute(sa.text(
        "SELECT COUNT(*) FROM tests"
        " WHERE scoring_profile IS NOT NULL OR campaign_only"
    )).scalar()
    if flagged:
        raise RuntimeError(
            "Cannot downgrade a3e7c1f9d5b2: "
            f"{flagged} test(s) use scoring_profile/campaign_only. Dropping the "
            "columns would silently expose campaign-only tests in the student "
            "catalog; clear the flags first."
        )

    # STRICT: без IF EXISTS — рассинхрон схемы должен упасть, а не замаскироваться.
    op.drop_index(
        "ix_campaign_response_answers_option_id",
        table_name="campaign_response_answers",
    )
    op.drop_index(
        "ix_campaign_response_answers_question_id",
        table_name="campaign_response_answers",
    )
    op.drop_table("campaign_response_answers")
    op.drop_table("campaign_response_scales")
    op.drop_index(
        "ix_campaign_responses_campaign_submitted", table_name="campaign_responses",
    )
    op.drop_table("campaign_responses")
    op.drop_index("ix_test_campaigns_test_id", table_name="test_campaigns")
    op.drop_index("ix_test_campaigns_created", table_name="test_campaigns")
    op.drop_table("test_campaigns")

    op.drop_constraint("ck_tests_scoring_profile", "tests", type_="check")
    op.drop_column("tests", "campaign_only")
    op.drop_column("tests", "scoring_profile")
