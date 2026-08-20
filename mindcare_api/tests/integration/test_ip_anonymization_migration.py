"""
Round-trip / ACL migration test для Stage 7A (adopt_ip_anonymization, c8e2b5f7a3d1).

ГЕЙТИНГ (не менять schema revision во время обычного full suite):
  - по умолчанию SKIPPED; запускается только при MINDCARE_MIGRATION_ROUNDTRIP=1;
  - при открытом gate любое нарушение безопасности — ОШИБКА, не skip:
      ENV=test, DATABASE_URL присутствует, current_database() ~ mindcare_test_<random>;
  - использует СОБСТВЕННЫЙ engine/connection (не SessionLocal / app engine);
  - перед Alembic-командами свои соединения закрыты и dispose'нуты;
  - используются ТОЧНЫЕ revision ID (не downgrade -1);
  - после проверок БД остаётся на head И с существующими функциями;
    одноразовую БД удалит Stage 1 runner.

Отдельный запуск (disposable PostgreSQL, credentials только через TEST_DATABASE_URL):
  ENV=test MINDCARE_MIGRATION_ROUNDTRIP=1 TEST_DATABASE_URL=... \
      python scripts/isolated_test_db.py -k ip_anonymization_migration -v

ПОКРЫТИЕ (идентификаторы сценариев — из плана Stage 7):
  T1  чистая Alembic-БД без функций -> upgrade создаёт обе
  T2  legacy-функция с ТОЧНОЙ сигнатурой -> upgrade заменяет её
  T3  unmanaged overload -> preflight fail-closed ДО любого DDL
  T4  ровно один entry point на каждое управляемое имя
  T17 strict downgrade удаляет обе; повторный upgrade восстанавливает
  T17b schema drift -> downgrade падает, alembic_version НЕ сдвигается,
       успевший выполниться DROP откатывается вместе с транзакцией
  T18/T27 PUBLIC не имеет EXECUTE ни на одной из функций
  T26 явный grant предопределённой роли НЕ переживает upgrade
  T28 владелец / current migration role имеет EXECUTE
  T29 proacl не содержит посторонних grantee
  T30 то же, что T26, но через реально созданную роль (гейтится правами)
  T31 зависимый объект -> preflight fail-closed ДО любого DDL
  T38 обе функции действительно RETURNS bigint
  T40 ограниченная роль с EXECUTE, но без табличных прав -> отказ без мутации

Synthetic legacy-функция НЕ берётся из db/sql bootstrap: тест создаёт её сам с
ТОЧНОЙ сигнатурой, RETURNS integer (как в legacy) и ПУСТЫМ телом. Настоящее
legacy-тело обнуляет ip_address и при days_old <= 0 стирает ВСЕ адреса —
воспроизводить его в тесте недопустимо. Все probe-объекты точечные и удаляются
в teardown.

Probe-строки используют ФИКСИРОВАННУЮ синтетическую дату (не date.today()),
чтобы детерминированно попадать в гарантированную baseline-партицию
(2026-01..2028-12, migration 3a7c5e2b8f1d).

Лечение drift'а — ответственность теста, который его внёс. `alembic upgrade
head` — no-op, если alembic_version уже head, поэтому физически удалённую вне
Alembic функцию он НЕ восстановит: для этого есть _heal_managed_functions(),
использующий ТЕ ЖЕ DDL-константы, что и сама миграция (единый источник истины).
"""
import importlib.util
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DatabaseError

STAGE7A_REVISION = "c8e2b5f7a3d1"
PREV_REVISION = "d4a7b2c9f6e1"
_TEST_DB_RE = re.compile(r"^mindcare_test_[a-z0-9]+$")
API_DIR = Path(__file__).resolve().parents[2]   # mindcare_api/

MIGRATION_PATH = (
    API_DIR / "alembic" / "versions" / f"{STAGE7A_REVISION}_adopt_ip_anonymization.py"
)

