"""
Доставка сохранённых намерений system-сообщений (ADR-029). Без FastAPI/HTTP.

  deliver_intent       — одна попытка: текст по коду → publish_system_message
                         (существующий publisher, event_key) → mark_delivered.
                         delivered отмечается ТОЛЬКО после успешного результата
                         publisher (dict, в т.ч. created=False — сообщение уже
                         опубликовано прошлой попыткой, упавшей до отметки).
  deliver_by_key_soft  — post-commit шаг основной операции: никогда не бросает,
                         сбой оставляет намерение недоставленным для retry-job.
  run_pending          — пакет для retry-job: чтение outbox НЕ глотается
                         (ошибка ≠ «пустая очередь»), каждый не-DELIVERED исход
                         считается failed.

Технические сбои доставки — не бизнес-исход: audit-событий здесь нет (решение
по заявке/регистрация уже зафиксированы своим событием; создание беседы
покрывает system_conversation_created). Диагностика — только фаза и класс
исключения: без recipient_id, event_key, текста и str(exc).
"""
import enum
import logging
from dataclasses import dataclass
from typing import Optional

from app.notifications import storage
from app.notifications.templates import MESSAGE_TEMPLATES

log = logging.getLogger(__name__)


class DeliveryOutcome(enum.Enum):
    DELIVERED = "delivered"
    PUBLISH_FAILED = "publish_failed"
    MARK_FAILED = "mark_failed"


@dataclass(frozen=True)
class DeliveryStats:
    found: int
    delivered: int
    failed: int


def _diag(phase: str, error_class: str) -> None:
    log.warning("[system_message_intents] phase=%s error=%s", phase, error_class)


def _record_attempt_soft(intent_id: int) -> None:
    try:
        storage.record_attempt(intent_id)
    except Exception as exc:  # noqa: BLE001 — счётчик не меняет исход попытки
        _diag("record_attempt", type(exc).__name__)


def deliver_intent(intent: dict) -> DeliveryOutcome:
    """Одна попытка доставки намерения. Наружу не бросает."""
    text = MESSAGE_TEMPLATES.get(intent["message_code"])
    if text is None:
        _diag("template", "UnknownMessageCode")
        _record_attempt_soft(intent["id"])
        return DeliveryOutcome.PUBLISH_FAILED

    # Поздний импорт: publisher подменяется в тестах на уровне модуля.
    from app.chat.system_publisher import publish_system_message
    try:
        result = publish_system_message(
            recipient_id=int(intent["recipient_id"]),
            event_key=intent["event_key"],
            text=text,
        )
    except Exception as exc:  # noqa: BLE001 — publisher обязан не бросать
        _diag("publish", type(exc).__name__)
        result = None

    if result is None:
        _record_attempt_soft(intent["id"])
        return DeliveryOutcome.PUBLISH_FAILED

    try:
        storage.mark_delivered(intent["id"])
    except Exception as exc:  # noqa: BLE001 — сообщение есть, отметку повторит job
        _diag("mark_delivered", type(exc).__name__)
        return DeliveryOutcome.MARK_FAILED
    return DeliveryOutcome.DELIVERED


def deliver_by_key_soft(recipient_id: int, event_key: str) -> Optional[DeliveryOutcome]:
    """
    Post-commit доставка намерения основной операции. Soft-fail: регистрация
    или решение уже зафиксированы — сбой здесь их не откатывает и наружу не
    выходит. Нет недоставленного намерения → None.
    """
    try:
        intent = storage.get_undelivered_by_key(recipient_id, event_key)
        if intent is None:
            return None
        return deliver_intent(intent)
    except Exception as exc:  # noqa: BLE001 — post-commit soft-fail
        _diag("post_commit", type(exc).__name__)
        return None


def run_pending(limit: int) -> DeliveryStats:
    """
    Пакет недоставленных намерений для retry-job. Ошибка чтения outbox
    всплывает (job завершится ненулевым кодом, а не отчитается пустой очередью).
    """
    intents = storage.get_undelivered(limit)
    delivered = 0
    failed = 0
    for intent in intents:
        if deliver_intent(intent) is DeliveryOutcome.DELIVERED:
            delivered += 1
        else:
            failed += 1
    return DeliveryStats(found=len(intents), delivered=delivered, failed=failed)


def count_pending() -> int:
    """Только счёт недоставленных (dry-run job). Ошибка чтения всплывает."""
    return storage.count_undelivered()
