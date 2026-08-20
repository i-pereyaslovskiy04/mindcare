"""
Round-trip migration test для Stage 2 (audit_log.outcome / failure_reason_code).

ГЕЙТИНГ (не менять schema revision во время обычного full suite):
  - по умолчанию SKIPPED; запускается только при MINDCARE_MIGRATION_ROUNDTRIP=1;
  - при открытом gate любое нарушение безопасности — ОШИБКА, не skip:
      ENV=test, DATABASE_URL присутствует, current_database() ~ mindcare_test_<random>;
  - использует СОБСТВЕННЫЙ engine/connection (не SessionLocal / app engine) для
    проверок состояния; DDL прогоняется через Alembic (его собственный engine);
  - перед Alembic-командами свои соединения закрыты и dispose'нуты;
  - используются ТОЧНЫЕ revision ID (не downgrade -1);
  - после проверок БД остаётся на head; одноразовую БД удалит Stage 1 runner.

Отдельный запуск (disposable PostgreSQL, credentials только через TEST_DATABASE_URL):
  ENV=test MINDCARE_MIGRATION_ROUNDTRIP=1 TEST_DATABASE_URL=... \
      python scripts/isolated_test_db.py -k audit_outcome_migration -v

strict-drift (downgrade без IF EXISTS) проверяется статически в
tests/test_audit_outcome_model.py, а не деструктивным кейсом здесь.

Все probe-строки используют ФИКСИРОВАННЫЕ синтетические даты (не date.today()/
DEFAULT now()), чтобы тест не зависел от того, в каком месяце он запускается, и
детерминированно попадал в гарантированные baseline-партиции (2026-01..2028-12,
migration 3a7c5e2b8f1d) либо в отдельно созданную far-future партицию.
"""
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

STAGE2_REVISION = "f2a9c4e7b1d8"
PREV_REVISION = "3b46b9d94c08"
_TEST_DB_RE = re.compile(r"^mindcare_test_[a-z0-9]+$")
_PROBE = "roundtrip_probe_stage2"          # синтетический event, без ПДн
API_DIR = Path(__file__).resolve().parents[2]   # mindcare_api/

# Фиксированная дата внутри гарантированной baseline-партиции (3a7c5e2b8f1d
# создаёт 2026-01..2028-12) — НЕ date.today(), не зависит от даты запуска теста.
PROBE_CREATED_AT = datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)
PROBE_PARTITION = "audit_log_2026_07"

# Отдельная baseline-партиция (не default для probe) — для проверки, что CHECK
# реально enforced на insert, роутящийся именно в эту, специально выбранную
# партицию, а не только в ту, что используется по умолчанию выше.
CHECK_PROBE_CREATED_AT = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
CHECK_PROBE_PARTITION = "audit_log_2026_01"

