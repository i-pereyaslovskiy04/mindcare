"""
Round-trip migration test для Stage 8 (хронологические индексы трёх журналов).

ГЕЙТИНГ: по умолчанию SKIPPED, запускается только при
`MINDCARE_MIGRATION_ROUNDTRIP=1`. При открытом gate любое нарушение
безопасности — ОШИБКА, а не skip (ENV=test, `current_database()` совпадает с
`mindcare_test_<random>`).

Отдельный запуск:
  ENV=test MINDCARE_MIGRATION_ROUNDTRIP=1 TEST_DATABASE_URL=... \
      python scripts/isolated_test_db.py -k audit_created_indexes_migration -v

Проверяется то, ради чего индексы объявлены на partitioned parent: PostgreSQL
обязан материализовать дочерний индекс на КАЖДОЙ существующей партиции и на
каждой новой. Для `auth_log` и `data_change_log` такой проверки в проекте
раньше не было вообще — существующий Stage 2 round-trip покрывал только
`audit_log`.

Строки-пробники не вставляются: ревизия не трогает данные ни в одну сторону.
"""
import os
import re
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

REVISION = "e6c3a9f1d574"
PREV_REVISION = "c8e2b5f7a3d1"

API_DIR = Path(__file__).resolve().parents[2]        # mindcare_api/
_TEST_DB_RE = re.compile(r"^mindcare_test_[a-z0-9]+$")

# (родительская таблица, имя индекса), объявленные ревизией.
TARGETS = (
    ("audit_log", "idx_audit_created"),
    ("auth_log", "idx_auth_created"),
    ("data_change_log", "idx_dcl_created"),
)

# Индексы соседних ревизий: downgrade обязан их не тронуть.
FOREIGN_INDEXES = (
    ("audit_log", "idx_audit_outcome"),
    ("audit_log", "idx_audit_user"),
    ("auth_log", "idx_auth_user"),
    ("data_change_log", "idx_dcl_actor"),
)

# Синтетическая far-future партиция, создаваемая ТЕМ ЖЕ DDL-паттерном, что и
# scripts/ensure_audit_partitions.py — далёкий диапазон, не пересекается с
# baseline-партициями "_YYYY_MM" (2026-01..2028-12).
FUTURE_SUFFIX = "stage8_created_idx_future_probe"
FUTURE_FROM = "2098-01-01"
FUTURE_TO = "2098-02-01"

pytestmark = pytest.mark.skipif(
    os.environ.get("MINDCARE_MIGRATION_ROUNDTRIP") != "1",
    reason="round-trip migration disabled (set MINDCARE_MIGRATION_ROUNDTRIP=1)",
)


# ── Собственный engine (не SessionLocal приложения) ──────────────────────────

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


def _execute(sql, **params):
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


# ── Интроспекция ──────────────────────────────────────────────────────────────

def _parent_index_exists(index_name: str) -> bool:
    """Индекс существует на самой партиционированной таблице (relkind 'I')."""
    return bool(_scalar(
        """
        SELECT count(*) > 0
        FROM pg_class i
        JOIN pg_namespace n ON n.oid = i.relnamespace
        WHERE n.nspname = 'public' AND i.relname = :name AND i.relkind = 'I'
        """,
        name=index_name,
    ))


def _index_exists_at_all(index_name: str) -> bool:
    return bool(_scalar(
        "SELECT count(*) > 0 FROM pg_class WHERE relname = :name",
        name=index_name,
    ))


def _partitions(parent: str) -> list:
    rows = _fetchall(
        """
        SELECT c.relname
        FROM pg_inherits i
        JOIN pg_class p ON p.oid = i.inhparent
        JOIN pg_class c ON c.oid = i.inhrelid
        JOIN pg_namespace pn ON pn.oid = p.relnamespace
        WHERE pn.nspname = 'public' AND p.relname = :parent
        ORDER BY c.relname
        """,
        parent=parent,
    )
    return [r[0] for r in rows]


def _partition_has_child_index(partition: str, parent_index: str) -> bool:
    """Партиция несёт дочерний индекс, унаследованный от partitioned index."""
    return bool(_scalar(
        """
        SELECT count(*) > 0
        FROM pg_inherits pi
        JOIN pg_class child_idx  ON child_idx.oid  = pi.inhrelid
        JOIN pg_class parent_idx ON parent_idx.oid = pi.inhparent
        JOIN pg_index idx ON idx.indexrelid = child_idx.oid
        JOIN pg_class c   ON c.oid = idx.indrelid
        WHERE parent_idx.relname = :parent_index AND c.relname = :partition
        """,
        parent_index=parent_index, partition=partition,
    ))


def _index_columns(index_name: str) -> list:
    rows = _fetchall(
        """
        SELECT a.attname
        FROM pg_class i
        JOIN pg_index idx ON idx.indexrelid = i.oid
        JOIN pg_attribute a
          ON a.attrelid = idx.indrelid AND a.attnum = ANY(idx.indkey)
        WHERE i.relname = :name
        ORDER BY array_position(idx.indkey, a.attnum)
        """,
        name=index_name,
    )
    return [r[0] for r in rows]


