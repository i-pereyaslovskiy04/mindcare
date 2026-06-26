"""appointments: add booking_source + created_by columns

Revision ID: d3e6f9a2b5c8
Revises: b2d4f6a8c1e3
Create Date: 2026-06-19

booking_source — кто инициировал запись:
  'student_self'  — студент самостоятельно через API;
  'supervisor'    — вручную супервизором или администратором.
  NOT NULL, DEFAULT 'student_self' (обратная совместимость существующих строк).

created_by — FK на users.id: кто создал запись (студент или супервизор).
  NULL для строк, созданных до этой миграции.
  ON DELETE SET NULL.
"""

from alembic import op
import sqlalchemy as sa


revision = "d3e6f9a2b5c8"
down_revision = "b2d4f6a8c1e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "appointments",
        sa.Column(
            "booking_source",
            sa.String(30),
            nullable=False,
            server_default="student_self",
        ),
    )
    op.add_column(
        "appointments",
        sa.Column("created_by", sa.Integer, nullable=True),
    )
    op.create_foreign_key(
        "fk_appointments_created_by_users",
        "appointments",
        "users",
        ["created_by"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_appointments_created_by_users",
        "appointments",
        type_="foreignkey",
    )
    op.drop_column("appointments", "created_by")
    op.drop_column("appointments", "booking_source")
