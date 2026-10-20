"""add_normalized_email_unique_index

Adds a functional unique index on lower(trim(email)) in the users table
to enforce DB-level uniqueness of normalized emails regardless of case
or surrounding whitespace.

Leaves existing raw unique index ix_users_email in place.

Revision ID: e5a8f3c1d2b6
Revises: d2e5f8a1b4c7
Create Date: 2026-06-11
"""
from alembic import op
import sqlalchemy as sa

revision = 'e5a8f3c1d2b6'
down_revision = 'd2e5f8a1b4c7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_context().connection
    row = conn.execute(sa.text(
        """
        SELECT lower(trim(email)) AS normalized_email, COUNT(*) AS cnt
        FROM users
        GROUP BY lower(trim(email))
        HAVING COUNT(*) > 1
        LIMIT 1
        """
    )).fetchone()
    if row is not None:
        raise RuntimeError(
            "Cannot create ux_users_email_normalized: "
            "duplicate normalized emails exist. Clean data before migration."
        )

    op.create_index(
        "ux_users_email_normalized",
        "users",
        [sa.text("lower(trim(email))")],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ux_users_email_normalized", table_name="users")
