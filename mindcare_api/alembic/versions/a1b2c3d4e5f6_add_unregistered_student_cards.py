"""add_unregistered_student_cards

Карточка незарегистрированного студента (walk-in) + связь с appointments.

Changes:
  NEW TABLE unregistered_student_cards
    - uuid UNIQUE; FK created_by/linked_user_id -> users (ON DELETE SET NULL)
    - indexes: normalized_email, archived_at, created_by
  ALTER TABLE appointments:
    ALTER COLUMN client_id  DROP NOT NULL (nullable=True)
    + unregistered_student_card_id  FK -> unregistered_student_cards (RESTRICT, nullable)
    + CHECK chk_appointment_subject_exactly_one:
        num_nonnulls(client_id, unregistered_student_card_id) = 1
      (ровно одна ссылка на субъекта; существующие строки имеют client_id → валидны)

Notes:
  - CHECK добавляется последним, когда существующие строки уже удовлетворяют ему.
  - RESTRICT на FK appointments.unregistered_student_card_id: карточки
    soft-архивируются, а не удаляются — не даём осиротить appointment.
  - downgrade восстанавливает NOT NULL на appointments.client_id; упадёт, если в БД
    есть card-appointments (client_id IS NULL) — ожидаемо, такие строки нужно
    обработать до отката.

Revision ID: a1b2c3d4e5f6
Revises: f1a4c7e0b9d2
Create Date: 2026-06-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "f1a4c7e0b9d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── unregistered_student_cards ────────────────────────────────────
    op.create_table(
        "unregistered_student_cards",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("normalized_email", sa.String(length=255), nullable=True),
        sa.Column("birth_date", sa.Date(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("primary_concern", sa.Text(), nullable=True),
        sa.Column(
            "personal_data_consent",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column(
            "consent_obtained_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "consent_source",
            sa.String(length=30),
            nullable=True,
            server_default="in_person",
        ),
        sa.Column("linked_user_id", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
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
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["linked_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index(
        "ix_unreg_cards_normalized_email",
        "unregistered_student_cards",
        ["normalized_email"],
    )
    op.create_index(
        "ix_unreg_cards_archived_at",
        "unregistered_student_cards",
        ["archived_at"],
    )
    op.create_index(
        "ix_unreg_cards_created_by",
        "unregistered_student_cards",
        ["created_by"],
    )

    # ── appointments: subject can be a card instead of a registered user ──
    op.alter_column(
        "appointments",
        "client_id",
        existing_type=sa.Integer(),
        nullable=True,
    )
    op.add_column(
        "appointments",
        sa.Column(
            "unregistered_student_card_id", sa.Integer(), nullable=True
        ),
    )
    op.create_foreign_key(
        "fk_appointments_unregistered_student_card_id",
        "appointments",
        "unregistered_student_cards",
        ["unregistered_student_card_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "chk_appointment_subject_exactly_one",
        "appointments",
        "num_nonnulls(client_id, unregistered_student_card_id) = 1",
    )


def downgrade() -> None:
    op.drop_constraint(
        "chk_appointment_subject_exactly_one",
        "appointments",
        type_="check",
    )
    op.drop_constraint(
        "fk_appointments_unregistered_student_card_id",
        "appointments",
        type_="foreignkey",
    )
    op.drop_column("appointments", "unregistered_student_card_id")
    # Restore NOT NULL — fails if any client_id IS NULL (card-appointments).
    op.alter_column(
        "appointments",
        "client_id",
        existing_type=sa.Integer(),
        nullable=False,
    )

    op.drop_index(
        "ix_unreg_cards_created_by",
        table_name="unregistered_student_cards",
    )
    op.drop_index(
        "ix_unreg_cards_archived_at",
        table_name="unregistered_student_cards",
    )
    op.drop_index(
        "ix_unreg_cards_normalized_email",
        table_name="unregistered_student_cards",
    )
    op.drop_table("unregistered_student_cards")
