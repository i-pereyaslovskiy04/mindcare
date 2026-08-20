"""add_audit_outcome

Stage 2 единого audit trail: структурные колонки исхода действия в audit_log.
  - outcome VARCHAR(10) NOT NULL DEFAULT 'success' — success | failure
  - failure_reason_code VARCHAR(100) NULL — стабильный enum-код (без PII/exc text)
  - CHECK ck_audit_outcome (outcome IN ('success','failure'))
  - INDEX idx_audit_outcome (outcome, created_at)

audit_log — RANGE-partitioned по created_at. Все DDL выполняются на parent через
raw op.execute и распространяются на существующие/новые партиции (PG11+):
  - ADD COLUMN ... NOT NULL DEFAULT: fast default, существующие строки = 'success';
  - ADD CONSTRAINT CHECK: наследуется партициями, валидируется быстро;
  - CREATE INDEX на parent: partitioned index, авто-propagate на партиции;
  - scripts/ensure_audit_partitions.py править не нужно (PARTITION OF наследует всё).

downgrade — STRICT (без IF EXISTS): schema drift должен ронять миграцию, а не
маскироваться. DROP COLUMN сохраняет строки и партиции, но БЕЗВОЗВРАТНО удаляет
значения outcome/failure_reason_code. На prod downgrade — только по отдельному
operational/compliance-решению (при необходимости с предварительным сохранением
значений новых колонок). Предназначен прежде всего для disposable/test DB.

Revision ID: f2a9c4e7b1d8
Revises: 3b46b9d94c08
Create Date: 2026-07-30
"""
from typing import Sequence, Union

from alembic import op

revision: str = "f2a9c4e7b1d8"
down_revision: Union[str, Sequence[str], None] = "3b46b9d94c08"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # outcome: add + backfill существующих строк + NOT NULL + server default —
    # один ALTER на partitioned parent (распространяется на все партиции).
    op.execute(
        "ALTER TABLE audit_log "
        "ADD COLUMN outcome VARCHAR(10) NOT NULL DEFAULT 'success'"
    )
    op.execute(
        "ALTER TABLE audit_log ADD COLUMN failure_reason_code VARCHAR(100)"
    )
    op.execute(
        "ALTER TABLE audit_log ADD CONSTRAINT ck_audit_outcome "
        "CHECK (outcome IN ('success', 'failure'))"
    )
    op.execute(
        "CREATE INDEX idx_audit_outcome ON audit_log (outcome, created_at)"
    )


def downgrade() -> None:
    # STRICT: без IF EXISTS — рассинхрон схемы должен упасть, а не замаскироваться.
    op.execute("DROP INDEX idx_audit_outcome")
    op.execute("ALTER TABLE audit_log DROP CONSTRAINT ck_audit_outcome")
    op.execute("ALTER TABLE audit_log DROP COLUMN failure_reason_code")
    op.execute("ALTER TABLE audit_log DROP COLUMN outcome")
