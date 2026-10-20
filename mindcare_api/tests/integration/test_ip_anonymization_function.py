"""
Поведение функций IP-анонимизации и CLI на head-схеме (Stage 7B).

Схему НЕ двигает: работает на уже накаченной ревизии `c8e2b5f7a3d1`, поэтому
гейт MINDCARE_MIGRATION_ROUNDTRIP здесь не нужен.

ГЕРМЕТИЧНОСТЬ. `anonymize_old_ips` — ГЛОБАЛЬНАЯ мутация: она обнуляет
`ip_address` во всех строках старше границы, а не только в probe-строках. В
общей одноразовой БД полного прогона это задело бы данные соседних тестов.
Поэтому подавляющее большинство сценариев целиком выполняется внутри ОДНОЙ
транзакции, которая гарантированно откатывается: probe-строки, при
необходимости DDL партиций, вызов функции и все проверки. PostgreSQL
транзакционен и для DDL, так что после отката не остаётся ни строк, ни
партиций — teardown им не нужен.

Исключение — сценарии, которым нужен эффект МЕЖДУ соединениями (конкурентный
захват advisory lock, откат при сбое одного UPDATE, прогон CLI собственным
engine). Они используют зафиксированные probe-строки и точечный teardown по
собственным маркерам.

ГРАНИЦА ВРЕМЕНИ. `now()` в PostgreSQL — время НАЧАЛА транзакции, поэтому внутри
одной транзакции граница `now() - make_interval(days => N)` одинакова и в
INSERT probe-строк, и внутри функции. Это позволяет проверять границу точно, до
секунды, не завися от реального календаря.

Покрытие: T5-T16, T19, T37, T39, T41, T42, T45.
"""
import os
import re
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DatabaseError, InvalidRequestError

API_DIR = Path(__file__).resolve().parents[2]   # mindcare_api/
_SCRIPTS_DIR = API_DIR / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import anonymize_old_ips as cli  # noqa: E402

_TEST_DB_RE = re.compile(r"^mindcare_test_[a-z0-9]+$")

ANON_SIG = "public.anonymize_old_ips(integer)"
COUNT_SIG = "public.count_old_ips(integer)"

# Маркеры probe-строк: точечные фильтры очистки, ни с чем не пересекаются.
PROBE_MARKER = "ip_anon_fn_probe"
PROBE_IP = "203.0.113.7"        # TEST-NET-3 (RFC 5737), не реальный адрес

# Фиксированные даты внутри гарантированных baseline-партиций (2026-01..2028-12).
PROBE_2026_01 = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
PROBE_2026_07 = datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)
# Дата в будущем: попадает в существующую партицию, но НИКОГДА не «старая».
PROBE_FUTURE = datetime(2028, 12, 15, 12, 0, 0, tzinfo=timezone.utc)

# Партиция вне baseline-диапазона: создаётся тестом тем же DDL-паттерном, что и
# scripts/ensure_audit_partitions.py::_process_partition.
NEW_PARTITION = "audit_log_2025_01"
NEW_PARTITION_FROM = "2025-01-01"
NEW_PARTITION_TO = "2025-02-01"
PROBE_2025_01 = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

# Триггер для инъекции сбоя в ТРЕТИЙ по счёту UPDATE (data_change_log).
FAIL_TRIGGER = "ip_anon_fn_fail_trigger"
FAIL_TRIGGER_FN = "ip_anon_fn_fail_trigger_fn"
FAIL_PARTITION = "data_change_log_2026_07"

# Заведомо недостижимая граница: предикат не матчит ничего, мутации нет.
FAR_PAST_DAYS = 36500


# ── Соединения ───────────────────────────────────────────────────────────────

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


@contextmanager
def _rollback_tx():
    """Транзакция, которая ВСЕГДА откатывается — включая DDL.

    Всё, что сделано внутри (probe-строки, партиции, вызов функции), исчезает
    без следа, поэтому глобальная по своей природе мутация не задевает данные
    соседних тестов в общей одноразовой БД.
    """
    eng = _engine()
    try:
        with eng.connect() as conn:
            trans = conn.begin()
            try:
                yield conn
            finally:
                trans.rollback()
    finally:
        eng.dispose()


