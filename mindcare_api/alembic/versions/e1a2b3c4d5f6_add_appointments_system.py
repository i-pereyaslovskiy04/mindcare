"""add_appointments_system

Appointments system: MeetingType, GroupSession, GroupSessionRegistration,
appointment extension (meeting_type_id, decline_reason, status VARCHAR(30)).

Changes:
  NEW TABLE meeting_types
  NEW TABLE group_sessions
  NEW TABLE group_session_registrations
    - partial unique index (group_session_id, student_id) WHERE status='registered'
  ALTER TABLE appointments:
    + meeting_type_id  FK -> meeting_types (nullable)
    + decline_reason   TEXT
    ALTER COLUMN status VARCHAR(20) -> VARCHAR(30)

Notes:
  - Does NOT use ALTER TYPE: status is VARCHAR in the Alembic chain.
  - Does NOT add ends_at: baseline af13ad7a133c already has it.
  - Partial unique index on group_session_registrations allows re-registration
    after cancel (only one 'registered' row per session+student at a time).

Revision ID: e1a2b3c4d5f6
Revises: c4f7a2e9d1b8
Create Date: 2026-06-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e1a2b3c4d5f6"
down_revision: Union[str, Sequence[str], None] = "c4f7a2e9d1b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── meeting_types ─────────────────────────────────────────────────
    op.create_table(
        "meeting_types",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "duration_minutes",
            sa.Integer(),
            nullable=False,
            server_default="50",
        ),
        sa.Column(
            "allow_in_person",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
        sa.Column(
            "allow_online",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
        sa.Column(
            "is_group",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
        sa.Column(
            "is_bookable",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
        sa.Column(
            "display_order",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── group_sessions ────────────────────────────────────────────────
    op.create_table(
        "group_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "uuid", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("meeting_type_id", sa.Integer(), nullable=False),
        sa.Column("psychologist_id", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column(
            "starts_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "ends_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column("format", sa.String(length=20), nullable=False),
        sa.Column(
            "capacity",
            sa.Integer(),
            nullable=False,
            server_default="10",
        ),
        sa.Column(
            "booking_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="scheduled",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["meeting_type_id"],
            ["meeting_types.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["psychologist_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
    )

    # ── group_session_registrations ───────────────────────────────────
    # Partial unique index instead of full UNIQUE constraint:
    # allows re-registration after cancel (cancelled rows are ignored).
    op.create_table(
        "group_session_registrations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "uuid", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("group_session_id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="registered",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["group_session_id"],
            ["group_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index(
        "ux_gsr_active",
        "group_session_registrations",
        ["group_session_id", "student_id"],
        unique=True,
        postgresql_where=sa.text("status = 'registered'"),
    )

    # ── appointments: new columns ─────────────────────────────────────
    op.add_column(
        "appointments",
        sa.Column("meeting_type_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "appointments",
        sa.Column("decline_reason", sa.Text(), nullable=True),
    )
    op.create_foreign_key(
        "fk_appointments_meeting_type_id",
        "appointments",
        "meeting_types",
        ["meeting_type_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Widen status: VARCHAR(20) -> VARCHAR(30).
    # "pending_confirmation" is exactly 20 chars — borderline safe.
    # ORM model declares String(30), so align the DB column.
    op.alter_column(
        "appointments",
        "status",
        existing_type=sa.String(length=20),
        type_=sa.String(length=30),
        existing_nullable=True,
    )


def downgrade() -> None:
    # Restore status column width
    op.alter_column(
        "appointments",
        "status",
        existing_type=sa.String(length=30),
        type_=sa.String(length=20),
        existing_nullable=True,
    )

    # Remove new columns from appointments
    op.drop_constraint(
        "fk_appointments_meeting_type_id",
        "appointments",
        type_="foreignkey",
    )
    op.drop_column("appointments", "decline_reason")
    op.drop_column("appointments", "meeting_type_id")

    # Drop tables in reverse FK order
    op.drop_index(
        "ux_gsr_active",
        table_name="group_session_registrations",
    )
    op.drop_table("group_session_registrations")
    op.drop_table("group_sessions")
    op.drop_table("meeting_types")
