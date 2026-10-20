"""
ADR-029 — unit-тесты scripts/deliver_system_message_intents.py БЕЗ БД.

Сервис outbox подменяется: проверяется control flow job'а — коды выхода,
отсутствие маскировки ошибки чтения под «пустую очередь», минимизированная
диагностика (только агрегаты и фаза/класс, без id/ключей/текста).
"""
import logging
import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import deliver_system_message_intents as cli  # noqa: E402

from app.notifications import service as outbox_service  # noqa: E402

SECRET_KEY = "student_verification_invite:user:4242"


@pytest.fixture
def logger(caplog):
    caplog.set_level(logging.DEBUG, logger="cli-test")
    return logging.getLogger("cli-test")


def _stats(found, delivered, failed):
    return outbox_service.DeliveryStats(found=found, delivered=delivered, failed=failed)


def test_all_delivered_exits_zero(monkeypatch, logger, caplog):
    monkeypatch.setattr(outbox_service, "run_pending", lambda limit: _stats(3, 3, 0))
    assert cli.run(limit=10, dry_run=False, logger=logger) == 0
    assert "found=3 delivered=3 failed=0" in caplog.text


def test_empty_queue_after_successful_read_exits_zero(monkeypatch, logger, caplog):
    monkeypatch.setattr(outbox_service, "run_pending", lambda limit: _stats(0, 0, 0))
    assert cli.run(limit=10, dry_run=False, logger=logger) == 0
    assert "found=0" in caplog.text


def test_any_failed_delivery_or_mark_exits_nonzero(monkeypatch, logger):
    monkeypatch.setattr(outbox_service, "run_pending", lambda limit: _stats(2, 1, 1))
    assert cli.run(limit=10, dry_run=False, logger=logger) == 1


def test_read_error_is_not_reported_as_empty_queue(monkeypatch, logger, caplog):
    def _boom(limit):
        raise RuntimeError(f"connection refused for {SECRET_KEY}")
    monkeypatch.setattr(outbox_service, "run_pending", _boom)
    assert cli.run(limit=10, dry_run=False, logger=logger) == 1
    assert "phase=read error=RuntimeError" in caplog.text
    assert "found=" not in caplog.text
    assert SECRET_KEY not in caplog.text and "connection refused" not in caplog.text


def test_dry_run_only_counts(monkeypatch, logger, caplog):
    monkeypatch.setattr(outbox_service, "count_pending", lambda: 4)
    monkeypatch.setattr(outbox_service, "run_pending",
                        lambda limit: pytest.fail("dry-run must not deliver"))
    assert cli.run(limit=10, dry_run=True, logger=logger) == 0
    assert "pending=4" in caplog.text


def test_dry_run_read_error_exits_nonzero(monkeypatch, logger, caplog):
    def _boom():
        raise RuntimeError("db down")
    monkeypatch.setattr(outbox_service, "count_pending", _boom)
    assert cli.run(limit=10, dry_run=True, logger=logger) == 1
    assert "phase=read error=RuntimeError" in caplog.text


def test_limit_must_be_positive():
    with pytest.raises(SystemExit):
        cli.main(["--limit", "0"])


def test_main_returns_run_code(monkeypatch, logger):
    monkeypatch.setattr(cli, "_setup_logging", lambda log_dir: logger)
    monkeypatch.setattr(outbox_service, "run_pending", lambda limit: _stats(1, 0, 1))
    assert cli.main(["--limit", "5"]) == 1