# ── Probe-строки ─────────────────────────────────────────────────────────────
# created_at задаётся ЯВНО: либо фиксированной датой, либо выражением от now()
# для проверки границы.

_INSERTS = {
    "audit_log": (
        "INSERT INTO audit_log (event_type, ip_address, created_at) "
        "VALUES (:m, CAST(:ip AS inet), {ts})"
    ),
    "auth_log": (
        "INSERT INTO auth_log (event, success, ip_address, created_at) "
        "VALUES (:m, TRUE, CAST(:ip AS inet), {ts})"
    ),
    "data_change_log": (
        "INSERT INTO data_change_log "
        "(table_name, record_id, operation, changed_fields, ip_address, created_at) "
        "VALUES (:m, 1, 'UPDATE', CAST('{{probe}}' AS text[]), "
        "CAST(:ip AS inet), {ts})"
    ),
}

_COUNTS = {
    "audit_log": "SELECT count(*) FROM audit_log WHERE event_type = :m",
    "auth_log": "SELECT count(*) FROM auth_log WHERE event = :m",
    "data_change_log": "SELECT count(*) FROM data_change_log WHERE table_name = :m",
}


def _insert_probe(conn, table, *, at=None, days_ago=None, seconds_extra=0, ip=PROBE_IP):
    """Вставляет probe-строку либо на фиксированную дату, либо на границу.

    `days_ago` строит created_at как `now() - make_interval(days => N)` —
    ровно то выражение, по которому функция считает cutoff, что и позволяет
    проверить границу точно.
    """
    if days_ago is None:
        ts_sql = ":ts"
        params = {"ts": at}
    else:
        ts_sql = (
            "now() - make_interval(days => :d) "
            "+ make_interval(secs => :extra)"
        )
        params = {"d": days_ago, "extra": seconds_extra}
    sql = _INSERTS[table].format(ts=ts_sql)
    conn.execute(text(sql), {"m": PROBE_MARKER, "ip": ip, **params})


def _probe_with_ip(conn, table) -> int:
    return conn.execute(
        text(_COUNTS[table] + " AND ip_address IS NOT NULL"), {"m": PROBE_MARKER}
    ).scalar()


def _probe_total(conn, table) -> int:
    return conn.execute(text(_COUNTS[table]), {"m": PROBE_MARKER}).scalar()


def _anonymize(conn, days) -> int:
    return conn.execute(
        text("SELECT public.anonymize_old_ips(:d)"), {"d": days}
    ).scalar()


def _count_old(conn, days) -> int:
    return conn.execute(
        text("SELECT public.count_old_ips(:d)"), {"d": days}
    ).scalar()


def _delete_committed_probes() -> None:
    """Удаляет ТОЛЬКО строки `committed_probes` — по маркеру И фиксированной
    дате разом. `committed_probes` вставляет строки исключительно на
    `PROBE_2026_07`; второе условие — defense-in-depth поверх и без того
    синтетического маркера, а не расширение охвата удаления."""
    _exec(
        "DELETE FROM audit_log WHERE event_type = :m AND created_at = :ts",
        m=PROBE_MARKER, ts=PROBE_2026_07,
    )
    _exec(
        "DELETE FROM auth_log WHERE event = :m AND created_at = :ts",
        m=PROBE_MARKER, ts=PROBE_2026_07,
    )
    _exec(
        "DELETE FROM data_change_log WHERE table_name = :m AND created_at = :ts",
        m=PROBE_MARKER, ts=PROBE_2026_07,
    )


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def guard_disposable_db():
    """Тесты мутируют журналы — работать только на одноразовой mindcare_test_*."""
    current = _scalar("SELECT current_database()")
    if not (current and _TEST_DB_RE.match(current)):
        raise RuntimeError(
            "ip anonymization tests require a disposable mindcare_test_<random> DB."
        )
    if _scalar("SELECT to_regprocedure(:s)::oid", s=ANON_SIG) is None:
        raise RuntimeError("migration c8e2b5f7a3d1 is not applied.")


