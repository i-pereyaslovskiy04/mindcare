"""adopt_ip_anonymization

Stage 7A — переносит IP-анонимизацию audit-журналов из legacy bootstrap-SQL в
Alembic-цепочку и заменяет её тело безопасным контрактом.

ЧТО БЫЛО. Функция `anonymize_old_ips()` жила только в `db/sql/migrations/
009_views_functions.sql` и `db/sql/full_schema.sql`. На БД, поднятой через
Alembic, её не существовало вовсе, consumer'а не было ни одного, и заявленная
в документации 90-дневная анонимизация фактически не выполнялась. Само legacy-
тело содержало дефект: `NOW() - (days_old || ' days')::interval` при
`days_old <= 0` даёт границу в БУДУЩЕМ и обнуляет ВСЕ `ip_address`, включая
свежие; при `days_old IS NULL` — молча ничего не делает.

ЧТО ДЕЛАЕТ ЭТА РЕВИЗИЯ. Создаёт две функции:
  - `public.anonymize_old_ips(integer) RETURNS bigint` — обнуляет `ip_address`
    старше границы в `audit_log` / `auth_log` / `data_change_log`;
  - `public.count_old_ips(integer) RETURNS bigint` — строго read-only счётчик
    тех же строк, чтобы dry-run consumer'а не требовал мутации и проверяемо
    совпадал с live-прогоном.

Отличия от legacy-тела (каждое закрывает конкретный дефект):
  - `days_old IS NULL OR days_old < 1` -> RAISE EXCEPTION (SQLSTATE 22023);
  - `make_interval(days => days_old)` вместо конкатенации строк;
  - единый `cutoff`, вычисленный один раз на все три UPDATE;
  - schema-qualified таблицы + `SET search_path = pg_catalog, public`;
  - явный `SECURITY INVOKER`;
  - `pg_try_advisory_xact_lock` (SQLSTATE 55P03 при конфликте) — параллельный
    прогон падает сразу, а не ждёт на row locks;
  - `bigint` вместо `integer`: `ROW_COUNT` и `count(*)` в PostgreSQL — bigint,
    и присваивание в integer-переменную сужает тип.

ПОЧЕМУ `DROP` + `CREATE`, А НЕ `CREATE OR REPLACE`. `CREATE OR REPLACE`
сохраняет ownership и ЯВНЫЕ grants существующей функции: на legacy-БД, где
кто-то выполнил `GRANT EXECUTE ON FUNCTION anonymize_old_ips(int) TO <role>`,
такой grant пережил бы замену тела, а `REVOKE ... FROM PUBLIC` его бы не снял —
`PUBLIC` и role-specific ACL являются независимыми записями `aclitem`. Итоговый
доступ оказался бы РАЗНЫМ на legacy- и на чистой БД. `DROP` + `CREATE`
сбрасывает `proacl` к дефолту и переназначает владельца на роль, выполняющую
миграцию, — состояние ACL становится детерминированным. Дополнительно
`CREATE OR REPLACE` здесь неприменим в принципе: он не может изменить тип
возвращаемого значения (legacy `integer` -> `bigint`).

`DROP` выполняется БЕЗ `CASCADE`. Авторитетный enforcement — сам `RESTRICT`
(default): наличие зависимого объекта роняет миграцию. Preflight лишь даёт
чистую диагностику раньше. Расширять `DROP` до `CASCADE` в ответ на отказ
ЗАПРЕЩЕНО: это молча удалило бы зависимые объекты.

Диагностика preflight — только стабильный код и счётчик: без имён объектов,
ролей, SQL, URL и raw exception text.

ЧТО ЭТА РЕВИЗИЯ НЕ ДЕЛАЕТ. Не удаляет ни одной строки журналов, не трогает
партиции, не выдаёт `GRANT` именованным ролям, не вводит `SECURITY DEFINER`, не
вызывает созданные функции. Первый (необратимый) прогон — операторское действие
вне миграции.

ПРИВИЛЕГИИ. `SECURITY INVOKER` означает, что `EXECUTE` — лишь право войти в
функцию; `SELECT`/`UPDATE` внутри тела выполняются с правами ВЫЗЫВАЮЩЕЙ роли.
Миграция управляет только ACL самих функций (владелец + `REVOKE ... FROM
PUBLIC`); табличные права она не выдаёт. Поддерживаемый контракт развёртывания —
одна роль для Alembic и для maintenance-consumer'а (общий `DATABASE_URL`).

ROUND-TRIP НАМЕРЕННО НЕПОЛНЫЙ. До upgrade возможны два разных состояния —
legacy-БД с дефектным телом и Alembic-БД без функции вовсе; одна ветка
`downgrade` не может восстановить оба. `downgrade` приводит БД к состоянию
Alembic-цепочки (функций нет) и НЕ восстанавливает legacy-тело: возврат
варианта, стирающего все IP при `days_old <= 0`, не является операционной
процедурой.

`downgrade` — STRICT (без `IF EXISTS`): schema drift обязан ронять миграцию, а
не маскироваться под успех.

ВНИМАНИЕ: УЖЕ ОБНУЛЁННЫЕ `ip_address` НЕ ВОССТАНАВЛИВАЮТСЯ. `downgrade`
возвращает механизм, но не данные: строки, обработанные `anonymize_old_ips`,
потеряны безвозвратно.

Миграция использует `op.get_bind()` для preflight и потому не поддерживает
offline-режим (`alembic upgrade --sql`) — как и `d4a7b2c9f6e1`.

Revision ID: c8e2b5f7a3d1
Revises: d4a7b2c9f6e1
Create Date: 2026-08-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c8e2b5f7a3d1"
down_revision: Union[str, Sequence[str], None] = "d4a7b2c9f6e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ── Управляемые объекты ──────────────────────────────────────────────────────

#: Точные сигнатуры для `to_regprocedure()` — идентификация строго по ним, а не
#: по одному лишь имени: одноимённая функция с другой сигнатурой не должна быть
#: принята за нашу.
ANONYMIZE_SIGNATURE = "public.anonymize_old_ips(integer)"
COUNT_SIGNATURE = "public.count_old_ips(integer)"

#: Имена, которыми владеет эта ревизия. У каждого в `public` должен остаться
#: ровно ОДИН разрешённый entry point.
MANAGED_NAMES = ("anonymize_old_ips", "count_old_ips")

#: Журналы, из которых обнуляется `ip_address`. Строго три: `user_sessions`,
#: `consent_records` и `user_legal_basis_records` содержат IP другого
#: назначения (активная сессия, доказательство согласия, документированное
#: основание) и в охват Stage 7 не входят.
AUDIT_TABLES = ("audit_log", "auth_log", "data_change_log")

#: 64-битный ключ transaction-level advisory lock.
#: Детерминирован: (crc32(b"mindcare_ip_anonymization") << 32)
#:                 | crc32(b"anonymize_old_ips").
#: ОБЯЗАН отличаться от ключа scripts/ensure_audit_partitions.py
#: (5566827076427522049) — иначе два независимых maintenance-job'а
#: блокировали бы друг друга.
ADVISORY_LOCK_KEY = 6888150381656956263

# Стабильные коды preflight. Порядок фиксирован: детерминированная диагностика.
_CODE_UNEXPECTED_SIGNATURE = "unexpected_managed_function_signature"
_CODE_HAS_DEPENDENTS = "managed_function_has_dependents"


def _fail(code: str, count: int) -> None:
    """Фиксированная диагностика: только стабильный код и счётчик.

    Ни имя объекта, ни роль, ни SQL, ни текст исходного исключения сюда не
    попадают — тот же контракт, что в `d4a7b2c9f6e1`.
    """
    raise RuntimeError(f"preflight failed: code={code} count={count}")


# ── Preflight ────────────────────────────────────────────────────────────────

def _oid(conn, signature: str):
    """OID по ТОЧНОЙ сигнатуре либо None.

    `to_regprocedure()` возвращает NULL для несуществующей функции — не бросает
    исключение и не может совпасть с одноимённой функцией другой сигнатуры или
    из другой схемы.
    """
    return conn.execute(
        sa.text("SELECT to_regprocedure(:sig)::oid"), {"sig": signature}
    ).scalar()


def _preflight_unexpected_signatures(conn) -> None:
    """Fail-closed: в `public` не должно быть НИ ОДНОЙ функции с управляемым
    именем и сигнатурой, отличной от `(integer)`.

    Причина запрета — НЕ «неоднозначность вызова»: например `(integer, text)`
    без DEFAULT вызов `anonymize_old_ips(90)` неоднозначным не делает, он просто
    не подходит по арности. Проблема в другом: `DROP ... (integer)` такую
    функцию НЕ удаляет, поэтому после миграции в схеме остался бы unmanaged
    overload — со своим телом, владельцем и ACL, полностью вне контроля этой
    ревизии, и потенциально с опасным legacy-телом. Инвариант: ровно один
    разрешённый entry point на имя.
    """
    count = conn.execute(sa.text("""
        SELECT count(*)
          FROM pg_proc p
          JOIN pg_namespace n ON n.oid = p.pronamespace
         WHERE n.nspname = 'public'
           AND p.proname = ANY(:names)
           AND p.oid <> COALESCE(to_regprocedure(:sig_anon)::oid, 0::oid)
           AND p.oid <> COALESCE(to_regprocedure(:sig_count)::oid, 0::oid)
    """), {
        "names": list(MANAGED_NAMES),
        "sig_anon": ANONYMIZE_SIGNATURE,
        "sig_count": COUNT_SIGNATURE,
    }).scalar()

    if count:
        _fail(_CODE_UNEXPECTED_SIGNATURE, count)


def _preflight_dependents(conn) -> None:
    """Fail-closed проверка зависимостей ТОЛЬКО для найденных OID.

    deptype 'i' (internal) исключён — это собственная служебная связь объекта.
    Считаются строки, где функция выступает РЕФЕРЕНТОМ (`refobjid`), то есть
    объекты, зависящие ОТ неё: ровно те, что заставят `DROP ... RESTRICT`
    упасть. Имена зависимых объектов не читаются и не логируются.
    """
    total = 0
    for signature in (ANONYMIZE_SIGNATURE, COUNT_SIGNATURE):
        oid = _oid(conn, signature)
        if oid is None:
            continue    # функции нет — штатно для БД, поднятых через Alembic
        total += conn.execute(sa.text("""
            SELECT count(*)
              FROM pg_depend d
             WHERE d.refclassid = 'pg_proc'::regclass
               AND d.refobjid = :oid
               AND d.deptype <> 'i'
        """), {"oid": oid}).scalar()

    if total:
        _fail(_CODE_HAS_DEPENDENTS, total)


# ── DDL ──────────────────────────────────────────────────────────────────────

# `DROP` схема-квалифицирован, по точной сигнатуре, БЕЗ CASCADE. `IF EXISTS`
# здесь уместен и НЕ ослабляет контракт: на чистой Alembic-БД функций никогда
# не было, и их отсутствие — штатное состояние, а не drift. Это ровно тот
# случай, который `downgrade` (STRICT) трактует иначе: там отсутствие объекта
# означает рассинхрон и обязано ронять миграцию.
DROP_ANONYMIZE_SQL = f"DROP FUNCTION IF EXISTS {ANONYMIZE_SIGNATURE}"
DROP_COUNT_SQL = f"DROP FUNCTION IF EXISTS {COUNT_SIGNATURE}"

# STRICT-варианты для downgrade.
DROP_ANONYMIZE_STRICT_SQL = f"DROP FUNCTION {ANONYMIZE_SIGNATURE}"
DROP_COUNT_STRICT_SQL = f"DROP FUNCTION {COUNT_SIGNATURE}"


def _update_block(table: str) -> str:
    return f"""
    UPDATE public.{table}
       SET ip_address = NULL
     WHERE created_at < cutoff
       AND ip_address IS NOT NULL;
    GET DIAGNOSTICS cnt = ROW_COUNT;
    affected := affected + cnt;
