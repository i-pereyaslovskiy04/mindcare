"""
Stage 6-A — ORM-metadata DataChangeLog + drift-контроль миграции
d4a7b2c9f6e1 (harden_data_change_log).

Без подключения к PostgreSQL. Проверяются:
  - nullable/типы колонок после Stage 6-A;
  - три именованных CheckConstraint;
  - ТОЧНОЕ совпадение имён и текста CHECK между ORM и миграцией;
  - согласованность preflight-кодов с набором вводимых ограничений;
  - strict-семантика downgrade (без IF EXISTS) и обратный порядок операций;
  - schema-qualified DROP FUNCTION с точной сигнатурой и БЕЗ CASCADE;
  - зафиксированный в docstring намеренно неполный round-trip.
"""
import ast
import re
from pathlib import Path

from sqlalchemy import ARRAY, CheckConstraint, Integer, Text

from app.db.models.audit import DataChangeLog

_TABLE = DataChangeLog.__table__

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic" / "versions" / "d4a7b2c9f6e1_harden_data_change_log.py"
)
_MIGRATION_SRC = _MIGRATION_PATH.read_text(encoding="utf-8")

_UPGRADE_BLOCK = _MIGRATION_SRC.split("def upgrade")[1].split("def downgrade")[0]
_DOWNGRADE_BLOCK = _MIGRATION_SRC.split("def downgrade")[1]


def _ddl_statements(func_name: str) -> list:
    """SQL-строки из op.execute(...) указанной функции миграции.

    Через AST, а не текстовым поиском: docstring и комментарии миграции
    ЛЕГИТИМНО упоминают CASCADE и IF EXISTS, объясняя, почему они НЕ
    применяются. Проверять такие запреты по сырому тексту — ложное срабатывание.
    f-string склеивается из литеральных частей (имена CHECK подставляются из
    модульных констант и проверяются отдельным тестом).
    """
    tree = ast.parse(_MIGRATION_SRC)
    target = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == func_name
    )
    statements = []
    for node in ast.walk(target):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_execute = (
            isinstance(func, ast.Attribute) and func.attr == "execute"
            and isinstance(func.value, ast.Name) and func.value.id == "op"
        )
        if not is_execute or not node.args:
            continue
        statements.append(_literal_sql(node.args[0]))
    return statements


