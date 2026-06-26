"""rework_schedule_slot_model

Переработка модели расписания/слотов:
- MeetingType владеет длительностью и буфером (duration_minutes + buffer_minutes);
  добавлено description.
- ScheduleRule описывает только доступность: добавлены meeting_type_id, period,
  series_id; удалены slot_duration_minutes и break_minutes.
- Новая таблица schedule_breaks — повторяющиеся перерывы (например обед).
- schedule_exceptions: снята уникальность «одно исключение на дату»; enum
  schedule_exception_type расширен значениями unavailable / extra_availability.
- group_sessions: добавлено description.

Revision ID: 9e193b84bba8
Revises: 71dfb9c56b13
Create Date: 2026-06-18 16:03:57.673625

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '9e193b84bba8'
down_revision: Union[str, Sequence[str], None] = '71dfb9c56b13'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── meeting_types: description + buffer_minutes ──────────────────────────
    op.add_column(
        "meeting_types",
        sa.Column("description", sa.Text(), nullable=True),
    )
    op.add_column(
        "meeting_types",
        sa.Column(
            "buffer_minutes",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("10"),
        ),
    )

    # ── schedule_rules: availability-only model ──────────────────────────────
    # Legacy view v_schedule_active (из db/sql/009) ссылается на удаляемые
    # колонки — пересоздаём его без slot_duration_minutes/break_minutes.
    op.execute("DROP VIEW IF EXISTS v_schedule_active")
    op.add_column(
        "schedule_rules",
        sa.Column("meeting_type_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "schedule_rules_meeting_type_id_fkey",
        "schedule_rules",
        "meeting_types",
        ["meeting_type_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "schedule_rules",
        sa.Column("period", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "schedule_rules",
        sa.Column("series_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.drop_column("schedule_rules", "slot_duration_minutes")
    op.drop_column("schedule_rules", "break_minutes")
    # Пересоздаём availability-view без удалённых колонок.
    op.execute(
        """
        CREATE VIEW v_schedule_active AS
        SELECT
            sr.psychologist_id,
            sr.meeting_type_id,
            sr.day_of_week,
            sr.start_time,
            sr.end_time,
            sr.period,
            sr.effective_from,
            sr.effective_until
        FROM schedule_rules sr
        WHERE sr.is_active = TRUE
          AND sr.effective_from <= CURRENT_DATE
          AND (sr.effective_until IS NULL OR sr.effective_until >= CURRENT_DATE)
        """
    )

    # ── schedule_breaks: recurring breaks ────────────────────────────────────
    op.create_table(
        "schedule_breaks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("psychologist_id", sa.Integer(), nullable=False),
        sa.Column("day_of_week", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("series_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["psychologist_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.CheckConstraint(
            "start_time < end_time", name="chk_schedule_break_times"
        ),
    )
    op.create_index(
        "ix_schedule_breaks_psych_day",
        "schedule_breaks",
        ["psychologist_id", "day_of_week"],
    )

    # ── group_sessions: description ──────────────────────────────────────────
    op.add_column(
        "group_sessions",
        sa.Column("description", sa.Text(), nullable=True),
    )

    # ── schedule_exceptions: drop unique-per-date, enum → varchar ────────────
    op.drop_constraint(
        "schedule_exceptions_psychologist_id_exception_date_key",
        "schedule_exceptions",
        type_="unique",
    )
    # exception_type был PG enum schedule_exception_type (owned by postgres,
    # ALTER TYPE недоступен под MindcareUser). ORM-модель давно объявляет
    # String(20) — приводим колонку к VARCHAR, чтобы принимать новые значения
    # day_off / unavailable / extra_availability без enum-ограничений.
    op.alter_column(
        "schedule_exceptions",
        "exception_type",
        existing_type=postgresql.ENUM(name="schedule_exception_type"),
        type_=sa.String(length=20),
        existing_nullable=False,
        postgresql_using="exception_type::text",
    )


def downgrade() -> None:
    # group_sessions
    op.drop_column("group_sessions", "description")

    # schedule_breaks
    op.drop_index("ix_schedule_breaks_psych_day", table_name="schedule_breaks")
    op.drop_table("schedule_breaks")

    # schedule_rules
    op.execute("DROP VIEW IF EXISTS v_schedule_active")
    op.drop_constraint(
        "schedule_rules_meeting_type_id_fkey",
        "schedule_rules",
        type_="foreignkey",
    )
    op.drop_column("schedule_rules", "series_id")
    op.drop_column("schedule_rules", "period")
    op.drop_column("schedule_rules", "meeting_type_id")
    op.add_column(
        "schedule_rules",
        sa.Column(
            "slot_duration_minutes",
            sa.Integer(),
            server_default=sa.text("50"),
            nullable=True,
        ),
    )
    op.add_column(
        "schedule_rules",
        sa.Column(
            "break_minutes",
            sa.Integer(),
            server_default=sa.text("10"),
            nullable=True,
        ),
    )
    op.execute(
        """
        CREATE VIEW v_schedule_active AS
        SELECT
            sr.psychologist_id,
            sr.day_of_week,
            sr.start_time,
            sr.end_time,
            sr.slot_duration_minutes,
            sr.break_minutes,
            sr.effective_from,
            sr.effective_until
        FROM schedule_rules sr
        WHERE sr.is_active = TRUE
          AND sr.effective_from <= CURRENT_DATE
          AND (sr.effective_until IS NULL OR sr.effective_until >= CURRENT_DATE)
        """
    )

    # meeting_types
    op.drop_column("meeting_types", "buffer_minutes")
    op.drop_column("meeting_types", "description")

    # schedule_exceptions: varchar → enum (мапим новые значения на legacy,
    # чтобы каст в enum не падал), затем возвращаем unique-per-date.
    op.alter_column(
        "schedule_exceptions",
        "exception_type",
        existing_type=sa.String(length=20),
        type_=postgresql.ENUM(name="schedule_exception_type"),
        existing_nullable=False,
        postgresql_using=(
            "(CASE "
            "WHEN exception_type = 'unavailable' THEN 'reduced_hours' "
            "WHEN exception_type = 'extra_availability' THEN 'extra_hours' "
            "ELSE exception_type END)::schedule_exception_type"
        ),
    )
    op.create_unique_constraint(
        "schedule_exceptions_psychologist_id_exception_date_key",
        "schedule_exceptions",
        ["psychologist_id", "exception_date"],
    )
