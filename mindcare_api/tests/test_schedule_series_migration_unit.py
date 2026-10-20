"""
Stage 5C-0A — no-DB unit-тесты identity-миграции `schedule_series`.

Проверяет структуру ORM-модели, цепочку ревизий и КОНТРАКТ ДИАГНОСТИК: фиксированные
сообщения fail-closed не должны содержать UUID/id/SQL/ПДн. Реальная БД не
используется (round-trip и backfill — в gated integration).
"""
import importlib.util
import re
from pathlib import Path

import pytest

from app.db.models import ScheduleBreak, ScheduleRule, ScheduleSeries

_VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
_MIGRATION = _VERSIONS / "a1c4e8b2f7d3_add_schedule_series_identity.py"
_MIGRATION_FK = _VERSIONS / "b5d7f0a3c9e1_enforce_schedule_series_fk.py"


def _load(path=None, name="_mig_5c0a"):
    spec = importlib.util.spec_from_file_location(name, path or _MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_fk():
    return _load(_MIGRATION_FK, "_mig_5c0c")


# ══════════════════════════════════════════════════════════════════════════
# 1. ORM-модель: identity, а не дубликат состояния серии
# ══════════════════════════════════════════════════════════════════════════

def test_model_table_and_columns():
    assert ScheduleSeries.__tablename__ == "schedule_series"
    cols = {c.name for c in ScheduleSeries.__table__.columns}
    assert cols == {"id", "series_uuid", "psychologist_id", "created_at"}


def test_model_does_not_duplicate_series_state():
    """is_active/effective_*/auto_extend остаются в rules/breaks (единственный
    источник истины); created_by не хранится — у ScheduleBreak его нет."""
    cols = {c.name for c in ScheduleSeries.__table__.columns}
    for forbidden in ("is_active", "effective_from", "effective_until",
                      "auto_extend", "created_by", "day_of_week",
                      "start_time", "end_time", "period"):
        assert forbidden not in cols, forbidden


def test_series_uuid_named_unique_and_not_null():
    """Имя UNIQUE синхронизировано с DDL — на него ссылаются FK из 5C-0C."""
    col = ScheduleSeries.__table__.columns["series_uuid"]
    assert col.nullable is False
    uniques = [
        c for c in ScheduleSeries.__table__.constraints
        if c.__class__.__name__ == "UniqueConstraint"
    ]
    assert len(uniques) == 1
    assert uniques[0].name == "uq_schedule_series_uuid"
    assert [c.name for c in uniques[0].columns] == ["series_uuid"]


# ══════════════════════════════════════════════════════════════════════════
# 1b. ORM ↔ DDL 5C-0C: FK объявлены в metadata (drift-check)
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("model,fk_name", [
    (ScheduleRule, "fk_schedule_rules_series"),
    (ScheduleBreak, "fk_schedule_breaks_series"),
])
def test_series_fk_declared_in_orm_metadata(model, fk_name):
    col = model.__table__.columns["series_id"]
    fks = list(col.foreign_keys)
    assert len(fks) == 1, model.__tablename__
    fk = fks[0]
    assert fk.constraint.name == fk_name
    assert fk.target_fullname == "schedule_series.series_uuid"
    # ON DELETE не задан — идентично DDL 5C-0C (NO ACTION)
    assert fk.ondelete is None


@pytest.mark.parametrize("model", [ScheduleRule, ScheduleBreak])
def test_series_id_stays_nullable_uuid(model):
    """FK не должен менять тип/nullable: legacy-строки без серии допустимы."""
    from sqlalchemy.dialects.postgresql import UUID as PG_UUID
    col = model.__table__.columns["series_id"]
    assert col.nullable is True
    assert isinstance(col.type, PG_UUID)


def test_psychologist_id_nullable_set_null_not_cascade():
    """Удаление пользователя не должно уничтожать identity-строку, на которую
    ссылается append-only audit_log."""
    col = ScheduleSeries.__table__.columns["psychologist_id"]
    assert col.nullable is True
    fk = list(col.foreign_keys)[0]
    assert fk.ondelete == "SET NULL"


# ══════════════════════════════════════════════════════════════════════════
# 2. Цепочка ревизий
# ══════════════════════════════════════════════════════════════════════════

def test_revision_chain():
    mod = _load()
    assert mod.revision == "a1c4e8b2f7d3"
    assert mod.down_revision == "f2a9c4e7b1d8"


def test_upgrade_does_not_add_foreign_keys():
    """FK добавляются только в 5C-0C (expand/contract) — иначе старый writer в
    окне совместимости нарушит constraint."""
    src = _MIGRATION.read_text(encoding="utf-8")
    upgrade_src = src.split("def upgrade()", 1)[1].split("def downgrade()", 1)[0]
    assert "ADD CONSTRAINT" not in upgrade_src.upper()
    assert "VALIDATE CONSTRAINT" not in upgrade_src.upper()


# ══════════════════════════════════════════════════════════════════════════
# 3. Fail-closed диагностики без UUID/id/SQL/ПДн
# ══════════════════════════════════════════════════════════════════════════

_UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}")