ANON_SIG = "public.anonymize_old_ips(integer)"
COUNT_SIG = "public.count_old_ips(integer)"

# Unmanaged overload: ДРУГАЯ сигнатура того же имени. `DROP ... (integer)` её не
# удаляет, поэтому она обязана останавливать миграцию (иначе в схеме остался бы
# второй entry point вне контроля ревизии).
OVERLOAD_SIG = "public.anonymize_old_ips(integer, text)"
OVERLOAD_ARGS_DDL = "days_old integer, note text"
OVERLOAD_DROP_ARGS = "integer, text"

# Зависимый объект для проверки RESTRICT. VIEW подходит: управляемая функция
# возвращает скаляр (не void), а CREATE VIEW её НЕ выполняет — только записывает
# зависимость pg_rewrite -> pg_proc (deptype 'n').
DEPENDENT_VIEW = "ip_anon_stage7a_dependent_view"

# Предопределённая роль (PG10+; проект требует PG15+). Выдача object privilege
# требует лишь ВЛАДЕНИЯ объектом, поэтому CREATE ROLE для T26 не нужен.
PREDEFINED_GRANTEE = "pg_monitor"

# Роль, создаваемая тестом (T30/T40). Гейтится правами current_user.
PROBE_ROLE = "ip_anon_stage7a_probe_role"

# Probe-строка в audit_log: собственный event_type — точечный фильтр очистки.
PROBE_EVENT_TYPE = "ip_anon_stage7a_probe"
PROBE_CREATED_AT = datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)
PROBE_IP = "203.0.113.7"   # TEST-NET-3 (RFC 5737), не реальный адрес

pytestmark = pytest.mark.skipif(
    os.environ.get("MINDCARE_MIGRATION_ROUNDTRIP") != "1",
    reason="round-trip migration disabled (set MINDCARE_MIGRATION_ROUNDTRIP=1)",
)


# ── Низкоуровневые помощники (собственный engine, не SessionLocal) ───────────

def _engine():
    return create_engine(
        os.environ["DATABASE_URL"], connect_args={"client_encoding": "utf8"}
    )


def _scalar(sql, **params):
    eng = _engine()
    try:
        with eng.connect() as c:
            return c.execute(text(sql), params).scalar()
    finally:
        eng.dispose()


def _exec(sql, **params):
    eng = _engine()
    try:
        with eng.begin() as c:
            c.execute(text(sql), params)
    finally:
        eng.dispose()


def _alembic(action: str, revision: str) -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_DIR / "alembic"))
    if action == "upgrade":
        command.upgrade(cfg, revision)
    else:
        command.downgrade(cfg, revision)


