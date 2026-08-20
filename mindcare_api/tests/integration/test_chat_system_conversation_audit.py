"""
Stage 4B-3 — gated integration: system_conversation_created через record_event()
с race-safe conversation_created (app.chat.system_publisher). Запуск ТОЛЬКО через
Stage 1 isolated runner; dev/prod запрещены.

Триггер — registration confirm (auth/service.py::register_confirm), которое
публикует welcome system-сообщение новому пользователю: первый вызов создаёт
system-беседу впервые, что должно дать РОВНО одну строку system_conversation_
created с точным actor mapping (user_id IS NULL, user_role == "system", не NULL).
"""
import uuid as _uuid

from app.core.normalization import normalize_email
from app.db.session import SessionLocal
from app.db.models import AuditLog, ChatConversation, User
from tests.integration.conftest import ALLOWED_TEST_DOMAIN

PASSWORD = "SecurePass42!"


def _register(client, capture_emails, email):
    r = client.post("/api/auth/register/init",
                    json={"name": "SysConv User", "email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    code = capture_emails[email][-1]
    r = client.post("/api/auth/register/confirm", json={"email": email, "code": code})
    assert r.status_code == 201, r.text
    return r


def test_system_conversation_created_exact_mapping(client, capture_emails):
    email = f"integ_sysconv_{_uuid.uuid4().hex[:10]}@{ALLOWED_TEST_DOMAIN}"
    _register(client, capture_emails, email)

    with SessionLocal() as db:
        user_id = (
            db.query(User.id)
            .filter(User.email == normalize_email(email))
            .scalar()
        )
        conv = (
            db.query(ChatConversation)
            .filter(ChatConversation.type == "system", ChatConversation.recipient_id == user_id)
            .first()
        )
        assert conv is not None, "system-беседа должна быть создана welcome-уведомлением"

        rows = (
            db.query(AuditLog)
            .filter(
                AuditLog.event_type == "system_conversation_created",
                AuditLog.entity_type == "chat_conversation",
                AuditLog.entity_id == conv.id,
            )
            .all()
        )

    # Ровно одна строка на фактически созданную системную беседу.
    assert len(rows) == 1
    row = rows[0]
    # Точный actor mapping: user_id IS NULL И user_role == "system" — NULL
    # user_role НЕ считается допустимой альтернативой (см. Stage 4B-3 plan §2).
    assert row.user_id is None
    assert row.user_role == "system"
    assert row.entity_id == conv.id
    assert (row.log_metadata or {}) == {}
    assert row.description is None
    # recipient_id (== user_id пользователя) не должен фигурировать как actor.
    assert row.user_id != user_id


def test_second_welcome_call_does_not_duplicate_conversation_created(client, capture_emails):
    # Идемпотентность по event_key ("welcome:user:{id}") означает, что
    # get_or_create_system_conversation при повторном вызове (гипотетически,
    # если бы welcome вызывался дважды для того же recipient) вернёт
    # conversation_created=False на второй раз — не должно быть второй строки.
    from app.chat.system_publisher import publish_system_message

    email = f"integ_sysconv2_{_uuid.uuid4().hex[:10]}@{ALLOWED_TEST_DOMAIN}"
    _register(client, capture_emails, email)

    with SessionLocal() as db:
        user_id = db.query(User.id).filter(User.email == normalize_email(email)).scalar()

    # Повторная публикация (другой event_key, та же system-беседа получателя).
    publish_system_message(
        recipient_id=user_id, event_key=f"extra:user:{user_id}", text="second",
    )

    with SessionLocal() as db:
        conv = (
            db.query(ChatConversation)
            .filter(ChatConversation.type == "system", ChatConversation.recipient_id == user_id)
            .first()
        )
        rows = (
            db.query(AuditLog)
            .filter(
                AuditLog.event_type == "system_conversation_created",
                AuditLog.entity_id == conv.id,
            )
            .all()
        )
    assert len(rows) == 1   # беседа создана только один раз welcome-уведомлением
