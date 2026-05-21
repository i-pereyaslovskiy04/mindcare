"""rebuild_audit_indexes

Пересоздаёт индексы audit-таблиц: удаляет старые (с DESC из create_audit_tables.sql)
и создаёт новые без DESC, что соответствует ORM-определениям в audit.py.

Revision ID: e9a3d7f2b5c0
Revises: f4b9e2c6a1d8
Create Date: 2026-05-20
"""
from typing import Sequence, Union

from alembic import op

revision: str = "e9a3d7f2b5c0"
down_revision: Union[str, Sequence[str], None] = "f4b9e2c6a1d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Индексы, которые нужно пересоздать (старые имели DESC на created_at)
_INDEXES = [
    # (name, table, columns_sql)
    ("idx_auth_user",     "auth_log",         "user_id, created_at"),
    ("idx_auth_ip",       "auth_log",         "ip_address, created_at"),
    ("idx_auth_failures", "auth_log",         "ip_address, created_at"),
    ("idx_audit_user",    "audit_log",        "user_id, created_at"),
    ("idx_audit_event",   "audit_log",        "event_type, created_at"),
    ("idx_dcl_actor",     "data_change_log",  "actor_id, created_at"),
    ("idx_dcl_operation", "data_change_log",  "operation, created_at"),
]


def upgrade() -> None:
    for name, table, cols in _INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {name}")
        op.execute(f"CREATE INDEX {name} ON {table} ({cols})")


def downgrade() -> None:
    # Restore DESC variants (original create_audit_tables.sql behaviour)
    for name, table, cols in _INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {name}")
        # Reconstruct with DESC on created_at (last column)
        base_cols = cols.rsplit(",", 1)[0].strip()
        op.execute(f"CREATE INDEX {name} ON {table} ({base_cols}, created_at DESC)")