# Синтетическая far-future партиция, создаваемая ТЕМ ЖЕ DDL-паттерном, что
# scripts/ensure_audit_partitions.py::_process_partition (CREATE TABLE ...
# PARTITION OF ... FOR VALUES FROM (...) TO (...)) — уникальное безопасное имя,
# далёкий диапазон, не пересекается с baseline "_YYYY_MM".
FUTURE_PARTITION_NAME = "audit_log_stage2_roundtrip_future_probe"
FUTURE_PARTITION_FROM = "2099-01-01"
FUTURE_PARTITION_TO = "2099-02-01"
FUTURE_CREATED_AT = datetime(2099, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

pytestmark = pytest.mark.skipif(
    os.environ.get("MINDCARE_MIGRATION_ROUNDTRIP") != "1",
    reason="round-trip migration disabled (set MINDCARE_MIGRATION_ROUNDTRIP=1)",
)


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


def _fetchall(sql, **params):
    eng = _engine()
    try:
        with eng.connect() as c:
            return c.execute(text(sql), params).fetchall()
    finally:
        eng.dispose()


def _column_exists(table: str, column: str) -> int:
    return _scalar(
        "SELECT count(*) FROM information_schema.columns "
        "WHERE table_name = :t AND column_name = :c",
        t=table, c=column,
    )


def _all_audit_log_partitions() -> list:
    """Полный список существующих партиций audit_log через pg_inherits/pg_class."""
    rows = _fetchall(
        """
        SELECT c.relname
        FROM pg_inherits i
        JOIN pg_class p ON p.oid = i.inhparent
        JOIN pg_class c ON c.oid = i.inhrelid
        JOIN pg_namespace pn ON pn.oid = p.relnamespace
        WHERE pn.nspname = 'public' AND p.relname = 'audit_log'
        ORDER BY c.relname
        """
    )
    return [r[0] for r in rows]


def _partition_has_outcome_index(partition: str) -> bool:
    """Партиция имеет дочерний индекс, унаследованный от idx_audit_outcome
    (через pg_inherits на уровне отношений-индексов, PG11+ partitioned index)."""
    return bool(_scalar(
        """
        SELECT count(*) > 0
        FROM pg_inherits pi
        JOIN pg_class child_idx  ON child_idx.oid  = pi.inhrelid
        JOIN pg_class parent_idx ON parent_idx.oid = pi.inhparent
        JOIN pg_index idx ON idx.indexrelid = child_idx.oid
        JOIN pg_class c   ON c.oid = idx.indrelid
        WHERE parent_idx.relname = 'idx_audit_outcome' AND c.relname = :p
        """,
        p=partition,
    ))


def _alembic(action: str, revision: str) -> None:
    # Свои соединения уже dispose'нуты вызывающим кодом; Alembic online-режим
    # открывает собственный engine (NullPool) через env.py — не app SessionLocal.
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_DIR / "alembic"))
    if action == "upgrade":
        command.upgrade(cfg, revision)
    else:
        command.downgrade(cfg, revision)


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
    # Downgrade проходит НИЖЕ ревизий Stage 5C, а те fail-closed отказываются
    # откатываться при исторических ссылках на schedule_series. Такие строки
    # появляются от gated-тестов 5C в общем прогоне — это несовместимый режим
    # запуска, а не регрессия миграции outcome. Пропускаем явно.
    if _scalar(
        "SELECT count(*) FROM audit_log WHERE entity_type = 'schedule_series'"
    ):
        pytest.skip(
            "round-trip requires a pristine DB: audit_log already references "
            "schedule_series (run separately with -k audit_outcome_migration)"
        )
    yield
    # Оставить БД на head (повторный upgrade); саму БД удалит Stage 1 runner.
    _alembic("upgrade", STAGE2_REVISION)


def _insert_event(event: str, created_at: datetime, outcome: str = None) -> None:
    """Явный created_at ВСЕГДА — без DEFAULT now(), детерминированная партиция."""
    eng = _engine()
    try:
        with eng.begin() as c:
            if outcome is None:
                c.execute(
                    text(
                        "INSERT INTO audit_log (event_type, created_at) "
                        "VALUES (:e, :ts)"
                    ),
                    {"e": event, "ts": created_at},
                )
            else:
                c.execute(
                    text(
                        "INSERT INTO audit_log (event_type, created_at, outcome) "
                        "VALUES (:e, :ts, :o)"
                    ),
                    {"e": event, "ts": created_at, "o": outcome},
                )
    finally:
        eng.dispose()


def _insert_invalid_outcome(event: str, created_at: datetime) -> None:
    """INSERT с outcome вне ('success','failure') — ожидается IntegrityError (CHECK)."""
    eng = _engine()
    try:
        with eng.begin() as c:
            c.execute(
                text(
                    "INSERT INTO audit_log (event_type, created_at, outcome) "
                    "VALUES (:e, :ts, 'bogus')"
                ),
                {"e": event, "ts": created_at},
            )
    finally:
        eng.dispose()


def _create_partition_like_ensure_script(
    schema: str, table: str, partition_name: str, from_dt: str, to_dt: str
) -> None:
    """Тот же DDL-паттерн, что scripts/ensure_audit_partitions.py::_process_partition."""
    eng = _engine()
    try:
        with eng.begin() as c:
            c.execute(text(
                f"CREATE TABLE {schema}.{partition_name} "
                f"PARTITION OF {schema}.{table} "
                f"FOR VALUES FROM ('{from_dt}') TO ('{to_dt}')"
            ))
    finally:
        eng.dispose()


