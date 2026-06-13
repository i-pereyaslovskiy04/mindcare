"""add_system_conversation_support

System Conversation backend foundation (Stage 29b): read-only системные
сообщения внутри существующей chat-инфраструктуры.

  chat_conversations:
    + type           — 'engagement' (1:1 student↔psychologist) | 'system'
    + recipient_id    — получатель system-беседы (NULL для engagement)
    engagement_id     становится nullable (у system-беседы его нет)
    CHECK: engagement ⟹ engagement_id NOT NULL AND recipient_id NULL;
           system     ⟹ engagement_id NULL AND recipient_id NOT NULL
    partial UNIQUE(recipient_id) WHERE type='system' — одна system-беседа
    на пользователя.

  chat_messages:
    sender_id становится nullable (у system-сообщения отправителя нет)
    + message_kind   — 'user' | 'system'
    + event_key       — идемпотентность publish (partial unique с conversation_id)
    CHECK: user ⟹ sender_id NOT NULL; system ⟹ sender_id NULL

Существующие строки остаются валидными: type='engagement', message_kind='user'
проставляются DEFAULT, recipient_id/event_key = NULL.

content по-прежнему хранит ТОЛЬКО enc:v1: (шифрование — app/core/encryption.py).

Revision ID: c4f7a2e9d1b8
Revises: d8f3a6c1e9b4
Create Date: 2026-06-13
"""
from alembic import op
import sqlalchemy as sa

revision = 'c4f7a2e9d1b8'
down_revision = 'd8f3a6c1e9b4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── chat_conversations ──────────────────────────────────────────────────
    op.add_column(
        'chat_conversations',
        sa.Column('type', sa.String(length=20), server_default='engagement',
                  nullable=False),
    )
    op.add_column(
        'chat_conversations',
        sa.Column('recipient_id', sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        'fk_chat_conversations_recipient', 'chat_conversations', 'users',
        ['recipient_id'], ['id'], ondelete='RESTRICT',
    )
    op.alter_column('chat_conversations', 'engagement_id', nullable=True)

    op.create_check_constraint(
        'ck_chat_conversations_type',
        'chat_conversations',
        "(type = 'engagement' AND engagement_id IS NOT NULL AND recipient_id IS NULL)"
        " OR "
        "(type = 'system' AND engagement_id IS NULL AND recipient_id IS NOT NULL)",
    )
    op.create_index(
        'ux_chat_conversations_system_recipient',
        'chat_conversations', ['recipient_id'],
        unique=True,
        postgresql_where=sa.text("type = 'system'"),
    )

    # ── chat_messages ───────────────────────────────────────────────────────
    op.add_column(
        'chat_messages',
        sa.Column('message_kind', sa.String(length=20), server_default='user',
                  nullable=False),
    )
    op.add_column(
        'chat_messages',
        sa.Column('event_key', sa.String(), nullable=True),
    )
    op.alter_column('chat_messages', 'sender_id', nullable=True)

    op.create_check_constraint(
        'ck_chat_messages_kind_sender',
        'chat_messages',
        "(message_kind = 'user' AND sender_id IS NOT NULL)"
        " OR "
        "(message_kind = 'system' AND sender_id IS NULL)",
    )
    op.create_index(
        'ux_chat_messages_event_key',
        'chat_messages', ['conversation_id', 'event_key'],
        unique=True,
        postgresql_where=sa.text('event_key IS NOT NULL'),
    )


def downgrade() -> None:
    # System-данные — собственность этой фичи; удаляем их, чтобы безопасно
    # восстановить NOT NULL на sender_id / engagement_id. Engagement-переписка
    # (type='engagement') не затрагивается.
    op.execute(
        "DELETE FROM chat_messages WHERE conversation_id IN "
        "(SELECT id FROM chat_conversations WHERE type = 'system')"
    )
    op.execute("DELETE FROM chat_conversations WHERE type = 'system'")

    op.drop_index('ux_chat_messages_event_key', table_name='chat_messages')
    op.drop_constraint('ck_chat_messages_kind_sender', 'chat_messages',
                       type_='check')
    op.alter_column('chat_messages', 'sender_id', nullable=False)
    op.drop_column('chat_messages', 'event_key')
    op.drop_column('chat_messages', 'message_kind')

    op.drop_index('ux_chat_conversations_system_recipient',
                  table_name='chat_conversations')
    op.drop_constraint('ck_chat_conversations_type', 'chat_conversations',
                       type_='check')
    op.alter_column('chat_conversations', 'engagement_id', nullable=False)
    op.drop_constraint('fk_chat_conversations_recipient', 'chat_conversations',
                       type_='foreignkey')
    op.drop_column('chat_conversations', 'recipient_id')
    op.drop_column('chat_conversations', 'type')
