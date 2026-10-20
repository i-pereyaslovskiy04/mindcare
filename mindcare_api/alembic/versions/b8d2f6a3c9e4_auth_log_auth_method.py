"""auth_log_auth_method

Stage Social Auth 3A: способ аутентификации в auth_log.
  - auth_method VARCHAR(20) NULL
  - CHECK ck_auth_log_auth_method
      (auth_method IS NULL OR auth_method IN ('password','yandex','vk'))
  - индекс НЕ создаётся: значений мало, выборки admin viewer идут по окну
    created_at (idx_auth_created).

Пишется только для login (обязательно) и failed_login (если способ известен) —
политика EventSpec.auth_method_policy в app/audit/registry.py. Остальные
события AUTH_LOG — NULL. mfa_method (второй фактор) не переиспользуется.

Backfill исторических строк (до Stage 3A реального провайдера в production-
реестре не было, Stage 2B проверялся только FakeProvider в одноразовых БД):
  - login → 'password';
  - failed_login → 'password' ТОЛЬКО если строка однозначно парольная:
    user_email заполнен (вход по паролю всегда пишет введённый email, и legacy
    log_auth_event тоже; OAuth-ветка Stage 2B email не пишет) и failure_reason
    не OAuth-код Stage 2B;
  - неоднозначные OAuth-подобные строки и все остальные события → NULL.
  Провайдер (yandex/vk) для старых строк не угадывается.

auth_log — RANGE-partitioned по created_at. DDL выполняется на parent и
распространяется на все существующие партиции (PG11+); будущие партиции
(scripts/ensure_audit_partitions.py, CREATE TABLE ... PARTITION OF) наследуют
колонку и CHECK — скрипт не меняется. ADD COLUMN без DEFAULT — изменение только
каталога; UPDATE переписывает лишь строки login/failed_login; ADD CONSTRAINT
проверяет партиции сканированием (журнал небольшой). Порядок: колонка →
backfill → CHECK.

downgrade — fail-closed: при наличии строк с auth_method IN ('yandex','vk')
откат отказывается (иначе необратимо теряется, что вход был через провайдера).
Без таких строк — DROP CONSTRAINT, DROP COLUMN (значения 'password'
восстанавливаются повторным upgrade). STRICT, без IF EXISTS.

Revision ID: b8d2f6a3c9e4
Revises: c6e1a4f8b2d7
Create Date: 2026-10-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b8d2f6a3c9e4"
down_revision: Union[str, Sequence[str], None] = "c6e1a4f8b2d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# failure_reason, которые пишет ТОЛЬКО OAuth-ветка Stage 2B (app/oauth/routes.py).
_OAUTH_FAILURE_CODES = (
    "oauth_state_invalid",
    "oauth_provider_error",
    "oauth_identity_unknown",
    "oauth_ticket_invalid",
    "social_login_not_allowed",
)
_OAUTH_CODES_SQL = ", ".join(f"'{code}'" for code in _OAUTH_FAILURE_CODES)


def upgrade() -> None:
    op.execute("ALTER TABLE auth_log ADD COLUMN auth_method VARCHAR(20)")

    op.execute("UPDATE auth_log SET auth_method = 'password' WHERE event = 'login'")
    op.execute(
        "UPDATE auth_log SET auth_method = 'password' "
        "WHERE event = 'failed_login' "
        "AND user_email IS NOT NULL "
        f"AND (failure_reason IS NULL OR failure_reason NOT IN ({_OAUTH_CODES_SQL}))"
    )

    op.execute(
        "ALTER TABLE auth_log ADD CONSTRAINT ck_auth_log_auth_method "
        "CHECK (auth_method IS NULL OR auth_method IN ('password', 'yandex', 'vk'))"
    )


def downgrade() -> None:
    conn = op.get_context().connection

    # Fail-closed ДО любых изменений. Только количество — без email/IP/user_id.
    social_rows = conn.execute(sa.text(
        "SELECT COUNT(*) FROM auth_log WHERE auth_method IN ('yandex', 'vk')"
    )).scalar()
    if social_rows:
        raise RuntimeError(
            "Cannot downgrade b8d2f6a3c9e4: "
            f"{social_rows} auth_log row(s) record a social auth_method "
            "(yandex/vk). Dropping the column would irreversibly erase how these "
            "logins were authenticated; export or resolve them manually first."
        )

    # STRICT: без IF EXISTS — рассинхрон схемы должен упасть, а не замаскироваться.
    op.execute("ALTER TABLE auth_log DROP CONSTRAINT ck_auth_log_auth_method")
    op.execute("ALTER TABLE auth_log DROP COLUMN auth_method")
