"""
Round-trip migration test для Stage 6-A (harden_data_change_log, d4a7b2c9f6e1).

ГЕЙТИНГ (не менять schema revision во время обычного full suite):
  - по умолчанию SKIPPED; запускается только при MINDCARE_MIGRATION_ROUNDTRIP=1;
  - при открытом gate любое нарушение безопасности — ОШИБКА, не skip:
      ENV=test, DATABASE_URL присутствует, current_database() ~ mindcare_test_<random>;
  - использует СОБСТВЕННЫЙ engine/connection (не SessionLocal / app engine);
  - перед Alembic-командами свои соединения закрыты и dispose'нуты;
  - используются ТОЧНЫЕ revision ID (не downgrade -1);
  - после проверок БД остаётся на head; одноразовую БД удалит Stage 1 runner.

Отдельный запуск (disposable PostgreSQL, credentials только через TEST_DATABASE_URL):
  ENV=test MINDCARE_MIGRATION_ROUNDTRIP=1 TEST_DATABASE_URL=... \
      python scripts/isolated_test_db.py -k data_change_migration -v

Legacy-функция НЕ берётся из db/sql bootstrap: тест сам создаёт синтетическую
функцию с ТОЧНОЙ legacy-сигнатурой и ПУСТЫМ телом. Настоящая реализация
копирует полные ORM-строки в old_values/new_values — воспроизводить её в тесте
недопустимо. Все probe-объекты точечные и удаляются в try/finally.

Probe-строки используют ФИКСИРОВАННЫЕ синтетические даты (не date.today()),
чтобы детерминированно попадать в гарантированные baseline-партиции
(2026-01..2028-12, migration 3a7c5e2b8f1d).

Изоляция strict-drift сценария (corrective pass): ручной DROP CONSTRAINT вне
Alembic коммитится сразу же (собственная транзакция _exec()), а падающий
`alembic downgrade` откатывает СВОЮ транзакцию целиком — включая обновление
alembic_version. Ревизия поэтому остаётся на head, но физически constraint уже
отсутствует: `alembic upgrade head` после этого no-op (ревизия и так head) и
НЕ восстанавливает схему. Тест, вносящий такой ручной drift, обязан вылечить
его САМ (см. _heal_manual_check_drift) — это не обязанность fixture teardown.
"""
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError, ProgrammingError

STAGE6A_REVISION = "d4a7b2c9f6e1"
PREV_REVISION = "b5d7f0a3c9e1"
_TEST_DB_RE = re.compile(r"^mindcare_test_[a-z0-9]+$")
API_DIR = Path(__file__).resolve().parents[2]   # mindcare_api/

# Синтетическая таблица-цель probe-строк: только data_change_log.
_PROBE_TABLE_NAME = "roundtrip_probe_stage6a"    # значение колонки table_name

# Фиксированные даты внутри гарантированных baseline-партиций.
PROBE_CREATED_AT = datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)
PROBE_PARTITION = "data_change_log_2026_07"
SECOND_PROBE_CREATED_AT = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
SECOND_PROBE_PARTITION = "data_change_log_2026_01"

