#!/usr/bin/env python3
"""
complete_group_sessions.py — maintenance-скрипт перевода начавшихся/прошедших
групповых занятий в статус `completed` (Stage 5C-3).

Переводит `status='scheduled' AND starts_at <= now` → `completed` и закрывает
запись (`booking_enabled=false`). Каждый реальный переход пишет audit-событие
`group_session_completed` с системным actor'ом (user_id=NULL,
user_role='system') в ТОЙ ЖЕ транзакции: сбой аудита откатывает переход.

Ранее этот переход выполнялся лениво из GET/list-эндпоинтов и из регистрации
студента. Начиная со Stage 5C-3 read-пути НЕ мутируют данные, поэтому:

  ⚠ ЭКСПЛУАТАЦИОННОЕ ТРЕБОВАНИЕ (обязательное, не опция):
    скрипт обязан запускаться внешним планировщиком (cron / systemd timer /
    Windows Task Scheduler) с задокументированной периодичностью — наравне с
    extend_schedules.py и ensure_audit_partitions.py. Без него `status`
    групповых занятий перестаёт актуализироваться.

Запись студента на прошедшее занятие при этом НЕ становится возможной:
регистрация самостоятельно проверяет `status`, `booking_enabled` и lead time
(не позднее чем за 1 час до начала).

Использование:
    cd mindcare_api/
    python scripts/complete_group_sessions.py

Логи сохраняются в:
    mindcare_api/logs/maintenance/complete_group_sessions_<timestamp>.log

Правила:
  - Запускать ОТДЕЛЬНО от FastAPI startup/lifespan (cron/Task Scheduler).
  - НЕ вызывать из FastAPI lifespan.
  - Любая ошибка (мутация / audit / commit) → exit code 1.
  - Диагностика содержит только фазу и класс исключения (без str(exc)/SQL/id).
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
    log_file = log_dir / f"complete_group_sessions_{ts}.log"

    logger = logging.getLogger("complete_group_sessions")
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
            "Complete group sessions whose start time has passed "
            "(status scheduled -> completed)."
        )
    )
    parser.parse_args()

    log_dir = _API_ROOT / "logs" / "maintenance"
    logger = _setup_logging(log_dir)

    logger.info("=== complete_group_sessions START ===")

    try:
        from app.appointments import service

        result = service.complete_due_group_sessions_job()
        logger.info(
            "[result] completed_sessions=%d", result["completed_sessions"]
        )
        logger.info("=== complete_group_sessions SUCCESS ===")
    except Exception as exc:
        # Минимизация: только фаза и класс исключения — без str(exc), SQL,
        # id занятий и дат.
        logger.error(
            "[error] phase=complete_group_sessions error=%s",
            type(exc).__name__,
        )
        logger.error("=== complete_group_sessions FAILED ===")
        sys.exit(1)


if __name__ == "__main__":
    main()
