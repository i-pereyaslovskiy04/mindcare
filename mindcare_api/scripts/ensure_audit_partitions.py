#!/usr/bin/env python3
"""
ensure_audit_partitions.py — maintenance-скрипт для создания месячных
партиций аудит-таблиц (auth_log, audit_log, data_change_log).

Использование:
    cd mindcare_api/
    python scripts/ensure_audit_partitions.py --months-ahead 24
    python scripts/ensure_audit_partitions.py --months-ahead 24 --dry-run
    python scripts/ensure_audit_partitions.py --months-ahead 6 --start-month 2029-01

Логи сохраняются в:
    mindcare_api/logs/maintenance/ensure_audit_partitions_<timestamp>.log

Правила:
  - Запускать ОТДЕЛЬНО от FastAPI startup/lifespan
  - Не запускать параллельно (защищён advisory lock)
  - Не конвертирует обычные таблицы в partitioned (требует alembic upgrade head)
  - Не удаляет старые партиции
  - Strict-by-default: любая ошибка → rollback + exit 1
"""

import argparse
import logging
import re
import sys
from datetime import date, datetime
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy import pool, text

# Путь к корню mindcare_api/ — для импорта app.core.config
_SCRIPT_DIR = Path(__file__).resolve().parent
_API_ROOT = _SCRIPT_DIR.parent
sys.path.insert(0, str(_API_ROOT))

from app.core.config import settings  # noqa: E402

# ── Константы ─────────────────────────────────────────────────────────────────

AUDIT_TABLES = ("auth_log", "audit_log", "data_change_log")

# 64-битный ключ advisory lock, уникальный для этого скрипта.
# Вычислен как crc32("mindcare_audit_partitions") | 0x00000000_XXXXXXXX,
# затем сдвинут в положительный диапазон bigint.
_ADVISORY_LOCK_KEY = 5_566_827_076_427_522_049


# ── Вспомогательные функции ───────────────────────────────────────────────────

def _mask_db_url(url: str) -> str:
    """Заменяет пароль в DATABASE_URL на *** для безопасного логирования."""
    return re.sub(r"(://[^:@]+:)[^@]+(@)", r"\1***\2", url)


def _next_month(d: date) -> date:
    return date(d.year + 1, 1, 1) if d.month == 12 else date(d.year, d.month + 1, 1)


def _iter_months(start: date, count: int):
    """Генерирует (suffix, from_iso, to_iso) для count месяцев начиная с start."""
    d = start.replace(day=1)
    for _ in range(count):
        n = _next_month(d)
        yield d.strftime("%Y_%m"), d.isoformat(), n.isoformat()
        d = n


def _setup_logging(log_dir: Path) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"ensure_audit_partitions_{ts}.log"

    logger = logging.getLogger("ensure_audit_partitions")
    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    logger.info("Log file: %s", log_file)
    return logger


# ── Проверки схемы и таблиц ───────────────────────────────────────────────────

def _check_schema(conn, schema: str, logger: logging.Logger) -> None:
    """Проверяет, что схема существует."""
    exists = conn.execute(
        text("SELECT 1 FROM pg_namespace WHERE nspname = :schema"),
        {"schema": schema},
    ).scalar()
    if not exists:
        raise RuntimeError(f"Schema '{schema}' does not exist in this database.")
    logger.info("[check] Schema '%s': OK", schema)


def _check_table(conn, table: str, schema: str, logger: logging.Logger) -> None:
    """
    Проверяет:
      1. Таблица существует в схеме.
      2. Является partitioned table (pg_partitioned_table).
      3. Partition key = RANGE (created_at).
    """
    # 1. Существование
    exists = conn.execute(
        text("""
            SELECT 1
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = :schema AND c.relname = :table
        """),
        {"schema": schema, "table": table},
    ).scalar()
    if not exists:
        raise RuntimeError(
            f"Table '{schema}.{table}' does not exist. "
            f"Run 'alembic upgrade head' on a fresh database first."
        )

    # 2. Является partitioned table
    is_partitioned = conn.execute(
        text("""
            SELECT 1
            FROM pg_partitioned_table pt
            JOIN pg_class c ON c.oid = pt.partrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = :schema AND c.relname = :table
        """),
        {"schema": schema, "table": table},
    ).scalar()
    if not is_partitioned:
        raise RuntimeError(
            f"Table '{schema}.{table}' is NOT a partitioned table. "
            f"This script only manages partitioned audit tables. "
            f"To convert: run 'alembic downgrade' to before revision 3a7c5e2b8f1d, "
            f"then 'alembic upgrade head' on a fresh database."
        )

    # 3. Partition key = RANGE (created_at)
    partkey = conn.execute(
        text("""
            SELECT pg_get_partkeydef(c.oid)
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = :schema AND c.relname = :table
        """),
        {"schema": schema, "table": table},
    ).scalar()

    expected = "RANGE (created_at)"
    if partkey != expected:
        raise RuntimeError(
            f"Table '{schema}.{table}' has unexpected partition key: "
            f"'{partkey}'. Expected: '{expected}'."
        )
    logger.info("[check] Table '%s': partitioned, key='%s' OK", table, partkey)


