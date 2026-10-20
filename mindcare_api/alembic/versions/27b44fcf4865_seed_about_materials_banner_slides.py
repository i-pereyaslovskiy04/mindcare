"""seed_about_materials_banner_slides

Переносит в banner_slides статичные баннеры ещё двух страниц — /about и
/materials, — которые до сих пор рендерились компонентом PageHero с текстом,
захардкоженным прямо в JSX (About.jsx, MaterialsPage.jsx). После миграции обе
страницы используют тот же Hero с placement='about' / 'materials', то есть их
баннер редактируется через админку наравне с главной и услугами.

Схему таблицы миграция НЕ меняет: placement — обычная строка, допустимые
значения задаёт app/banner_slides/schemas.py::BannerPlacement. Это чистый
data-перенос, как bulk_insert в 0531e37e2f95.

Заголовок /about был двухстрочным через жёсткий <br /> («Ресурсный центр» /
«практической психологии»); вторая строка кладётся в highlight — поле ровно
для такой структуры (как «Забота о вашей» / «душевной гармонии» на главной).
В Hero highlight рендерится курсивом акцентным цветом, поэтому вторая строка
станет акцентной — осознанное изменение вида, согласовано.

Revision ID: 27b44fcf4865
Revises: d14143842079
Create Date: 2026-08-28
"""
from alembic import op
import sqlalchemy as sa

revision = '27b44fcf4865'
down_revision = 'd14143842079'
branch_labels = None
depends_on = None


_SEED_SLIDES = [
    {
        "label": "Донецкий государственный университет",
        "title": "Ресурсный центр",
        "highlight": "практической психологии",
        "sub": "Психологическая помощь и поддержка студентов, преподавателей "
               "и сотрудников ДонГУ",
        "placement": "about",
        "display_order": 0,
    },
    {
        "label": "Ресурсный центр практической психологии",
        "title": "Материалы",
        "highlight": None,
        "sub": "Статьи, вебинары и упражнения для поддержки психологического "
               "здоровья",
        "placement": "materials",
        "display_order": 0,
    },
]

_PLACEMENTS = tuple(s["placement"] for s in _SEED_SLIDES)


def upgrade():
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
    # Удаляются только строки этих двух placement. Слайды home/services
    # (0531e37e2f95) и то, что админ мог добавить для about/materials уже
    # после миграции, downgrade не различает — поэтому чистится по placement,
    # а не по «первым двум id».
    op.execute(
        sa.text("DELETE FROM banner_slides WHERE placement IN :placements")
        .bindparams(sa.bindparam("placements", _PLACEMENTS, expanding=True))
    )
