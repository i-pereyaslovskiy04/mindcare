"""add_banner_slides

Добавляет таблицу banner_slides — редактируемое через админку/супервизора
содержимое переиспользуемого баннера-слайдера (Hero.jsx, общий для нескольких
страниц через placement) — и сразу переносит в неё слайды, ранее
захардкоженные в JSX: три слайда главной страницы (DEFAULT_SLIDES_BY_PLACEMENT
в Hero.jsx остаётся как fallback на случай пустой/недоступной таблицы) и один
слайд страницы /services (бывший статичный PageHero).

Revision ID: 0531e37e2f95
Revises: e6c3a9f1d574
Create Date: 2026-08-27
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = '0531e37e2f95'
down_revision = 'e6c3a9f1d574'
branch_labels = None
depends_on = None


_SEED_SLIDES = [
    {
        "label": "Психологическая служба · ДонГУ",
        "title": "Забота о вашей",
        "highlight": "душевной гармонии",
        "sub": "Профессиональная психологическая поддержка студентов и "
               "сотрудников Донецкого государственного университета.",
        "placement": "home",
        "display_order": 0,
    },
    {
        "label": "Поддержка и развитие",
        "title": "Ты не один",
        "highlight": "на своём пути",
        "sub": "Помогаем справляться с тревогой, стрессом и трудностями "
               "студенческой жизни в безопасном пространстве.",
        "placement": "home",
        "display_order": 1,
    },
    {
        "label": "Запись на консультацию",
        "title": "Сделай первый",
        "highlight": "шаг к себе",
        "sub": "Доверительная беседа с опытным психологом — конфиденциально "
               "и без осуждения.",
        "placement": "home",
        "display_order": 2,
    },
    {
        "label": "Донецкий государственный университет",
        "title": "Центр психологической помощи ДонГУ",
        "highlight": None,
        "sub": "Поддержка, развитие и психологическое благополучие студентов "
               "и сотрудников университета. Мы помогаем справляться с "
               "трудностями и находить внутренние ресурсы.",
        "placement": "services",
        "display_order": 0,
    },
]


def upgrade():
    op.create_table(
        'banner_slides',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('uuid', UUID(as_uuid=True), nullable=False, unique=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('label', sa.String(255)),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('highlight', sa.String(255)),
        sa.Column('sub', sa.Text),
        sa.Column('image_id', sa.Integer,
                  sa.ForeignKey('media_files.id', ondelete='SET NULL')),
        # Страница, на которой показывается слайд: 'home' | 'services'
        # (расширяется правкой кода — app/banner_slides/schemas.py::BannerPlacement,
        # без новой миграции схемы).
        sa.Column('placement', sa.String(50), nullable=False, server_default='home'),
        sa.Column('display_order', sa.Integer, server_default='0'),
        sa.Column('is_active', sa.Boolean, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
    )

    banner_slides = sa.table(
        'banner_slides',
        sa.column('label', sa.String),
        sa.column('title', sa.String),
        sa.column('highlight', sa.String),
        sa.column('sub', sa.Text),
        sa.column('placement', sa.String),
        sa.column('display_order', sa.Integer),
        sa.column('is_active', sa.Boolean),
    )
    op.bulk_insert(banner_slides, [
        {**s, "is_active": True} for s in _SEED_SLIDES
    ])


def downgrade():
    op.drop_table('banner_slides')
