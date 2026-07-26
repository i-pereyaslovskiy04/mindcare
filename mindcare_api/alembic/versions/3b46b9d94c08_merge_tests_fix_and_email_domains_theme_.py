"""merge_tests_fix_and_email_domains_theme_heads

После merge mindcare_alex в dev (email-domains + ui-theme-prefs, уже объединённые
в 27202a87a892) и параллельной работы над психодиагностикой в dev (a4f2c8e1b7d9,
построена поверх e7c1a9d4b385) Alembic снова имел два head с общим предком
e7c1a9d4b385:
- a4f2c8e1b7d9 (encrypt_student_answer_free_text, ветка tests-fix);
- 27202a87a892 (merge email-domains + ui-theme-prefs, ветка mindcare_alex).

Пустая merge-ревизия (upgrade/downgrade = pass) по образцу be8d3ad39b3a,
db0b2e177da5 и 27202a87a892; операций над схемой не содержит.

Revision ID: 3b46b9d94c08
Revises: a4f2c8e1b7d9, 27202a87a892
Create Date: 2026-07-26 21:05:10.278691

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3b46b9d94c08'
down_revision: Union[str, Sequence[str], None] = ('a4f2c8e1b7d9', '27202a87a892')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
