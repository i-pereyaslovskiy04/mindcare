"""add_chat_conversations_and_messages

Chat MVP foundation (Stage 28b): one-to-one чат student ↔ psychologist
поверх therapy_engagements.

  chat_conversations — одна беседа = один engagement (UNIQUE engagement_id).
    Закрытость чата определяется через therapy_engagements.status,
    отдельного closed_at нет. Беседа не существует без engagement.

  chat_messages — сообщения. content будет хранить ТОЛЬКО Fernet
    ciphertext с префиксом enc:v1: (шифрование подключается в Stage 28c,
    plaintext fallback не предусматривается). read_at — простой MVP
    read receipt для one-to-one; deleted_at — soft delete.

FK policy: RESTRICT везде — переписка (спец. категория ПДн) не должна
каскадно уничтожаться; пользователи и так soft-deleted.

Revision ID: d8f3a6c1e9b4
Revises: b6e1f4a7c9d3
Create Date: 2026-06-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'd8f3a6c1e9b4'
down_revision = 'b6e1f4a7c9d3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'chat_conversations',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('uuid', sa.UUID(), nullable=False),
        sa.Column('engagement_id', sa.Integer(), nullable=False),
        sa.Column('last_message_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(
            ['engagement_id'], ['therapy_engagements.id'], ondelete='RESTRICT',
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('uuid'),
        sa.UniqueConstraint('engagement_id', name='ux_chat_conversations_engagement'),
    )
    op.create_index(
        'ix_chat_conversations_last_message_at',
        'chat_conversations', ['last_message_at'],
    )

    op.create_table(
        'chat_messages',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('uuid', sa.UUID(), nullable=False),
        sa.Column('conversation_id', sa.Integer(), nullable=False),
        sa.Column('sender_id', sa.Integer(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ['conversation_id'], ['chat_conversations.id'], ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['sender_id'], ['users.id'], ondelete='RESTRICT',
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('uuid'),
    )
    # Пагинация истории беседы (living messages only)
    op.create_index(
        'ix_chat_messages_conv_created',
        'chat_messages', ['conversation_id', 'created_at'],
        postgresql_where=sa.text('deleted_at IS NULL'),
    )
    op.create_index('ix_chat_messages_sender', 'chat_messages', ['sender_id'])
    # Быстрый unread count
    op.create_index(
        'ix_chat_messages_unread',
        'chat_messages', ['conversation_id'],
        postgresql_where=sa.text('read_at IS NULL AND deleted_at IS NULL'),
    )


def downgrade() -> None:
    op.drop_index('ix_chat_messages_unread', table_name='chat_messages')
    op.drop_index('ix_chat_messages_sender', table_name='chat_messages')
    op.drop_index('ix_chat_messages_conv_created', table_name='chat_messages')
    op.drop_table('chat_messages')
    op.drop_index('ix_chat_conversations_last_message_at',
                  table_name='chat_conversations')
    op.drop_table('chat_conversations')
