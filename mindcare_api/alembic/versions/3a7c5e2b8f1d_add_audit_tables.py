"""add_audit_tables

Создаёт партиционированные таблицы аудита:
  - auth_log        — аутентификационные события (login, logout, register, ...)
  - audit_log       — бизнес-события (действия пользователей над сущностями)
  - data_change_log — изменения данных (ФЗ-152)

Partition strategy: RANGE по полю created_at, месячные партиции.
PRIMARY KEY: составной (id, created_at) — требование PostgreSQL для
partitioned tables: partition key должен входить в PK.

Стартовые партиции: 2026-01 .. 2028-12 (36 месяцев на каждую таблицу).
Будущие партиции добавляются отдельным maintenance-скриптом:
  cd mindcare_api/
  python scripts/ensure_audit_partitions.py --months-ahead 24

Совместимость с downstream-миграциями:
  - c5d8a1b4e7f2 (otp_code_varchar64)       — не затрагивает audit
  - f4b9e2c6a1d8 (audit_indexes_and_types)   — ALTER TYPE TEXT[]->TEXT[] = no-op
  - e9a3d7f2b5c0 (rebuild_audit_indexes)     — DROP/CREATE INDEX на parent = OK
  - b3c5e7a9f1d2 (extend_auth_log_event)     — ALTER COLUMN на parent = OK в PG15+

Revision ID: 3a7c5e2b8f1d
Revises: af13ad7a133c
Create Date: 2026-05-20
"""
from datetime import date
from typing import Sequence, Union

from alembic import op

revision: str = "3a7c5e2b8f1d"
down_revision: Union[str, Sequence[str], None] = "af13ad7a133c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ── Partition range ───────────────────────────────────────────────────────────
# Стартовые партиции: январь 2026 — декабрь 2028 включительно
_PARTITION_START = date(2026, 1, 1)
_PARTITION_END_EXCLUSIVE = date(2029, 1, 1)  # 2028-12 закрывается датой 2029-01-01


def _next_month(d: date) -> date:
    return date(d.year + 1, 1, 1) if d.month == 12 else date(d.year, d.month + 1, 1)


def _iter_months(start: date, end_exclusive: date):
    """Yields (suffix, from_iso, to_iso) for each month in [start, end_exclusive)."""
    d = start
    while d < end_exclusive:
        n = _next_month(d)
        yield d.strftime("%Y_%m"), d.isoformat(), n.isoformat()
        d = n


_TABLES = ("auth_log", "audit_log", "data_change_log")


def upgrade() -> None:
    # ── auth_log ──────────────────────────────────────────────────────────────
    # event VARCHAR(50): будет расширен до VARCHAR(150) миграцией b3c5e7a9f1d2
    op.execute("""
        CREATE TABLE IF NOT EXISTS auth_log (
            id             BIGSERIAL NOT NULL,
            user_id        INTEGER REFERENCES users(id) ON DELETE SET NULL,
            user_email     VARCHAR(255),
            event          VARCHAR(50) NOT NULL,
            success        BOOLEAN NOT NULL DEFAULT TRUE,
            failure_reason VARCHAR(255),
            ip_address     INET,
            user_agent     TEXT,
            session_id     VARCHAR(255),
            mfa_method     VARCHAR(20),
            created_at     TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY (id, created_at)
        ) PARTITION BY RANGE (created_at)
    """)

    # ── audit_log ─────────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id             BIGSERIAL NOT NULL,
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
            created_at     TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY (id, created_at)
        ) PARTITION BY RANGE (created_at)
    """)

    # ── data_change_log ───────────────────────────────────────────────────────
    # changed_fields создаётся как TEXT[] (ORM-тип ARRAY(Text())).
    # Миграция f4b9e2c6a1d8 делает ALTER TYPE TEXT[]->TEXT[] — no-op на PG15.
    op.execute("""
        CREATE TABLE IF NOT EXISTS data_change_log (
            id             BIGSERIAL NOT NULL,
            actor_id       INTEGER REFERENCES users(id) ON DELETE SET NULL,
            actor_role     VARCHAR(50),
            table_name     VARCHAR(100) NOT NULL,
            record_id      INTEGER,
            operation      VARCHAR(10) NOT NULL,
            old_values     JSONB,
            new_values     JSONB,
            changed_fields TEXT[],
            ip_address     INET,
            created_at     TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY (id, created_at)
        ) PARTITION BY RANGE (created_at)
    """)

    # ── Стартовые месячные партиции 2026-01 .. 2028-12 ───────────────────────
    # IF NOT EXISTS: безопасно для повторного запуска и частично применённых
    # предыдущих вариантов этой миграции.
    for suffix, from_dt, to_dt in _iter_months(_PARTITION_START, _PARTITION_END_EXCLUSIVE):
        for table in _TABLES:
            op.execute(
                f"CREATE TABLE IF NOT EXISTS {table}_{suffix} "
                f"PARTITION OF {table} "
                f"FOR VALUES FROM ('{from_dt}') TO ('{to_dt}')"
            )


def downgrade() -> None:
    # CASCADE удаляет дочерние партиции вместе с родительской таблицей
    op.execute("DROP TABLE IF EXISTS data_change_log CASCADE")
    op.execute("DROP TABLE IF EXISTS audit_log CASCADE")
    op.execute("DROP TABLE IF EXISTS auth_log CASCADE")