@pytest.fixture()
def committed_probes():
    """Probe-строки, ЗАФИКСИРОВАННЫЕ в БД (нужны между соединениями)."""
    _delete_committed_probes()
    eng = _engine()
    try:
        with eng.begin() as conn:
            for table in _INSERTS:
                _insert_probe(conn, table, at=PROBE_2026_07)
    finally:
        eng.dispose()
    try:
        yield
    finally:
        _delete_committed_probes()


# ── T5 / T6: граница ─────────────────────────────────────────────────────────

def test_cutoff_boundary_is_strict():
    """T5 — строка ровно на границе НЕ анонимизируется, на секунду старше — да."""
    with _rollback_tx() as conn:
        # ровно cutoff  -> предикат `created_at < cutoff` ложен
        _insert_probe(conn, "audit_log", days_ago=1, seconds_extra=0)
        # на секунду раньше cutoff -> истинен
        _insert_probe(conn, "audit_log", days_ago=1, seconds_extra=-1)

        assert _probe_with_ip(conn, "audit_log") == 2
        affected = _anonymize(conn, 1)

        assert affected == 1
        assert _probe_with_ip(conn, "audit_log") == 1


def test_fresh_rows_are_not_touched():
    """T6 — свежие строки не затрагиваются."""
    with _rollback_tx() as conn:
        _insert_probe(conn, "audit_log", days_ago=0)      # created_at = now()

        assert _anonymize(conn, 1) == 0
        assert _probe_with_ip(conn, "audit_log") == 1


# ── T7 / T8 / T9 / T10 / T14: счётчик и идемпотентность ──────────────────────

def test_all_three_journals_are_anonymized():
    """T7 — обнуляются audit_log, auth_log и data_change_log."""
    with _rollback_tx() as conn:
        for table in _INSERTS:
            _insert_probe(conn, table, at=PROBE_2026_07)
            assert _probe_with_ip(conn, table) == 1

        _anonymize(conn, 1)

        for table in _INSERTS:
            assert _probe_with_ip(conn, table) == 0, table
            assert _probe_total(conn, table) == 1, f"{table}: строка не удалена"


def test_already_null_rows_are_not_counted():
    """T8 — строки с уже NULL не попадают в affected."""
    with _rollback_tx() as conn:
        before = _count_old(conn, 1)
        _insert_probe(conn, "audit_log", at=PROBE_2026_07, ip=None)
        _insert_probe(conn, "audit_log", at=PROBE_2026_07)

        # NULL-строка не увеличила число кандидатов.
        assert _count_old(conn, 1) == before + 1
        assert _anonymize(conn, 1) == before + 1


def test_second_run_affects_nothing():
    """T9 — повторный прогон в той же транзакции даёт 0.

    Advisory lock — transaction-level и принадлежит этой сессии, поэтому
    повторный захват в той же транзакции успешен и конфликта не создаёт.
    """
    with _rollback_tx() as conn:
        _insert_probe(conn, "audit_log", at=PROBE_2026_07)

        first = _anonymize(conn, 1)
        assert first >= 1

        assert _anonymize(conn, 1) == 0
        assert _count_old(conn, 1) == 0


def test_affected_count_is_exact_and_matches_counter():
    """T10 + T14 — affected равен числу кандидатов, а count_old_ips == anonymize."""
    with _rollback_tx() as conn:
        for table in _INSERTS:
            _insert_probe(conn, table, at=PROBE_2026_01)

        expected = _count_old(conn, 1)
        assert expected >= 3

        assert _anonymize(conn, 1) == expected
        assert _count_old(conn, 1) == 0


# ── T11 / T12: партиции ──────────────────────────────────────────────────────

def test_existing_partitions_are_all_covered():
    """T11 — строки в разных существующих партициях обрабатываются одинаково."""
    with _rollback_tx() as conn:
        _insert_probe(conn, "audit_log", at=PROBE_2026_01)
        _insert_probe(conn, "audit_log", at=PROBE_2026_07)
        _insert_probe(conn, "audit_log", at=PROBE_FUTURE)   # будущая дата

        assert _anonymize(conn, 1) == 2

        # Осталась ровно строка с датой в будущем — она никогда не «старая».
        remaining = conn.execute(text(
            "SELECT count(*) FROM audit_log "
            "WHERE event_type = :m AND ip_address IS NOT NULL AND created_at = :ts"
        ), {"m": PROBE_MARKER, "ts": PROBE_FUTURE}).scalar()
        assert remaining == 1


