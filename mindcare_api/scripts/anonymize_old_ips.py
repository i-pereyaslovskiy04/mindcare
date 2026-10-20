#!/usr/bin/env python3
"""
anonymize_old_ips.py — maintenance-скрипт обнуления устаревших IP-адресов в
audit-журналах (Stage 7B).

Вызывает функции, созданные миграцией `c8e2b5f7a3d1`:
  - live     -> `public.anonymize_old_ips(days)`  (мутация, RETURNS bigint)
  - dry-run  -> `public.count_old_ips(days)`      (строго read-only)

Обе считают одну и ту же границу по одному и тому же предикату, поэтому dry-run
не дублирует логику отбора в Python и его результат совпадает с числом строк,
которые изменил бы live-прогон.

Использование:
    cd mindcare_api/
    python scripts/anonymize_old_ips.py --days 90 --dry-run
    python scripts/anonymize_old_ips.py --days 90

Логи сохраняются в:
    mindcare_api/logs/maintenance/anonymize_old_ips_<timestamp>.log

⚠ ПЕРВЫЙ ПРОГОН НЕОБРАТИМ. Обнулённые `ip_address` не восстанавливаются ни
`alembic downgrade`, ни повторным запуском: downgrade возвращает механизм, но не
данные. Порядок ввода в эксплуатацию — dry-run, оценка объёма, ручной live-прогон
в окно низкой нагрузки, и только затем активация systemd-таймера.

Правила:
  - Запускать ОТДЕЛЬНО от FastAPI startup/lifespan (cron / systemd timer).
  - НЕ вызывать из FastAPI lifespan.
  - Любая ошибка (конфигурация / соединение / привилегии / выполнение) -> exit 1.
  - Диагностика содержит ТОЛЬКО фазу и класс исключения: без `str(exc)`, SQL,
    DATABASE_URL, имён ролей, id и самих IP-адресов.
  - DATABASE_URL не логируется вообще, даже маскированным.

ТРАНЗАКЦИОННЫЙ КОНТУР. Вся работа идёт внутри ОДНОЙ явной границы
`with engine.begin() as conn`: сначала три preflight-проверки, затем — и только
затем — рабочая функция. Так сделано из-за autobegin в SQLAlchemy 2.0: первый же
`conn.execute()` неявно открывает транзакцию, поэтому схема «preflight, потом
`conn.begin()`» упала бы с `InvalidRequestError: a transaction is already begun
on this connection`. Соседний `ensure_audit_partitions.py` этой ловушки избегает
случайно — он ничего не выполняет до `with conn.begin()`, и копировать его форму
сюда нельзя.

Следствия контура:
  - preflight выполняется в начале транзакции, ДО вызова рабочей функции и ДО
    любой мутации;
  - отказ preflight откатывает транзакцию, рабочая функция не вызывается;
  - сбой самой рабочей функции откатывает ту же транзакцию целиком;
  - `engine.begin()` закрывает соединение и на успехе, и на сбое; `dispose()`
    вызывается в `finally`.

ПРИВИЛЕГИИ. Функции объявлены `SECURITY INVOKER`, поэтому `EXECUTE` — лишь право
войти в функцию: `SELECT`/`UPDATE` внутри тела выполняются с правами ВЫЗЫВАЮЩЕЙ
роли. Preflight различает эти случаи отдельными фазами, чтобы отказ по правам не
выглядел как отсутствие миграции.

Advisory lock скрипт НЕ берёт: он живёт внутри `anonymize_old_ips` — один
источник истины о параллельном запуске. Второй одновременный прогон падает с
SQLSTATE 55P03 и завершается ненулевым кодом.
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy import pool

# Путь к корню mindcare_api/ — для отложенного импорта app.core.config.
_SCRIPT_DIR = Path(__file__).resolve().parent
_API_ROOT = _SCRIPT_DIR.parent
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))


# ── Контракт, разделяемый с миграцией c8e2b5f7a3d1 ───────────────────────────
# Дублирование намеренно: runtime-скрипт не импортирует модуль ревизии (тот
# тянет alembic и не предназначен для продакшн-импорта). Расхождение ловит
# drift-тест tests/test_anonymize_ips_cli_unit.py.

ANONYMIZE_SIGNATURE = "public.anonymize_old_ips(integer)"
COUNT_SIGNATURE = "public.count_old_ips(integer)"
AUDIT_TABLES = ("audit_log", "auth_log", "data_change_log")

DEFAULT_DAYS = 90

# ── Стабильные фазы отказа ───────────────────────────────────────────────────
# Оператор различает причины ПО ФАЗЕ, а не по тексту ошибки: текст намеренно
# не содержит подробностей.

PHASE_CONFIG = "config"
PHASE_CONNECT = "connect"
PHASE_MISSING_FUNCTION = "missing_function"
PHASE_INSUFFICIENT_FUNCTION_PRIVILEGE = "insufficient_function_privilege"
PHASE_INSUFFICIENT_TABLE_PRIVILEGE = "insufficient_table_privilege"
PHASE_COUNT = "count"
PHASE_ANONYMIZE = "anonymize"

PREFLIGHT_PHASES = (
    PHASE_MISSING_FUNCTION,
    PHASE_INSUFFICIENT_FUNCTION_PRIVILEGE,
    PHASE_INSUFFICIENT_TABLE_PRIVILEGE,
)


class PhaseError(RuntimeError):
    """Отказ с указанием стабильной фазы.

    Сообщение исключения — ТОЛЬКО имя фазы. Класс исходного исключения
    сохраняется отдельным полем, чтобы попасть в лог, не таща за собой
    `str(exc)` с SQL, значениями строк или связкой параметров.
    """

    def __init__(self, phase: str, error_name: str):
        super().__init__(phase)
        self.phase = phase
        self.error_name = error_name


# ── Логирование ──────────────────────────────────────────────────────────────

def _setup_logging(log_dir: Path) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"anonymize_old_ips_{ts}.log"

    logger = logging.getLogger("anonymize_old_ips")
    logger.setLevel(logging.DEBUG)
    # Идемпотентность: повторный вызов (в т.ч. из тестов) не должен множить
    # хендлеры и дублировать строки.
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

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


# ── Конфигурация и engine ────────────────────────────────────────────────────

def database_url() -> str:
    """Отложенный импорт настроек: приложение не загружается до этого момента.

    Импортируется ТОЛЬКО `app.core.config` — ни `SessionLocal`, ни `app.main`,
    ни доменные сервисы. Значение никуда не логируется.
    """
    from app.core.config import settings

    db_url = getattr(settings, "DATABASE_URL", None)
    if not db_url:
        raise PhaseError(PHASE_CONFIG, "ValueError")
    return db_url


def create_engine_for(db_url: str):
    """Отдельная функция — точка подмены в unit-тестах (без реальной БД)."""
    return sa.create_engine(db_url, poolclass=pool.NullPool)


# ── Preflight (только read-only catalog-функции) ─────────────────────────────

def preflight_functions_exist(conn) -> None:
    """Обе функции существуют с ТОЧНЫМИ сигнатурами.

    Выполняется ПЕРВОЙ: `has_function_privilege()` на несуществующей функции
    бросает исключение, и без этой проверки отсутствие миграции выглядело бы
    как отказ по привилегиям.
    """
    try:
        ok = conn.execute(sa.text("""
            SELECT to_regprocedure(:anon) IS NOT NULL
               AND to_regprocedure(:cnt) IS NOT NULL
        """), {"anon": ANONYMIZE_SIGNATURE, "cnt": COUNT_SIGNATURE}).scalar()
    except Exception as exc:   # noqa: BLE001 — переупаковка в стабильную фазу
        raise PhaseError(PHASE_MISSING_FUNCTION, type(exc).__name__) from None
    if not ok:
        raise PhaseError(PHASE_MISSING_FUNCTION, "PhaseError")


def preflight_function_privileges(conn) -> None:
    """У вызывающей роли есть EXECUTE на ОБЕИХ функциях."""
    try:
        ok = conn.execute(sa.text("""
            SELECT has_function_privilege(current_user, :anon, 'EXECUTE')
               AND has_function_privilege(current_user, :cnt, 'EXECUTE')
        """), {"anon": ANONYMIZE_SIGNATURE, "cnt": COUNT_SIGNATURE}).scalar()
    except Exception as exc:   # noqa: BLE001 — переупаковка в стабильную фазу
        raise PhaseError(
            PHASE_INSUFFICIENT_FUNCTION_PRIVILEGE, type(exc).__name__
        ) from None
    if not ok:
        raise PhaseError(PHASE_INSUFFICIENT_FUNCTION_PRIVILEGE, "PhaseError")


def preflight_table_privileges(conn, *, live: bool) -> None:
    """Табличные права, которых требует `SECURITY INVOKER`.

    Проверяется ровно то, что нужно выбранному режиму: dry-run обращается к
    журналам только на чтение и НЕ должен падать из-за отсутствия UPDATE.

    Имена таблиц передаются schema-qualified (`public.<table>`), а не через
    `search_path`: `has_column_privilege()` резолвит текстовый аргумент так же,
    как обычная ссылка на объект, и без явной схемы могла бы попасть на
    одноимённую таблицу в другой схеме, если `search_path` вызывающей роли
    отличается от стандартного.
    """
    qualified_tables = [f"public.{table}" for table in AUDIT_TABLES]
    try:
        ok = conn.execute(sa.text("""
            SELECT bool_and(
                       has_column_privilege(current_user, t, 'created_at', 'SELECT')
                   AND has_column_privilege(current_user, t, 'ip_address', 'SELECT')
                   AND (NOT CAST(:live AS boolean)
                        OR has_column_privilege(current_user, t, 'ip_address',
                                                'UPDATE'))
                   )
              FROM unnest(CAST(:tables AS text[])) AS t
        """), {"live": live, "tables": qualified_tables}).scalar()
    except Exception as exc:   # noqa: BLE001 — переупаковка в стабильную фазу
        raise PhaseError(
            PHASE_INSUFFICIENT_TABLE_PRIVILEGE, type(exc).__name__
        ) from None
    if not ok:
        raise PhaseError(PHASE_INSUFFICIENT_TABLE_PRIVILEGE, "PhaseError")


# ── Выполнение ───────────────────────────────────────────────────────────────

def execute_job(conn, *, days: int, dry_run: bool) -> int:
    """Вызывает рабочую функцию. Вызывается ТОЛЬКО после всех трёх preflight."""
    phase = PHASE_COUNT if dry_run else PHASE_ANONYMIZE
    function = COUNT_SIGNATURE if dry_run else ANONYMIZE_SIGNATURE
    name = function.split("(")[0]
    try:
        # bigint приходит в Python как int произвольной точности — сужения нет.
        return conn.execute(
            sa.text(f"SELECT {name}(:days)"), {"days": days}
        ).scalar()
    except Exception as exc:   # noqa: BLE001 — переупаковка в стабильную фазу
        raise PhaseError(phase, type(exc).__name__) from None


def run(engine, *, days: int, dry_run: bool) -> int:
    """Единственная transaction boundary: preflight + работа.

    Отдельного `conn.begin()` здесь нет и быть не может — см. блок про autobegin
    в docstring модуля.
    """
    with engine.begin() as conn:
        preflight_functions_exist(conn)
        preflight_function_privileges(conn)
        preflight_table_privileges(conn, live=not dry_run)
        return execute_job(conn, days=days, dry_run=dry_run)


# ── Точка входа ──────────────────────────────────────────────────────────────

def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Null out ip_address older than N days in audit_log, auth_log and "
            "data_change_log."
        )
    )
    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_DAYS,
        metavar="N",
        help=f"Retention window in days, must be >= 1 (default: {DEFAULT_DAYS})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only count matching rows; never mutates and takes no locks",
    )
    return parser.parse_args(argv)


def _report_failure(logger, phase: str, error_name: str) -> None:
    """Единая точка минимизированной диагностики отказа.

    Если логгер уже создан — пишет через него (файл + stdout, как обычно).
    Если `_setup_logging` сама упала раньше, чем появился логгер, — пишет
    ТОЛЬКО в stderr, тем же форматом строки и с тем же контрактом
    (никаких путей, `str(exc)`, значений).
    """
    if logger is not None:
        logger.error("[error] phase=%s error=%s", phase, error_name)
        logger.error("=== anonymize_old_ips FAILED ===")
    else:
        print(f"[error] phase={phase} error={error_name}", file=sys.stderr)


def main(argv=None) -> int:
    args = parse_args(argv)

    # Определены заранее: любой сбой ДО их присвоения (включая саму настройку
    # логирования) обязан находить оба в предсказуемом состоянии — `dispose()`
    # не обращается к несуществующему engine, диагностика не падает на
    # отсутствующем логгере.
    engine = None
    logger = None
    phase = PHASE_CONFIG
    try:
        log_dir = _API_ROOT / "logs" / "maintenance"
        logger = _setup_logging(log_dir)

        mode = "dry-run" if args.dry_run else "live"
        logger.info("=== anonymize_old_ips START ===")
        logger.info("[config] mode=%s days=%s", mode, args.days)

        # Единственная проверка вне транзакции и вне БД: некорректное окно
        # ретенции обязано отсекаться ДО подключения. Границу дублирует и сама
        # функция (SQLSTATE 22023) — здесь это ранний, дешёвый отказ.
        if args.days < 1:
            raise PhaseError(PHASE_CONFIG, "ValueError")

        db_url = database_url()

        phase = PHASE_CONNECT
        engine = create_engine_for(db_url)

        affected = run(engine, days=args.days, dry_run=args.dry_run)

        logger.info(
            "[result] mode=%s days=%s affected_rows=%s", mode, args.days, affected
        )
        logger.info("=== anonymize_old_ips SUCCESS ===")
        return 0

    except PhaseError as exc:
        _report_failure(logger, exc.phase, exc.error_name)
        return 1

    except Exception as exc:   # noqa: BLE001 — см. правило минимизации выше
        # Сюда попадает в т.ч. сбой самой _setup_logging: `phase` в этот момент
        # ещё PHASE_CONFIG, поэтому диагностика получает верную фазу без
        # дополнительной ветки.
        _report_failure(logger, phase, type(exc).__name__)
        return 1

    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