@pytest.mark.parametrize("attr", ["_ERR_OWNERSHIP", "_ERR_AUDIT_REFS"])
def test_fixed_diagnostics_have_no_values(attr):
    msg = getattr(_load(), attr)
    assert isinstance(msg, str) and msg
    # без подстановок значений
    assert "%s" not in msg and "{" not in msg and "}" not in msg
    # без UUID и SQL
    assert not _UUID_RE.search(msg)
    for token in ("SELECT", "INSERT", "UPDATE", "DROP", "@"):
        assert token not in msg.upper() if token != "@" else token not in msg


def test_downgrade_is_fail_closed_on_audit_references():
    """DROP TABLE запрещён, если schedule_series уже использовалась как audit
    target: пересоздание выдало бы другие SERIAL id."""
    src = _MIGRATION.read_text(encoding="utf-8")
    down_src = src.split("def downgrade()", 1)[1]
    assert "audit_log" in down_src
    assert "entity_type = 'schedule_series'" in down_src
    assert "_ERR_AUDIT_REFS" in down_src
    # проверка выполняется ДО drop_table
    assert down_src.index("_ERR_AUDIT_REFS") < down_src.index("drop_table")


def test_backfill_is_idempotent_and_covers_both_sources():
    """Серии бывают rule-only, break-only (create_schedule_breaks_bulk генерирует
    свой series_id и не создаёт rules) и смешанные."""
    src = _MIGRATION.read_text(encoding="utf-8")
    assert "ON CONFLICT (series_uuid) DO NOTHING" in src
    assert "schedule_rules" in src and "schedule_breaks" in src
    assert "series_id IS NOT NULL" in src


def test_ownership_preflight_runs_before_insert():
    src = _MIGRATION.read_text(encoding="utf-8")
    up = src.split("def upgrade()", 1)[1].split("def downgrade()", 1)[0]
    assert up.index("_assert_consistent_ownership") < up.index("_backfill")


# ══════════════════════════════════════════════════════════════════════════
# 4. Stage 5C-0C — enforcement FK (expand/contract)
# ══════════════════════════════════════════════════════════════════════════

def test_fk_revision_chains_after_identity():
    mod = _load_fk()
    assert mod.revision == "b5d7f0a3c9e1"
    assert mod.down_revision == "a1c4e8b2f7d3"


def test_fk_upgrade_repeats_backfill_before_adding_constraints():
    """Между 5C-0A и деплоем 5C-0B старый writer мог создать серии без identity;
    без повторного backfill VALIDATE упал бы на сиротах."""
    src = _MIGRATION_FK.read_text(encoding="utf-8")
    up = src.split("def upgrade()", 1)[1].split("def downgrade()", 1)[0]
    assert up.index("_assert_consistent_ownership") < up.index("_backfill")
    assert up.index("_backfill") < up.index("ADD CONSTRAINT")