def test_newly_attached_partition_is_covered():
    """T12 — партиция, созданная после миграции, наследует поведение.

    DDL внутри транзакции откатывается вместе со всем остальным, поэтому
    партиция не остаётся в схеме.
    """
    with _rollback_tx() as conn:
        conn.execute(text(
            f"CREATE TABLE {NEW_PARTITION} PARTITION OF audit_log "
            f"FOR VALUES FROM ('{NEW_PARTITION_FROM}') TO ('{NEW_PARTITION_TO}')"
        ))
        _insert_probe(conn, "audit_log", at=PROBE_2025_01)

        # Строка физически лежит в новой партиции.
        assert conn.execute(text(
            f"SELECT count(*) FROM ONLY {NEW_PARTITION}"
        )).scalar() == 1

        assert _anonymize(conn, 1) == 1
        assert _probe_with_ip(conn, "audit_log") == 0


# ── T13: валидация аргумента ─────────────────────────────────────────────────

@pytest.mark.parametrize("days", [0, -1, None])
def test_invalid_days_raises_and_changes_nothing(committed_probes, days):
    """T13 — 0 / -1 / NULL отвергаются; legacy при 0 стирал бы ВСЕ адреса.

    Probe-строки ЗАФИКСИРОВАНЫ до вызова, поэтому «ничего не изменилось»
    проверяется на committed-состоянии, а не на строках той же откатываемой
    транзакции: это единственный способ отличить реальный отказ от отката.
    """
    eng = _engine()
    try:
        with eng.connect() as conn:
            trans = conn.begin()
            try:
                with pytest.raises(DatabaseError):
                    conn.execute(
                        text("SELECT public.anonymize_old_ips(CAST(:d AS integer))"),
                        {"d": days},
                    )
            finally:
                trans.rollback()
    finally:
        eng.dispose()

    eng = _engine()
    try:
        with eng.connect() as conn:
            for table in _INSERTS:
                assert _probe_with_ip(conn, table) == 1, table
    finally:
        eng.dispose()


@pytest.mark.parametrize("days", [0, -1, None])
def test_count_function_validates_identically(days):
    """Тот же валидатор у read-only счётчика: dry-run не мягче live."""
    with _rollback_tx() as conn:
        with pytest.raises(DatabaseError):
            conn.execute(
                text("SELECT public.count_old_ips(CAST(:d AS integer))"),
                {"d": days},
            )


def test_boolean_argument_does_not_resolve():
    """Неявного bool->int приведения нет: функция просто не находится."""
    with _rollback_tx() as conn:
        with pytest.raises(DatabaseError):
            conn.execute(text("SELECT public.anonymize_old_ips(true)"))


# ── T15: конкурентный запуск ─────────────────────────────────────────────────

def test_concurrent_invocation_is_rejected():
    """T15 — второй одновременный прогон падает, а не ждёт на row locks."""
    holder = _engine()
    rival = _engine()
    try:
        with holder.connect() as hconn:
            htx = hconn.begin()
            try:
                # Первая транзакция берёт advisory lock и держит его до конца.
                hconn.execute(
                    text("SELECT public.anonymize_old_ips(:d)"),
                    {"d": FAR_PAST_DAYS},
                )

                with rival.connect() as rconn:
                    rtx = rconn.begin()
                    try:
                        with pytest.raises(DatabaseError) as excinfo:
                            rconn.execute(
                                text("SELECT public.anonymize_old_ips(:d)"),
                                {"d": FAR_PAST_DAYS},
                            )
                        assert excinfo.value.orig.pgcode == "55P03"
                    finally:
                        rtx.rollback()
            finally:
                htx.rollback()
    finally:
        holder.dispose()
        rival.dispose()


