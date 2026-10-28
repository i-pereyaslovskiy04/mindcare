"""add_material_favorites

ADR-034: избранные материалы пользователя.

material_favorites — отметка «в избранном» для статьи библиотеки:
  - PRIMARY KEY (user_id, article_id) — одна отметка на пару, повтор — no-op;
  - user_id → users ON DELETE CASCADE, article_id → articles ON DELETE CASCADE;
  - created_at — порядок списка «моё избранное».
Индексы: (user_id, created_at) — список; (article_id) — каскад при удалении.

Backfill НЕТ. downgrade — fail-closed при наличии строк (иначе безвозвратно
теряются отметки пользователей). STRICT, без IF EXISTS.

Revision ID: ffd5e761b87b
Revises: eb1460dc4954
Create Date: 2026-10-27
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "ffd5e761b87b"
down_revision: Union[str, Sequence[str], None] = "eb1460dc4954"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "material_favorites",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("article_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("user_id", "article_id", name="material_favorites_pkey"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE",
            name="material_favorites_user_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["article_id"], ["articles.id"], ondelete="CASCADE",
            name="material_favorites_article_id_fkey",
        ),
    )
    op.create_index(
        "ix_material_favorites_user_created", "material_favorites", ["user_id", "created_at"],
    )
    op.create_index(
        "ix_material_favorites_article_id", "material_favorites", ["article_id"],
    )


def downgrade() -> None:
    conn = op.get_context().connection

    # Fail-closed ДО любых изменений. Только количество — без id.
    rows = conn.execute(sa.text("SELECT COUNT(*) FROM material_favorites")).scalar()
    if rows:
        raise RuntimeError(
            "Cannot downgrade ffd5e761b87b: "
            f"{rows} material favorite row(s) exist. Dropping the table would "
            "irreversibly erase users' favorites; export them first."
        )

    op.drop_index("ix_material_favorites_article_id", table_name="material_favorites")
    op.drop_index("ix_material_favorites_user_created", table_name="material_favorites")
    op.drop_table("material_favorites")