def test_fk_uses_not_valid_then_separate_validate():
    src = _MIGRATION_FK.read_text(encoding="utf-8")
    up = src.split("def upgrade()", 1)[1].split("def downgrade()", 1)[0]
    assert up.count("NOT VALID") == 2                    # оба FK
    assert up.count("VALIDATE CONSTRAINT") == 2
    assert up.index("NOT VALID") < up.index("VALIDATE CONSTRAINT")


def test_fk_targets_existing_uuid_columns_without_new_columns():
    src = _MIGRATION_FK.read_text(encoding="utf-8")
    up = src.split("def upgrade()", 1)[1].split("def downgrade()", 1)[0]
    assert "REFERENCES schedule_series(series_uuid)" in up
    assert "FOREIGN KEY (series_id)" in up
    assert "ADD COLUMN" not in up.upper()


def test_fk_downgrade_fail_closed_before_dropping_constraints():
    """Проверка должна стоять ДО DROP CONSTRAINT — иначе при отказе FK уже
    сняты (план §17, тест B требует «оба FK остаются»)."""
    src = _MIGRATION_FK.read_text(encoding="utf-8")
    down = src.split("def downgrade()", 1)[1]
    assert "entity_type = 'schedule_series'" in down
    # Сравниваем с реальным DDL-стейтментом, а не с упоминанием в комментарии.
    first_drop = down.index("ALTER TABLE schedule_breaks DROP CONSTRAINT")
    assert down.index("_ERR_AUDIT_REFS") < first_drop


@pytest.mark.parametrize("attr", [
    "_ERR_OWNERSHIP", "_ERR_AUDIT_REFS", "_ERR_IDENTITY_OWNER",
])
def test_fk_fixed_diagnostics_have_no_values(attr):
    msg = getattr(_load_fk(), attr)
    assert isinstance(msg, str) and msg
    assert "%s" not in msg and "{" not in msg and "}" not in msg
    assert not _UUID_RE.search(msg)
    assert "@" not in msg


def test_fk_checks_existing_identity_ownership_before_add_constraint():
    """ON CONFLICT DO NOTHING не обновляет уже существующие identity-строки,
    поэтому расхождение владельца обязано ловиться отдельной проверкой ДО FK."""
    src = _MIGRATION_FK.read_text(encoding="utf-8")
    up = src.split("def upgrade()", 1)[1].split("def downgrade()", 1)[0]
    assert up.index("_backfill") < up.index("_assert_identity_matches_children")
    # Сравниваем с реальным DDL-стейтментом, а не с упоминанием в комментарии.
    first_add = up.index("ALTER TABLE schedule_rules ADD CONSTRAINT")
    assert up.index("_assert_identity_matches_children") < first_add
    # NULL-владелец существующей строки тоже считается расхождением
    body = src.split("def _assert_identity_matches_children", 1)[1]
    assert "IS DISTINCT FROM" in body


# ══════════════════════════════════════════════════════════════════════════
# 5. Nullable legacy created_at не должен ронять NOT NULL identity-строки
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("path", [_MIGRATION, _MIGRATION_FK])
def test_backfill_coalesces_nullable_created_at(path):
    """schedule_rules/schedule_breaks.created_at NULLABLE → MIN может быть NULL.
    Контракт одинаков в 5C-0A и 5C-0C."""
    src = path.read_text(encoding="utf-8")
    assert "COALESCE(MIN(created_at), CURRENT_TIMESTAMP)" in src
    # «голый» MIN(created_at) как значение вставки не используется
    assert "), MIN(created_at)" not in src


def test_identity_created_at_is_not_an_audit_timestamp():
    """Техническое время создания identity не объявляется временем бизнес-события
    и не переносится в audit."""
    src = _MIGRATION.read_text(encoding="utf-8")
    assert "не юридическое" in src or "НЕ юридическое" in src
