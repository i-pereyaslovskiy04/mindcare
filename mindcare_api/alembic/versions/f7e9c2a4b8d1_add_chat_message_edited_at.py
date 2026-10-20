"""add_chat_message_edited_at

Редактирование своих сообщений Messenger (Stage 31x-fix).

  chat_messages:
    + edited_at — TIMESTAMPTZ NULL; NULL означает «сообщение не редактировалось».
                  Проставляется при PATCH сообщения участником беседы.

Без backfill: существующие строки получают NULL (корректно).
content по-прежнему хранит ТОЛЬКО enc:v1: (шифрование — app/core/encryption.py);
правка перезаписывает ciphertext, история старых версий в этом stage не ведётся.

Revision ID: f7e9c2a4b8d1
Revises: c4f7a2e9d1b8
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa

revision = 'f7e9c2a4b8d1'
down_revision = 'c4f7a2e9d1b8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'chat_messages',
        sa.Column('edited_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('chat_messages', 'edited_at')
