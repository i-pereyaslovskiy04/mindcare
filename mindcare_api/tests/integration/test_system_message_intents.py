"""
ADR-029 — gated integration: outbox system-сообщений на реальном PostgreSQL.

  * обычный дубль event_key → created=False, одно сообщение;
  * конкурентная доставка одного намерения двумя потоками → одно сообщение,
    намерение delivered, оба исхода DELIVERED;
  * нарушение ДРУГОГО ограничения (NOT NULL content) → publisher None, сообщения
    нет, намерение не отмечено, attempts растёт;
  * сбой после публикации до отметки delivered → retry отмечает без дубля;
  * enqueue повторного ключа — без второго намерения и без IntegrityError.
"""
import uuid as _uuid

from app.chat import storage as chat_storage
from app.chat.system_publisher import publish_system_message
from app.db.models import ChatConversation, ChatMessage, SystemMessageIntent
from app.db.session import SessionLocal
from app.notifications import service as outbox_service
from app.notifications import storage as outbox_storage
from app.notifications.templates import (
    MESSAGE_TEMPLATES, STUDENT_VERIFICATION_APPROVED,
)
from tests.integration.conftest import create_test_user
from tests.integration.lock_helpers import Gate, run_in_thread


def _user():
    email = f"integ_smi_{_uuid.uuid4().hex[:10]}@example.com"
    return int(create_test_user(email)["id"])


def _enqueue(user_id, key):
    with SessionLocal() as db:
        outbox_storage.enqueue_in_tx(
            db, recipient_id=user_id, event_key=key,
            message_code=STUDENT_VERIFICATION_APPROVED,
        )
        db.commit()
    return outbox_storage.get_undelivered_by_key(user_id, key)


def _intent(intent_id):
    with SessionLocal() as db:
        row = db.get(SystemMessageIntent, intent_id)
        db.expunge(row)
        return row


def _message_count(user_id, key):
    with SessionLocal() as db:
        return (
            db.query(ChatMessage)
            .join(ChatConversation, ChatConversation.id == ChatMessage.conversation_id)
            .filter(ChatConversation.recipient_id == user_id,
                    ChatMessage.event_key == key)
            .count()
        )


def test_plain_duplicate_event_key_is_reported_as_already_published(client):
    uid = _user()
    first = publish_system_message(uid, "dup:key", "A")
    second = publish_system_message(uid, "dup:key", "B")
    assert first["created"] is True and second["created"] is False
    assert _message_count(uid, "dup:key") == 1


def test_enqueue_same_key_twice_keeps_one_intent(client):
    uid = _user()
    _enqueue(uid, "same:key")
    _enqueue(uid, "same:key")
    with SessionLocal() as db:
        assert db.query(SystemMessageIntent).filter(
            SystemMessageIntent.recipient_id == uid).count() == 1


def test_concurrent_delivery_of_one_intent_publishes_once(client, monkeypatch):
    uid = _user()
    intent = _enqueue(uid, "concurrent:key")
    publish_system_message(uid, "warmup:key", "x")      # беседа уже существует
    gate = Gate()
    # Первый поток останавливается ДО вставки сообщения; второй успевает
    # опубликовать и отметить; первый затем упирается в ux_chat_messages_event_key.
    monkeypatch.setattr(chat_storage, "encrypt_text", gate.wrap(chat_storage.encrypt_text))
    first = run_in_thread(lambda: outbox_service.deliver_intent(dict(intent)))
    gate.wait_reached()
    second = run_in_thread(lambda: outbox_service.deliver_intent(dict(intent)))
    assert second.join() == ("ok", outbox_service.DeliveryOutcome.DELIVERED)
    gate.release.set()
    assert first.join() == ("ok", outbox_service.DeliveryOutcome.DELIVERED)

    assert _message_count(uid, "concurrent:key") == 1
    row = _intent(intent["id"])
    assert row.delivered_at is not None and row.attempts == 0


def test_foreign_constraint_violation_is_not_treated_as_delivered(client, monkeypatch):
    uid = _user()
    intent = _enqueue(uid, "notnull:key")
    publish_system_message(uid, "warmup:key", "x")
    monkeypatch.setattr(chat_storage, "encrypt_text", lambda text: None)  # NOT NULL

    outcome = outbox_service.deliver_intent(dict(intent))
    assert outcome is outbox_service.DeliveryOutcome.PUBLISH_FAILED
    assert _message_count(uid, "notnull:key") == 0
    row = _intent(intent["id"])
    assert row.delivered_at is None and row.attempts == 1 and row.last_attempt_at


def test_failure_between_publish_and_mark_is_recovered_without_duplicate(
    client, monkeypatch,
):
    uid = _user()
    intent = _enqueue(uid, "mark:key")

    def _boom(intent_id):
        raise RuntimeError("db went away")
    monkeypatch.setattr(outbox_storage, "mark_delivered", _boom)
    assert (outbox_service.deliver_intent(dict(intent))
            is outbox_service.DeliveryOutcome.MARK_FAILED)
    assert _message_count(uid, "mark:key") == 1
    assert _intent(intent["id"]).delivered_at is None

    monkeypatch.undo()
    stats = outbox_service.run_pending(1000)
    assert stats.found >= 1
    assert _intent(intent["id"]).delivered_at is not None
    assert _message_count(uid, "mark:key") == 1
    with SessionLocal() as db:
        (content,) = db.query(ChatMessage.content).filter(
            ChatMessage.event_key == "mark:key").one()
    from app.core.encryption import decrypt_text
    assert decrypt_text(content) == MESSAGE_TEMPLATES[STUDENT_VERIFICATION_APPROVED]
