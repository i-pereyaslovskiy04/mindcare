"""
Stage Social Auth 2A — DB-ограничения OAuth-фундамента (migration c6e1a4f8b2d7).

  F. user_oauth_identities: allowlist провайдеров, UNIQUE(provider, subject),
     UNIQUE(user_id, provider), FK + ON DELETE CASCADE, password_hash=NULL.
  G. oauth_auth_requests / oauth_pending_tickets: CHECK (provider/intent/kind,
     формат hash, verifier только enc:v1:, связка intent/kind ↔ user_id,
     нормализованный email, срок), one-time consumed_at.

Production-код записи в эти таблицы ещё не создаёт — здесь прямые ORM-вставки.
Нарушения распознаются по exc.orig.diag.constraint_name (стиль проекта).
Строки без user_id чистит локальная фикстура; с user_id — CASCADE при
удалении integ_*-пользователей в cleanup_test_records.
"""
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.encryption import encrypt_text
from app.db.models import (
    OAuthAuthRequest, OAuthPendingTicket, User, UserOAuthIdentity,
)
from app.db.session import SessionLocal

from tests.integration.conftest import create_test_user


@pytest.fixture(autouse=True)
def _cleanup_userless_oauth_rows():
    yield
    with SessionLocal() as db:
        db.query(OAuthAuthRequest).filter(
            OAuthAuthRequest.user_id.is_(None)
        ).delete(synchronize_session=False)
        db.query(OAuthPendingTicket).filter(
            OAuthPendingTicket.user_id.is_(None)
        ).delete(synchronize_session=False)
        db.commit()


# ── helpers ──────────────────────────────────────────────────────────────────

def _sha256_hex() -> str:
    return hashlib.sha256(secrets.token_bytes(32)).hexdigest()


def _subject() -> str:
    return f"integ_{uuid.uuid4().hex[:12]}"


def _future(minutes: int = 10) -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=minutes)


def _insert(obj):
    with SessionLocal() as db:
        db.add(obj)
        db.commit()


def _violation(obj) -> str:
    with pytest.raises(IntegrityError) as ei:
        _insert(obj)
    return ei.value.orig.diag.constraint_name


def _user_id(email: str) -> int:
    return int(create_test_user(email)["id"])


def _identity(user_id: int, provider="vk", subject=None) -> UserOAuthIdentity:
    return UserOAuthIdentity(
        user_id=user_id, provider=provider,
        provider_subject=_subject() if subject is None else subject,
    )


def _request(**kw) -> OAuthAuthRequest:
    data = dict(
        state_hash=_sha256_hex(), provider="yandex", intent="login",
        code_verifier_enc=encrypt_text(secrets.token_urlsafe(48)),
        user_id=None, expires_at=_future(),
    )
    data.update(kw)
    return OAuthAuthRequest(**data)


def _ticket(**kw) -> OAuthPendingTicket:
    data = dict(
        ticket_hash=_sha256_hex(), kind="registration", provider="vk",
        provider_subject=_subject(), email=None, suggested_name=None,
        user_id=None, expires_at=_future(),
    )
    data.update(kw)
    return OAuthPendingTicket(**data)


# ── F. user_oauth_identities ─────────────────────────────────────────────────

def test_identity_insert_and_defaults(client, test_email):
    user_id = _user_id(test_email)
    _insert(_identity(user_id, "yandex"))
    with SessionLocal() as db:
        row = db.query(UserOAuthIdentity).filter_by(user_id=user_id).one()
        assert row.uuid is not None
        assert row.created_at is not None
        assert row.last_login_at is None


def test_identity_provider_allowlist(client, test_email):
    user_id = _user_id(test_email)
    assert _violation(_identity(user_id, "telegram")) == "ck_user_oauth_identities_provider"


def test_identity_subject_must_be_non_empty(client, test_email):
    user_id = _user_id(test_email)
    assert _violation(_identity(user_id, subject="")) == (
        "ck_user_oauth_identities_subject_nonempty"
    )


def test_identity_provider_subject_is_unique_across_users(client, test_email, foreign_test_email):
    subject = _subject()
    _insert(_identity(_user_id(test_email), "vk", subject))
    assert _violation(_identity(_user_id(foreign_test_email), "vk", subject)) == (
        "ux_user_oauth_identities_provider_subject"
    )


def test_same_subject_allowed_for_different_providers(client, test_email, foreign_test_email):
    subject = _subject()
    _insert(_identity(_user_id(test_email), "vk", subject))
    _insert(_identity(_user_id(foreign_test_email), "yandex", subject))


def test_one_identity_per_provider_per_user(client, test_email):
    user_id = _user_id(test_email)
    _insert(_identity(user_id, "vk"))
    assert _violation(_identity(user_id, "vk")) == "ux_user_oauth_identities_user_provider"
    _insert(_identity(user_id, "yandex"))  # другой провайдер — можно