"""


def _count_block(table: str) -> str:
    return f"""
    SELECT count(*) INTO cnt
      FROM public.{table}
     WHERE created_at < cutoff
       AND ip_address IS NOT NULL;
    total := total + cnt;
"""


# Тела функций — ASCII-only. Кириллица внутри `CREATE FUNCTION` осела бы в
# `pg_proc.prosrc` и сделала бы DDL зависимым от `client_encoding` соединения,
# которым накатывается миграция. Развёрнутое обоснование каждого решения живёт
# здесь, в Python-комментариях; внутри SQL остаются короткие пометки.
#
# anonymize_old_ips:
#   1. Fail-fast по days_old. Legacy-тело при `days_old <= 0` уводило границу в
#      БУДУЩЕЕ и стирало ВСЕ ip_address, а при NULL молча не делало ничего.
#   2. Advisory lock — transaction-level: снимается сам на commit/rollback.
#      Конфликт даёт немедленный отказ (55P03), а не ожидание на row locks.
#   3. Единый `cutoff` на все три UPDATE. Интервал строится из integer через
#      make_interval, без конкатенации строк. Сравнение строгое `<`
#      (полуоткрытый интервал) — граница задокументирована и проверяется тестом.
#   4. Три UPDATE идут в транзакции ВЫЗЫВАЮЩЕГО: блока EXCEPTION нет, поэтому
#      субтранзакция не создаётся и сбой любого из них откатывает все три.
#   5. Предикат `ip_address IS NOT NULL` делает прогон идемпотентным и держит
#      счётчик точным: уже обнулённые строки не пересчитываются.
CREATE_ANONYMIZE_SQL = f"""
CREATE FUNCTION public.anonymize_old_ips(days_old integer DEFAULT 90)
RETURNS bigint
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, public
AS $fn$
DECLARE
    affected bigint := 0;
    cnt      bigint;
    cutoff   timestamptz;
