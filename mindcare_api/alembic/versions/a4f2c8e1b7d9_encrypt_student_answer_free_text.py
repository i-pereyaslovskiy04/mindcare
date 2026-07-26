"""encrypt_student_answer_free_text

Свободный текстовый ответ студента в психодиагностике — такой же свободный
терапевтический текст, как session_notes.content и chat_messages.content,
и должен храниться зашифрованным (Fernet, префикс enc:v1:).

Открытая колонка student_answers.free_text_answer заменяется на
free_text_answer_enc. Backfill не требуется и не выполняется: на момент
миграции free_text-вопросов не создавалось, ни одного непустого значения
в колонке нет (проверено запросом перед написанием миграции). Именно поэтому
старая колонка удаляется, а не остаётся рядом: пустая plaintext-колонка —
готовая ловушка для будущего кода.

Revision ID: a4f2c8e1b7d9
Revises: e7c1a9d4b385
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a4f2c8e1b7d9"
down_revision: Union[str, None] = "e7c1a9d4b385"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "student_answers",
        sa.Column("free_text_answer_enc", sa.Text(), nullable=True),
    )
    op.drop_column("student_answers", "free_text_answer")


def downgrade() -> None:
    # Обратный переход возвращает открытую колонку пустой: расшифровка в
    # миграции невозможна (ключ живёт в приложении), а писать сюда plaintext
    # из зашифрованных данных мы намеренно не будем.
    op.add_column(
        "student_answers",
        sa.Column("free_text_answer", sa.Text(), nullable=True),
    )
    op.drop_column("student_answers", "free_text_answer_enc")