def _migration_module():
    """Загружает модуль ревизии по пути — DDL-константы берутся ИЗ НЕЁ.

    Тест не переписывает тела функций у себя: любое расхождение между
    восстановлением drift'а и настоящей миграцией было бы источником ложных
    результатов. Импорт `alembic.op` на уровне модуля безопасен: это прокси,
    не требующий активного migration context.
    """
    spec = importlib.util.spec_from_file_location("stage7a_migration", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ── Инспекция схемы и привилегий ─────────────────────────────────────────────

def _oid(signature: str):
    return _scalar("SELECT to_regprocedure(:sig)::oid", sig=signature)


def _function_result(signature: str):
    """Тип возвращаемого значения ('bigint' / 'integer') либо None."""
    return _scalar(
        "SELECT pg_get_function_result(to_regprocedure(:sig))", sig=signature
    )


def _count_by_name(proname: str) -> int:
    return _scalar(
        """
        SELECT count(*)
          FROM pg_proc p
          JOIN pg_namespace n ON n.oid = p.pronamespace
         WHERE n.nspname = 'public' AND p.proname = :n
        """,
        n=proname,
    )


def _alembic_version():
    return _scalar("SELECT version_num FROM alembic_version")


def _public_execute_grants(signature: str) -> int:
    """Число aclitem, выданных PUBLIC (grantee = 0 в aclexplode).

    `has_function_privilege('public', ...)` для этого НЕ годится: 'public' там
    трактуется как имя роли, а роли `public` не существует.
    """
    return _scalar(
        """
        SELECT count(*)
          FROM pg_proc p, aclexplode(p.proacl) a
         WHERE p.oid = to_regprocedure(:sig)
           AND a.grantee = 0
        """,
        sig=signature,
    )


def _foreign_grants(signature: str) -> int:
    """Число aclitem, выданных кому-либо кроме владельца (PUBLIC входит сюда)."""
    return _scalar(
        """
        SELECT count(*)
          FROM pg_proc p, aclexplode(p.proacl) a
         WHERE p.oid = to_regprocedure(:sig)
           AND a.grantee <> p.proowner
        """,
        sig=signature,
    )


def _proacl_is_set(signature: str) -> bool:
    """proacl IS NOT NULL — доказательство, что ACL задан ЯВНО (REVOKE выполнен).

    NULL означает «дефолтные привилегии», то есть EXECUTE у PUBLIC.
    """
    return bool(_scalar(
        "SELECT p.proacl IS NOT NULL FROM pg_proc p WHERE p.oid = to_regprocedure(:sig)",
        sig=signature,
    ))


def _role_exists(role: str) -> bool:
    return bool(_scalar("SELECT count(*) > 0 FROM pg_roles WHERE rolname = :r", r=role))


def _has_execute(role: str, signature: str) -> bool:
    return bool(_scalar(
        "SELECT has_function_privilege(:r, :sig, 'EXECUTE')", r=role, sig=signature
    ))


def _current_user_has_execute(signature: str) -> bool:
    return bool(_scalar(
        "SELECT has_function_privilege(current_user, :sig, 'EXECUTE')", sig=signature
    ))


def _can_create_role() -> bool:
    return bool(_scalar(
        "SELECT rolsuper OR rolcreaterole FROM pg_roles WHERE rolname = current_user"
    ))


# ── Probe-объекты ────────────────────────────────────────────────────────────

def _create_legacy_anonymize() -> None:
    """Synthetic legacy-функция: ТОЧНАЯ сигнатура, RETURNS integer, ПУСТОЕ тело.

    Настоящее legacy-тело обнуляет ip_address в трёх журналах и при
    days_old <= 0 стирает ВСЕ адреса — воспроизводить его нельзя. Здесь важна
    только сигнатура и тип возврата: `integer` -> после upgrade `bigint`
    доказывает, что произошёл именно DROP+CREATE (CREATE OR REPLACE не может
    изменить тип возвращаемого значения).
    """
    _exec("""
        CREATE FUNCTION public.anonymize_old_ips(days_old integer DEFAULT 90)
        RETURNS integer AS $probe$
        BEGIN
            -- intentionally inert: probe only checks signature and result type
            RETURN 0;
        END;
        $probe$ LANGUAGE plpgsql
    """)


def _create_overload() -> None:
    _exec(f"""
        CREATE FUNCTION {OVERLOAD_SIG.split('(')[0]}({OVERLOAD_ARGS_DDL})
        RETURNS integer AS $probe$
        BEGIN
            -- intentionally inert unmanaged overload
            RETURN 0;
        END;
        $probe$ LANGUAGE plpgsql
    """)


def _drop_overload() -> None:
    _exec(
        f"DROP FUNCTION IF EXISTS "
        f"{OVERLOAD_SIG.split('(')[0]}({OVERLOAD_DROP_ARGS})"
    )


def _create_dependent_view() -> None:
    """Нормальная (не internal) зависимость -> DROP ... RESTRICT упадёт.

    CREATE VIEW не ВЫПОЛНЯЕТ функцию, а только записывает зависимость
    pg_rewrite -> pg_proc (deptype 'n') — ровно ту, что считает preflight.
    """
    _exec(
        f"CREATE VIEW {DEPENDENT_VIEW} AS "
        f"SELECT public.anonymize_old_ips(90) AS probe_value"
    )


def _drop_dependent_view() -> None:
    _exec(f"DROP VIEW IF EXISTS {DEPENDENT_VIEW}")


def _create_probe_role() -> None:
    _exec(f'CREATE ROLE "{PROBE_ROLE}" NOLOGIN')


def _drop_probe_role() -> None:
    """DROP OWNED BY снимает выданные роли привилегии, иначе DROP ROLE упадёт."""
    if not _role_exists(PROBE_ROLE):
        return
    _exec(f'DROP OWNED BY "{PROBE_ROLE}"')
    _exec(f'DROP ROLE IF EXISTS "{PROBE_ROLE}"')


def _insert_audit_probe() -> None:
    _exec(
        """
        INSERT INTO audit_log (event_type, ip_address, created_at)
        VALUES (:e, CAST(:ip AS inet), :ts)
        """,
        e=PROBE_EVENT_TYPE, ip=PROBE_IP, ts=PROBE_CREATED_AT,
    )


def _probe_rows_with_ip() -> int:
    return _scalar(
        "SELECT count(*) FROM audit_log "
        "WHERE event_type = :e AND ip_address IS NOT NULL",
        e=PROBE_EVENT_TYPE,
    )


def _delete_audit_probes() -> None:
    _exec("DELETE FROM audit_log WHERE event_type = :e", e=PROBE_EVENT_TYPE)


# ── Лечение drift'а ──────────────────────────────────────────────────────────

def _heal_managed_functions() -> None:
    """Восстанавливает управляемые функции, удалённые ВНЕ Alembic В ЭТОМ тесте.

    Нужен, потому что `alembic upgrade head` — no-op, если alembic_version уже
    head: падающий `alembic downgrade` откатывает СВОЮ транзакцию целиком,
    включая обновление alembic_version, но ручной `DROP FUNCTION` вне Alembic
    уже зафиксирован отдельной транзакцией. Обычный fixture teardown такой
    физический drift не лечит сам по себе — DDL берётся из модуля миграции,
    чтобы восстановленный объект был БАЙТ-В-БАЙТ тем же, что создаёт upgrade.
    """
    module = _migration_module()
    if _oid(ANON_SIG) is None:
        _exec(module.CREATE_ANONYMIZE_SQL)
        _exec(module.REVOKE_ANONYMIZE_SQL)
    if _oid(COUNT_SIG) is None:
        _exec(module.CREATE_COUNT_SQL)
        _exec(module.REVOKE_COUNT_SQL)


# ── Fixture ──────────────────────────────────────────────────────────────────

def _attempt(label: str, step) -> "str | None":
    """Пытается выполнить ОДИН точечный шаг cleanup независимо от остальных.

    Намеренно широкий except (не BaseException — KeyboardInterrupt/SystemExit
    проходят как обычно): единственная цель — не дать сбою ОДНОГО шага
    остановить остальные, в т.ч. критичный restore_head. Возвращает диагностику
    ТОЛЬКО как label + класс исключения — без str(exc)/SQL/значений, тот же
    формат, что в самой миграции.
    """
    try:
        step()
    except Exception as exc:  # noqa: BLE001 — см. docstring выше
        return f"{label}={type(exc).__name__}"
    return None


@pytest.fixture()
def safe_test_db():
    # Gate открыт → нарушения безопасности = ОШИБКА, не skip.
    if os.environ.get("ENV") != "test":
        raise RuntimeError("roundtrip: ENV must be 'test'.")
    if not os.environ.get("DATABASE_URL"):
        raise RuntimeError("roundtrip: DATABASE_URL must be present.")
    current = _scalar("SELECT current_database()")
    if not (current and _TEST_DB_RE.match(current)):
        raise RuntimeError(
            "roundtrip: current_database() must be mindcare_test_<random>."
        )
    if not MIGRATION_PATH.is_file():
        raise RuntimeError("roundtrip: Stage 7A revision file not found.")
    try:
        yield
    finally:
        # Каждый шаг — ТОЧЕЧНЫЙ: свои synthetic-идентификаторы (OVERLOAD /
        # DEPENDENT_VIEW / PROBE_ROLE / PROBE_EVENT_TYPE), НЕ глобальный
        # DELETE/DROP. Строки других тестов не затрагиваются.
        #
        # ПОРЯДОК ЗНАЧИМ:
        #   1. зависимый view — ДО upgrade, иначе preflight снова упадёт;
        #   2. overload — ДО upgrade по той же причине;
        #   3. upgrade — если тест оставил БД на PREV, настоящая миграция сама
        #      заменит любую synthetic legacy-функцию и сотрёт её grants;
        #   4. heal — только физический drift, оставшийся при head-ревизии.
        #
        # Synthetic legacy-функция НЕ дропается отдельным шагом: она делит
        # сигнатуру с УПРАВЛЯЕМОЙ функцией, и безусловный DROP снёс бы рабочий
        # объект. Её вытесняет upgrade (шаг 3) либо heal (шаг 4).
        failures = [
            err for err in (
                _attempt("drop_dependent_view", _drop_dependent_view),
                _attempt("drop_overload", _drop_overload),
                _attempt("drop_probe_role", _drop_probe_role),
                _attempt("delete_audit_probes", _delete_audit_probes),
                _attempt(
                    "restore_head",
                    lambda: _alembic("upgrade", STAGE7A_REVISION),
                ),
                _attempt("heal_managed_functions", _heal_managed_functions),
            )
            if err is not None
        ]
        if failures:
            raise RuntimeError(
                "safe_test_db teardown had failed step(s): " + ", ".join(failures)
            )


# ── T1 / T4 / T38: чистая БД, entry points, типы возврата ────────────────────

def test_upgrade_on_clean_db_creates_both_functions(safe_test_db):
    """T1 — на чистой Alembic-БД функций нет; upgrade создаёт обе."""
    _alembic("downgrade", PREV_REVISION)
    assert _oid(ANON_SIG) is None
    assert _oid(COUNT_SIG) is None

    _alembic("upgrade", STAGE7A_REVISION)
    assert _oid(ANON_SIG) is not None
    assert _oid(COUNT_SIG) is not None


def test_exactly_one_entry_point_per_managed_name(safe_test_db):
    """T4 — ровно один разрешённый entry point на каждое управляемое имя."""
    _alembic("upgrade", STAGE7A_REVISION)

    assert _count_by_name("anonymize_old_ips") == 1
    assert _count_by_name("count_old_ips") == 1


def test_both_functions_return_bigint(safe_test_db):
    """T38 — ROW_COUNT и count(*) в PostgreSQL bigint; сужения типа быть не должно."""
    _alembic("upgrade", STAGE7A_REVISION)

    assert _function_result(ANON_SIG) == "bigint"
    assert _function_result(COUNT_SIG) == "bigint"


def test_function_bodies_resolve_at_runtime(safe_test_db):
    """Smoke: тела функций исполняются целиком, без мутации данных.

    PL/pgSQL при CREATE проверяет только СИНТАКСИС тела: имена таблиц и колонок
    во вложенном SQL резолвятся при первом фактическом выполнении. Без этого
    теста опечатка в `ip_address` / `created_at` / имени журнала прошла бы
    миграцию и всплыла лишь на первом прогоне job'а.

    `days_old` берётся заведомо огромным (100 лет), поэтому предикат
    `created_at < cutoff` не матчит НИ ОДНОЙ строки: все три UPDATE и все три
    SELECT планируются и выполняются, но ничего не изменяется — тест безопасен
    и в общей БД полного прогона, где журналы наполнены другими тестами.

    Это НЕ поведенческое покрытие: границы, партиции, идемпотентность,
    конкурентность и rollback — сценарии T5–T16 подэтапа 7B.
    """
    _alembic("upgrade", STAGE7A_REVISION)

    far_past_days = 36500

    before = _scalar(
        "SELECT count(*) FROM audit_log WHERE ip_address IS NOT NULL"
    )

    assert _scalar(
        "SELECT public.count_old_ips(:d)", d=far_past_days
    ) == 0
    assert _scalar(
        "SELECT public.anonymize_old_ips(:d)", d=far_past_days
    ) == 0

    # Ни одна строка не затронута — предикат не совпал, а не «правами не дали».
    assert _scalar(
        "SELECT count(*) FROM audit_log WHERE ip_address IS NOT NULL"
    ) == before


# ── T2: legacy-функция заменяется ────────────────────────────────────────────

def test_legacy_exact_signature_function_is_replaced(safe_test_db):
    """T2 — legacy `integer` вытесняется управляемой `bigint`.

    Смена типа возврата — сама по себе доказательство DROP+CREATE:
    `CREATE OR REPLACE` изменить его не может и упал бы.
    """
    _alembic("downgrade", PREV_REVISION)
    _create_legacy_anonymize()
    assert _function_result(ANON_SIG) == "integer"

    _alembic("upgrade", STAGE7A_REVISION)

    assert _function_result(ANON_SIG) == "bigint"
    assert _count_by_name("anonymize_old_ips") == 1


# ── T3 / T31: fail-closed preflight ──────────────────────────────────────────

def test_unmanaged_overload_blocks_upgrade_before_any_ddl(safe_test_db):
    """T3 — чужая сигнатура того же имени останавливает миграцию ДО DDL."""
    _alembic("downgrade", PREV_REVISION)
    _create_overload()

    with pytest.raises(RuntimeError) as excinfo:
        _alembic("upgrade", STAGE7A_REVISION)

    message = str(excinfo.value)
    assert "unexpected_managed_function_signature" in message
    # Диагностика — только стабильный код и счётчик: ни имени объекта, ни SQL.
    assert "anonymize_old_ips" not in message
    assert "pg_proc" not in message

    # Ни одного DDL: управляемых функций как не было, так и нет.
    assert _alembic_version() == PREV_REVISION
    assert _oid(ANON_SIG) is None
    assert _oid(COUNT_SIG) is None


def test_dependent_object_blocks_upgrade_before_any_ddl(safe_test_db):
    """T31 — зависимый объект останавливает миграцию; CASCADE не применяется."""
    _alembic("downgrade", PREV_REVISION)
    _create_legacy_anonymize()
    _create_dependent_view()

    with pytest.raises(RuntimeError) as excinfo:
        _alembic("upgrade", STAGE7A_REVISION)

    message = str(excinfo.value)
    assert "managed_function_has_dependents" in message
    assert DEPENDENT_VIEW not in message

    # Ни DROP, ни CREATE не выполнялись: legacy-функция цела, view жив.
    assert _alembic_version() == PREV_REVISION
    assert _function_result(ANON_SIG) == "integer"
    assert _scalar(
        "SELECT count(*) > 0 FROM pg_class WHERE relname = :v", v=DEPENDENT_VIEW
    )


# ── T17 / T17b: strict downgrade ─────────────────────────────────────────────

def test_strict_downgrade_removes_both_and_upgrade_restores(safe_test_db):
    """T17 — downgrade удаляет обе функции; повторный upgrade восстанавливает."""
    _alembic("upgrade", STAGE7A_REVISION)
    assert _oid(ANON_SIG) is not None
    assert _oid(COUNT_SIG) is not None

    _alembic("downgrade", PREV_REVISION)
    assert _oid(ANON_SIG) is None
    assert _oid(COUNT_SIG) is None
    assert _alembic_version() == PREV_REVISION

    _alembic("upgrade", STAGE7A_REVISION)
    assert _oid(ANON_SIG) is not None
    assert _oid(COUNT_SIG) is not None
    assert _alembic_version() == STAGE7A_REVISION


def test_strict_downgrade_fails_on_schema_drift_and_rolls_back(safe_test_db):
    """T17b — отсутствие объекта роняет downgrade; версия НЕ сдвигается.

    Дропается именно `anonymize_old_ips` — ВТОРОЙ в порядке downgrade. Тогда
    первый `DROP count_old_ips` успевает выполниться, второй падает, и откат
    транзакции обязан вернуть count_old_ips на место. Это проверяет не только
    факт отказа, но и атомарность: частично применённого downgrade не бывает.
    """
    _alembic("upgrade", STAGE7A_REVISION)

    # Ручной drift ВНЕ Alembic — собственной зафиксированной транзакцией.
    _exec(f"DROP FUNCTION {ANON_SIG}")
    assert _oid(ANON_SIG) is None
    assert _oid(COUNT_SIG) is not None

    with pytest.raises(DatabaseError):
        _alembic("downgrade", PREV_REVISION)

    # Версия на месте, а успевший выполниться DROP откатился вместе с транзакцией.
    assert _alembic_version() == STAGE7A_REVISION
    assert _oid(COUNT_SIG) is not None

    # Drift лечит тот, кто его внёс: upgrade здесь no-op (ревизия уже head).
    _alembic("upgrade", STAGE7A_REVISION)
    assert _oid(ANON_SIG) is None, "upgrade на head обязан быть no-op"
    _heal_managed_functions()
    assert _oid(ANON_SIG) is not None

    # После лечения обычный цикл проходит.
    _alembic("downgrade", PREV_REVISION)
    assert _oid(ANON_SIG) is None
    assert _oid(COUNT_SIG) is None
    _alembic("upgrade", STAGE7A_REVISION)
    assert _oid(ANON_SIG) is not None
    assert _oid(COUNT_SIG) is not None


# ── T18 / T27 / T28 / T29: ACL после upgrade ─────────────────────────────────

def test_public_has_no_execute_after_upgrade(safe_test_db):
    """T18 / T27 — REVOKE ALL FROM PUBLIC выполнен для ОБЕИХ функций."""
    _alembic("upgrade", STAGE7A_REVISION)

    for signature in (ANON_SIG, COUNT_SIG):
        # proacl NOT NULL доказывает, что ACL задан явно: NULL означал бы
        # дефолтные привилегии, то есть EXECUTE у PUBLIC.
        assert _proacl_is_set(signature), signature
        assert _public_execute_grants(signature) == 0, signature


def test_owner_has_execute_after_upgrade(safe_test_db):
    """T28 — роль, накатившая миграцию, сохраняет EXECUTE (по факту владения)."""
    _alembic("upgrade", STAGE7A_REVISION)

    assert _current_user_has_execute(ANON_SIG)
    assert _current_user_has_execute(COUNT_SIG)


def test_proacl_contains_no_foreign_grantees(safe_test_db):
    """T29 — в ACL нет никого, кроме владельца."""
    _alembic("upgrade", STAGE7A_REVISION)

    assert _foreign_grants(ANON_SIG) == 0
    assert _foreign_grants(COUNT_SIG) == 0


# ── T26 / T30: legacy grant не переживает upgrade ────────────────────────────

def test_legacy_grant_to_predefined_role_does_not_survive(safe_test_db):
    """T26 — явный grant, выданный ДО миграции, снимается через DROP+CREATE.

    Ключевой ACL-сценарий: `CREATE OR REPLACE` сохранил бы этот grant, а
    `REVOKE ... FROM PUBLIC` его не снял бы (PUBLIC и role-specific ACL —
    независимые записи aclitem). Grantee — ПРЕДОПРЕДЕЛЁННАЯ роль: выдача
    object privilege требует лишь владения объектом, поэтому CREATE ROLE и
    повышенные права здесь не нужны.
    """
    if not _role_exists(PREDEFINED_GRANTEE):
        pytest.skip(f"predefined role {PREDEFINED_GRANTEE} is absent")

    _alembic("downgrade", PREV_REVISION)
    _create_legacy_anonymize()
    _exec(f'GRANT EXECUTE ON FUNCTION {ANON_SIG} TO "{PREDEFINED_GRANTEE}"')
    assert _has_execute(PREDEFINED_GRANTEE, ANON_SIG)

    _alembic("upgrade", STAGE7A_REVISION)

    assert not _has_execute(PREDEFINED_GRANTEE, ANON_SIG)
    assert _foreign_grants(ANON_SIG) == 0


def test_legacy_grant_to_created_role_does_not_survive(safe_test_db):
    """T30 — тот же сценарий через реально созданную роль.

    Гейтится правами: `CREATE ROLE` требует superuser или CREATEROLE. Skip
    касается ТОЛЬКО этого теста — T26–T29 остаются обязательными и от него не
    зависят.
    """
    if not _can_create_role():
        pytest.skip("current_user cannot CREATE ROLE")

    _alembic("downgrade", PREV_REVISION)
    _create_legacy_anonymize()
    _create_probe_role()
    _exec(f'GRANT EXECUTE ON FUNCTION {ANON_SIG} TO "{PROBE_ROLE}"')
    assert _has_execute(PROBE_ROLE, ANON_SIG)

    _alembic("upgrade", STAGE7A_REVISION)

    assert not _has_execute(PROBE_ROLE, ANON_SIG)
    assert _foreign_grants(ANON_SIG) == 0


# ── T40: SECURITY INVOKER требует табличных прав ─────────────────────────────

def test_execute_without_table_privileges_fails_closed(safe_test_db):
    """T40 — EXECUTE без табличных прав: отказ БЕЗ изменения строк.

    `SECURITY INVOKER` означает, что EXECUTE — лишь право войти в функцию:
    UPDATE внутри тела выполняется с правами вызывающей роли. Роль с одним лишь
    EXECUTE обязана падать на первом же обращении к журналу, и ни одна строка
    при этом измениться не должна.

    `SET LOCAL ROLE` ограничивает смену роли транзакцией — она снимается
    автоматически при rollback, отдельный RESET ROLE не нужен.
    """
    if not _can_create_role():
        pytest.skip("current_user cannot CREATE ROLE")

    _alembic("upgrade", STAGE7A_REVISION)
    _insert_audit_probe()
    _create_probe_role()
    # Только EXECUTE. Табличные права НЕ выдаются — в этом весь смысл теста.
    _exec(f'GRANT EXECUTE ON FUNCTION {ANON_SIG} TO "{PROBE_ROLE}"')
    _exec(f'GRANT EXECUTE ON FUNCTION {COUNT_SIG} TO "{PROBE_ROLE}"')

    before = _probe_rows_with_ip()
    assert before == 1, "probe-строка должна существовать до прогона"

    eng = _engine()
    try:
        with eng.connect() as conn:
            trans = conn.begin()
            try:
                conn.execute(text(f'SET LOCAL ROLE "{PROBE_ROLE}"'))
            except DatabaseError:
                trans.rollback()
                pytest.skip("cannot SET ROLE to probe role in this environment")

            # days_old=1: probe-строка (фиксированная прошлая дата) заведомо
            # старше границы, поэтому отказ вызван ИМЕННО правами, а не тем,
            # что обновлять было нечего.
            with pytest.raises(DatabaseError):
                conn.execute(text("SELECT public.anonymize_old_ips(1)"))
            trans.rollback()
    finally:
        eng.dispose()

    # Проверка на СВЕЖЕМ соединении: строка не тронута.
    assert _probe_rows_with_ip() == before
