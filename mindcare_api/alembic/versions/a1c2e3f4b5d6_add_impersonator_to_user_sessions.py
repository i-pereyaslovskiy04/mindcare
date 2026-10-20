"""add_impersonator_to_user_sessions

Impersonation (ADR-025): admin может создать сессию от имени другого
пользователя («Зайти под именем»). Колонка user_sessions.impersonator_user_id
помечает такую сессию — это server-side отметка, что за токеном стоит admin,
а не сам целевой пользователь.

Назначение — атрибуция и compliance (ФЗ-152): impersonation-сессия иначе
byte-for-byte неотличима от обычного логина. FK ON DELETE SET NULL: удаление
администратора не должно каскадно рвать активные сессии; отметка просто
теряется (сама сессия остаётся под целевым user_id).

Revision ID: a1c2e3f4b5d6
Revises: e1b4c8f2a6d9
Create Date: 2026-09-01
"""
from alembic import op
import sqlalchemy as sa


revision = "a1c2e3f4b5d6"
down_revision = "e1b4c8f2a6d9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_sessions",
        sa.Column("impersonator_user_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_user_sessions_impersonator_user_id_users",
        "user_sessions",
        "users",
        ["impersonator_user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_user_sessions_impersonator_user_id_users",
        "user_sessions",
        type_="foreignkey",
    )
    op.drop_column("user_sessions", "impersonator_user_id")
