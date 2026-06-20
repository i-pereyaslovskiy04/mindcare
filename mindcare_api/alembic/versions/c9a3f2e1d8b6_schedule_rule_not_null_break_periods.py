"""schedule_rule_not_null_break_periods

Two schema fixes:
1. schedule_rules.meeting_type_id → NOT NULL (required for all rules;
   "general availability" concept removed). FK changed to RESTRICT so
   deleting a meeting type that has active rules is rejected explicitly.
2. schedule_breaks.effective_from / effective_until added so breaks are
   bounded to a schedule period instead of living forever.

Revision ID: c9a3f2e1d8b6
Revises: 9e193b84bba8
Create Date: 2026-06-18
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c9a3f2e1d8b6'
down_revision: Union[str, Sequence[str], None] = '9e193b84bba8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. schedule_rules.meeting_type_id → NOT NULL ──────────────────────
    # Dev DB may have NULL rows from old tests; remove them before the
    # constraint is added (no production data at this stage).
    op.execute(
        "DELETE FROM schedule_rules WHERE meeting_type_id IS NULL"
    )

    # Drop FK that allowed SET NULL; re-create with RESTRICT.
    op.drop_constraint(
        'schedule_rules_meeting_type_id_fkey',
        'schedule_rules',
        type_='foreignkey',
    )
    op.alter_column(
        'schedule_rules',
        'meeting_type_id',
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.create_foreign_key(
        'schedule_rules_meeting_type_id_fkey',
        'schedule_rules',
        'meeting_types',
        ['meeting_type_id'],
        ['id'],
        ondelete='RESTRICT',
    )

    # ── 2. schedule_breaks: add effective_from / effective_until ──────────
    # effective_from: mandatory, back-fill existing rows with CURRENT_DATE,
    # then remove server_default so the application must supply the value.
    op.add_column(
        'schedule_breaks',
        sa.Column(
            'effective_from',
            sa.Date(),
            nullable=False,
            server_default=sa.text('CURRENT_DATE'),
        ),
    )
    op.alter_column(
        'schedule_breaks',
        'effective_from',
        server_default=None,
    )
    op.add_column(
        'schedule_breaks',
        sa.Column('effective_until', sa.Date(), nullable=True),
    )


def downgrade() -> None:
    # ── Remove effective_from / effective_until from schedule_breaks ───────
    op.drop_column('schedule_breaks', 'effective_until')
    op.drop_column('schedule_breaks', 'effective_from')

    # ── Restore schedule_rules.meeting_type_id → nullable + SET NULL FK ───
    op.drop_constraint(
        'schedule_rules_meeting_type_id_fkey',
        'schedule_rules',
        type_='foreignkey',
    )
    op.alter_column(
        'schedule_rules',
        'meeting_type_id',
        existing_type=sa.Integer(),
        nullable=True,
    )
    op.create_foreign_key(
        'schedule_rules_meeting_type_id_fkey',
        'schedule_rules',
        'meeting_types',
        ['meeting_type_id'],
        ['id'],
        ondelete='SET NULL',
    )
