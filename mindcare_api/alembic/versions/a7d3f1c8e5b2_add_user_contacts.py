"""add_user_contacts

ADR-032: контакты пользователя.

user_contacts — зашифрованная коллекция дополнительных способов связи владельца
аккаунта (1:1 с users, строка создаётся при первом сохранении):
  - user_id → users ON DELETE CASCADE (PRIMARY KEY);
  - contacts_enc — только Fernet `enc:v1:` (CHECK); внутри JSON-конверт
    {"v":1,"items":[...]};
  - version ≥ 1 — счётчик для compare-and-set при сохранении (защита от потери
    правок из двух вкладок);
  - created_at / updated_at.
Основной телефон остаётся в users.phone и в таблице не дублируется.

Backfill НЕТ: ни одна строка миграцией не создаётся.

downgrade — fail-closed: при наличии строк откат отказывается (иначе необратимо
теряются контакты пользователей). STRICT, без IF EXISTS.

Revision ID: a7d3f1c8e5b2
Revises: f5a3c8d1e7b2
Create Date: 2026-10-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a7d3f1c8e5b2"
down_revision: Union[str, Sequence[str], None] = "f5a3c8d1e7b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_contacts",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("contacts_enc", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("user_id", name="user_contacts_pkey"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE",
            name="user_contacts_user_id_fkey",
        ),
        sa.CheckConstraint(
            "contacts_enc LIKE 'enc:v1:%'", name="ck_user_contacts_enc_format",
        ),
        sa.CheckConstraint("version >= 1", name="ck_user_contacts_version_positive"),
    )


def downgrade() -> None:
    conn = op.get_context().connection

    # Fail-closed ДО любых изменений. Только количество — без id/содержимого.
    rows = conn.execute(sa.text("SELECT COUNT(*) FROM user_contacts")).scalar()
    if rows:
        raise RuntimeError(
            "Cannot downgrade a7d3f1c8e5b2: "
            f"{rows} user contacts row(s) exist. Dropping the table would "
            "irreversibly erase users' contact data; export it first."
        )

    # STRICT: без IF EXISTS — рассинхрон схемы должен упасть, а не замаскироваться.
    op.drop_table("user_contacts")
