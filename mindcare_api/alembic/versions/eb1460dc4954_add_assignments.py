"""add_assignments

ADR-033: задания психолога клиенту.

assignments — задание в рамках конкретного терапевтического сопровождения:
  - uuid — публичный идентификатор (UNIQUE);
  - engagement_id → therapy_engagements ON DELETE CASCADE; автор и получатель
    выводятся из сопровождения (пара в строке engagement не меняется);
  - text_enc — только Fernet `enc:v1:` (CHECK);
  - due_date — необязательный срок (DATE);
  - article_id → articles ON DELETE RESTRICT, необязательный материал
    (статьи удаляются мягко; RESTRICT не даёт молча потерять прикрепление);
  - status ∈ {active, completed, cancelled} (CHECK, server_default 'active')
    и согласованные отметки completed_at / cancelled_at (CHECK);
  - created_at / updated_at.
Индексы: (engagement_id, created_at) — списки; partial (engagement_id)
WHERE status = 'active' — счётчик; (article_id) — проверка RESTRICT.

Backfill НЕТ: ни одна строка миграцией не создаётся.

downgrade — fail-closed: при наличии строк откат отказывается (иначе необратимо
теряются задания и история их выполнения). STRICT, без IF EXISTS.

Revision ID: eb1460dc4954
Revises: a7d3f1c8e5b2
Create Date: 2026-10-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "eb1460dc4954"
down_revision: Union[str, Sequence[str], None] = "a7d3f1c8e5b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "assignments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("engagement_id", sa.Integer(), nullable=False),
        sa.Column("text_enc", sa.Text(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("article_id", sa.Integer(), nullable=True),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="active",
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="assignments_pkey"),
        sa.UniqueConstraint("uuid", name="assignments_uuid_key"),
        sa.ForeignKeyConstraint(
            ["engagement_id"], ["therapy_engagements.id"], ondelete="CASCADE",
            name="assignments_engagement_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["article_id"], ["articles.id"], ondelete="RESTRICT",
            name="assignments_article_id_fkey",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'completed', 'cancelled')",
            name="ck_assignments_status",
        ),
        sa.CheckConstraint(
            "(status = 'active' AND completed_at IS NULL AND cancelled_at IS NULL)"
            " OR (status = 'completed' AND completed_at IS NOT NULL"
            " AND cancelled_at IS NULL)"
            " OR (status = 'cancelled' AND cancelled_at IS NOT NULL"
            " AND completed_at IS NULL)",
            name="ck_assignments_status_timestamps",
        ),
        sa.CheckConstraint(
            "text_enc LIKE 'enc:v1:%'", name="ck_assignments_text_enc_format",
        ),
    )
    op.create_index(
        "ix_assignments_engagement_created", "assignments",
        ["engagement_id", "created_at"],
    )
    op.create_index(
        "ix_assignments_active_engagement", "assignments", ["engagement_id"],
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index("ix_assignments_article_id", "assignments", ["article_id"])


def downgrade() -> None:
    conn = op.get_context().connection

    # Fail-closed ДО любых изменений. Только количество — без id/содержимого.
    rows = conn.execute(sa.text("SELECT COUNT(*) FROM assignments")).scalar()
    if rows:
        raise RuntimeError(
            "Cannot downgrade eb1460dc4954: "
            f"{rows} assignment row(s) exist. Dropping the table would "
            "irreversibly erase assignments and their completion history; "
            "export them first."
        )

    # STRICT: без IF EXISTS — рассинхрон схемы должен упасть, а не замаскироваться.
    op.drop_index("ix_assignments_article_id", table_name="assignments")
    op.drop_index("ix_assignments_active_engagement", table_name="assignments")
    op.drop_index("ix_assignments_engagement_created", table_name="assignments")
    op.drop_table("assignments")
