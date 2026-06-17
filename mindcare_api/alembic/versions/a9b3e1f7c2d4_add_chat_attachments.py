"""add_chat_attachments

Chat Attachments DB foundation (Stage 32b): metadata table for files
attached to chat messages.

  chat_attachments — хранит ТОЛЬКО метаданные файлов (содержимое файла
    в PostgreSQL не хранится; физические файлы на диске управляются
    в Stage 32c через AttachmentStorage).

  Ключевые решения схемы:

  message_id nullable:
    При двухэтапной отправке (pre-upload) файл загружается до отправки
    сообщения. В момент upload message ещё не существует → message_id = NULL.
    При создании сообщения service привязывает attachment: message_id = msg.id.
    После привязки NULL-значение не допускается бизнес-логикой (Stage 32c),
    но схема оставляет его nullable, чтобы orphan-записи были чистимы
    скриптом без конфликтов NOT NULL.

  original_filename ≠ путь к файлу:
    original_filename используется ТОЛЬКО для Content-Disposition header
    при скачивании. Путь к файлу строится из storage_key (UUID-based).
    Это архитектурная защита от path traversal.

  storage_key — UUID-based уникальный ключ:
    Пример: '2026/06/550e8400-e29b-41d4-a716-446655440000.pdf'.
    Не содержит original_filename. UNIQUE — нельзя иметь два metadata-ряда
    на одно и то же физическое место на диске.

  checksum_sha256 nullable:
    Вычисляется в Stage 32c при записи файла на диск. Nullable — чтобы
    DB-схема была полноценной до реализации upload-логики. После Stage 32c
    application-layer всегда будет заполнять это поле.

  FK policy: RESTRICT для всех внешних ключей.
    Физическое удаление chat-записей в prod заблокировано (soft delete).
    RESTRICT служит safety-net: если кто-то попробует hard-delete message
    или conversation при наличии attachments — DB откажет. Данные терапии
    (ФЗ-152) не должны каскадно уничтожаться.

  deleted_at:
    Soft delete вложения — зеркалирует паттерн chat_messages.
    При soft delete сообщения (Stage 32c service) проставляется deleted_at
    и на все его chat_attachments. Физические файлы не удаляются.

  encrypted_at_rest flag:
    False в MVP. Зарезервирован для будущего at-rest шифрования файлов.
    При добавлении шифрования Stage 32x изменит default и логику upload.

Revision ID: a9b3e1f7c2d4
Revises: f7e9c2a4b8d1
Create Date: 2026-06-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'a9b3e1f7c2d4'
down_revision = 'f7e9c2a4b8d1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'chat_attachments',

        # PK / идентификаторы
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('uuid', postgresql.UUID(as_uuid=False), nullable=False),

        # FK: беседа (всегда известна при upload)
        sa.Column('conversation_id', sa.Integer(), nullable=False),

        # FK: сообщение (NULL пока message не создан — pre-upload window)
        sa.Column('message_id', sa.BigInteger(), nullable=True),

        # FK: загрузчик файла
        sa.Column('uploader_id', sa.Integer(), nullable=False),

        # Метаданные файла
        sa.Column('original_filename', sa.String(500), nullable=False),
        sa.Column('storage_key', sa.String(1000), nullable=False),
        sa.Column('mime_type', sa.String(100), nullable=False),
        sa.Column('file_size', sa.BigInteger(), nullable=False),
        sa.Column('checksum_sha256', sa.String(64), nullable=True),

        # Storage
        sa.Column(
            'storage_backend', sa.String(50), nullable=False,
            server_default='local_private',
        ),

        # Вспомогательные флаги
        sa.Column(
            'is_image', sa.Boolean(), nullable=False,
            server_default=sa.text('false'),
        ),
        sa.Column(
            'encrypted_at_rest', sa.Boolean(), nullable=False,
            server_default=sa.text('false'),
        ),

        # Timestamps
        sa.Column(
            'created_at', sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text('now()'),
        ),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),

        # Constraints
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('uuid', name='ux_chat_attachments_uuid'),
        sa.UniqueConstraint('storage_key', name='ux_chat_attachments_storage_key'),

        # FKs — все RESTRICT (см. комментарий к миграции)
        sa.ForeignKeyConstraint(
            ['conversation_id'], ['chat_conversations.id'], ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['message_id'], ['chat_messages.id'], ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['uploader_id'], ['users.id'], ondelete='RESTRICT',
        ),
    )

    # Индексы для типичных запросов:
    #   - «все файлы беседы» (проверка прав при download, listing)
    op.create_index(
        'ix_chat_attachments_conversation',
        'chat_attachments', ['conversation_id'],
    )
    #   - «файлы сообщения» (загрузка attachments при рендере)
    op.create_index(
        'ix_chat_attachments_message',
        'chat_attachments', ['message_id'],
        postgresql_where=sa.text('message_id IS NOT NULL'),
    )
    #   - «загрузки пользователя» (история, квота)
    op.create_index(
        'ix_chat_attachments_uploader',
        'chat_attachments', ['uploader_id'],
    )
    #   - «orphan cleanup» (скрипт: message_id IS NULL AND created_at < cutoff)
    op.create_index(
        'ix_chat_attachments_created_at',
        'chat_attachments', ['created_at'],
    )


def downgrade() -> None:
    op.drop_index('ix_chat_attachments_created_at', table_name='chat_attachments')
    op.drop_index('ix_chat_attachments_uploader',   table_name='chat_attachments')
    op.drop_index('ix_chat_attachments_message',    table_name='chat_attachments')
    op.drop_index('ix_chat_attachments_conversation', table_name='chat_attachments')
    op.drop_table('chat_attachments')
