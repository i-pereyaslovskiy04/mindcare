"""schedule_rules: meeting_type_id nullable (working windows, schedule v3)

Revision ID: f1a4c7e0b9d2
Revises: d3e6f9a2b5c8
Create Date: 2026-06-19

Schedule v3: a psychologist's schedule is a set of working windows
(Mon–Fri 09:00–18:00). The meeting type is chosen only at booking time, and
the slot duration/buffer come from the MeetingType, not the ScheduleRule.

Therefore schedule_rules.meeting_type_id is no longer mandatory:
  - DROP NOT NULL (new working windows have meeting_type_id = NULL);
  - the FK to meeting_types (ON DELETE RESTRICT) is preserved;
  - legacy rows that already have a meeting_type_id keep working as ordinary
    working windows (the value is ignored by slot computation).

Reversible: downgrade restores NOT NULL (fails if NULL rows exist — expected,
since v3 introduces NULL rows; backfill before downgrading if needed).
"""

from alembic import op


revision = "f1a4c7e0b9d2"
down_revision = "d3e6f9a2b5c8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "schedule_rules",
        "meeting_type_id",
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "schedule_rules",
        "meeting_type_id",
        nullable=False,
    )