BEGIN
    -- Fail-fast: reject NULL / non-positive retention window.
    IF days_old IS NULL OR days_old < 1 THEN
        RAISE EXCEPTION
            'anonymize_old_ips: days_old must be an integer greater than zero'
            USING ERRCODE = '22023';
    END IF;

    -- Transaction-level lock: released automatically on commit or rollback.
    IF NOT pg_catalog.pg_try_advisory_xact_lock({ADVISORY_LOCK_KEY}) THEN
        RAISE EXCEPTION
            'anonymize_old_ips: another run holds the advisory lock'
            USING ERRCODE = '55P03';
    END IF;

    -- Single cutoff shared by all three UPDATE statements.
    cutoff := pg_catalog.now()
              - pg_catalog.make_interval(days => days_old);
{_update_block("audit_log")}{_update_block("auth_log")}{_update_block("data_change_log")}
    RETURN affected;
END;
$fn$
"""

# count_old_ips:
#   - тот же валидатор, что у anonymize_old_ips: dry-run обязан отвергать ровно
#     те же аргументы, что и live-прогон;
#   - ТОТ ЖЕ предикат — поэтому consumer не дублирует логику границы в Python,
#     а тест сверяет `count_old_ips(n) == anonymize_old_ips(n)`;
#   - строго read-only: ни мутации, ни advisory lock. STABLE, потому что
#     now() внутри транзакции фиксирован.
CREATE_COUNT_SQL = f"""
CREATE FUNCTION public.count_old_ips(days_old integer DEFAULT 90)
RETURNS bigint
LANGUAGE plpgsql
STABLE
SECURITY INVOKER
SET search_path = pg_catalog, public
AS $fn$
DECLARE
    total  bigint := 0;
    cnt    bigint;
    cutoff timestamptz;
