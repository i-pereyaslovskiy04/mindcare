"""add_test_moderation_status

Moderation workflow тестов (Этап F, ADR-016): колонка tests.status
draft/in_review/published/needs_changes. Публичная видимость студенту =
status='published' AND is_active=True.

Data-миграция сохраняет текущую видимость: is_active=true → 'published'
(остальные остаются 'draft' по server_default). Известный эффект: ранее
деактивированный опубликованный тест станет 'draft' (был скрыт — остаётся скрыт;
вернуть в published можно только admin-действием publish).

Revision ID: e1b4c8f2a6d9
Revises: d9f2a1c7b3e4
Create Date: 2026-09-01
"""
from alembic import op
import sqlalchemy as sa


revision = "e1b4c8f2a6d9"
down_revision = "d9f2a1c7b3e4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tests",
        sa.Column("status", sa.String(length=20), nullable=False,
                  server_default="draft"),
    )
    # Сохраняем текущую видимость: активные тесты считаем опубликованными.
    op.execute("UPDATE tests SET status = 'published' WHERE is_active = true")


def downgrade() -> None:
    op.drop_column("tests", "status")