def _literal_sql(node: ast.expr) -> str:
    """Литеральный текст SQL-аргумента (Constant или f-string)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
            else:
                parts.append("<expr>")
        return "".join(parts)
    return ""


_UPGRADE_SQL = _ddl_statements("upgrade")
_DOWNGRADE_SQL = _ddl_statements("downgrade")

# Ожидаемое соответствие: имя CHECK → текст условия (как в ORM и в миграции).
_EXPECTED_CHECKS = {
    "ck_dcl_operation": "operation IN ('INSERT', 'UPDATE', 'DELETE')",
    "ck_dcl_changed_fields_nonempty": "cardinality(changed_fields) > 0",
    "ck_dcl_record_id_positive": "record_id > 0",
}

_EXPECTED_NOT_NULL = ("record_id", "changed_fields")


# ── ORM ──────────────────────────────────────────────────────────────────────

def test_record_id_is_not_null_integer():
    col = _TABLE.c.record_id
    assert isinstance(col.type, Integer)
    assert col.nullable is False


def test_changed_fields_is_not_null_text_array():
    col = _TABLE.c.changed_fields
    assert isinstance(col.type, ARRAY)
    assert isinstance(col.type.item_type, Text)
    assert col.nullable is False


def test_old_and_new_values_remain_nullable():
    """Колонки сохраняются физически и остаются nullable: их содержимое
    ограничивает application allowlist, а не БД."""
    assert _TABLE.c.old_values.nullable is True
    assert _TABLE.c.new_values.nullable is True


def test_three_named_check_constraints_present():
    checks = {
        c.name: str(c.sqltext)
        for c in _TABLE.constraints
        if isinstance(c, CheckConstraint) and c.name
    }
    assert set(checks) == set(_EXPECTED_CHECKS)
    for name, expected_sql in _EXPECTED_CHECKS.items():
        assert checks[name] == expected_sql, name


def test_existing_indexes_are_untouched():
    idx = {ix.name: [c.name for c in ix.columns] for ix in _TABLE.indexes}
    assert idx["idx_dcl_actor"] == ["actor_id", "created_at"]
    assert idx["idx_dcl_table"] == ["table_name", "record_id"]
    assert idx["idx_dcl_operation"] == ["operation", "created_at"]


# ── Drift: ORM ↔ миграция ────────────────────────────────────────────────────

def test_migration_revision_and_down_revision():
    assert 'revision: str = "d4a7b2c9f6e1"' in _MIGRATION_SRC
    assert (
        'down_revision: Union[str, Sequence[str], None] = "b5d7f0a3c9e1"'
        in _MIGRATION_SRC
    )


def test_migration_declares_the_same_check_names_and_sql_as_orm():
    for name, expected_sql in _EXPECTED_CHECKS.items():
        assert f"ADD CONSTRAINT {{{_const_var(name)}}} " in _UPGRADE_BLOCK or (
            name in _MIGRATION_SRC
        ), name
        # Текст CHECK в миграции обязан совпадать с ORM символ в символ.
        assert f"CHECK ({expected_sql})" in _UPGRADE_BLOCK, name


def _const_var(name: str) -> str:
    """Имя python-константы, под которой имя CHECK объявлено в миграции."""
    return {
        "ck_dcl_operation": "CK_OPERATION",
        "ck_dcl_changed_fields_nonempty": "CK_FIELDS_NONEMPTY",
        "ck_dcl_record_id_positive": "CK_RECORD_ID_POSITIVE",
    }[name]


def test_migration_constant_values_match_orm_constraint_names():
    for name in _EXPECTED_CHECKS:
        assert f'{_const_var(name)} = "{name}"' in _MIGRATION_SRC, name


def test_migration_sets_not_null_for_the_same_columns_as_orm():
    for column in _EXPECTED_NOT_NULL:
        assert (
            f"ALTER COLUMN {column} SET NOT NULL" in _UPGRADE_BLOCK
        ), column
    not_null_columns = set(
        re.findall(r"ALTER COLUMN (\w+) SET NOT NULL", _UPGRADE_BLOCK)
    )
    assert not_null_columns == set(_EXPECTED_NOT_NULL)


def test_orm_not_null_set_matches_migration_exactly():
    """Ни одна другая колонка не стала NOT NULL в ORM без миграции."""
    orm_not_null = {
        c.name for c in _TABLE.columns
        if not c.nullable and not c.primary_key
    }
    # table_name и operation были NOT NULL до Stage 6-A (baseline).
    assert orm_not_null == set(_EXPECTED_NOT_NULL) | {"table_name", "operation"}


# ── Preflight ────────────────────────────────────────────────────────────────

def test_preflight_covers_every_new_invariant():
    for code in (
        "bad_record_id_null",
        "bad_record_id_nonpositive",
        "bad_fields_null",
        "bad_fields_empty",
        "bad_operation",
    ):
        assert f'"{code}"' in _MIGRATION_SRC, code


def test_preflight_runs_before_any_ddl():
    """Оба preflight-вызова обязаны стоять раньше первого ALTER/DROP."""
    data_pos = _UPGRADE_BLOCK.index("_preflight_data(conn)")
    legacy_pos = _UPGRADE_BLOCK.index("_preflight_legacy_function(conn)")
    first_ddl = min(
        _UPGRADE_BLOCK.index("ALTER TABLE"),
        _UPGRADE_BLOCK.index("DROP FUNCTION"),
    )
    assert data_pos < first_ddl
    assert legacy_pos < first_ddl


def test_preflight_diagnostic_is_code_and_count_only():
    assert 'f"preflight failed: code={code} count={count}"' in _MIGRATION_SRC
    # Никаких значений строк/имён объектов в диагностике.
    for leak in ("old_values", "new_values", "actor_id", "table_name="):
        assert f"{{{leak}}}" not in _MIGRATION_SRC


def test_legacy_function_is_identified_by_exact_oid():
    assert "to_regprocedure" in _MIGRATION_SRC
    assert "public.log_data_change(" in _MIGRATION_SRC
    assert "integer,character varying,character varying,integer," in _MIGRATION_SRC
    assert "character varying,jsonb,jsonb,inet)" in _MIGRATION_SRC
    # Зависимости ищутся ТОЛЬКО по найденному OID.
    assert "d.refobjid = :oid" in _MIGRATION_SRC
    assert "'pg_proc'::regclass" in _MIGRATION_SRC


def test_drop_function_is_schema_qualified_without_cascade():
    drops = [sql for sql in _UPGRADE_SQL if "DROP FUNCTION" in sql.upper()]
    assert len(drops) == 1
    statement = drops[0]
    assert "public.log_data_change(" in statement
    # Точная сигнатура, schema-qualified, идемпотентный IF EXISTS.
    assert "IF EXISTS" in statement.upper()
    assert "<expr>" in statement           # список типов из модульной константы
    assert "CASCADE" not in statement.upper()


# ── Downgrade ────────────────────────────────────────────────────────────────

def test_downgrade_is_strict_no_if_exists():
    assert _DOWNGRADE_SQL
    for statement in _DOWNGRADE_SQL:
        assert "IF EXISTS" not in statement.upper(), statement


def test_downgrade_reverses_upgrade_order():
    """Три CHECK снимаются в обратном порядке, затем два NOT NULL."""
    order = re.findall(
        r"DROP CONSTRAINT \{(\w+)\}|ALTER COLUMN (\w+) DROP NOT NULL",
        _DOWNGRADE_BLOCK,
    )
    flat = [a or b for a, b in order]
    assert flat == [
        "CK_RECORD_ID_POSITIVE",
        "CK_FIELDS_NONEMPTY",
        "CK_OPERATION",
        "changed_fields",
        "record_id",
    ]


def test_downgrade_does_not_recreate_legacy_function():
    assert "CREATE OR REPLACE FUNCTION" not in _DOWNGRADE_BLOCK
    assert "CREATE FUNCTION" not in _DOWNGRADE_BLOCK


def test_docstring_records_intentionally_incomplete_round_trip():
    header = _MIGRATION_SRC.split('"""')[1]
    assert "НЕПОЛНЫЙ" in header
    assert "log_data_change" in header


