"""add_service_cards

Добавляет таблицу service_cards — редактируемые через админку/супервизора
карточки услуг страницы /services (ServicesSlider.jsx/ServiceCard.jsx) — и
сразу переносит в неё 5 карточек, ранее захардкоженных в JSX (константа
SERVICES). DEFAULT_SERVICE_CARDS в ServicesSlider.jsx остаётся как fallback
на случай пустой/недоступной таблицы — по тому же принципу, что
DEFAULT_SLIDES_BY_PLACEMENT в Hero.jsx после миграции 0531e37e2f95.

В отличие от banner_slides, здесь нет placement (единственная страница-
получатель) и есть benefits — JSONB-список строк-пунктов.

Revision ID: d14143842079
Revises: 72bfade01121
Create Date: 2026-08-28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = 'd14143842079'
down_revision = '72bfade01121'
branch_labels = None
depends_on = None


_SEED_CARDS = [
    {
        "title": "Психологическое консультирование",
        "description": "Индивидуальная работа с психологом — онлайн или офлайн. "
                        "Помогаем разобраться в трудностях, снять тревогу и найти "
                        "эффективный выход из сложных ситуаций.",
        "benefits": [
            "Разобраться в своей ситуации",
            "Выявить причины проблемы",
            "Найти конкретные пути выхода",
            "Восстановить психологический комфорт",
        ],
        "display_order": 0,
    },
    {
        "title": "Психодиагностика",
        "description": "Комплексная оценка психологического состояния на современном "
                        "оборудовании с сертифицированными методиками и подробным "
                        "разбором результатов с психологом.",
        "benefits": [
            "Оценка памяти, внимания и мышления",
            "Уровень интеллектуального развития",
            "Эмоционально-волевые качества",
            "Личностные черты и мотивация",
        ],
        "display_order": 1,
    },
    {
        "title": "Социально-психологические тренинги",
        "description": "Групповые занятия в безопасной обстановке — для тех, кто "
                        "хочет лучше понимать себя и других, развить навыки общения "
                        "и управления эмоциями.",
        "benefits": [
            "Лучше понимать других людей",
            "Узнать себя глубже",
            "Управлять эмоциями и реакциями",
            "Приобрести новые навыки общения",
        ],
        "display_order": 2,
    },
    {
        "title": "Профориентация",
        "description": "Помогаем выявить сильные стороны и склонности, выбрать "
                        "профессиональный путь и построить карьерный план — для "
                        "студентов, абитуриентов и сотрудников.",
        "benefits": [
            "Диагностика профессиональных склонностей",
            "Анализ ваших сильных сторон",
            "Построение карьерного плана",
            "Знакомство с профессиограммами",
        ],
        "display_order": 3,
    },
    {
        "title": "Супервизия и обучение",
        "description": "Постоянное развитие специалистов под руководством опытных "
                        "наставников — чтобы каждый клиент получал помощь самого "
                        "высокого профессионального уровня.",
        "benefits": [
            "Супервизия у опытных психологов",
            "Курсы повышения квалификации",
            "Участие в профессиональных конференциях",
            "Освоение современных методик",
        ],
        "display_order": 4,
    },
]


def upgrade():
    op.create_table(
        'service_cards',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('uuid', UUID(as_uuid=True), nullable=False, unique=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text, nullable=False),
        sa.Column('benefits', JSONB, nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column('image_id', sa.Integer,
                  sa.ForeignKey('media_files.id', ondelete='SET NULL')),
        sa.Column('link_url', sa.String(2048)),
        sa.Column('display_order', sa.Integer, server_default='0'),
        sa.Column('is_active', sa.Boolean, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
    )

    service_cards = sa.table(
        'service_cards',
        sa.column('title', sa.String),
        sa.column('description', sa.Text),
        sa.column('benefits', JSONB),
        sa.column('display_order', sa.Integer),
        sa.column('is_active', sa.Boolean),
    )
    op.bulk_insert(service_cards, [
        {**c, "is_active": True} for c in _SEED_CARDS
    ])


def downgrade():
    op.drop_table('service_cards')