# ── Fixture ───────────────────────────────────────────────────────────────────

@pytest.fixture()
def safe_test_db():
    if os.environ.get("ENV") != "test":
        raise RuntimeError("roundtrip: ENV must be 'test'.")
    if not os.environ.get("DATABASE_URL"):
        raise RuntimeError("roundtrip: DATABASE_URL must be present.")
    current = _scalar("SELECT current_database()")
    if not (current and _TEST_DB_RE.match(current)):
        raise RuntimeError(
            "roundtrip: current_database() must be mindcare_test_<random>."
        )
    yield
    # Оставить БД на head; саму одноразовую БД удалит Stage 1 runner.
    _alembic("upgrade", REVISION)
    _drop_future_partitions()


def _future_name(parent: str) -> str:
    return f"{parent}_{FUTURE_SUFFIX}"


def _drop_future_partitions() -> None:
    for parent, _ in TARGETS:
        _execute(f"DROP TABLE IF EXISTS {_future_name(parent)}")


# ── Тесты ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("parent,index_name", TARGETS)
def test_index_lives_on_the_partitioned_parent(safe_test_db, parent, index_name):
    _alembic("upgrade", REVISION)
    assert _parent_index_exists(index_name), (
        f"{index_name} должен быть partitioned index на {parent}"
    )
    assert _index_columns(index_name) == ["created_at", "id"]


@pytest.mark.parametrize("parent,index_name", TARGETS)
def test_every_existing_partition_inherits_the_index(
    safe_test_db, parent, index_name,
):
    _alembic("upgrade", REVISION)
    partitions = _partitions(parent)
    assert len(partitions) >= 36, f"{parent}: ожидались baseline-партиции"

    missing = [
        p for p in partitions if not _partition_has_child_index(p, index_name)
    ]
    assert not missing, f"{parent}: партиции без дочернего индекса: {missing}"


@pytest.mark.parametrize("parent,index_name", TARGETS)
def test_new_future_partition_inherits_the_index(safe_test_db, parent, index_name):
    """`PARTITION OF` наследует индексы parent'а — поэтому
    scripts/ensure_audit_partitions.py править не пришлось."""
    _alembic("upgrade", REVISION)
    name = _future_name(parent)
    _execute(
        f"CREATE TABLE IF NOT EXISTS {name} PARTITION OF {parent} "
        f"FOR VALUES FROM ('{FUTURE_FROM}') TO ('{FUTURE_TO}')"
    )
    try:
        assert _partition_has_child_index(name, index_name)
    finally:
        _execute(f"DROP TABLE IF EXISTS {name}")


def test_downgrade_removes_only_this_revision_indexes(safe_test_db):
    _alembic("upgrade", REVISION)
    _alembic("downgrade", PREV_REVISION)

    for _, index_name in TARGETS:
        assert not _index_exists_at_all(index_name), (
            f"{index_name} должен исчезнуть после downgrade"
        )
    for _, foreign in FOREIGN_INDEXES:
        assert _index_exists_at_all(foreign), (
            f"{foreign} принадлежит другой ревизии и трогать его нельзя"
        )


def test_downgrade_also_removes_child_indexes(safe_test_db):
    """DROP INDEX на parent каскадно снимает дочерние — отдельного DDL по
    партициям ревизия не содержит и не должна содержать."""
    _alembic("upgrade", REVISION)
    _alembic("downgrade", PREV_REVISION)

    for parent, index_name in TARGETS:
        for partition in _partitions(parent):
            assert not _partition_has_child_index(partition, index_name)


def test_upgrade_downgrade_upgrade_is_repeatable(safe_test_db):
    _alembic("upgrade", REVISION)
    _alembic("downgrade", PREV_REVISION)
    _alembic("upgrade", REVISION)

    for parent, index_name in TARGETS:
        assert _parent_index_exists(index_name)
        assert all(
            _partition_has_child_index(p, index_name) for p in _partitions(parent)
        )


def test_alembic_version_is_the_new_head_after_upgrade(safe_test_db):
    _alembic("upgrade", REVISION)
    assert _scalar("SELECT version_num FROM alembic_version") == REVISION


def test_migration_changes_no_journal_rows(safe_test_db):
    """Ревизия только создаёт/удаляет индексы: количество строк не меняется."""
    _alembic("upgrade", REVISION)
    before = {
        parent: _scalar(f"SELECT count(*) FROM {parent}") for parent, _ in TARGETS
    }
    _alembic("downgrade", PREV_REVISION)
    _alembic("upgrade", REVISION)
    after = {
        parent: _scalar(f"SELECT count(*) FROM {parent}") for parent, _ in TARGETS
    }
    assert before == after
