"""add_test_interpretations

Психодиагностика, Этап A: таблица порогов интерпретации результатов тестов.

  test_interpretations — диапазон балла → метка + рекомендация.

  Ключевые решения схемы:

  scale_name nullable:
    NULL  → интерпретация по итоговому total_score теста (одношкальные тесты).
    '...' → интерпретация по баллу конкретной шкалы
            (соответствует test_result_scales.scale_name) для многошкальных
            методик (HADS, MMPI, BDI и т.п.).

  min_score / max_score:
    Включительный диапазон [min_score, max_score]. Непересечение диапазонов
    в рамках одного (test_id, scale_name) гарантируется service-слоем,
    не constraint-ом (диапазоны произвольные, проверка прикладная).

  FK test_id ON DELETE CASCADE:
    Пороги — неотъемлемая часть конфигурации теста. При (soft) удалении
    теста через приложение пороги остаются; CASCADE срабатывает только
    при реальном hard-delete строки tests (зеркалит questions/options).

Revision ID: c1d4e7a2f9b3
Revises: a9b3e1f7c2d4
Create Date: 2026-06-20
"""
from alembic import op
import sqlalchemy as sa

revision = 'c1d4e7a2f9b3'
down_revision = 'a9b3e1f7c2d4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'test_interpretations',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('test_id', sa.Integer(), nullable=False),
        sa.Column('scale_name', sa.String(length=100), nullable=True),
        sa.Column('min_score', sa.Integer(), nullable=False),
        sa.Column('max_score', sa.Integer(), nullable=False),
        sa.Column('label', sa.String(length=255), nullable=False),
        sa.Column('recommendation', sa.Text(), nullable=True),
        sa.Column(
            'created_at', sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text('now()'),
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(
            ['test_id'], ['tests.id'], ondelete='CASCADE',
        ),
    )
    # «Все пороги теста / шкалы» — основной запрос при подсчёте результата.
    op.create_index(
        'ix_test_interpretations_test',
        'test_interpretations', ['test_id', 'scale_name'],
    )


def downgrade() -> None:
    op.drop_index('ix_test_interpretations_test', table_name='test_interpretations')
    op.drop_table('test_interpretations')
