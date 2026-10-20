"""add_supervisor_engagement_index

Добавляет partial unique index на therapy_engagements(client_id):
у одного клиента не может быть более одной активной связи с психологом.

Revision ID: d2e5f8a1b4c7
Revises: b3c5e7a9f1d2
Create Date: 2026-06-08
"""
from alembic import op
import sqlalchemy as sa

revision = 'd2e5f8a1b4c7'
down_revision = 'b3c5e7a9f1d2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ux_therapy_engagements_active_client",
        "therapy_engagements",
        ["client_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active' AND ended_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ux_therapy_engagements_active_client",
        table_name="therapy_engagements",
    )
