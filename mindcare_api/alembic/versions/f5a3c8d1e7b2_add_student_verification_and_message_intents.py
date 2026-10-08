"""add_student_verification_and_message_intents

ADR-029: подтверждение статуса студента ДонГУ + outbox system-сообщений.

1. student_verification_requests — заявки на подтверждение. Статус
   «Студент ДонГУ подтверждён» — НЕ роль: membership/permissions не меняются.
     - uuid (внешний идентификатор), user_id → users ON DELETE CASCADE;
     - faculty_code VARCHAR(64) — код каталога app/student_verification/
       faculties.py (единый источник; CHECK по списку намеренно нет);
     - ticket_number_enc / rejection_reason_enc — только Fernet `enc:v1:`;
     - status pending | approved | rejected; reviewed_by → users ON DELETE SET
       NULL; reviewed_at; CHECK согласованности статуса и полей решения;
     - partial UNIQUE ux_svr_user_pending / ux_svr_user_approved: не больше
       одной pending и одной одобренной заявки на пользователя.
2. system_message_intents — сохранённые намерения доставки system-сообщений
   (текста нет — только message_code), UNIQUE (recipient_id, event_key),
   partial index по недоставленным.

Backfill НЕТ: существующие student_profiles.faculty подтверждением не являются,
ни одна заявка миграцией не создаётся и не одобряется.

downgrade — fail-closed: при наличии строк в любой из таблиц откат
отказывается (иначе необратимо теряются заявки, история решений и
недоставленные/доставленные намерения). STRICT, без IF EXISTS.

Revision ID: f5a3c8d1e7b2
Revises: d7e2a9c4f1b6
Create Date: 2026-10-07
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f5a3c8d1e7b2"
down_revision: Union[str, Sequence[str], None] = "d7e2a9c4f1b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. student_verification_requests ────────────────────────────────────
    op.create_table(
        "student_verification_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("faculty_code", sa.String(length=64), nullable=False),
        sa.Column("ticket_number_enc", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "submitted_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("reviewed_by", sa.Integer(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason_enc", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="student_verification_requests_pkey"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE",
            name="student_verification_requests_user_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"], ["users.id"], ondelete="SET NULL",
            name="student_verification_requests_reviewed_by_fkey",
        ),
        sa.UniqueConstraint("uuid", name="ux_svr_uuid"),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')", name="ck_svr_status",
        ),
        sa.CheckConstraint(
            "ticket_number_enc LIKE 'enc:v1:%'", name="ck_svr_ticket_encrypted",
        ),
        sa.CheckConstraint(
            "rejection_reason_enc IS NULL OR rejection_reason_enc LIKE 'enc:v1:%'",
            name="ck_svr_reason_encrypted",
        ),
        sa.CheckConstraint(
            "(status = 'pending' AND reviewed_at IS NULL AND reviewed_by IS NULL "
            "AND rejection_reason_enc IS NULL) "
            "OR (status = 'approved' AND reviewed_at IS NOT NULL "
            "AND rejection_reason_enc IS NULL) "
            "OR (status = 'rejected' AND reviewed_at IS NOT NULL "
            "AND rejection_reason_enc IS NOT NULL)",
            name="ck_svr_decision_consistent",
        ),
    )
    op.create_index(
        "ux_svr_user_pending", "student_verification_requests", ["user_id"],
        unique=True, postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index(
        "ux_svr_user_approved", "student_verification_requests", ["user_id"],
        unique=True, postgresql_where=sa.text("status = 'approved'"),
    )
    op.create_index(
        "ix_svr_status_submitted", "student_verification_requests",
        ["status", "submitted_at"],
    )
    op.create_index(
        "ix_svr_user_id", "student_verification_requests", ["user_id"],
    )

    # ── 2. system_message_intents ────────────────────────────────────────────
    op.create_table(
        "system_message_intents",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("recipient_id", sa.Integer(), nullable=False),
        sa.Column("event_key", sa.String(length=200), nullable=False),
        sa.Column("message_code", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "attempts", sa.Integer(), nullable=False, server_default=sa.text("0"),
        ),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="system_message_intents_pkey"),
        sa.ForeignKeyConstraint(
            ["recipient_id"], ["users.id"], ondelete="CASCADE",
            name="system_message_intents_recipient_id_fkey",
        ),
        sa.UniqueConstraint(
            "recipient_id", "event_key", name="ux_system_message_intents_key",
        ),
    )
    op.create_index(
        "ix_system_message_intents_undelivered", "system_message_intents", ["id"],
        postgresql_where=sa.text("delivered_at IS NULL"),
    )


def downgrade() -> None:
    conn = op.get_context().connection

    # Fail-closed ДО любых изменений. Только количество — без id/содержимого.
    requests = conn.execute(sa.text(
        "SELECT COUNT(*) FROM student_verification_requests"
    )).scalar()
    intents = conn.execute(sa.text(
        "SELECT COUNT(*) FROM system_message_intents"
    )).scalar()
    if requests or intents:
        raise RuntimeError(
            "Cannot downgrade f5a3c8d1e7b2: "
            f"{requests} student verification request(s) and {intents} system "
            "message intent(s) exist. Dropping the tables would irreversibly "
            "erase verification history and delivery state; export them first."
        )

    # STRICT: без IF EXISTS — рассинхрон схемы должен упасть, а не замаскироваться.
    op.drop_index(
        "ix_system_message_intents_undelivered", table_name="system_message_intents",
    )
    op.drop_table("system_message_intents")
    op.drop_index("ix_svr_user_id", table_name="student_verification_requests")
    op.drop_index("ix_svr_status_submitted", table_name="student_verification_requests")
    op.drop_index("ux_svr_user_approved", table_name="student_verification_requests")
    op.drop_index("ux_svr_user_pending", table_name="student_verification_requests")
    op.drop_table("student_verification_requests")