def test_counter_does_not_take_the_lock():
    """count_old_ips не берёт lock — dry-run не мешает параллельному прогону."""
    holder = _engine()
    rival = _engine()
    try:
        with holder.connect() as hconn:
            htx = hconn.begin()
            try:
                hconn.execute(
                    text("SELECT public.anonymize_old_ips(:d)"),
                    {"d": FAR_PAST_DAYS},
                )
                with rival.connect() as rconn:
                    rtx = rconn.begin()
                    try:
                        # Не должно бросать: счётчик lock не запрашивает.
                        rconn.execute(
                            text("SELECT public.count_old_ips(:d)"),
                            {"d": FAR_PAST_DAYS},
                        )
                    finally:
                        rtx.rollback()
            finally:
                htx.rollback()
    finally:
        holder.dispose()
        rival.dispose()


# ── T16 / T45: сбой одного UPDATE откатывает всё ─────────────────────────────

@pytest.fixture()
def failing_third_update():
    """Триггер, роняющий UPDATE на партиции data_change_log (ТРЕТИЙ по счёту).

    К моменту его срабатывания audit_log и auth_log в той же транзакции уже
    обновлены — поэтому проверка «их IP на месте» доказывает именно откат, а не
    то, что до них не дошли.
    """
    _exec(f"""
        CREATE FUNCTION {FAIL_TRIGGER_FN}() RETURNS trigger AS $t$
        BEGIN
            RAISE EXCEPTION 'injected failure' USING ERRCODE = 'raise_exception';
        END;
        $t$ LANGUAGE plpgsql
    """)
    _exec(
        f"CREATE TRIGGER {FAIL_TRIGGER} BEFORE UPDATE ON {FAIL_PARTITION} "
        f"FOR EACH ROW EXECUTE FUNCTION {FAIL_TRIGGER_FN}()"
    )
    try:
        yield
    finally:
        _exec(f"DROP TRIGGER IF EXISTS {FAIL_TRIGGER} ON {FAIL_PARTITION}")
        _exec(f"DROP FUNCTION IF EXISTS {FAIL_TRIGGER_FN}()")


def test_failure_in_one_update_rolls_back_all(committed_probes, failing_third_update):
    """T16 — исключение пробрасывается наружу и откатывает уже сделанные UPDATE.

    Если бы функция имела внутренний EXCEPTION-блок и «проглатывала» сбой,
    исключение не дошло бы до вызывающего, и первые два UPDATE зафиксировались
    бы отдельной субтранзакцией.
    """
    eng = _engine()
    try:
        with eng.connect() as conn:
            trans = conn.begin()
            try:
                with pytest.raises(DatabaseError):
                    conn.execute(
                        text("SELECT public.anonymize_old_ips(:d)"), {"d": 1}
                    )
            finally:
                trans.rollback()
    finally:
        eng.dispose()

    # Свежее соединение: ни один из трёх журналов не потерял IP.
    eng = _engine()
    try:
        with eng.connect() as conn:
            for table in _INSERTS:
                assert _probe_with_ip(conn, table) == 1, table
    finally:
        eng.dispose()


def test_cli_live_failure_rolls_back(committed_probes, failing_third_update):
    """T45 — сбой рабочей функции откатывает транзакцию CLI целиком."""
    engine = cli.create_engine_for(os.environ["DATABASE_URL"])
    try:
        with pytest.raises(cli.PhaseError) as excinfo:
            cli.run(engine, days=1, dry_run=False)
        assert excinfo.value.phase == cli.PHASE_ANONYMIZE
    finally:
        engine.dispose()

    eng = _engine()
    try:
        with eng.connect() as conn:
            for table in _INSERTS:
                assert _probe_with_ip(conn, table) == 1, table
    finally:
        eng.dispose()


# ── T19 / T42 / T39: CLI на реальной БД ──────────────────────────────────────

def test_cli_dry_run_does_not_mutate(committed_probes):
    """T19 — dry-run не меняет ни одной строки."""
    engine = cli.create_engine_for(os.environ["DATABASE_URL"])
    try:
        result = cli.run(engine, days=1, dry_run=True)
    finally:
        engine.dispose()

    assert result >= 3   # три probe-строки заведомо старше границы

    eng = _engine()
    try:
        with eng.connect() as conn:
            for table in _INSERTS:
                assert _probe_with_ip(conn, table) == 1, table
    finally:
        eng.dispose()