# ── Обработка одной партиции ──────────────────────────────────────────────────

def _process_partition(
    conn,
    table: str,
    suffix: str,
    from_dt: str,
    to_dt: str,
    schema: str,
    dry_run: bool,
    logger: logging.Logger,
) -> str:
    """
    Проверяет/создаёт одну партицию.
    Возвращает: 'created' | 'exists' | вызывает RuntimeError.
    """
    partition_name = f"{table}_{suffix}"

    # Проверяем, есть ли уже такое имя в схеме
    row = conn.execute(
        text("""
            SELECT
                c.relname,
                c.relkind,
                (
                    SELECT p.relname
                    FROM pg_inherits i
                    JOIN pg_class p ON p.oid = i.inhparent
                    JOIN pg_namespace pn ON pn.oid = p.relnamespace
                    WHERE i.inhrelid = c.oid AND pn.nspname = :schema
                ) AS parent_name
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = :schema AND c.relname = :partition_name
        """),
        {"schema": schema, "partition_name": partition_name},
    ).fetchone()

    if row is not None:
        # Имя занято — проверяем, что это партиция нужной parent table
        if row.parent_name != table:
            raise RuntimeError(
                f"Name '{schema}.{partition_name}' already exists "
                f"but belongs to parent '{row.parent_name}' (expected '{table}'). "
                f"Manual intervention required."
            )
        # Перепроверяем через pg_inherits
        attached = conn.execute(
            text("""
                SELECT 1
                FROM pg_inherits i
                JOIN pg_class p ON p.oid = i.inhparent
                JOIN pg_class c ON c.oid = i.inhrelid
                JOIN pg_namespace pn ON pn.oid = p.relnamespace
                WHERE pn.nspname = :schema
                  AND p.relname = :table
                  AND c.relname = :partition_name
            """),
            {"schema": schema, "table": table, "partition_name": partition_name},
        ).scalar()
        if not attached:
            raise RuntimeError(
                f"Table '{schema}.{partition_name}' exists but is NOT attached "
                f"to '{table}' in pg_inherits. Database may be in inconsistent state."
            )
        logger.debug("[partition] %s.%s: already exists, skipping", schema, partition_name)
        return "exists"

    # Партиции нет — создаём
    ddl = (
        f"CREATE TABLE {schema}.{partition_name} "
        f"PARTITION OF {schema}.{table} "
        f"FOR VALUES FROM ('{from_dt}') TO ('{to_dt}')"
    )

    if dry_run:
        logger.info("[dry-run] Would create: %s (%s .. %s)", partition_name, from_dt, to_dt)
        return "created"

    logger.info("[partition] Creating: %s (%s .. %s)", partition_name, from_dt, to_dt)
    try:
        conn.execute(text(ddl))
    except Exception as exc:
        raise RuntimeError(
            f"Failed to create partition '{schema}.{partition_name}'.\n"
            f"SQL: {ddl}\n"
            f"Error: {type(exc).__name__}: {exc}"
        ) from exc

    # Верифицируем через pg_inherits после создания
    attached = conn.execute(
        text("""
            SELECT 1
            FROM pg_inherits i
            JOIN pg_class p ON p.oid = i.inhparent
            JOIN pg_class c ON c.oid = i.inhrelid
            JOIN pg_namespace pn ON pn.oid = p.relnamespace
            WHERE pn.nspname = :schema
              AND p.relname = :table
              AND c.relname = :partition_name
        """),
        {"schema": schema, "table": table, "partition_name": partition_name},
    ).scalar()
    if not attached:
        raise RuntimeError(
            f"Partition '{schema}.{partition_name}' was created but "
            f"pg_inherits does not confirm it is attached to '{table}'."
        )
    logger.info("[partition] Created and verified: %s", partition_name)
    return "created"


