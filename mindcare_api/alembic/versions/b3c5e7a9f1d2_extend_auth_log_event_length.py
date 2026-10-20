"""extend_auth_log_event_length

auth_log.event VARCHAR(50) слишком мал для admin-событий с UUID.
Например: 'admin_create_tag:xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx' = 53 символа.
Расширяем до VARCHAR(150) с запасом.

Revision ID: b3c5e7a9f1d2
Revises: a8c3f1d9e2b5
Create Date: 2026-05-28
"""
import sqlalchemy as sa
from alembic import op

revision = 'b3c5e7a9f1d2'
down_revision = 'a8c3f1d9e2b5'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        'auth_log',
        'event',
        existing_type=sa.String(50),
        type_=sa.String(150),
        existing_nullable=False,
    )


def downgrade():
    op.alter_column(
        'auth_log',
        'event',
        existing_type=sa.String(150),
        type_=sa.String(50),
        existing_nullable=False,
    )