@pytest.mark.parametrize("dry_run", [True, False])
def test_cli_preflight_and_work_share_one_transaction(dry_run):
    """T42 — autobegin не ломает контур: отдельного conn.begin() нет.

    Прежняя схема «preflight, затем conn.begin()» упала бы здесь с
    InvalidRequestError. days берётся заведомо недостижимым, поэтому live-режим
    безопасен: предикат не матчит ни одной строки.
    """
    engine = cli.create_engine_for(os.environ["DATABASE_URL"])
    try:
        result = cli.run(engine, days=FAR_PAST_DAYS, dry_run=dry_run)
    except InvalidRequestError as exc:      # pragma: no cover — регрессия
        pytest.fail(f"autobegin regression: {type(exc).__name__}")
    finally:
        engine.dispose()

    assert result == 0


def test_cli_main_returns_zero_on_dry_run():
    """main() возвращает код возврата, а не вызывает sys.exit — это тестируемо."""
    assert cli.main(["--days", str(FAR_PAST_DAYS), "--dry-run"]) == 0


def test_result_is_python_int_without_narrowing():
    """T39 — bigint приходит как Python int; 32-битного сужения на пути нет."""
    engine = cli.create_engine_for(os.environ["DATABASE_URL"])
    try:
        result = cli.run(engine, days=FAR_PAST_DAYS, dry_run=True)
    finally:
        engine.dispose()

    assert isinstance(result, int) and not isinstance(result, bool)

    # Значение вне 32-битного диапазона проходит драйвер без потерь — создавать
    # миллиарды строк для этого не требуется.
    big = 2 ** 40
    assert _scalar("SELECT CAST(:v AS bigint)", v=big) == big
    assert _scalar("SELECT pg_typeof(public.count_old_ips(:d))::text",
                   d=FAR_PAST_DAYS) == "bigint"


# ── T37 / T41: фазы preflight против реальной БД ─────────────────────────────

def test_preflight_detects_missing_functions():
    """T37 (фаза missing_function) — на настоящем SQL, без отката миграции.

    Функции удаляются ВНУТРИ транзакции: DDL транзакционен, поэтому откат
    возвращает их на место и схема не страдает.
    """
    with _rollback_tx() as conn:
        # Сначала контроль: на head проверка проходит.
        cli.preflight_functions_exist(conn)

        conn.execute(text(f"DROP FUNCTION {COUNT_SIG}"))

        with pytest.raises(cli.PhaseError) as excinfo:
            cli.preflight_functions_exist(conn)
        assert excinfo.value.phase == cli.PHASE_MISSING_FUNCTION

    # Откат вернул функцию.
    assert _scalar("SELECT to_regprocedure(:s)::oid", s=COUNT_SIG) is not None


def _can_create_role() -> bool:
    return bool(_scalar(
        "SELECT rolsuper OR rolcreaterole FROM pg_roles WHERE rolname = current_user"
    ))


@pytest.mark.parametrize("live, expected_phase", [
    (True, cli.PHASE_INSUFFICIENT_TABLE_PRIVILEGE),
    (False, cli.PHASE_INSUFFICIENT_TABLE_PRIVILEGE),
])
def test_preflight_detects_missing_table_privileges(live, expected_phase):
    """T41 — SECURITY INVOKER требует табличных прав; EXECUTE их не заменяет.

    Роль создаётся и переключается ВНУТРИ откатываемой транзакции: `SET LOCAL
    ROLE` действует до конца транзакции и снимается сама.
    """
    if not _can_create_role():
        pytest.skip("current_user cannot CREATE ROLE")

    role = "ip_anon_fn_probe_role"
    with _rollback_tx() as conn:
        conn.execute(text(f'CREATE ROLE "{role}" NOLOGIN'))
        conn.execute(text(f'GRANT EXECUTE ON FUNCTION {ANON_SIG} TO "{role}"'))
        conn.execute(text(f'GRANT EXECUTE ON FUNCTION {COUNT_SIG} TO "{role}"'))
        conn.execute(text(f'SET LOCAL ROLE "{role}"'))

        # EXECUTE есть — эта фаза проходит.
        cli.preflight_functions_exist(conn)
        cli.preflight_function_privileges(conn)

        # А табличных прав нет.
        with pytest.raises(cli.PhaseError) as excinfo:
            cli.preflight_table_privileges(conn, live=live)
        assert excinfo.value.phase == expected_phase


