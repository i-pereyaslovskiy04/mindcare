"""add_user_ui_theme_prefs

Оформление UI в профиле пользователя: users.ui_theme_palette / ui_theme_mode.
NULL = «не задано» (действует выбор устройства из localStorage).
Только ADD COLUMN — обратимо, данные не трогаются.

Revision ID: e7c1a9d4b385
Revises: db0b2e177da5
Create Date: 2026-07-12
"""
from alembic import op
import sqlalchemy as sa

revision = "e7c1a9d4b385"
down_revision = "db0b2e177da5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("ui_theme_palette", sa.String(length=20), nullable=True))
    op.add_column("users", sa.Column("ui_theme_mode", sa.String(length=10), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "ui_theme_mode")
    op.drop_column("users", "ui_theme_palette")
