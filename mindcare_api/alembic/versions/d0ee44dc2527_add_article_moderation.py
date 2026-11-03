"""add_article_moderation

ADR-034: модерация статей, которые пишет психолог.

articles:
  - status VARCHAR(20) NOT NULL DEFAULT 'draft' ∈ {draft, in_review,
    needs_changes, published} (CHECK ck_articles_status);
  - review_comment_enc TEXT NULL — комментарий проверяющего при возврате на
    доработку, только Fernet `enc:v1:` (CHECK ck_articles_review_comment_enc);
  - CHECK ck_articles_status_published: (status = 'published') =
    (is_published IS TRUE) — публичность по-прежнему определяет is_published,
    статус с ней согласован;
  - индекс ix_articles_status (очередь модерации).

Backfill: опубликованные статьи (is_published IS TRUE) → status 'published',
остальные остаются 'draft'. Ни одна статья не меняет видимость.

downgrade — fail-closed, если есть статьи на проверке / на доработке или
комментарии проверяющих (иначе молча теряется состояние модерации).

Revision ID: d0ee44dc2527
Revises: ffd5e761b87b
Create Date: 2026-10-27
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d0ee44dc2527"
down_revision: Union[str, Sequence[str], None] = "ffd5e761b87b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "articles",
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
    )
    op.add_column("articles", sa.Column("review_comment_enc", sa.Text(), nullable=True))
    op.execute("UPDATE articles SET status = 'published' WHERE is_published IS TRUE")
    op.create_check_constraint(
        "ck_articles_status", "articles",
        "status IN ('draft', 'in_review', 'needs_changes', 'published')",
    )
    op.create_check_constraint(
        "ck_articles_status_published", "articles",
        "(status = 'published') = (is_published IS TRUE)",
    )
    op.create_check_constraint(
        "ck_articles_review_comment_enc", "articles",
        "review_comment_enc IS NULL OR review_comment_enc LIKE 'enc:v1:%'",
    )
    op.create_index("ix_articles_status", "articles", ["status"])


def downgrade() -> None:
    conn = op.get_context().connection

    # Fail-closed ДО любых изменений. Только количество — без id/содержимого.
    rows = conn.execute(sa.text(
        "SELECT COUNT(*) FROM articles "
        "WHERE status IN ('in_review', 'needs_changes') OR review_comment_enc IS NOT NULL"
    )).scalar()
    if rows:
        raise RuntimeError(
            "Cannot downgrade d0ee44dc2527: "
            f"{rows} article(s) are in moderation or carry reviewer comments. "
            "Dropping the columns would silently lose the moderation state."
        )

    op.drop_index("ix_articles_status", table_name="articles")
    op.drop_constraint("ck_articles_review_comment_enc", "articles", type_="check")
    op.drop_constraint("ck_articles_status_published", "articles", type_="check")
    op.drop_constraint("ck_articles_status", "articles", type_="check")
    op.drop_column("articles", "review_comment_enc")
    op.drop_column("articles", "status")