def test_preflight_passes_for_owner():
    """Контроль: у владельца проходят все три фазы в обоих режимах."""
    with _rollback_tx() as conn:
        cli.preflight_functions_exist(conn)
        cli.preflight_function_privileges(conn)
        cli.preflight_table_privileges(conn, live=True)
        cli.preflight_table_privileges(conn, live=False)


# ── Corrective pass: NOLOGIN-роль БЕЗ единого grant'а ────────────────────────

class _ConnAsEngine:
    """Адаптер: превращает уже открытое соединение в объект с API `engine.begin()`,
    которого ожидает `cli.run()`.

    Нужен, чтобы прогнать НАСТОЯЩИЙ `cli.run()` (не вызывать preflight-функции
    по отдельности вручную) внутри уже открытой, управляемой тестом транзакции —
    так же, как это делает `test_ip_anonymization_migration.py` не требуется,
    а здесь `_rollback_tx()` уже держит транзакцию, которую `cli.run()` не
    должен открывать заново.
    """

    def __init__(self, conn):
        self._conn = conn

    def begin(self):
        return self

    def __enter__(self):
        return self._conn

    def __exit__(self, exc_type, exc, tb):
        return False   # исключение не гасится — пробрасывается вызывающему


def test_no_grants_at_all_fails_at_function_privilege_phase():
    """Corrective pass, п.5 — NOLOGIN-роль БЕЗ единого grant'а (ни EXECUTE, ни
    табличных прав).

    `functions_exist` не зависит от прав вызывающего и обязана пройти;
    `preflight_function_privileges` обязана упасть первой из двух оставшихся
    фаз — именно на ней, а не на table-preflight (у роли нет прав ни там, ни
    там, поэтому важен порядок, а не сам факт отказа). Прогоняется через
    настоящий `cli.run()`, чтобы засвидетельствовать порядок вызовов реального
    production-контура, а не только ручную последовательность.

    Всё — внутри ОДНОЙ откатываемой транзакции; `SET LOCAL ROLE` действует до
    конца транзакции и снимается автоматическим rollback'ом, отдельный
    `RESET ROLE`/`DROP ROLE` не нужен.
    """
    if not _can_create_role():
        pytest.skip("current_user cannot CREATE ROLE")

    role = "ip_anon_fn_no_grants_role"
    with _rollback_tx() as conn:
        conn.execute(text(f'CREATE ROLE "{role}" NOLOGIN'))
        # Намеренно НИ ОДНОГО GRANT: ни EXECUTE, ни SELECT/UPDATE колонок.

        # Probe-строка, вставленная ЕЩЁ владельцем — до переключения роли —
        # чтобы после отказа проверить, что рабочая функция её не коснулась.
        _insert_probe(conn, "audit_log", at=PROBE_2026_07)
        assert _probe_with_ip(conn, "audit_log") == 1

        conn.execute(text(f'SET LOCAL ROLE "{role}"'))

        with pytest.raises(cli.PhaseError) as excinfo:
            cli.run(_ConnAsEngine(conn), days=1, dry_run=False)

        assert excinfo.value.phase == cli.PHASE_INSUFFICIENT_FUNCTION_PRIVILEGE

        # Роль лишена прав и на существование не влияет: проверяется отдельно,
        # чтобы «упало на верной фазе» не подтверждалось совпадением с любой
        # другой (роль без прав упала бы и на table-preflight).
        conn.execute(text("RESET ROLE"))
        cli.preflight_functions_exist(conn)   # не бросает — существование ОК

        conn.execute(text(f'SET LOCAL ROLE "{role}"'))
        with pytest.raises(cli.PhaseError) as excinfo2:
            cli.preflight_table_privileges(conn, live=False)
        assert (
            excinfo2.value.phase == cli.PHASE_INSUFFICIENT_TABLE_PRIVILEGE
        ), "у роли действительно нет и табличных прав — иначе тест бы ничего не доказывал"

        # Владельцем: probe-строка не тронута — до table-preflight и рабочей
        # функции дело не дошло у `cli.run()` выше.
        conn.execute(text("RESET ROLE"))
        assert _probe_with_ip(conn, "audit_log") == 1


