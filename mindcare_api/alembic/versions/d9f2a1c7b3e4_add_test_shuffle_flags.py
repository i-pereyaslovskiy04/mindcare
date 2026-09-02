"""add_test_shuffle_flags

Случайный порядок вопросов/вариантов при прохождении теста. Флаги на уровне
теста (у `tests` нет JSONB-config). Перемешивание презентационное — submit и
scoring адресуют по question_id/option_id, а не по порядку.

Revision ID: d9f2a1c7b3e4
Revises: 27b44fcf4865
Create Date: 2026-08-30
"""
from alembic import op
import sqlalchemy as sa


revision = "d9f2a1c7b3e4"
down_revision = "27b44fcf4865"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tests",
        sa.Column("shuffle_questions", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
    )
    op.add_column(
        "tests",
        sa.Column("shuffle_options", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("tests", "shuffle_options")
    op.drop_column("tests", "shuffle_questions")
