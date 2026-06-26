"""merge_appointments_and_psychodiagnostics_heads

Revision ID: be8d3ad39b3a
Revises: b7c8d9e0f1a2, c1d4e7a2f9b3
Create Date: 2026-06-26 14:06:25.357802

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'be8d3ad39b3a'
down_revision: Union[str, Sequence[str], None] = ('b7c8d9e0f1a2', 'c1d4e7a2f9b3')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
