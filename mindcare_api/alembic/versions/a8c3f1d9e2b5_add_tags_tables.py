"""add_tags_tables

Добавляет таблицы тегов и связей тегов с контентом.

Revision ID: a8c3f1d9e2b5
Revises: e9a3d7f2b5c0
Create Date: 2026-05-28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = 'a8c3f1d9e2b5'
down_revision = 'e9a3d7f2b5c0'
branch_labels = None
depends_on = None


def upgrade():
    # Сами теги: uuid для внешнего API, name с уникальностью без учёта регистра
    op.create_table(
        'tags',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('uuid', UUID(as_uuid=True), nullable=False, unique=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
    )
    # Функциональный уникальный индекс: lower(name) — нельзя создать "Тревога" и "тревога"
    op.create_index('tags_name_lower_unique', 'tags', [sa.text('lower(name)')], unique=True)

    # M:N связи — при удалении тега или контента связи удаляются каскадно
    op.create_table(
        'article_tags',
        sa.Column('article_id', sa.Integer,
                  sa.ForeignKey('articles.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('tag_id', sa.Integer,
                  sa.ForeignKey('tags.id', ondelete='CASCADE'), primary_key=True),
    )

    op.create_table(
        'news_tags',
        sa.Column('news_id', sa.Integer,
                  sa.ForeignKey('news.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('tag_id', sa.Integer,
                  sa.ForeignKey('tags.id', ondelete='CASCADE'), primary_key=True),
    )

    op.create_table(
        'test_tags',
        sa.Column('test_id', sa.Integer,
                  sa.ForeignKey('tests.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('tag_id', sa.Integer,
                  sa.ForeignKey('tags.id', ondelete='CASCADE'), primary_key=True),
    )


def downgrade():
    op.drop_table('test_tags')
    op.drop_table('news_tags')
    op.drop_table('article_tags')
    op.drop_index('tags_name_lower_unique', table_name='tags')
    op.drop_table('tags')
