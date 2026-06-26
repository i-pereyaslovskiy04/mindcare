"""index unregistered_student_cards.linked_user_id

Этап 2 (привязка карточки к аккаунту): индекс под фильтр по linked_user_id.

Используется в /api/appointments/my (выборка appointments по карточкам,
привязанным к текущему пользователю) и при отмене/подтверждении linked card
appointment. FK на linked_user_id уже существует (миграция a1b2c3d4e5f6), но
Postgres не создаёт индекс для FK-колонки автоматически.

normalized_email уже проиндексирован в a1b2c3d4e5f6 (ix_unreg_cards_normalized_email)
— повторно не добавляем.

Revision ID: b7c8d9e0f1a2
Revises: a1b2c3d4e5f6
Create Date: 2026-06-20
"""

from typing import Sequence, Union

from alembic import op

revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_unreg_cards_linked_user_id",
        "unregistered_student_cards",
        ["linked_user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_unreg_cards_linked_user_id",
        table_name="unregistered_student_cards",
    )
