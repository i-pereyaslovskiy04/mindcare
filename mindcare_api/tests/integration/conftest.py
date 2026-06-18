"""
Fixtures for API/integration tests (tests/integration/).

Prerequisites:
  - PostgreSQL dev DB must be running with alembic upgrade head applied.
  - Seed data must include privacy_policy and data_processing consents.
  - EMAIL_MODE=dev (default) — no real email is sent; transport is patched.

These fixtures are scoped to tests/integration/ only and do NOT affect the
unit tests in tests/  (test_change_password, test_encryption, test_normalization).
"""

import re
import uuid
from unittest.mock import patch

import bcrypt
import pytest
from starlette.testclient import TestClient

from app.main import app
from app.auth import storage as auth_storage
from app.db.session import SessionLocal
from app.db.models import (
    ChatAttachment, ChatConversation, ChatMessage, ConsentRecord,
    OtpVerification, TherapyEngagement, User,
)


# ─── HTTP client ──────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def client():
    """
    Session-scoped TestClient backed by the real dev PostgreSQL DB.
    Runs the FastAPI lifespan (init_db + seed) exactly once per test session.
    """
    # client=("127.0.0.1", 50000) provides a valid inet address for DB columns.
    # Default "testclient" is not a valid inet value and causes DataError.
    with TestClient(app, client=("127.0.0.1", 50000)) as c:
        yield c


# ─── Test email ───────────────────────────────────────────────────────────────

@pytest.fixture
def test_email():
    """
    Unique per-test email address.  Uses example.com (IANA reserved for tests).
    Cleanup fixture removes all integ_* @example.com records after each test.
    """
    return f"integ_{uuid.uuid4().hex[:12]}@example.com"


# ─── Email / OTP interception ─────────────────────────────────────────────────

@pytest.fixture
def capture_emails():
    """
    Patches app.services._smtp.send_email and captures OTP codes by recipient.

    Yields a dict: { to_address: [code, ...] }

    The key is the pre-normalization address passed to send_email (i.e. the
    address the service received from the request body after pydantic parsed it,
    but before storage normalized it).  Use capture_emails[init_email][-1] to
    get the most recently sent code.
    """
    sent: dict[str, list[str]] = {}

    def _fake(to: str, subject: str, body: str, html: str | None = None) -> None:
        match = re.search(r"Ваш код: (\d{6})", body)
        if match:
            sent.setdefault(to, []).append(match.group(1))

    # email_service.py does `from app.services._smtp import send_email`,
    # so we must patch the imported name in that module, not the source.
    with patch("app.services.email_service.send_email", side_effect=_fake):
        yield sent


# ─── Rate limiter isolation ───────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """
    Сбрасывает in-memory rate limiter перед каждым тестом.

    Все integration-тесты ходят через один TestClient с одним IP (127.0.0.1),
    поэтому без сброса IP-лимиты auth-эндпоинтов срабатывали бы на сумме
    запросов всей сессии, а не одного теста.
    """
    from app.core import rate_limit
    rate_limit.reset()
    yield


# ─── DB cleanup ───────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def cleanup_test_records():
    """
    Deletes all integ_*@example.com test records from the dev DB after each test.

    Cleanup order respects FK constraints:
      1. chat_messages → chat_conversations → therapy_engagements
         (chat FKs — ON DELETE RESTRICT: иначе cascade-удаление engagement
          при удалении user заблокируется беседой)
      2. consent_records (ondelete=SET NULL — must delete explicitly)
      3. users            (cascades user_roles, user_sessions, profiles, etc.)
      4. otp_verifications (no FK to users — standalone)
    """
    yield
    with SessionLocal() as db:
        ids = [
            row.id
            for row in db.query(User.id)
            .filter(User.email.like("integ_%@example.com"))
            .all()
        ]
        if ids:
            eng_ids = [
                row.id
                for row in db.query(TherapyEngagement.id).filter(
                    TherapyEngagement.client_id.in_(ids)
                    | TherapyEngagement.psychologist_id.in_(ids)
                ).all()
            ]
            # Беседы integ-пользователей: system (по recipient_id) + engagement (по eng_ids).
            conv_ids = set(
                row.id
                for row in db.query(ChatConversation.id).filter(
                    ChatConversation.recipient_id.in_(ids)
                ).all()
            )
            if eng_ids:
                conv_ids |= set(
                    row.id
                    for row in db.query(ChatConversation.id).filter(
                        ChatConversation.engagement_id.in_(eng_ids)
                    ).all()
                )
            conv_ids = list(conv_ids)
            if conv_ids:
                # chat_attachments FK → chat_messages (RESTRICT): удалять до messages.
                db.query(ChatAttachment).filter(
                    ChatAttachment.conversation_id.in_(conv_ids)
                ).delete(synchronize_session=False)
                db.query(ChatMessage).filter(
                    ChatMessage.conversation_id.in_(conv_ids)
                ).delete(synchronize_session=False)
                db.query(ChatConversation).filter(
                    ChatConversation.id.in_(conv_ids)
                ).delete(synchronize_session=False)
            if eng_ids:
                db.query(TherapyEngagement).filter(
                    TherapyEngagement.id.in_(eng_ids)
                ).delete(synchronize_session=False)
            db.query(ConsentRecord).filter(
                ConsentRecord.user_id.in_(ids)
            ).delete(synchronize_session=False)
            db.query(User).filter(
                User.id.in_(ids)
            ).delete(synchronize_session=False)
        db.query(OtpVerification).filter(
            OtpVerification.email.like("integ_%@example.com")
        ).delete(synchronize_session=False)
        db.commit()


# ─── Test user factory ────────────────────────────────────────────────────────

def create_test_user(email: str, password: str = "SecurePass42!") -> dict:
    """
    Insert a test user directly into the dev DB via auth storage.
    Use this in tests that need a pre-existing user (login tests, reset tests).
    The user gets the 'student' role; no consent_records are created.
    """
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    return auth_storage.save_user({
        "name":            "Integration Test User",
        "email":           email,
        "hashed_password": pw_hash,
        "role":            "student",
    })
