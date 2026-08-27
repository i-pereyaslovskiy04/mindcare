"""add_banner_slide_link

Добавляет banner_slides.link_url — опциональный CTA-переход слайда
(рендерится в Hero.jsx кнопкой «Подробнее», когда задан).

Revision ID: 72bfade01121
Revises: 0531e37e2f95
Create Date: 2026-08-27
"""
from alembic import op
import sqlalchemy as sa

revision = '72bfade01121'
down_revision = '0531e37e2f95'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('banner_slides', sa.Column('link_url', sa.String(2048)))


def downgrade():
    op.drop_column('banner_slides', 'link_url')
