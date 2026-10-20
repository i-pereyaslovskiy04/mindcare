"""add_user_legal_basis_records

Добавляет таблицу user_legal_basis_records — фиксация документированного
основания организации для создания учётной записи и обработки персональных
данных пользователя (admin-created psychologist/supervisor/admin, bootstrap).

Не путать с consent_records: consent — личное согласие субъекта (студента),
legal basis — основание организации (трудовое/служебное/договорное/приказ).

FK policy:
  user_id              → CASCADE  (запись живёт и умирает с пользователем,
                                   физического удаления users нет — soft delete)
  confirmed_by_user_id → SET NULL (запись не теряется при удалении актора)

Revision ID: b6e1f4a7c9d3
Revises: e5a8f3c1d2b6
Create Date: 2026-06-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'b6e1f4a7c9d3'
down_revision = 'e5a8f3c1d2b6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'user_legal_basis_records',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('basis_type', sa.String(length=50), nullable=False),
        sa.Column('basis_source', sa.String(length=50), nullable=False),
        sa.Column('basis_reference', sa.String(length=255), nullable=True),
        sa.Column('confirmed_by_user_id', sa.Integer(), nullable=True),
        sa.Column('confirmed_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('ip_address', postgresql.INET(), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['confirmed_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_user_legal_basis_records_user_id',
        'user_legal_basis_records', ['user_id'],
    )
    op.create_index(
        'ix_user_legal_basis_records_confirmed_by_user_id',
        'user_legal_basis_records', ['confirmed_by_user_id'],
    )
    op.create_index(
        'ix_user_legal_basis_records_basis_type',
        'user_legal_basis_records', ['basis_type'],
    )


def downgrade() -> None:
    op.drop_index('ix_user_legal_basis_records_basis_type',
                  table_name='user_legal_basis_records')
    op.drop_index('ix_user_legal_basis_records_confirmed_by_user_id',
                  table_name='user_legal_basis_records')
    op.drop_index('ix_user_legal_basis_records_user_id',
                  table_name='user_legal_basis_records')
    op.drop_table('user_legal_basis_records')
