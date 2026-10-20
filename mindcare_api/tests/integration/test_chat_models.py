"""
DB/model constraint tests for Chat MVP foundation (Stage 28b).

Покрывает только схему и ограничения БД:
  - conversation создаётся для существующего engagement;
  - двух conversations на один engagement быть не может (UNIQUE);
  - message создаётся, content вмещает enc:v1:-строку;
  - sender связан с users; orphan message/conversation невозможны (FK);
  - read_at / deleted_at по умолчанию NULL.

Encryption и chat API здесь НЕ тестируются — это Stage 28c.
Требования: dev PostgreSQL на alembic head (d8f3a6c1e9b4).
"""

import uuid as _uuid

import bcrypt
import pytest
from sqlalchemy.exc import IntegrityError

from app.auth import storage as auth_storage
from app.db.session import SessionLocal
from app.db.models import ChatConversation, ChatMessage, TherapyEngagement

PASSWORD = "SecurePass42!"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_user(role: str) -> int:
    user = auth_storage.save_user({
        "name":            f"Chat Model {role.capitalize()}",
        "email":           f"integ_chat_{role}_{_uuid.uuid4().hex[:10]}@example.com",
        "hashed_password": bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode(),
        "role":            role,
    })
    return int(user["id"])


def _make_engagement() -> int:
    """Создаёт student + psychologist + active engagement. Возвращает engagement id."""
    student_id = _make_user("student")
    psychologist_id = _make_user("psychologist")
    with SessionLocal() as db:
        eng = TherapyEngagement(
            client_id=student_id,
            psychologist_id=psychologist_id,
            status="active",
        )
        db.add(eng)
        db.commit()
        db.refresh(eng)
        return eng.id


def _make_conversation(engagement_id: int) -> int:
    with SessionLocal() as db:
        conv = ChatConversation(engagement_id=engagement_id)
        db.add(conv)
        db.commit()
        db.refresh(conv)
        return conv.id


# ─── 1. Conversations ─────────────────────────────────────────────────────────

class TestChatConversation:
    def test_create_for_existing_engagement(self, client):
        eng_id = _make_engagement()
        conv_id = _make_conversation(eng_id)

        with SessionLocal() as db:
            conv = db.query(ChatConversation).filter(
                ChatConversation.id == conv_id
            ).one()
            assert conv.engagement_id == eng_id
            assert conv.uuid is not None
            assert conv.created_at is not None
            assert conv.last_message_at is None
            assert conv.engagement.id == eng_id  # relationship работает

    def test_duplicate_conversation_per_engagement_rejected(self, client):
        eng_id = _make_engagement()
        _make_conversation(eng_id)

        with pytest.raises(IntegrityError):
            _make_conversation(eng_id)  # ux_chat_conversations_engagement

    def test_conversation_without_engagement_rejected(self, client):
        with SessionLocal() as db:
            db.add(ChatConversation(engagement_id=999_999_999))
            with pytest.raises(IntegrityError):
                db.commit()


# ─── 2. Messages ──────────────────────────────────────────────────────────────

class TestChatMessage:
    def test_create_message_with_encrypted_style_content(self, client):
        eng_id = _make_engagement()
        conv_id = _make_conversation(eng_id)
        sender_id = _make_user("student")
        ciphertext = "enc:v1:" + "gAAAAA" + "x" * 100  # формат будущего ciphertext

        with SessionLocal() as db:
            msg = ChatMessage(
                conversation_id=conv_id,
                sender_id=sender_id,
                content=ciphertext,
            )
            db.add(msg)
            db.commit()
            db.refresh(msg)

            assert msg.uuid is not None
            assert msg.content == ciphertext
            assert msg.created_at is not None
            assert msg.read_at is None       # default NULL
            assert msg.deleted_at is None    # default NULL
            assert msg.sender.id == sender_id        # relationship → users
            assert msg.conversation.id == conv_id    # relationship → conversation

    def test_message_without_conversation_rejected(self, client):
        sender_id = _make_user("student")
        with SessionLocal() as db:
            db.add(ChatMessage(
                conversation_id=999_999_999,
                sender_id=sender_id,
                content="enc:v1:orphan",
            ))
            with pytest.raises(IntegrityError):
                db.commit()

    def test_message_without_sender_rejected(self, client):
        eng_id = _make_engagement()
        conv_id = _make_conversation(eng_id)
        with SessionLocal() as db:
            db.add(ChatMessage(
                conversation_id=conv_id,
                sender_id=999_999_999,
                content="enc:v1:nosender",
            ))
            with pytest.raises(IntegrityError):
                db.commit()