def test_no_ddl_statement_uses_cascade():
    """CASCADE запрещён во ВСЕХ операторах обеих функций: он молча удалил бы
    зависимые объекты вместо fail-closed отказа RESTRICT."""
    for statement in _UPGRADE_SQL + _DOWNGRADE_SQL:
        assert "CASCADE" not in statement.upper(), statement


def test_data_change_log_docstring_is_legally_neutral():
    """Stage 6-A corrective: docstring НЕ утверждает прямое требование
    какого-либо закона и НЕ утверждает соответствие законодательству — это
    отдельное решение DPO/ответственного лица, вне охвата ORM-модели.
    Формулировка — техническая мера прослеживаемости, а не юридический вывод.
    """
    doc = DataChangeLog.__doc__ or ""
    assert doc.strip()

    # Прежняя формулировка ("ФЗ-152" как прямое основание/цель модели) удалена.
    assert "ФЗ-152" not in doc
    assert "фз-152" not in doc.lower()

    # Новая формулировка — техническая мера, явно не юридический вывод.
    assert "техническая мера прослеживаемости" in doc
    assert "DPO" in doc

    # Поведение модели (nullable/CheckConstraint/имена) в 21-24 не изменилось —
    # проверяется отдельными тестами выше (test_three_named_check_constraints_present
    # и др.); этот тест — только про текст, не про схему.
