#!/usr/bin/env python3
"""
extend_schedules.py — maintenance-скрипт ежемесячного автопродления расписаний.

Продлевает effective_until на N месяцев для активных серий расписания с
auto_extend=True, у которых окно заканчивается в пределах --within-days дней.
После продления создавшему серию supervisor'у отправляется system-сообщение.

Использование:
    cd mindcare_api/
    python scripts/extend_schedules.py
    python scripts/extend_schedules.py --within-days 14 --months 1
    python scripts/extend_schedules.py --dry-run

Логи сохраняются в:
    mindcare_api/logs/maintenance/extend_schedules_<timestamp>.log

Правила:
  - Запускать ОТДЕЛЬНО от FastAPI startup/lifespan (cron/Task Scheduler).
  - НЕ вызывать из FastAPI lifespan.
  - dry-run не меняет БД и не шлёт уведомления.
  - Любая ошибка → exit 1.
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

# Путь к корню mindcare_api/ — для импорта app.*
_SCRIPT_DIR = Path(__file__).resolve().parent
_API_ROOT = _SCRIPT_DIR.parent
sys.path.insert(0, str(_API_ROOT))


def _setup_logging(log_dir: Path) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"extend_schedules_{ts}.log"

    logger = logging.getLogger("extend_schedules")
    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

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


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Auto-extend schedule series (auto_extend=True) by N months."
        )
    )
    parser.add_argument(
        "--within-days",
        type=int,
        default=14,
        metavar="N",
        help="Extend series whose window ends within N days (default: 14)",
    )
    parser.add_argument(
        "--months",
        type=int,
        default=1,
        metavar="M",
        help="Number of months to extend by (default: 1)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be extended without changing the DB",
    )
    args = parser.parse_args()

    if args.within_days < 0:
        print("ERROR: --within-days must be >= 0", file=sys.stderr)
        sys.exit(1)
    if args.months < 1:
        print("ERROR: --months must be >= 1", file=sys.stderr)
        sys.exit(1)

    log_dir = _API_ROOT / "logs" / "maintenance"
    logger = _setup_logging(log_dir)

    logger.info("=== extend_schedules START ===")
    logger.info(
        "mode=%s  within_days=%d  months=%d",
        "DRY-RUN" if args.dry_run else "LIVE",
        args.within_days,
        args.months,
    )

    try:
        from app.appointments import service

        result = service.auto_extend_schedules(
            within_days=args.within_days,
            months=args.months,
            dry_run=args.dry_run,
        )
        logger.info(
            "[result] extended_series=%d notified=%d dry_run=%s",
            result["extended_series"],
            result["notified"],
            result["dry_run"],
        )
        logger.info("=== extend_schedules SUCCESS ===")
    except Exception as exc:
        # Минимизация (Stage 5C-3): только фаза и класс исключения. Без
        # str(exc), SQL, series UUID, дат и иных значений — по образцу
        # app/audit/service.py::_diag.
        logger.error(
            "[error] phase=auto_extend error=%s", type(exc).__name__
        )
        logger.error("=== extend_schedules FAILED ===")
        sys.exit(1)


if __name__ == "__main__":
    main()