# Синтетическая far-future партиция, создаваемая ТЕМ ЖЕ DDL-паттерном, что
# scripts/ensure_audit_partitions.py::_process_partition.
FUTURE_PARTITION_NAME = "data_change_log_stage6a_roundtrip_future_probe"
FUTURE_PARTITION_FROM = "2099-01-01"
FUTURE_PARTITION_TO = "2099-02-01"
FUTURE_CREATED_AT = datetime(2099, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

# Legacy-функция: ТОЧНАЯ сигнатура (db/sql/migrations/009_views_functions.sql).
LEGACY_SIGNATURE = (
    "public.log_data_change("
    "integer,character varying,character varying,integer,"
    "character varying,jsonb,jsonb,inet)"
)
LEGACY_ARGS_DDL = (
    "p_actor_id integer, p_actor_role character varying, "
    "p_table_name character varying, p_record_id integer, "
    "p_operation character varying, p_old_values jsonb DEFAULT NULL, "
    "p_new_values jsonb DEFAULT NULL, p_ip inet DEFAULT NULL"
)
LEGACY_DROP_ARGS = (
    "integer, character varying, character varying, integer, "
    "character varying, jsonb, jsonb, inet"
)
# Зависимый объект для проверки RESTRICT. VIEW не годится: legacy-функция
# возвращает void, а колонка представления не может иметь псевдотип void
# ("столбец ... имеет псевдотип void"). SQL-body функция (BEGIN ATOMIC, PG14+)
# ссылается на неё корректно и создаёт нормальную запись pg_depend
# (objid = обёртка, refobjid = log_data_change, deptype='n').
DEPENDENT_FUNCTION = "roundtrip_probe_stage6a_dependent_fn"
MIN_SERVER_VERSION_NUM = 140000   # BEGIN ATOMIC

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


# ── Инспекция схемы ──────────────────────────────────────────────────────────

def _constraint_exists(name: str) -> bool:
    return bool(_scalar(
        """
        SELECT count(*) > 0
          FROM pg_constraint con
          JOIN pg_class c ON c.oid = con.conrelid
         WHERE c.relname = 'data_change_log' AND con.conname = :n
        """,
        n=name,
    ))


def _column_is_not_null(column: str) -> bool:
    return bool(_scalar(
        """
        SELECT attnotnull
          FROM pg_attribute a
          JOIN pg_class c ON c.oid = a.attrelid
         WHERE c.relname = 'data_change_log' AND a.attname = :col
        """,
        col=column,
    ))


# CHECK-выражения ТОЧНО как в migration d4a7b2c9f6e1 / ORM DataChangeLog — см.
# tests/test_data_change_model.py::_EXPECTED_CHECKS (drift-контроль двух мест).
_CHECK_SQL = {
    "ck_dcl_operation": "operation IN ('INSERT', 'UPDATE', 'DELETE')",
    "ck_dcl_changed_fields_nonempty": "cardinality(changed_fields) > 0",
    "ck_dcl_record_id_positive": "record_id > 0",
}


def _heal_manual_check_drift(name: str) -> None:
    """Восстанавливает ОДИН CHECK, снятый вручную (вне Alembic) В ЭТОМ тесте.

    Нужен, потому что `alembic upgrade head` — no-op, если alembic_version уже
    head (см. header модуля): падающий `alembic downgrade` откатывает СВОЮ
    транзакцию целиком, включая обновление alembic_version, но ручной
    `DROP CONSTRAINT` вне Alembic уже зафиксирован отдельной транзакцией.
    Обычный fixture teardown такой физический drift не лечит — тест, который
    его внёс, обязан вызвать этот helper сам, ДО того как полагаться на
    реальный downgrade/upgrade цикл для возврата в согласованный head.
    """
    if _constraint_exists(name):
        return
    _exec(
        f"ALTER TABLE data_change_log ADD CONSTRAINT {name} "
        f"CHECK ({_CHECK_SQL[name]})"
    )


def _partition_constraint_exists(partition: str, name: str) -> bool:
    """CHECK, унаследованный партицией от parent (PG11+ наследует по имени)."""
    return bool(_scalar(
        """
        SELECT count(*) > 0
          FROM pg_constraint con
          JOIN pg_class c ON c.oid = con.conrelid
         WHERE c.relname = :p AND con.conname = :n
        """,
        p=partition, n=name,
    ))


def _partition_column_is_not_null(partition: str, column: str) -> bool:
    return bool(_scalar(
        """
        SELECT attnotnull
          FROM pg_attribute a
          JOIN pg_class c ON c.oid = a.attrelid
         WHERE c.relname = :p AND a.attname = :col
        """,
        p=partition, col=column,
    ))


def _legacy_function_oid():
    return _scalar("SELECT to_regprocedure(:sig)::oid", sig=LEGACY_SIGNATURE)


def _legacy_dependents() -> int:
    oid = _legacy_function_oid()
    if oid is None:
        return 0
    return _scalar(
        """
        SELECT count(*)
          FROM pg_depend d
         WHERE d.refclassid = 'pg_proc'::regclass
           AND d.refobjid = :oid
           AND d.deptype <> 'i'
        """,
        oid=oid,
    )


# ── Probe-объекты ────────────────────────────────────────────────────────────

def _create_legacy_function() -> None:
    """Синтетическая функция с ТОЧНОЙ legacy-сигнатурой и ПУСТЫМ телом.

    Настоящая реализация копирует p_old_values/p_new_values в data_change_log;
    здесь тело намеренно ничего не делает — тест проверяет DROP по сигнатуре,
    а не поведение небезопасной функции.
    """
    _exec(f"""
        CREATE OR REPLACE FUNCTION {LEGACY_SIGNATURE.split('(')[0]}({LEGACY_ARGS_DDL})
        RETURNS void AS $$
        BEGIN
            -- намеренно пусто: probe только для проверки DROP по сигнатуре
        END;
        $$ LANGUAGE plpgsql
    """)


def _drop_legacy_function() -> None:
    _exec(f"DROP FUNCTION IF EXISTS public.log_data_change({LEGACY_DROP_ARGS})")


def _create_dependent_function() -> None:
    """Нормальная (не internal) зависимость от функции → DROP ... RESTRICT упадёт.

    SQL-body функция: PostgreSQL разбирает её тело при CREATE и записывает
    зависимость в pg_depend. Тело намеренно ничего не делает сверх вызова.
    """
    _exec(f"""
        CREATE FUNCTION {DEPENDENT_FUNCTION}() RETURNS void
        LANGUAGE SQL
        BEGIN ATOMIC
            SELECT public.log_data_change(
                NULL::integer, NULL::character varying, NULL::character varying,
                NULL::integer, NULL::character varying, NULL::jsonb,
                NULL::jsonb, NULL::inet
            );
        END
    """)


def _drop_dependent_function() -> None:
    _exec(f"DROP FUNCTION IF EXISTS {DEPENDENT_FUNCTION}()")


def _function_exists(name: str) -> bool:
    return bool(_scalar(
        "SELECT count(*) > 0 FROM pg_proc p "
        "JOIN pg_namespace n ON n.oid = p.pronamespace "
        "WHERE p.proname = :n AND n.nspname = 'public'",
        n=name,
    ))


def _insert_probe(created_at, record_id=1, operation="UPDATE",
                  changed_fields="{full_name}") -> None:
    _exec(
        """
        INSERT INTO data_change_log
               (table_name, record_id, operation, changed_fields, created_at)
        VALUES (:t, :rid, :op, CAST(:cf AS text[]), :ts)
        """,
        t=_PROBE_TABLE_NAME, rid=record_id, op=operation,
        cf=changed_fields, ts=created_at,
    )


def _delete_probes() -> None:
    _exec(
        "DELETE FROM data_change_log WHERE table_name = :t",
        t=_PROBE_TABLE_NAME,
    )


# ── Fixture ──────────────────────────────────────────────────────────────────

def _attempt(label: str, step) -> "str | None":
    """Пытается выполнить ОДИН точечный шаг cleanup независимо от остальных.

    Намеренно широкий except (не BaseException — KeyboardInterrupt/SystemExit
    проходят как обычно): единственная цель — не дать сбою ОДНОГО шага (say,
    уже отсутствующего probe-объекта) остановить остальные шаги teardown, в
    т.ч. критичный `restore_head`. Возвращает диагностику ТОЛЬКО как
    label + класс исключения — без str(exc)/SQL/значений, тот же формат, что
    в самой миграции. Ошибка НЕ поглощается молча: вызывающий агрегирует все
    неудачные шаги и поднимает их одним RuntimeError В КОНЦЕ, когда уже все
    шаги (включая restore_head) попробованы.
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
    version_num = int(_scalar("SHOW server_version_num"))
    if version_num < MIN_SERVER_VERSION_NUM:
        raise RuntimeError(
            "roundtrip: dependency probe requires PostgreSQL 14+ (BEGIN ATOMIC)."
        )
    try:
        yield
    finally:
        # Каждый шаг — ТОЧЕЧНЫЙ: свои synthetic-идентификаторы
        # (_PROBE_TABLE_NAME / DEPENDENT_FUNCTION / LEGACY_SIGNATURE /
        # FUTURE_PARTITION_NAME), НЕ глобальный DELETE/DROP; рабочие
        # audit_log/data_change_log-строки других тестов/модулей не трогаются
        # (_delete_probes фильтрует WHERE table_name = _PROBE_TABLE_NAME).
        #
        # Каждый шаг пробуется НЕЗАВИСИМО от исхода предыдущих — иначе сбой
        # ранней уборки (например) не дал бы дойти до restore_head, который
        # обязателен ВСЕГДА. Ручной schema drift (см. _heal_manual_check_drift)
        # сюда не входит: это ответственность теста, который его вносит, а не
        # общего teardown (upgrade head — no-op, если ревизия и так head).
        failures = [
            err for err in (
                _attempt("drop_dependent_function", _drop_dependent_function),
                _attempt("drop_legacy_function", _drop_legacy_function),
                _attempt("delete_probes", _delete_probes),
                _attempt(
                    "drop_future_partition",
                    lambda: _exec(f"DROP TABLE IF EXISTS {FUTURE_PARTITION_NAME}"),
                ),
                # Оставить БД на head; обязателен, даже если шаги выше упали.
                _attempt(
                    "restore_head",
                    lambda: _alembic("upgrade", STAGE6A_REVISION),
                ),
            )
            if err is not None
        ]
        if failures:
            # Диагностика видна (не замаскирована) — но это отдельная от
            # исходной ошибки теста (если она была) причина: pytest репортит
            # обе фазы (call и teardown) независимо, ничего не подменяется.
            raise RuntimeError(
                "safe_test_db teardown had failed step(s): " + ", ".join(failures)
            )


# ── 1. Схема после upgrade ───────────────────────────────────────────────────

def test_upgrade_applies_not_null_and_checks(safe_test_db):
    _alembic("upgrade", STAGE6A_REVISION)

    assert _column_is_not_null("record_id")
    assert _column_is_not_null("changed_fields")
    assert _constraint_exists("ck_dcl_operation")
    assert _constraint_exists("ck_dcl_changed_fields_nonempty")
    assert _constraint_exists("ck_dcl_record_id_positive")


def test_constraints_are_enforced_on_insert(safe_test_db):
    _alembic("upgrade", STAGE6A_REVISION)

    with pytest.raises(IntegrityError):
        _insert_probe(PROBE_CREATED_AT, operation="PATCH")
    with pytest.raises(IntegrityError):
        _insert_probe(PROBE_CREATED_AT, record_id=0)
    with pytest.raises(IntegrityError):
        _insert_probe(PROBE_CREATED_AT, changed_fields="{}")

    # Валидная строка проходит.
    _insert_probe(PROBE_CREATED_AT)
    assert _scalar(
        "SELECT count(*) FROM data_change_log WHERE table_name = :t",
        t=_PROBE_TABLE_NAME,
    ) == 1


# ── 2. Партиции: существующие и новая ────────────────────────────────────────

def test_existing_partitions_inherit_constraints(safe_test_db):
    _alembic("upgrade", STAGE6A_REVISION)

    for partition in (PROBE_PARTITION, SECOND_PROBE_PARTITION):
        assert _partition_column_is_not_null(partition, "record_id"), partition
        assert _partition_column_is_not_null(partition, "changed_fields"), partition
        for check in ("ck_dcl_operation", "ck_dcl_changed_fields_nonempty",
                      "ck_dcl_record_id_positive"):
            assert _partition_constraint_exists(partition, check), (partition, check)

    # Строки, роутящиеся в РАЗНЫЕ партиции, обе проходят проверки.
    _insert_probe(PROBE_CREATED_AT)
    _insert_probe(SECOND_PROBE_CREATED_AT, record_id=2)
    assert _scalar(
        "SELECT count(*) FROM data_change_log WHERE table_name = :t",
        t=_PROBE_TABLE_NAME,
    ) == 2


def test_new_partition_inherits_constraints(safe_test_db):
    """Партиция, созданная ТЕМ ЖЕ DDL-паттерном, что ensure_audit_partitions.py,
    наследует NOT NULL и все три CHECK."""
    _alembic("upgrade", STAGE6A_REVISION)

    _exec(
        f"CREATE TABLE {FUTURE_PARTITION_NAME} PARTITION OF data_change_log "
        f"FOR VALUES FROM ('{FUTURE_PARTITION_FROM}') "
        f"TO ('{FUTURE_PARTITION_TO}')"
    )

    assert _partition_column_is_not_null(FUTURE_PARTITION_NAME, "record_id")
    assert _partition_column_is_not_null(FUTURE_PARTITION_NAME, "changed_fields")
    for check in ("ck_dcl_operation", "ck_dcl_changed_fields_nonempty",
                  "ck_dcl_record_id_positive"):
        assert _partition_constraint_exists(FUTURE_PARTITION_NAME, check), check

    with pytest.raises(IntegrityError):
        _insert_probe(FUTURE_CREATED_AT, operation="PATCH")
    _insert_probe(FUTURE_CREATED_AT)


# ── 3. Preflight по данным останавливает миграцию ДО DDL ────────────────────

@pytest.mark.parametrize("bad_kwargs,expected_code", [
    ({"operation": "PATCH"}, "bad_operation"),
    ({"record_id": 0}, "bad_record_id_nonpositive"),
])
def test_data_preflight_blocks_upgrade_before_any_ddl(
    safe_test_db, bad_kwargs, expected_code,
):
    _alembic("downgrade", PREV_REVISION)
    _insert_probe(PROBE_CREATED_AT, **bad_kwargs)

    with pytest.raises(RuntimeError) as excinfo:
        _alembic("upgrade", STAGE6A_REVISION)

    message = str(excinfo.value)
    assert f"code={expected_code}" in message
    assert "count=1" in message
    # Диагностика не раскрывает содержимого строк.
    assert _PROBE_TABLE_NAME not in message

    # НИ ОДИН DDL-объект не применён.
    assert not _column_is_not_null("record_id")
    assert not _column_is_not_null("changed_fields")
    assert not _constraint_exists("ck_dcl_operation")
    assert not _constraint_exists("ck_dcl_changed_fields_nonempty")
    assert not _constraint_exists("ck_dcl_record_id_positive")

    # После устранения нарушителя upgrade проходит.
    _delete_probes()
    _alembic("upgrade", STAGE6A_REVISION)
    assert _constraint_exists("ck_dcl_operation")


# ── 4. Legacy-функция: OID, зависимости, RESTRICT ───────────────────────────

def test_legacy_function_is_dropped_by_exact_signature(safe_test_db):
    _alembic("downgrade", PREV_REVISION)
    _create_legacy_function()
    assert _legacy_function_oid() is not None

    _alembic("upgrade", STAGE6A_REVISION)
    assert _legacy_function_oid() is None


def test_drop_is_idempotent_when_function_absent(safe_test_db):
    """БД, поднятая через Alembic, функции никогда не имела — upgrade всё равно
    проходит (IF EXISTS)."""
    _alembic("downgrade", PREV_REVISION)
    _drop_legacy_function()
    assert _legacy_function_oid() is None

    _alembic("upgrade", STAGE6A_REVISION)
    assert _legacy_function_oid() is None

    # Повторный прогон на БД без функции — тоже no-op.
    _alembic("downgrade", PREV_REVISION)
    _alembic("upgrade", STAGE6A_REVISION)
    assert _legacy_function_oid() is None


def test_dependency_blocks_upgrade_and_nothing_is_dropped_or_cascaded(safe_test_db):
    """Зависимый объект → fail closed ДО DDL. Ни функция, ни зависимый объект
    не удаляются: CASCADE не используется."""
    _alembic("downgrade", PREV_REVISION)
    _create_legacy_function()
    _create_dependent_function()
    assert _legacy_dependents() >= 1

    with pytest.raises(RuntimeError) as excinfo:
        _alembic("upgrade", STAGE6A_REVISION)
    assert "code=legacy_function_has_dependents" in str(excinfo.value)
    # Имена объектов в диагностику не попадают.
    assert DEPENDENT_FUNCTION not in str(excinfo.value)

    # Функция и зависимый объект целы.
    assert _legacy_function_oid() is not None
    assert _function_exists(DEPENDENT_FUNCTION)
    # DDL не применён.
    assert not _constraint_exists("ck_dcl_operation")
    assert not _column_is_not_null("record_id")

    # После устранения зависимости upgrade проходит и удаляет функцию.
    _drop_dependent_function()
    _alembic("upgrade", STAGE6A_REVISION)
    assert _legacy_function_oid() is None
    assert _constraint_exists("ck_dcl_operation")


def test_similarly_named_function_with_other_signature_is_untouched(safe_test_db):
    """Идентификация строго по OID точной сигнатуры: одноимённая функция с
    другой сигнатурой не должна быть затронута."""
    _alembic("downgrade", PREV_REVISION)
    _exec(
        "CREATE OR REPLACE FUNCTION public.log_data_change(p_only integer) "
        "RETURNS void AS $$ BEGIN END; $$ LANGUAGE plpgsql"
    )
    try:
        _alembic("upgrade", STAGE6A_REVISION)
        assert _scalar(
            "SELECT to_regprocedure('public.log_data_change(integer)')::oid"
        ) is not None
    finally:
        _exec("DROP FUNCTION IF EXISTS public.log_data_change(integer)")


# ── 5. Round-trip ────────────────────────────────────────────────────────────

def test_upgrade_downgrade_upgrade_round_trip(safe_test_db):
    _alembic("upgrade", STAGE6A_REVISION)
    assert _constraint_exists("ck_dcl_operation")
    assert _column_is_not_null("record_id")

    _alembic("downgrade", PREV_REVISION)
    assert not _constraint_exists("ck_dcl_operation")
    assert not _constraint_exists("ck_dcl_changed_fields_nonempty")
    assert not _constraint_exists("ck_dcl_record_id_positive")
    assert not _column_is_not_null("record_id")
    assert not _column_is_not_null("changed_fields")

    _alembic("upgrade", STAGE6A_REVISION)
    assert _constraint_exists("ck_dcl_operation")
    assert _constraint_exists("ck_dcl_changed_fields_nonempty")
    assert _constraint_exists("ck_dcl_record_id_positive")
    assert _column_is_not_null("record_id")
    assert _column_is_not_null("changed_fields")


def test_downgrade_does_not_restore_legacy_function(safe_test_db):
    """Round-trip НАМЕРЕННО неполный: функция не возвращается."""
    _alembic("downgrade", PREV_REVISION)
    _create_legacy_function()
    assert _legacy_function_oid() is not None

    _alembic("upgrade", STAGE6A_REVISION)
    assert _legacy_function_oid() is None

    _alembic("downgrade", PREV_REVISION)
    assert _legacy_function_oid() is None, (
        "downgrade must NOT recreate the unsafe legacy function"
    )


def test_downgrade_is_strict_on_schema_drift(safe_test_db):
    """Без IF EXISTS: если ограничение уже снято вручную, downgrade падает,
    а не маскирует рассинхрон.

    Ручной DROP CONSTRAINT коммитится сразу (своя транзакция _exec()).
    Падающий alembic downgrade откатывает СВОЮ транзакцию целиком — включая
    alembic_version, поэтому ревизия остаётся на head, а constraint уже
    отсутствует физически. Это ручной drift, который САМ этот тест обязан
    устранить (см. header модуля и _heal_manual_check_drift): обычный
    fixture teardown (`upgrade head` как no-op) его не лечит, а оставленный
    drift сломал бы последующие тесты этого модуля на той же disposable БД.
    """
    _alembic("upgrade", STAGE6A_REVISION)
    _exec("ALTER TABLE data_change_log DROP CONSTRAINT ck_dcl_record_id_positive")

    try:
        with pytest.raises(ProgrammingError):
            _alembic("downgrade", PREV_REVISION)
    finally:
        # 1. Вернуть ИМЕННО снятый constraint точным SQL (совпадает с
        #    migration/ORM) и подтвердить, что он снова существует.
        _heal_manual_check_drift("ck_dcl_record_id_positive")
        assert _constraint_exists("ck_dcl_record_id_positive")

        # 2. Детерминированно вернуть И revision, И физическую схему в
        #    согласованный head РЕАЛЬНЫМ циклом миграции (не одним патчем):
        #    теперь, когда constraint восстановлен вручную, настоящий
        #    downgrade успешно снимает все пять инвариантов, а upgrade заново
        #    создаёт их через штатный DDL-путь миграции.
        _alembic("downgrade", PREV_REVISION)
        _alembic("upgrade", STAGE6A_REVISION)


def test_round_trip_is_clean_immediately_after_strict_drift_scenario(safe_test_db):
    """Regression: доказывает, что сразу после strict-drift сценария (heal
    внутри теста, как в test_downgrade_is_strict_on_schema_drift) следующий
    downgrade/upgrade проходит БЕЗ какого-либо ДОПОЛНИТЕЛЬНОГО ручного
    вмешательства — drift не просачивается дальше точки heal.

    Тест самодостаточен (не полагается на порядок выполнения соседних тестов):
    сам воспроизводит тот же ручной drift + heal, а затем — начиная с
    отмеченной границы — вызывает ТОЛЬКО _alembic(...), без единого _exec()
    с ALTER/DROP CONSTRAINT.
    """
    _alembic("upgrade", STAGE6A_REVISION)
    _exec("ALTER TABLE data_change_log DROP CONSTRAINT ck_dcl_record_id_positive")
    with pytest.raises(ProgrammingError):
        _alembic("downgrade", PREV_REVISION)
    _heal_manual_check_drift("ck_dcl_record_id_positive")
    assert _constraint_exists("ck_dcl_record_id_positive")

    # ── Граница: с этой точки — НИ ОДНОГО ручного ALTER/DROP CONSTRAINT ─────
    _alembic("downgrade", PREV_REVISION)
    assert not _constraint_exists("ck_dcl_operation")
    assert not _constraint_exists("ck_dcl_changed_fields_nonempty")
    assert not _constraint_exists("ck_dcl_record_id_positive")
    assert not _column_is_not_null("record_id")
    assert not _column_is_not_null("changed_fields")

    _alembic("upgrade", STAGE6A_REVISION)
    assert _constraint_exists("ck_dcl_operation")
    assert _constraint_exists("ck_dcl_changed_fields_nonempty")
    assert _constraint_exists("ck_dcl_record_id_positive")
    assert _column_is_not_null("record_id")
    assert _column_is_not_null("changed_fields")
