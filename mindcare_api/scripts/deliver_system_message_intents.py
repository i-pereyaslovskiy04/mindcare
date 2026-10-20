#!/usr/bin/env python3
"""
deliver_system_message_intents.py — повторная доставка сохранённых намерений
system-сообщений (outbox `system_message_intents`, ADR-029).

Намерение пишется в транзакции бизнес-операции (регистрация по паролю и через
Яндекс — приглашение подтвердить статус студента ДонГУ; решение supervisor'а
по заявке — результат). Сразу после commit операция пытается доставить его
сама (soft-fail). Этот job добирает то, что не доставилось: сбой publisher,
падение процесса между commit и публикацией, сбой отметки delivered.

Дубля не бывает: повторная публикация с тем же event_key не создаёт второе
сообщение (partial UNIQUE ux_chat_messages_event_key), а publisher в этом случае
возвращает успешный результат — намерение отмечается доставленным.

Audit: событий НЕ пишет — это техническая доставка уже зафиксированного
решения/регистрации, прав и состояния заявок не меняет. Создание system-беседы
по-прежнему пишет system_conversation_created (publisher).

Использование:
    cd mindcare_api/
    python scripts/deliver_system_message_intents.py              # доставка
    python scripts/deliver_system_message_intents.py --dry-run    # только счёт
    python scripts/deliver_system_message_intents.py --limit 200

Exit code:
    0 — чтение outbox успешно и все найденные намерения доставлены
        (пустая очередь — только при УСПЕШНОМ чтении);
    1 — ошибка чтения outbox, либо хотя бы одна публикация/отметка delivered
        не удалась (намерение останется в очереди до следующего запуска).

Логи: mindcare_api/logs/maintenance/deliver_system_message_intents_<ts>.log.
Диагностика — только агрегаты (found/delivered/failed) и фаза/класс
исключения: без id пользователей, event_key, текста сообщений и str(exc).

Правила:
  - Запускать ОТДЕЛЬНО от FastAPI (systemd timer
    mindcare-deliver-system-messages.timer, cron, Task Scheduler).
  - НЕ вызывать из FastAPI lifespan.
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

DEFAULT_LIMIT = 500
_NAME = "deliver_system_message_intents"


def _setup_logging(log_dir: Path) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"{_NAME}_{ts}.log"

    logger = logging.getLogger(_NAME)
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


def _positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be >= 1")
    return number


def run(*, limit: int, dry_run: bool, logger: logging.Logger) -> int:
    """Возвращает exit code. Ошибка чтения outbox → 1 (не «пустая очередь»)."""
    from app.notifications import service

    if dry_run:
        try:
            pending = service.count_pending()
        except Exception as exc:  # noqa: BLE001 — только фаза и класс
            logger.error("[error] phase=read error=%s", type(exc).__name__)
            return 1
        logger.info("[dry-run] pending=%d", pending)
        return 0

    try:
        stats = service.run_pending(limit)
    except Exception as exc:  # noqa: BLE001 — только фаза и класс
        logger.error("[error] phase=read error=%s", type(exc).__name__)
        return 1

    logger.info(
        "[result] found=%d delivered=%d failed=%d",
        stats.found, stats.delivered, stats.failed,
    )
    return 1 if stats.failed else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Deliver pending system message intents (outbox retry).",
    )
    parser.add_argument(
        "--limit", type=_positive_int, default=DEFAULT_LIMIT,
        help=f"max intents per run (default {DEFAULT_LIMIT})",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="only count undelivered intents, deliver nothing",
    )
    args = parser.parse_args(argv)

    logger = _setup_logging(_API_ROOT / "logs" / "maintenance")
    logger.info("=== %s START ===", _NAME)
    code = run(limit=args.limit, dry_run=args.dry_run, logger=logger)
    logger.info("=== %s %s ===", _NAME, "SUCCESS" if code == 0 else "FAILED")
    return code


if __name__ == "__main__":
    sys.exit(main())
