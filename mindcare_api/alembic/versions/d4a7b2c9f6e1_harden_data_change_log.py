"""harden_data_change_log

Stage 6-A — превращает application-контракт минимизированного data_change_log в
DB-enforced инварианты и убирает legacy SQL-путь копирования ПДн.

data_change_log — RANGE-partitioned по created_at. Все DDL выполняются на parent
через raw op.execute и наследуются существующими и будущими партициями (PG11+):
  - ALTER COLUMN ... SET NOT NULL — распространяется на все партиции;
  - ADD CONSTRAINT CHECK — наследуется партициями;
  - scripts/ensure_audit_partitions.py править не нужно (PARTITION OF наследует).

Содержимое таблицы НЕ проверялось ни в одной среде (production-writer'ов нет, но
это не доказательство пустоты), поэтому upgrade начинается с fail-closed
preflight. Миграция НЕ «чинит» унаследованные строки молча: любой ненулевой
счётчик останавливает её ДО первого DDL. Диагностика — только стабильный код
проверки и счётчик: без значений строк, без table_name/actor_id/old_values,
без текста SQL и без имён объектов.

Legacy-функция log_data_change() определяется СТРОГО по точному OID через
to_regprocedure(): ни по proname, ни по одной лишь схеме — иначе можно было бы
задеть одноимённую функцию с другой сигнатурой. Зависимости проверяются только
для найденного OID; DROP выполняется schema-qualified, БЕЗ CASCADE (default
RESTRICT — авторитетный enforcement, preflight лишь даёт чистую диагностику
раньше). Расширять DROP до CASCADE в ответ на отказ ЗАПРЕЩЕНО: это молча удалило
бы зависимые объекты.

ROUND-TRIP НАМЕРЕННО НЕПОЛНЫЙ. downgrade снимает три CHECK и два NOT NULL, но
НЕ восстанавливает log_data_change(): её контракт (p_old_values/p_new_values
полными JSONB-строками) прямо противоречит минимизации, и возврат небезопасного
пути копирования ПДн не является операционной процедурой. После
upgrade → downgrade legacy-БД остаётся без этой функции; владелец такой БД
принимает решение о её судьбе отдельно, вне Stage 6.

downgrade — STRICT (без IF EXISTS): schema drift должен ронять миграцию, а не
маскироваться. Предназначен прежде всего для disposable/test БД.

Revision ID: d4a7b2c9f6e1
Revises: b5d7f0a3c9e1
Create Date: 2026-08-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4a7b2c9f6e1"
down_revision: Union[str, Sequence[str], None] = "b5d7f0a3c9e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ── Имена ограничений (ORM объявляет ТЕ ЖЕ имена и тот же SQL) ───────────────
CK_OPERATION = "ck_dcl_operation"
CK_FIELDS_NONEMPTY = "ck_dcl_changed_fields_nonempty"
CK_RECORD_ID_POSITIVE = "ck_dcl_record_id_positive"

# Точная legacy-сигнатура (db/sql/migrations/009_views_functions.sql:150-158).
# Идентификация только по ней: to_regprocedure вернёт NULL, если такой функции
# нет, — чистая проверка существования без исключений.
LEGACY_FUNCTION_SIGNATURE = (
    "public.log_data_change("
    "integer,character varying,character varying,integer,"
    "character varying,jsonb,jsonb,inet)"
)

# Тот же список аргументов для DROP (с пробелами — читаемость DDL).
_LEGACY_DROP_ARGS = (
    "integer, character varying, character varying, integer, "
    "character varying, jsonb, jsonb, inet"
)

# Стабильные коды preflight. Порядок фиксирован: детерминированная диагностика.
_DATA_PREFLIGHT_CODES = (
    "bad_record_id_null",
    "bad_record_id_nonpositive",
    "bad_fields_null",
    "bad_fields_empty",
    "bad_operation",
)
_CODE_LEGACY_DEPENDENTS = "legacy_function_has_dependents"


def _fail(code: str, count: int) -> None:
    """Фиксированная диагностика: только стабильный код и счётчик."""
    raise RuntimeError(f"preflight failed: code={code} count={count}")


def _preflight_data(conn) -> None:
    """Fail-closed проверка строк ДО любого DDL.

    Считает нарушителей каждого будущего DB-инварианта отдельно, чтобы код
    отказа однозначно указывал, какое ограничение недостижимо. Значения строк
    не читаются и не логируются — только count(*).
    """
    row = conn.execute(sa.text("""
        SELECT
          count(*) FILTER (WHERE record_id IS NULL)
              AS bad_record_id_null,
          count(*) FILTER (WHERE record_id IS NOT NULL AND record_id <= 0)
              AS bad_record_id_nonpositive,
          count(*) FILTER (WHERE changed_fields IS NULL)
              AS bad_fields_null,
          count(*) FILTER (WHERE changed_fields IS NOT NULL
                             AND cardinality(changed_fields) = 0)
              AS bad_fields_empty,
          count(*) FILTER (WHERE operation NOT IN ('INSERT','UPDATE','DELETE'))
              AS bad_operation
          FROM data_change_log
    """)).one()

    for index, code in enumerate(_DATA_PREFLIGHT_CODES):
        count = row[index]
        if count:
            _fail(code, count)


def _legacy_function_oid(conn):
    """OID legacy-функции по ТОЧНОЙ сигнатуре либо None.

    to_regprocedure() возвращает NULL для несуществующей функции — не бросает
    исключение и не может случайно совпасть с одноимённой функцией другой
    сигнатуры или из другой схемы.
    """
    return conn.execute(
        sa.text("SELECT to_regprocedure(:sig)::oid"),
        {"sig": LEGACY_FUNCTION_SIGNATURE},
    ).scalar()


def _preflight_legacy_function(conn) -> None:
    """Fail-closed проверка зависимостей ТОЛЬКО для найденного OID.

    deptype 'i' (internal) исключён: это собственная служебная связь объекта.
    Считаются строки, где функция выступает РЕФЕРЕНТОМ (refobjid), то есть
    объекты, зависящие ОТ неё, — ровно те, что заставят DROP ... RESTRICT
    упасть. Имена зависимых объектов не читаются и не логируются.
    """
    oid = _legacy_function_oid(conn)
    if oid is None:
        return  # функции нет (штатно для БД, поднятых через Alembic)

    dependents = conn.execute(sa.text("""
        SELECT count(*)
          FROM pg_depend d
         WHERE d.refclassid = 'pg_proc'::regclass
           AND d.refobjid = :oid
           AND d.deptype <> 'i'
    """), {"oid": oid}).scalar()

    if dependents:
        _fail(_CODE_LEGACY_DEPENDENTS, dependents)


def upgrade() -> None:
    conn = op.get_bind()

    # ── 1. Preflight ДО любого DDL ───────────────────────────────────────────
    # Транзакционный DDL PostgreSQL + этот порядок гарантируют: при отказе не
    # применён ни один NOT NULL, ни один CHECK и функция не удалена.
    _preflight_data(conn)
    _preflight_legacy_function(conn)

    # ── 2. NOT NULL на partitioned parent (наследуется партициями) ───────────
    op.execute(
        "ALTER TABLE data_change_log ALTER COLUMN record_id SET NOT NULL"
    )
    op.execute(
        "ALTER TABLE data_change_log ALTER COLUMN changed_fields SET NOT NULL"
    )

    # ── 3. CHECK-ограничения ────────────────────────────────────────────────
    op.execute(
        f"ALTER TABLE data_change_log ADD CONSTRAINT {CK_OPERATION} "
        "CHECK (operation IN ('INSERT', 'UPDATE', 'DELETE'))"
    )
    op.execute(
        f"ALTER TABLE data_change_log ADD CONSTRAINT {CK_FIELDS_NONEMPTY} "
        "CHECK (cardinality(changed_fields) > 0)"
    )
    # NOT NULL не делает этот CHECK избыточным и наоборот: CHECK с NULL даёт
    # NULL и проходит, поэтому нужны оба.
    op.execute(
        f"ALTER TABLE data_change_log ADD CONSTRAINT {CK_RECORD_ID_POSITIVE} "
        "CHECK (record_id > 0)"
    )

    # ── 4. Удаление legacy-функции ──────────────────────────────────────────
    # schema-qualified, точная сигнатура, БЕЗ CASCADE. IF EXISTS обеспечивает
    # идемпотентность на БД, где функции никогда не было (Alembic-цепочка).
    op.execute(
        f"DROP FUNCTION IF EXISTS public.log_data_change({_LEGACY_DROP_ARGS})"
    )


def downgrade() -> None:
    # STRICT: без IF EXISTS — рассинхрон схемы обязан упасть, а не замаскироваться.
    # Обратный порядок относительно upgrade: сначала три CHECK, затем два NOT NULL.
    op.execute(
        f"ALTER TABLE data_change_log DROP CONSTRAINT {CK_RECORD_ID_POSITIVE}"
    )
    op.execute(
        f"ALTER TABLE data_change_log DROP CONSTRAINT {CK_FIELDS_NONEMPTY}"
    )
    op.execute(
        f"ALTER TABLE data_change_log DROP CONSTRAINT {CK_OPERATION}"
    )
    op.execute(
        "ALTER TABLE data_change_log ALTER COLUMN changed_fields DROP NOT NULL"
    )
    op.execute(
        "ALTER TABLE data_change_log ALTER COLUMN record_id DROP NOT NULL"
    )
    # log_data_change() НЕ восстанавливается — см. docstring модуля.
