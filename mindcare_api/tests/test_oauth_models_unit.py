"""
Stage Social Auth 2A — контракт ORM-моделей OAuth-фундамента (без БД).

Фиксирует: таблицы зарегистрированы в metadata, именованные ограничения
объявлены, и ни одна модель не имеет колонки для секрета/сырого значения
(provider token, authorization code, raw state/ticket, plaintext verifier,
client secret, email/профиль провайдера в identity).
"""
from app.db.base import Base
from app.db.models import (
    OAuthAuthRequest, OAuthPendingTicket, OtpVerification, User, UserOAuthIdentity,
)

_FORBIDDEN_COLUMNS = {
    "access_token", "refresh_token", "id_token", "token", "code",
    "authorization_code", "state", "raw_state", "ticket", "raw_ticket",
    "code_verifier", "verifier", "client_secret", "secret",
    "profile", "raw_profile", "provider_profile", "provider_email", "password",
}


def _columns(model) -> set:
    return {c.name for c in model.__table__.columns}


def _constraint_names(model) -> set:
    return {c.name for c in model.__table__.constraints if c.name} | {
        i.name for i in model.__table__.indexes
    }


def test_tables_registered_in_metadata():
    for name in ("user_oauth_identities", "oauth_auth_requests", "oauth_pending_tickets"):
        assert name in Base.metadata.tables


def test_no_secret_or_raw_columns():
    for model in (UserOAuthIdentity, OAuthAuthRequest, OAuthPendingTicket):
        assert not (_columns(model) & _FORBIDDEN_COLUMNS), model.__tablename__


def test_identity_does_not_store_provider_email():
    assert "email" not in _columns(UserOAuthIdentity)


def test_identity_contract():
    assert _columns(UserOAuthIdentity) == {
        "id", "uuid", "user_id", "provider", "provider_subject",
        "created_at", "last_login_at",
    }
    assert {
        "ck_user_oauth_identities_provider",
        "ck_user_oauth_identities_subject_nonempty",
        "ux_user_oauth_identities_provider_subject",
        "ux_user_oauth_identities_user_provider",
        "ix_user_oauth_identities_user_id",
    } <= _constraint_names(UserOAuthIdentity)
    fk = next(iter(UserOAuthIdentity.__table__.c.user_id.foreign_keys))
    assert fk.ondelete == "CASCADE"
    assert UserOAuthIdentity.__table__.c.user_id.nullable is False
    assert UserOAuthIdentity.__table__.c.last_login_at.nullable is True


def test_auth_request_contract():
    assert _columns(OAuthAuthRequest) == {
        "state_hash", "provider", "intent", "code_verifier_enc", "user_id",
        "created_at", "expires_at", "consumed_at",
    }
    assert {
        "ck_oauth_auth_requests_provider", "ck_oauth_auth_requests_intent",
        "ck_oauth_auth_requests_state_hash_format",
        "ck_oauth_auth_requests_verifier_encrypted",
        "ck_oauth_auth_requests_intent_user", "ck_oauth_auth_requests_expiry",
    } <= _constraint_names(OAuthAuthRequest)
    table = OAuthAuthRequest.__table__
    assert [c.name for c in table.primary_key.columns] == ["state_hash"]
    assert table.c.user_id.nullable is True
    assert table.c.consumed_at.nullable is True


def test_pending_ticket_contract():
    assert _columns(OAuthPendingTicket) == {
        "ticket_hash", "kind", "provider", "provider_subject", "email",
        "suggested_name", "user_id", "created_at", "expires_at", "consumed_at",
    }
    assert {
        "ck_oauth_pending_tickets_provider", "ck_oauth_pending_tickets_kind",
        "ck_oauth_pending_tickets_ticket_hash_format",
        "ck_oauth_pending_tickets_subject_nonempty",
        "ck_oauth_pending_tickets_login_user",
        "ck_oauth_pending_tickets_registration_no_user",
        "ck_oauth_pending_tickets_email_normalized",
        "ck_oauth_pending_tickets_expiry",
    } <= _constraint_names(OAuthPendingTicket)
    assert [c.name for c in OAuthPendingTicket.__table__.primary_key.columns] == ["ticket_hash"]


def test_password_hash_columns_are_nullable():
    assert User.__table__.c.password_hash.nullable is True
    assert OtpVerification.__table__.c.password_hash.nullable is True
