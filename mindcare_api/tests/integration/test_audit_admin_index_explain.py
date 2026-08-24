"""
Stage 8 — измерение планов ДО добавления новых индексов.

Задача решает один вопрос: достаточно ли трёх хронологических индексов
`(created_at, id)` для ленты admin viewer, или нужны дополнительные по
`event_type` / `table_name` / `success`. Набор «на всякий случай» не
добавляется — сначала замер.

ГЕЙТИНГ: по умолчанию SKIPPED (`MINDCARE_AUDIT_EXPLAIN=1`). Тест наполняет
журналы синтетическим объёмом, поэтому в обычный прогон он не входит:
вставленные строки видны другим тестам.

Утверждается только устойчивый инвариант — план основной ленты идёт по
`*_created`-индексу и не содержит узла `Sort` (индекс уже даёт нужный порядок).
Планы фильтрованных запросов выводятся как диагностика, без assert'ов: их выбор
зависит от селективности и версии PostgreSQL, и превращать это в тест значило бы
получить плавающее падение.
"""
import os

import pytest
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.skipif(
    os.environ.get("MINDCARE_AUDIT_EXPLAIN") != "1",
    reason="index EXPLAIN probe disabled (set MINDCARE_AUDIT_EXPLAIN=1)",
)

# Объём, при котором планировщик уже предпочитает индекс последовательному
# чтению партиций. Строки синтетические, без ПДн: только счётчики и enum'ы.
ROWS = 40_000
WINDOW_DAYS = 90


def _engine():
    return create_engine(
        os.environ["DATABASE_URL"], connect_args={"client_encoding": "utf8"}
    )


@pytest.fixture(scope="module")
def seeded():
    eng = _engine()
    try:
        with eng.begin() as c:
            c.execute(text(
                """
                INSERT INTO audit_log
                    (event_type, user_id, user_role, entity_type, entity_id,
                     outcome, created_at)
                SELECT
                    CASE WHEN g % 3 = 0 THEN 'admin_role_add'
                         WHEN g % 3 = 1 THEN 'appointment_created'
                         ELSE 'chat_message_edited' END,
                    NULL, 'admin', 'user', (g % 500) + 1,
                    CASE WHEN g % 97 = 0 THEN 'failure' ELSE 'success' END,
                    TIMESTAMPTZ '2027-01-01 00:00:00+03'
                        + (g % (:days * 24)) * INTERVAL '1 hour'
                FROM generate_series(1, :rows) AS g
                """
            ), {"rows": ROWS, "days": WINDOW_DAYS})
            c.execute(text(
                """
                INSERT INTO auth_log (event, user_id, success, created_at)
                SELECT
                    CASE WHEN g % 4 = 0 THEN 'failed_login' ELSE 'login' END,
                    NULL, g % 4 <> 0,
                    TIMESTAMPTZ '2027-01-01 00:00:00+03'
                        + (g % (:days * 24)) * INTERVAL '1 hour'
                FROM generate_series(1, :rows) AS g
                """
            ), {"rows": ROWS, "days": WINDOW_DAYS})
            c.execute(text(
                """
                INSERT INTO data_change_log
                    (actor_id, actor_role, table_name, record_id, operation,
                     changed_fields, created_at)
                SELECT
                    NULL, 'admin',
                    CASE WHEN g % 2 = 0 THEN 'meeting_types' ELSE 'group_sessions' END,
                    (g % 500) + 1, 'UPDATE', ARRAY['title']::text[],
                    TIMESTAMPTZ '2027-01-01 00:00:00+03'
                        + (g % (:days * 24)) * INTERVAL '1 hour'
                FROM generate_series(1, :rows) AS g
                """
            ), {"rows": ROWS, "days": WINDOW_DAYS})
            c.execute(text("ANALYZE audit_log"))
            c.execute(text("ANALYZE auth_log"))
            c.execute(text("ANALYZE data_change_log"))
    finally:
        eng.dispose()
    yield
    # Одноразовую БД удалит Stage 1 runner; чистка здесь не нужна.


def _plan(sql: str, **params) -> str:
    eng = _engine()
    try:
        with eng.connect() as c:
            rows = c.execute(text(f"EXPLAIN {sql}"), params).fetchall()
    finally:
        eng.dispose()
    return "\n".join(r[0] for r in rows)


