"""add_allowed_email_domains

Добавляет таблицу allowed_email_domains — организационный allowlist почтовых
доменов, с которых разрешено создавать новые учётные записи (self-registration,
admin-created staff, supervisor-created student).

Отсутствие домена в активном allowlist = запрет создания аккаунта на этом домене
(отдельного denylist нет). Политика применяется только при создании новых
аккаунтов и не влияет на login/password reset существующих пользователей.

`domain` хранится нормализованным (lower/trim, без trailing dot); уникальность
нормализованного домена гарантируется на уровне БД (ux_allowed_email_domains_domain).
Отключение — через is_active=False (физического DELETE нет).

Seed: начальный allowlist (11 доменов) вставляется в upgrade(). INSERT без
ON CONFLICT — таблица создаётся тем же upgrade, конфликтов нет (downgrade дропает
таблицу целиком).

Revision ID: c7f1a9e4d2b8
Revises: db0b2e177da5
Create Date: 2026-07-15
"""
from alembic import op
import sqlalchemy as sa

revision = 'c7f1a9e4d2b8'
down_revision = 'db0b2e177da5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'allowed_email_domains',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('domain', sa.String(length=255), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False,
                  server_default=sa.text('true')),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'],
                                ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('domain', name='ux_allowed_email_domains_domain'),
    )
    op.create_index(
        'ix_allowed_email_domains_is_active',
        'allowed_email_domains', ['is_active'],
    )

    # ── Seed: начальный allowlist (нормализованные, lower) ──────────────────────
    op.execute("""
        INSERT INTO allowed_email_domains (domain, is_active) VALUES
        ('donnu.ru',   true),
        ('yandex.ru',  true),
        ('ya.ru',      true),
        ('mail.ru',    true),
        ('inbox.ru',   true),
        ('list.ru',    true),
        ('bk.ru',      true),
        ('vk.com',     true),
        ('rambler.ru', true),
        ('lenta.ru',   true),
        ('ro.ru',      true)
    """)


def downgrade() -> None:
    op.drop_index(
        'ix_allowed_email_domains_is_active',
        table_name='allowed_email_domains',
    )
    op.drop_table('allowed_email_domains')