BEGIN
    -- Same validator as anonymize_old_ips: dry-run rejects the same arguments.
    IF days_old IS NULL OR days_old < 1 THEN
        RAISE EXCEPTION
            'count_old_ips: days_old must be an integer greater than zero'
            USING ERRCODE = '22023';
    END IF;

    cutoff := pg_catalog.now()
              - pg_catalog.make_interval(days => days_old);
{_count_block("audit_log")}{_count_block("auth_log")}{_count_block("data_change_log")}
    RETURN total;
END;
$fn$
"""

# `CREATE FUNCTION` по умолчанию выдаёт EXECUTE роли PUBLIC. Снимаем его сразу.
# GRANT именованным ролям НЕ выполняется: ревизия не угадывает имя роли, а
# владелец (роль, накатившая миграцию) права сохраняет по факту владения.
REVOKE_ANONYMIZE_SQL = f"REVOKE ALL ON FUNCTION {ANONYMIZE_SIGNATURE} FROM PUBLIC"
REVOKE_COUNT_SQL = f"REVOKE ALL ON FUNCTION {COUNT_SIGNATURE} FROM PUBLIC"


def upgrade() -> None:
    conn = op.get_bind()

    # ── 1. Preflight ДО любого DDL ───────────────────────────────────────────
    # Транзакционный DDL PostgreSQL + этот порядок гарантируют: при отказе не
    # удалена и не создана ни одна функция и ни один ACL не изменён.
    _preflight_unexpected_signatures(conn)
    _preflight_dependents(conn)

    # ── 2. DROP по точным сигнатурам, без CASCADE ────────────────────────────
    op.execute(DROP_ANONYMIZE_SQL)
    op.execute(DROP_COUNT_SQL)

    # ── 3. CREATE заново (не CREATE OR REPLACE) ──────────────────────────────
    op.execute(CREATE_ANONYMIZE_SQL)
    op.execute(CREATE_COUNT_SQL)

    # ── 4. ACL: только владелец ──────────────────────────────────────────────
    op.execute(REVOKE_ANONYMIZE_SQL)
    op.execute(REVOKE_COUNT_SQL)


def downgrade() -> None:
    # STRICT: без IF EXISTS и без CASCADE — рассинхрон схемы обязан упасть, а не
    # замаскироваться. Обратный порядок относительно upgrade.
    #
    # ВНИМАНИЕ: возвращает механизм, но НЕ данные: уже обнулённые ip_address
    # восстановлению не подлежат.
    op.execute(DROP_COUNT_STRICT_SQL)
    op.execute(DROP_ANONYMIZE_STRICT_SQL)