# ── Corrective pass: schema-qualified preflight не путает shadow-таблицу ────

SHADOW_SCHEMA = "ip_anon_fn_shadow_schema"


def test_table_privilege_check_ignores_shadow_table_on_altered_search_path():
    """Corrective pass, п.2 — при изменённом `search_path` preflight не должен
    молча резолвиться на одноимённую таблицу в другой схеме.

    Создаётся `<shadow_schema>.audit_log` — таблица с теми же именами колонок,
    но БЕЗ единого grant'а какой-либо роли. Если бы `preflight_table_privileges`
    передавал голое имя `audit_log`, а `search_path` вызывающей роли ставил
    теневую схему ПЕРЕД `public`, проверка тихо отработала бы на подставном
    объекте вместо настоящего audit-журнала. Schema-qualified `public.<table>`
    делает это невозможным независимо от `search_path`.
    """
    if not _can_create_role():
        pytest.skip("current_user cannot CREATE ROLE")

    role = "ip_anon_fn_shadow_role"
    with _rollback_tx() as conn:
        conn.execute(text(f'CREATE SCHEMA "{SHADOW_SCHEMA}"'))
        conn.execute(text(f"""
            CREATE TABLE "{SHADOW_SCHEMA}".audit_log (
                created_at timestamptz,
                ip_address inet
            )
        """))

        conn.execute(text(f'CREATE ROLE "{role}" NOLOGIN'))
        # Роль владеет теневой таблицей (полные права на неё) и НЕ владеет
        # настоящей `public.audit_log`. Если бы preflight резолвился по
        # search_path на теневую схему, эта проверка ошибочно прошла бы.
        conn.execute(text(
            f'ALTER TABLE "{SHADOW_SCHEMA}".audit_log OWNER TO "{role}"'
        ))
        # USAGE на схему обязателен: без него PostgreSQL не находит объекты
        # теневой схемы через search_path вовсе (проверено отдельно — ниже
        # первый контрольный SELECT упал бы с InsufficientPrivilege, а не
        # вернул False), и тест перестал бы воспроизводить сценарий.
        conn.execute(text(f'GRANT USAGE ON SCHEMA "{SHADOW_SCHEMA}" TO "{role}"'))
        conn.execute(text(f'GRANT EXECUTE ON FUNCTION {ANON_SIG} TO "{role}"'))
        conn.execute(text(f'GRANT EXECUTE ON FUNCTION {COUNT_SIG} TO "{role}"'))

        conn.execute(text(f'SET LOCAL ROLE "{role}"'))
        conn.execute(text(f'SET LOCAL search_path = "{SHADOW_SCHEMA}", public'))

        # Явный контроль: голый `has_column_privilege('audit_log', ...)` при
        # ЭТОМ search_path резолвится на теневую таблицу, где у роли есть
        # SELECT (она её владелец) — то есть уязвимость реальна, если бы
        # preflight не квалифицировал имя схемой.
        unqualified_resolves_to_shadow = conn.execute(text(
            "SELECT has_column_privilege(current_user, 'audit_log', "
            "'created_at', 'SELECT')"
        )).scalar()
        assert unqualified_resolves_to_shadow is True

        # А сам preflight — schema-qualified, поэтому обязан упасть: у роли
        # нет прав на НАСТОЯЩУЮ public.audit_log.
        with pytest.raises(cli.PhaseError) as excinfo:
            cli.preflight_table_privileges(conn, live=False)
        assert excinfo.value.phase == cli.PHASE_INSUFFICIENT_TABLE_PRIVILEGE