def test_identity_requires_existing_user(client):
    assert _violation(_identity(2_000_000_000)) == "user_oauth_identities_user_id_fkey"


def test_identity_is_deleted_with_user(client, test_email):
    user_id = _user_id(test_email)
    _insert(_identity(user_id, "vk"))
    with SessionLocal() as db:
        db.query(User).filter(User.id == user_id).delete()
        db.commit()
        assert db.query(UserOAuthIdentity).filter_by(user_id=user_id).count() == 0


def test_identity_can_belong_to_passwordless_user(client, test_email):
    with SessionLocal() as db:
        user = User(full_name="Integ Social Only", email=test_email, password_hash=None)
        db.add(user)
        db.commit()
        user_id = user.id
    _insert(_identity(user_id, "yandex"))


# ── G1. oauth_auth_requests ──────────────────────────────────────────────────

def test_login_request_valid_and_consumable(client):
    req = _request()
    state_hash = req.state_hash
    _insert(req)
    with SessionLocal() as db:
        row = db.get(OAuthAuthRequest, state_hash)
        assert row.consumed_at is None and row.created_at is not None
        row.consumed_at = datetime.now(timezone.utc)
        db.commit()
        assert db.get(OAuthAuthRequest, state_hash).consumed_at is not None


def test_link_request_requires_user(client, test_email):
    assert _violation(_request(intent="link")) == "ck_oauth_auth_requests_intent_user"
    _insert(_request(intent="link", user_id=_user_id(test_email)))


def test_login_request_must_not_have_user(client, test_email):
    assert _violation(_request(user_id=_user_id(test_email))) == (
        "ck_oauth_auth_requests_intent_user"
    )


@pytest.mark.parametrize("field,value,constraint", [
    ("provider", "google", "ck_oauth_auth_requests_provider"),
    ("intent", "register", "ck_oauth_auth_requests_intent"),
    ("state_hash", "raw-state-value", "ck_oauth_auth_requests_state_hash_format"),
    ("state_hash", "A" * 64, "ck_oauth_auth_requests_state_hash_format"),
    ("code_verifier_enc", "plaintext-verifier", "ck_oauth_auth_requests_verifier_encrypted"),
])
def test_request_check_constraints(client, field, value, constraint):
    assert _violation(_request(**{field: value})) == constraint


def test_request_expiry_must_be_after_creation(client):
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    assert _violation(_request(expires_at=past)) == "ck_oauth_auth_requests_expiry"


def test_request_state_hash_is_primary_key(client):
    state_hash = _sha256_hex()
    _insert(_request(state_hash=state_hash))
    assert _violation(_request(state_hash=state_hash)) == "oauth_auth_requests_pkey"


# ── G2. oauth_pending_tickets ────────────────────────────────────────────────

def test_registration_ticket_valid(client):
    _insert(_ticket(email="integ_someone@donnu.ru", suggested_name="Integ Name"))


def test_registration_ticket_must_not_have_user(client, test_email):
    assert _violation(_ticket(user_id=_user_id(test_email))) == (
        "ck_oauth_pending_tickets_registration_no_user"
    )


def test_login_ticket_requires_user(client, test_email):
    assert _violation(_ticket(kind="login")) == "ck_oauth_pending_tickets_login_user"
    _insert(_ticket(kind="login", user_id=_user_id(test_email)))


def test_link_required_ticket_allowed_with_or_without_user(client, test_email):
    _insert(_ticket(kind="link_required"))
    _insert(_ticket(kind="link_required", user_id=_user_id(test_email)))


@pytest.mark.parametrize("field,value,constraint", [
    ("provider", "telegram", "ck_oauth_pending_tickets_provider"),
    ("kind", "link", "ck_oauth_pending_tickets_kind"),
    ("ticket_hash", "raw-ticket", "ck_oauth_pending_tickets_ticket_hash_format"),
    ("provider_subject", "", "ck_oauth_pending_tickets_subject_nonempty"),
    ("email", "Integ_Mixed@DonNU.ru", "ck_oauth_pending_tickets_email_normalized"),
    ("email", " integ_space@donnu.ru", "ck_oauth_pending_tickets_email_normalized"),
])
def test_ticket_check_constraints(client, field, value, constraint):
    assert _violation(_ticket(**{field: value})) == constraint


def test_ticket_expiry_and_one_time_consumption(client):
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    assert _violation(_ticket(expires_at=past)) == "ck_oauth_pending_tickets_expiry"

    ticket = _ticket()
    ticket_hash = ticket.ticket_hash
    _insert(ticket)
    with SessionLocal() as db:
        row = db.get(OAuthPendingTicket, ticket_hash)
        assert row.consumed_at is None
        row.consumed_at = datetime.now(timezone.utc)
        db.commit()
