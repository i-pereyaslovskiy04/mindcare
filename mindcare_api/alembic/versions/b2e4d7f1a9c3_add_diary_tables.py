"""add_diary_tables

Diary module DB foundation (Stage Diary Backend):
  diary_emotions — справочник эмоций (key, label, sort_order, is_active).
  diary_entries  — ежедневные записи студента; sensitive fields зашифрованы
                   application-layer Fernet (enc:v1:) на уровне service/storage.

Ключевые решения схемы:

  mood_score_enc / entry_text_enc / emotions_enc — TEXT, не INT/JSON:
    Значения хранятся исключительно в зашифрованном виде (enc:v1:).
    Plaintext никогда не попадает в БД.

  entry_text_enc nullable:
    NULL если студент не заполнил текстовое поле.

  emotions_enc NOT NULL:
    Зашифрованный JSON-массив ключей эмоций. Пустой список → encrypt("[]"),
    не NULL. Не связующая таблица: plaintext состав эмоций в БД не хранится.

  Partial UNIQUE INDEX (student_id, entry_date) WHERE deleted_at IS NULL:
    Гарантирует одну активную запись на студента в день.
    Мягкое удаление (deleted_at) не блокирует повторную запись на ту же дату
    после «удаления» в будущих этапах.

  FK RESTRICT на users.id:
    Предотвращает случайное каскадное уничтожение терапевтических данных.

Seed:
  10 начальных эмоций вставляются в upgrade(). Данные идемпотентны
  относительно возможного downgrade+upgrade (INSERT без ON CONFLICT —
  таблица создаётся заново, поэтому конфликтов нет).

Revision ID: b2e4d7f1a9c3
Revises: a9b3e1f7c2d4
Create Date: 2026-06-18
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'b2e4d7f1a9c3'
down_revision = 'a9b3e1f7c2d4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── diary_emotions ─────────────────────────────────────────────────────────
    op.create_table(
        'diary_emotions',
        sa.Column('id',          sa.BigInteger(),               autoincrement=True, nullable=False),
        sa.Column('key',         sa.String(50),                 nullable=False),
        sa.Column('label',       sa.String(100),                nullable=False),
        sa.Column('description', sa.Text(),                     nullable=True),
        sa.Column('sort_order',  sa.Integer(),                  nullable=False),
        sa.Column('is_active',   sa.Boolean(),                  nullable=False, server_default=sa.text('true')),
        sa.Column('created_at',  sa.DateTime(timezone=True),    nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at',  sa.DateTime(timezone=True),    nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key', name='ux_diary_emotions_key'),
    )
    op.create_index('ix_diary_emotions_sort_order', 'diary_emotions', ['sort_order'])

    # ── diary_entries ──────────────────────────────────────────────────────────
    op.create_table(
        'diary_entries',
        sa.Column('id',             sa.BigInteger(),             autoincrement=True, nullable=False),
        sa.Column('uuid',           postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('student_id',     sa.Integer(),                nullable=False),
        sa.Column('entry_date',     sa.Date(),                   nullable=False),
        sa.Column('mood_score_enc', sa.Text(),                   nullable=False),
        sa.Column('entry_text_enc', sa.Text(),                   nullable=True),
        sa.Column('emotions_enc',   sa.Text(),                   nullable=False),
        sa.Column('created_at',     sa.DateTime(timezone=True),  nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at',     sa.DateTime(timezone=True),  nullable=False, server_default=sa.text('now()')),
        sa.Column('deleted_at',     sa.DateTime(timezone=True),  nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('uuid', name='ux_diary_entries_uuid'),
        sa.ForeignKeyConstraint(['student_id'], ['users.id'], ondelete='RESTRICT'),
    )
    op.create_index('ix_diary_entries_student_id', 'diary_entries', ['student_id'])
    op.create_index('ix_diary_entries_entry_date',  'diary_entries', ['entry_date'])
    # Partial unique: одна активная запись на студента в день
    op.create_index(
        'ux_diary_entries_student_date_active',
        'diary_entries',
        ['student_id', 'entry_date'],
        unique=True,
        postgresql_where=sa.text('deleted_at IS NULL'),
    )

    # ── Seed: стартовые эмоции ─────────────────────────────────────────────────
    op.execute("""
        INSERT INTO diary_emotions (key, label, sort_order, is_active) VALUES
        ('calm',      'спокойно',         1,  true),
        ('joyful',    'радостно',         2,  true),
        ('anxious',   'тревожно',         3,  true),
        ('sad',       'грустно',          4,  true),
        ('tired',     'устало',           5,  true),
        ('angry',     'злобно',           6,  true),
        ('inspired',  'вдохновлённо',     7,  true),
        ('confused',  'растерянно',       8,  true),
        ('light',     'легко',            9,  true),
        ('focused',   'сосредоточенно',  10,  true)
    """)


def downgrade() -> None:
    op.drop_index('ux_diary_entries_student_date_active', table_name='diary_entries')
    op.drop_index('ix_diary_entries_entry_date',          table_name='diary_entries')
    op.drop_index('ix_diary_entries_student_id',          table_name='diary_entries')
    op.drop_table('diary_entries')
    op.drop_index('ix_diary_emotions_sort_order', table_name='diary_emotions')
    op.drop_table('diary_emotions')
