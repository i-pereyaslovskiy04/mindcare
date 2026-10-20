"""add_online_to_appointment_modality

Revision ID: 71dfb9c56b13
Revises: e1a2b3c4d5f6
Create Date: 2026-06-18 12:06:17.970432

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '71dfb9c56b13'
down_revision: Union[str, Sequence[str], None] = 'e1a2b3c4d5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # appointments.modality is VARCHAR(20) in the Alembic baseline.
    # The appointment_modality PG enum only exists in DBs bootstrapped from
    # db/sql/ (legacy path). On a clean Alembic-only DB this is a no-op.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_type
                WHERE typname = 'appointment_modality'
            ) THEN
                EXECUTE
                    'ALTER TYPE appointment_modality'
                    ' ADD VALUE IF NOT EXISTS ''online''';
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    # PostgreSQL does not support removing enum values; no-op in both paths.
    pass
