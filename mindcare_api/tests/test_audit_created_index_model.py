"""
Stage 8 — хронологические индексы трёх журналов: ORM ↔ миграция, без PostgreSQL.

Индексы `(created_at, id)` обслуживают ленту admin viewer: составной PK
партиционированных журналов — `(id, created_at)`, поэтому упорядоченное окно по
времени им не покрывается.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.db.models.audit import AuditLog, AuthLog, DataChangeLog

# Predecessor зафиксирован ДО создания ревизии (`alembic heads` на шаге 0).
# Сравнивать `down_revision` с ТЕКУЩИМ head нельзя: после добавления миграции
# текущим head стала она сама.
PREDECESSOR = "c8e2b5f7a3d1"
REVISION = "e6c3a9f1d574"

# Текущий global alembic head — обновляется каждой следующей миграцией
# (последняя правка: d14143842079_add_service_cards). REVISION выше —
# это собственная неизменная идентичность ревизии Stage 8, а не текущий
# head; их совпадение было верно только до появления следующей миграции.
CURRENT_HEAD = "d14143842079"

_VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"

_EXPECTED = {
    AuditLog: ("idx_audit_created", "audit_log"),
    AuthLog: ("idx_auth_created", "auth_log"),
    DataChangeLog: ("idx_dcl_created", "data_change_log"),
}


def _migration_source() -> str:
    matches = list(_VERSIONS.glob("*add_audit_chronological_indexes*.py"))
    assert len(matches) == 1, matches
    return matches[0].read_text(encoding="utf-8")


# ── ORM ───────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("model", list(_EXPECTED))
def test_orm_declares_the_chronological_index(model):
    name, _ = _EXPECTED[model]
    indexes = {ix.name: [c.name for c in ix.columns] for ix in model.__table__.indexes}
    assert name in indexes, f"{model.__tablename__}: индекс не объявлен в ORM"
    assert indexes[name] == ["created_at", "id"], (
        "порядок столбцов обязан повторять ORDER BY эндпоинтов"
    )


@pytest.mark.parametrize("model", list(_EXPECTED))
def test_existing_indexes_are_untouched(model):
    """Ревизия только добавляет; чужие индексы трогать нельзя."""
    names = {ix.name for ix in model.__table__.indexes}
    legacy = {
        AuditLog: {"idx_audit_user", "idx_audit_event", "idx_audit_entity",
                   "idx_audit_outcome"},
        AuthLog: {"idx_auth_user", "idx_auth_ip", "idx_auth_failures"},
        DataChangeLog: {"idx_dcl_actor", "idx_dcl_table", "idx_dcl_operation"},
    }[model]
    assert legacy <= names


def test_primary_key_order_is_why_the_new_index_is_needed():
    """Фиксирует причину существования ревизии: PK ведёт по `id`, поэтому
    хронологическое окно им не обслуживается."""
    pk = [c.name for c in AuditLog.__table__.primary_key.columns]
    assert pk == ["id", "created_at"]


# ── Миграция ──────────────────────────────────────────────────────────────────

def test_revision_chain_points_at_the_recorded_predecessor():
    src = _migration_source()
    assert f'revision: str = "{REVISION}"' in src
    assert f'down_revision: Union[str, Sequence[str], None] = "{PREDECESSOR}"' in src


def test_alembic_has_exactly_one_head_and_it_is_this_revision():
    from tests.alembic_script import script_directory

    heads = script_directory().get_heads()
    assert list(heads) == [CURRENT_HEAD], heads


@pytest.mark.parametrize("index_name,table", list(_EXPECTED.values()))
def test_upgrade_creates_the_index_on_the_partitioned_parent(index_name, table):
    upgrade = _migration_source().split("def upgrade")[1].split("def downgrade")[0]
    statement = f"CREATE INDEX {index_name} ON {table} (created_at, id)"
    assert statement in upgrade


def test_downgrade_is_strict_and_reverse_ordered():
    downgrade = _migration_source().split("def downgrade")[1]
    exec_lines = [ln for ln in downgrade.splitlines() if "op.execute" in ln]
    assert len(exec_lines) == 3

    # STRICT: рассинхрон схемы должен ронять миграцию, а не маскироваться.
    assert not any("IF EXISTS" in ln.upper() for ln in exec_lines)
    # Без CASCADE: снимаем только свои индексы.
    assert not any("CASCADE" in ln.upper() for ln in exec_lines)

    order = [ln.split("DROP INDEX ")[1].split('"')[0].strip() for ln in exec_lines]
    assert order == ["idx_dcl_created", "idx_auth_created", "idx_audit_created"]


def test_migration_touches_no_data_and_no_other_objects():
    src = _migration_source()
    body = src.split("def upgrade")[1]
    for forbidden in ("DELETE", "UPDATE ", "INSERT", "DROP TABLE", "ALTER TABLE"):
        assert forbidden not in body.upper(), forbidden


def test_migration_does_not_use_create_index_helper():
    """Стиль audit-миграций проекта: raw op.execute на partitioned parent."""
    src = _migration_source()
    assert "op.create_index" not in src
    assert "op.drop_index" not in src


def test_concurrently_is_not_used():
    """PostgreSQL не поддерживает такой режим для partitioned table — попытка
    сломала бы миграцию на проде.

    Проверяется только исполняемый SQL: в docstring самой ревизии это слово
    присутствует намеренно, как объяснение выбранного компромисса.
    """
    sql_lines = [
        ln for ln in _migration_source().splitlines() if "op.execute" in ln
    ]
    assert sql_lines
    assert not any("CONCURRENTLY" in ln.upper() for ln in sql_lines)