# ── Точка входа ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Ensure monthly partitions exist for audit tables "
            "(auth_log, audit_log, data_change_log)."
        )
    )
    parser.add_argument(
        "--months-ahead",
        type=int,
        default=24,
        metavar="N",
        help="Ensure partitions for the next N months (default: 24)",
    )
    parser.add_argument(
        "--schema",
        default="public",
        help="PostgreSQL schema name (default: public)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show planned partitions without executing DDL",
    )
    parser.add_argument(
        "--start-month",
        metavar="YYYY-MM",
        help="First month to ensure (default: current month). Example: 2029-01",
    )
    args = parser.parse_args()

    if args.months_ahead < 1:
        print("ERROR: --months-ahead must be >= 1", file=sys.stderr)
        sys.exit(1)

    # Проверка имени схемы: только допустимые PostgreSQL-идентификаторы
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", args.schema):
        print(f"ERROR: invalid --schema name '{args.schema}'", file=sys.stderr)
        sys.exit(1)

    # ── Логирование ───────────────────────────────────────────────────────────
    log_dir = _API_ROOT / "logs" / "maintenance"
    logger = _setup_logging(log_dir)

    logger.info("=== ensure_audit_partitions START ===")
    logger.info(
        "mode=%s  months_ahead=%d  schema=%s",
        "DRY-RUN" if args.dry_run else "LIVE",
        args.months_ahead,
        args.schema,
    )

    # ── Стартовый месяц ───────────────────────────────────────────────────────
    if args.start_month:
        try:
            start = datetime.strptime(args.start_month, "%Y-%m").date()
        except ValueError:
            logger.error(
                "[config] Invalid --start-month '%s'. Expected format: YYYY-MM",
                args.start_month,
            )
            sys.exit(1)
    else:
        today = date.today()
        start = date(today.year, today.month, 1)

    planned = list(_iter_months(start, args.months_ahead))
    logger.info(
        "[config] Partition range: %s .. %s (%d months per table)",
        planned[0][0], planned[-1][0], len(planned),
    )

    # ── DATABASE_URL ──────────────────────────────────────────────────────────
    db_url = getattr(settings, "DATABASE_URL", None)
    if not db_url:
        logger.error("[config] DATABASE_URL not found in settings")
        sys.exit(1)
    logger.info("[config] Database: %s", _mask_db_url(db_url))

    # ── Подключение ───────────────────────────────────────────────────────────
    try:
        engine = sa.create_engine(db_url, poolclass=pool.NullPool)
        conn = engine.connect()
    except Exception as exc:
        logger.error("[connect] Failed to connect: %s: %s", type(exc).__name__, exc)
        sys.exit(1)
    logger.info("[connect] Database connection: OK")

    # ── Основная работа в транзакции ──────────────────────────────────────────
    exit_code = 0
    try:
        with conn.begin():
            # Transaction-level advisory lock: автоматически освобождается
            # при commit или rollback — не требует явного unlock.
            acquired = conn.execute(
                text("SELECT pg_try_advisory_xact_lock(:key)"),
                {"key": _ADVISORY_LOCK_KEY},
            ).scalar()
            if not acquired:
                raise RuntimeError(
                    f"Could not acquire advisory lock (key={_ADVISORY_LOCK_KEY}). "
                    f"Another instance may be running."
                )
            logger.info("[lock] Advisory lock acquired (key=%d)", _ADVISORY_LOCK_KEY)

            # ── Проверки ─────────────────────────────────────────────────────
            logger.info("[checks] Starting pre-flight checks...")
            _check_schema(conn, args.schema, logger)
            for table in AUDIT_TABLES:
                _check_table(conn, table, args.schema, logger)
            logger.info("[checks] All pre-flight checks passed")

            # ── Партиции ─────────────────────────────────────────────────────
            created_count = 0
            exists_count = 0

            for table in AUDIT_TABLES:
                logger.info("[partitions] Processing table: %s", table)
                for suffix, from_dt, to_dt in planned:
                    result = _process_partition(
                        conn, table, suffix, from_dt, to_dt,
                        args.schema, args.dry_run, logger,
                    )
                    if result == "created":
                        created_count += 1
                    else:
                        exists_count += 1

            # ── Итог ─────────────────────────────────────────────────────────
            if args.dry_run:
                logger.info(
                    "[result] DRY-RUN complete: would create %d partitions, "
                    "%d already exist",
                    created_count, exists_count,
                )
                # Rollback — в dry-run режиме DDL не выполнялся, но на всякий случай
                raise _DryRunComplete()
            else:
                logger.info(
                    "[result] Done: created %d partitions, %d already existed",
                    created_count, exists_count,
                )
                logger.info("=== ensure_audit_partitions SUCCESS ===")
                # Транзакция коммитится при выходе из блока `with conn.begin()`

    except _DryRunComplete:
        logger.info("=== ensure_audit_partitions DRY-RUN COMPLETE ===")
        # exit_code = 0 (dry-run успех)

    except Exception as exc:
        logger.error(
            "[error] %s: %s",
            type(exc).__name__, exc,
        )
        logger.error("=== ensure_audit_partitions FAILED ===")
        exit_code = 1
        # Транзакция уже откачена при выходе из блока `with conn.begin()` с исключением

    finally:
        conn.close()
        engine.dispose()

    sys.exit(exit_code)


class _DryRunComplete(Exception):
    """Внутреннее исключение для выхода из транзакции в dry-run режиме."""


if __name__ == "__main__":
    main()
