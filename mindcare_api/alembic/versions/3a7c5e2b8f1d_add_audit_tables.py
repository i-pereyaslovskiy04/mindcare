"""add_audit_tables

Добавляет таблицы аудита в Alembic-управление:
  - auth_log       — аутентификационные события (login, logout, register, ...)
  - audit_log      — бизнес-события (действия пользователей над сущностями)
  - data_change_log — изменения данных (who changed what)

Использует CREATE TABLE IF NOT EXISTS для безопасного применения
в средах, где таблицы уже были созданы через create_audit_tables.sql.

В production-БД эти таблицы могут быть партиционированы по месяцам.
В этом случае миграция создаёт непартиционированные аналоги,
а partition-child tables управляются отдельно через SQL.

Revision ID: 3a7c5e2b8f1d
Revises: af13ad7a133c
Create Date: 2026-05-20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "3a7c5e2b8f1d"
down_revision: Union[str, Sequence[str], None] = "af13ad7a133c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create audit tables if they don't already exist."""
    # IF NOT EXISTS: safe for environments where these tables were
    # previously created via db/sql/create_audit_tables.sql
    op.execute("""
        CREATE TABLE IF NOT EXISTS auth_log (
            id             BIGSERIAL PRIMARY KEY,
            user_id        INTEGER REFERENCES users(id) ON DELETE SET NULL,
            user_email     VARCHAR(255),
            event          VARCHAR(50) NOT NULL,
            success        BOOLEAN NOT NULL DEFAULT TRUE,
            failure_reason VARCHAR(255),
            ip_address     INET,
            user_agent     TEXT,
            session_id     VARCHAR(255),
            mfa_method     VARCHAR(20),
            created_at     TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id             BIGSERIAL PRIMARY KEY,
            user_id        INTEGER REFERENCES users(id) ON DELETE SET NULL,
            user_role      VARCHAR(50),
            event_type     VARCHAR(100) NOT NULL,
            entity_type    VARCHAR(100),
            entity_id      INTEGER,
            description    TEXT,
            metadata       JSONB,
            ip_address     INET,
            user_agent     TEXT,
            session_id     VARCHAR(255),
            request_url    VARCHAR(500),
            request_method VARCHAR(10),
            created_at     TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS data_change_log (
            id             BIGSERIAL PRIMARY KEY,
            actor_id       INTEGER REFERENCES users(id) ON DELETE SET NULL,
            actor_role     VARCHAR(50),
            table_name     VARCHAR(100) NOT NULL,
            record_id      INTEGER,
            operation      VARCHAR(10) NOT NULL,
            old_values     JSONB,
            new_values     JSONB,
            changed_fields TEXT[],
            ip_address     INET,
            created_at     TIMESTAMPTZ DEFAULT NOW()
        )
    """)


def downgrade() -> None:
    """Drop audit tables."""
    # DROP IF EXISTS: safe if the tables were already manually removed
    op.execute("DROP TABLE IF EXISTS data_change_log")
    op.execute("DROP TABLE IF EXISTS audit_log")
    op.execute("DROP TABLE IF EXISTS auth_log")
