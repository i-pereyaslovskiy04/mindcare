"""merge_diary_into_dev_heads

Revision ID: db0b2e177da5
Revises: be8d3ad39b3a, c3a7f8e2d1b9
Create Date: 2026-06-26 14:35:19.020860

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'db0b2e177da5'
down_revision: Union[str, Sequence[str], None] = ('be8d3ad39b3a', 'c3a7f8e2d1b9')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