def test_audit_outcome_migration_roundtrip(safe_test_db):
    # 1. downgrade к предыдущей ревизии (точный ID).
    _alembic("downgrade", PREV_REVISION)
    assert _column_exists("audit_log", "outcome") == 0

    # 2. синтетическая «легаси» строка (без ПДн, без колонки outcome), явный
    #    фиксированный created_at внутри гарантированной baseline-партиции.
    _insert_event(_PROBE, PROBE_CREATED_AT)

    # 3. upgrade к Stage 2 (точный ID).
    _alembic("upgrade", STAGE2_REVISION)

    # 4. backfill существующей строки → 'success'.
    assert _scalar(
        "SELECT outcome FROM audit_log WHERE event_type = :e", e=_PROBE
    ) == "success"

    # 5. ВСЕ существующие партиции audit_log — не только >= 1, а каждая.
    existing_partitions = _all_audit_log_partitions()
    assert len(existing_partitions) >= 36, existing_partitions  # 2026-01..2028-12
    assert PROBE_PARTITION in existing_partitions
    assert CHECK_PROBE_PARTITION in existing_partitions
    for partition in existing_partitions:
        assert _column_exists(partition, "outcome") == 1, partition
        assert _column_exists(partition, "failure_reason_code") == 1, partition
        assert _partition_has_outcome_index(partition), partition

    # 6. INSERT без outcome → success; success/failure принимаются.
    _insert_event(_PROBE + "_2", PROBE_CREATED_AT)
    _insert_event(_PROBE + "_3", PROBE_CREATED_AT, outcome="failure")
    assert _scalar(
        "SELECT outcome FROM audit_log WHERE event_type = :e", e=_PROBE + "_2"
    ) == "success"

    # 7. CHECK реально применяется к вставке в выбранную (не default) партицию:
    #    default-партиция probe (2026_07) и отдельно выбранная (2026_01).
    with pytest.raises(IntegrityError):
        _insert_invalid_outcome(_PROBE + "_bad_default", PROBE_CREATED_AT)
    with pytest.raises(IntegrityError):
        _insert_invalid_outcome(_PROBE + "_bad_selected", CHECK_PROBE_CREATED_AT)

    # 8. Новая партиция — тем же DDL-паттерном, что ensure_audit_partitions.py,
    #    далёкий синтетический диапазон, уникальное безопасное имя.
    _create_partition_like_ensure_script(
        "public", "audit_log", FUTURE_PARTITION_NAME,
        FUTURE_PARTITION_FROM, FUTURE_PARTITION_TO,
    )
    assert _column_exists(FUTURE_PARTITION_NAME, "outcome") == 1
    assert _column_exists(FUTURE_PARTITION_NAME, "failure_reason_code") == 1
    assert _partition_has_outcome_index(FUTURE_PARTITION_NAME)
    # default success на новой партиции
    _insert_event(_PROBE + "_future", FUTURE_CREATED_AT)
    assert _scalar(
        "SELECT outcome FROM audit_log WHERE event_type = :e",
        e=_PROBE + "_future",
    ) == "success"
    # CHECK enforced на новой партиции
    with pytest.raises(IntegrityError):
        _insert_invalid_outcome(_PROBE + "_future_bad", FUTURE_CREATED_AT)

    # 9. downgrade к предыдущей ревизии (точный ID).
    _alembic("downgrade", PREV_REVISION)

    # 10. строки и ВСЕ партиции (включая новую) сохранены; Stage 2 колонки
    #     отсутствуют на каждой партиции.
    assert _scalar(
        "SELECT count(*) FROM audit_log WHERE event_type = :e", e=_PROBE
    ) >= 1
    assert _scalar(
        "SELECT count(*) FROM audit_log WHERE event_type = :e",
        e=_PROBE + "_future",
    ) >= 1
    assert _column_exists("audit_log", "outcome") == 0
    assert _column_exists("audit_log", "failure_reason_code") == 0
    partitions_after_downgrade = _all_audit_log_partitions()
    assert FUTURE_PARTITION_NAME in partitions_after_downgrade
    for partition in partitions_after_downgrade:
        assert _column_exists(partition, "outcome") == 0, partition
        assert _column_exists(partition, "failure_reason_code") == 0, partition

    # 11. upgrade обратно к Stage 2 — восстановление на parent и на новой партиции.
    _alembic("upgrade", STAGE2_REVISION)
    assert _column_exists("audit_log", "outcome") == 1
    assert _column_exists("audit_log", "failure_reason_code") == 1
    assert _column_exists(FUTURE_PARTITION_NAME, "outcome") == 1
    assert _column_exists(FUTURE_PARTITION_NAME, "failure_reason_code") == 1
    assert _partition_has_outcome_index(FUTURE_PARTITION_NAME)
