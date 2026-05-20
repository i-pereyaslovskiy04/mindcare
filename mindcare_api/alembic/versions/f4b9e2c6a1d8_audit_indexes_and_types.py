"""audit_indexes_and_types

Добавляет индексы на audit-таблицы и исправляет тип
data_change_log.changed_fields (ARRAY(String) → ARRAY(TEXT)).

Использует IF NOT EXISTS — безопасно для сред, где индексы уже
существуют (созданы через create_audit_tables.sql).

Revision ID: f4b9e2c6a1d8
Revises: c5d8a1b4e7f2
Create Date: 2026-05-20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "f4b9e2c6a1d8"
down_revision: Union[str, Sequence[str], None] = "c5d8a1b4e7f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── auth_log indexes ──────────────────────────────────────────────────────
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_auth_user "
        "ON auth_log (user_id, created_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_auth_ip "
        "ON auth_log (ip_address, created_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_auth_failures "
        "ON auth_log (ip_address, created_at)"
    )

    # ── audit_log indexes ─────────────────────────────────────────────────────
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_user "
        "ON audit_log (user_id, created_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_event "
        "ON audit_log (event_type, created_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_entity "
        "ON audit_log (entity_type, entity_id)"
    )

    # ── data_change_log indexes ───────────────────────────────────────────────
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_dcl_actor "
        "ON data_change_log (actor_id, created_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_dcl_table "
        "ON data_change_log (table_name, record_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_dcl_operation "
        "ON data_change_log (operation, created_at)"
    )

    # ── data_change_log.changed_fields: ARRAY(varchar) → ARRAY(text) ─────────
    # PostgreSQL TEXT and VARCHAR-without-limit are storage-equivalent,
    # but SQLAlchemy reflection distinguishes them. Aligning to TEXT[].
    op.alter_column(
        "data_change_log",
        "changed_fields",
        existing_type=sa.ARRAY(sa.String()),
        type_=sa.ARRAY(sa.Text()),
        existing_nullable=True,
    )


def downgrade() -> None:
    # Reverse type change
    op.alter_column(
        "data_change_log",
        "changed_fields",
        existing_type=sa.ARRAY(sa.Text()),
        type_=sa.ARRAY(sa.String()),
        existing_nullable=True,
    )

    # Drop indexes
    for idx in [
        "idx_auth_user", "idx_auth_ip", "idx_auth_failures",
        "idx_audit_user", "idx_audit_event", "idx_audit_entity",
        "idx_dcl_actor", "idx_dcl_table", "idx_dcl_operation",
    ]:
        op.execute(f"DROP INDEX IF EXISTS {idx}")
