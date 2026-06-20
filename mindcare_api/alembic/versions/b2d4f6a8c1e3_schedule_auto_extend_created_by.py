"""schedule_auto_extend_created_by

Adds supervisor schedule-management fields to schedule_rules:
1. auto_extend BOOLEAN NOT NULL DEFAULT FALSE — when true, the schedule
   series is eligible for monthly auto-extension by the maintenance script
   (effective_until is mandatory for such series, enforced in the service).
2. created_by INTEGER NULL FK users(id) ON DELETE SET NULL — the supervisor
   who created the series, so auto-extension can notify them.

Breaks created together with rules share the rules' series_id, so no new
columns are needed on schedule_breaks for the series-level operations.

Revision ID: b2d4f6a8c1e3
Revises: c9a3f2e1d8b6
Create Date: 2026-06-19
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b2d4f6a8c1e3'
down_revision: Union[str, Sequence[str], None] = 'c9a3f2e1d8b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── auto_extend: NOT NULL, default false (kept as server_default) ─────
    op.add_column(
        'schedule_rules',
        sa.Column(
            'auto_extend',
            sa.Boolean(),
            nullable=False,
            server_default=sa.text('false'),
        ),
    )

    # ── created_by: nullable FK to users, SET NULL on user delete ─────────
    op.add_column(
        'schedule_rules',
        sa.Column('created_by', sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        'schedule_rules_created_by_fkey',
        'schedule_rules',
        'users',
        ['created_by'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint(
        'schedule_rules_created_by_fkey',
        'schedule_rules',
        type_='foreignkey',
    )
    op.drop_column('schedule_rules', 'created_by')
    op.drop_column('schedule_rules', 'auto_extend')