_WINDOW = (
    "created_at >= TIMESTAMPTZ '2027-02-01 00:00:00+03' "
    "AND created_at < TIMESTAMPTZ '2027-03-01 00:00:00+03'"
)

FEEDS = [
    ("audit_log", "idx_audit_created"),
    ("auth_log", "idx_auth_created"),
    ("data_change_log", "idx_dcl_created"),
]


def _child_index_names(parent_index: str) -> set:
    """Имена дочерних индексов, унаследованных партициями от partitioned index.

    В плане фигурирует именно ДОЧЕРНИЙ индекс: окно по `created_at` отсекает все
    партиции кроме одной, и сканируется её собственный индекс с автоматически
    сгенерированным именем вида `<partition>_created_at_id_idx`. Искать в плане
    имя родительского индекса бессмысленно — связь с ним восстанавливается
    через `pg_inherits`.
    """
    eng = _engine()
    try:
        with eng.connect() as c:
            rows = c.execute(text(
                """
                SELECT child_idx.relname
                FROM pg_inherits pi
                JOIN pg_class child_idx  ON child_idx.oid  = pi.inhrelid
                JOIN pg_class parent_idx ON parent_idx.oid = pi.inhparent
                WHERE parent_idx.relname = :parent
                """
            ), {"parent": parent_index}).fetchall()
    finally:
        eng.dispose()
    return {r[0] for r in rows}


@pytest.mark.parametrize("table,index_name", FEEDS)
def test_default_feed_uses_the_chronological_index(seeded, table, index_name, capsys):
    plan = _plan(
        f"SELECT id, created_at FROM {table} WHERE {_WINDOW} "
        f"ORDER BY created_at DESC, id DESC LIMIT 20"
    )
    with capsys.disabled():
        print(f"\n=== {table}: лента по умолчанию ===\n{plan}")

    children = _child_index_names(index_name)
    assert children, f"{index_name}: дочерние индексы не созданы"
    assert any(name in plan for name in children), (
        f"{table}: план не использует ни один дочерний индекс {index_name}"
    )
    assert "Sort" not in plan, (
        f"{table}: появилась внешняя сортировка — индекс не даёт нужный порядок"
    )
    assert "Seq Scan" not in plan, f"{table}: последовательное чтение партиции"


@pytest.mark.parametrize("table", [t for t, _ in FEEDS])
def test_window_prunes_partitions(seeded, table, capsys):
    """Фильтр по created_at обязан отсекать лишние месячные партиции."""
    plan = _plan(
        f"SELECT count(*) FROM {table} WHERE {_WINDOW}"
    )
    with capsys.disabled():
        print(f"\n=== {table}: count по окну ===\n{plan}")

    scanned = [ln for ln in plan.splitlines() if f"{table}_20" in ln]
    assert scanned, "план не содержит партиций — проверьте формат вывода"
    assert len(scanned) <= 3, (
        f"{table}: просматривается {len(scanned)} партиций вместо 1–2 — "
        "похоже, partition pruning не сработал"
    )


# ── Диагностика фильтрованных запросов (без assert'ов) ───────────────────────

def test_report_filtered_plans(seeded, capsys):
    """Материал для решения о дополнительных индексах.

    Assert'ов здесь нет намеренно: выбор плана зависит от селективности и
    версии PostgreSQL, поэтому фиксировать его тестом значило бы получить
    плавающее падение. Вывод приводится в отчёте по задаче.
    """
    probes = {
        "audit_log + event_type": (
            "SELECT id FROM audit_log WHERE " + _WINDOW +
            " AND event_type = 'admin_role_add'"
            " ORDER BY created_at DESC, id DESC LIMIT 20"
        ),
        "audit_log + outcome": (
            "SELECT id FROM audit_log WHERE " + _WINDOW +
            " AND outcome = 'failure'"
            " ORDER BY created_at DESC, id DESC LIMIT 20"
        ),
        "auth_log + success": (
            "SELECT id FROM auth_log WHERE " + _WINDOW +
            " AND success IS FALSE"
            " ORDER BY created_at DESC, id DESC LIMIT 20"
        ),
        "data_change_log + table_name": (
            "SELECT id FROM data_change_log WHERE " + _WINDOW +
            " AND table_name = 'meeting_types'"
            " ORDER BY created_at DESC, id DESC LIMIT 20"
        ),
    }
    with capsys.disabled():
        for label, sql in probes.items():
            print(f"\n=== {label} ===\n{_plan(sql)}")
