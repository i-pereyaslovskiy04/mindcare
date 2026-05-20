"""otp_code_varchar64

Расширяет otp_verifications.code с VARCHAR(6) до VARCHAR(64).

Причина: OTP-коды теперь хранятся в виде SHA-256 хеша (hex, 64 символа),
а не plaintext (6 символов). Это защищает от утечки действующих кодов
при компрометации БД.

Безопасность SHA-256 для OTP:
  - TTL = 10 минут → атакующий имеет ограниченное время
  - MAX_ATTEMPTS = 5 → brute force через API заблокирован
  - 1_000_000 вариантов (000000–999999) → Rainbow table возможен,
    но бесполезен при коротком TTL + attempt limit

Revision ID: c5d8a1b4e7f2
Revises: 3a7c5e2b8f1d
Create Date: 2026-05-20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c5d8a1b4e7f2"
down_revision: Union[str, Sequence[str], None] = "3a7c5e2b8f1d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Extend code column from VARCHAR(6) to VARCHAR(64) for SHA-256 hash."""
    # Existing rows: if any OTP records exist during migration, they have
    # plaintext 6-digit codes. These are short-lived (10 min TTL) and
    # will expire naturally. Extending VARCHAR is non-destructive.
    op.alter_column(
        "otp_verifications",
        "code",
        existing_type=sa.String(length=6),
        type_=sa.String(length=64),
        existing_nullable=False,
    )


def downgrade() -> None:
    """Shrink code column back to VARCHAR(6). Warning: truncates hash values."""
    op.alter_column(
        "otp_verifications",
        "code",
        existing_type=sa.String(length=64),
        type_=sa.String(length=6),
        existing_nullable=False,
    )
