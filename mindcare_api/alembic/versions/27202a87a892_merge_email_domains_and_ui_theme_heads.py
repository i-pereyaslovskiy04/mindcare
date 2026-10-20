"""merge_email_domains_and_ui_theme_heads

Revision ID: 27202a87a892
Revises: e7c1a9d4b385, c7f1a9e4d2b8
Create Date: 2026-07-16 14:59:53.253494

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '27202a87a892'
down_revision: Union[str, Sequence[str], None] = ('e7c1a9d4b385', 'c7f1a9e4d2b8')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
