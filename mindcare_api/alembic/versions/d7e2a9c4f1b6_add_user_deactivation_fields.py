"""add_user_deactivation_fields

ADR-028: единый обратимый lifecycle отключения/восстановления аккаунта.
Колонки описывают ТЕКУЩЕЕ отключение пользователя:
  - deactivated_at          TIMESTAMPTZ NULL — момент отключения;
  - deactivation_source     VARCHAR(10) NULL — 'admin' | 'self';
  - deactivation_reason_enc TEXT NULL        — причина, только Fernet `enc:v1:`
    (app/core/encryption.py); plaintext в БД не хранится.

CHECK:
  - ck_users_deactivation_source: NULL или 'admin'/'self';
  - ck_users_deactivation_reason_enc: NULL или префикс 'enc:v1:';
  - ck_users_deactivation_fields_consistent: все три поля NULL ЛИБО все три
    заданы (отключение без источника/причины, как и «осиротевшая» причина,
    невозможно).

Backfill НЕТ: у исторических отключений (is_active=false и/или deleted_at до
ADR-028) источник и причина неизвестны — поля остаются NULL, CHECK
согласованности выполняется. Восстановление администратором обнуляет все три
поля; история отключений — в audit_log (admin_user_deactivated /
user_self_deactivated / admin_user_activated), текст причины туда не пишется.

ADD COLUMN без DEFAULT — изменение только каталога; ADD CONSTRAINT проверяет
таблицу users сканированием (NULL-колонки — проверка тривиальна).

downgrade — fail-closed: при наличии строк с deactivation_reason_enc IS NOT
NULL откат отказывается (иначе необратимо теряются источник и причина
действующих отключений). Без таких строк — DROP CONSTRAINT ×3, DROP COLUMN ×3.
STRICT, без IF EXISTS.

Revision ID: d7e2a9c4f1b6
Revises: b8d2f6a3c9e4
Create Date: 2026-10-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d7e2a9c4f1b6"
down_revision: Union[str, Sequence[str], None] = "b8d2f6a3c9e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN deactivated_at TIMESTAMPTZ")
    op.execute("ALTER TABLE users ADD COLUMN deactivation_source VARCHAR(10)")
    op.execute("ALTER TABLE users ADD COLUMN deactivation_reason_enc TEXT")

    op.execute(
        "ALTER TABLE users ADD CONSTRAINT ck_users_deactivation_source "
        "CHECK (deactivation_source IS NULL "
        "OR deactivation_source IN ('admin', 'self'))"
    )
    op.execute(
        "ALTER TABLE users ADD CONSTRAINT ck_users_deactivation_reason_enc "
        "CHECK (deactivation_reason_enc IS NULL "
        "OR deactivation_reason_enc LIKE 'enc:v1:%')"
    )
    op.execute(
        "ALTER TABLE users ADD CONSTRAINT ck_users_deactivation_fields_consistent "
        "CHECK ((deactivated_at IS NULL AND deactivation_source IS NULL "
        "AND deactivation_reason_enc IS NULL) "
        "OR (deactivated_at IS NOT NULL AND deactivation_source IS NOT NULL "
        "AND deactivation_reason_enc IS NOT NULL))"
    )


def downgrade() -> None:
    conn = op.get_context().connection

    # Fail-closed ДО любых изменений. Только количество — без email/id/причин.
    active_rows = conn.execute(sa.text(
        "SELECT COUNT(*) FROM users WHERE deactivation_reason_enc IS NOT NULL"
    )).scalar()
    if active_rows:
        raise RuntimeError(
            "Cannot downgrade d7e2a9c4f1b6: "
            f"{active_rows} user row(s) carry a current deactivation record "
            "(source + encrypted reason). Dropping the columns would "
            "irreversibly erase them; restore or export these accounts first."
        )

    # STRICT: без IF EXISTS — рассинхрон схемы должен упасть, а не замаскироваться.
    op.execute(
        "ALTER TABLE users DROP CONSTRAINT ck_users_deactivation_fields_consistent"
    )
    op.execute("ALTER TABLE users DROP CONSTRAINT ck_users_deactivation_reason_enc")
    op.execute("ALTER TABLE users DROP CONSTRAINT ck_users_deactivation_source")
    op.execute("ALTER TABLE users DROP COLUMN deactivation_reason_enc")
    op.execute("ALTER TABLE users DROP COLUMN deactivation_source")
    op.execute("ALTER TABLE users DROP COLUMN deactivated_at")
