"""
Stage 5A-2 — no-DB unit-тесты: typed precommit → AuthError.audit_code (service),
duplicate-email контракт (storage), фазовые границы failure-writer (routes_admin).
Реальная БД не используется.
"""
import uuid as _uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

import app.users.service as users_service
import app.users.storage as users_storage
import app.users.routes_admin as routes_admin
from app.audit import Outcome
from app.auth.service import AuthError
from app.users.errors import (
    ActorContextError, EmailAlreadyExistsError, InvalidUserRequestError,
    RoleConfigError, UserNotFoundError,
)
from app.users.storage import RoleChangeError
from app.users.schemas import AdminUserCreate, AdminUserUpdate

ACTOR_ID = 101


def _mock_session(mock_db):
    m = MagicMock()
    m.return_value.__enter__ = MagicMock(return_value=mock_db)
    m.return_value.__exit__ = MagicMock(return_value=False)
    return m


def _create_data():
    return AdminUserCreate(
        email="new@donnu.ru", full_name="Тест Тестов", role="psychologist",
        basis_type="service_duty", basis_reference="Приказ № 1",
        legal_basis_confirmed=True,
    )


# ══════════════════════════════════════════════════════════════════════════
# 1. Service typed precommit → AuthError.audit_code (по ТИПУ, не по тексту)
# ══════════════════════════════════════════════════════════════════════════

def _assert_auth(exc_info, status, code):
    e = exc_info.value
    assert isinstance(e, AuthError)
    assert e.status_code == status
    assert e.audit_code == code


@pytest.mark.parametrize("raised, status, code", [
    (EmailAlreadyExistsError("dup"), 409, "email_already_exists"),
    (RoleConfigError("cfg"), 500, "internal_error"),
    (ActorContextError("ctx"), 500, "internal_error"),
])
def test_create_service_maps_typed_to_audit_code(monkeypatch, raised, status, code):
    monkeypatch.setattr(users_service.storage, "create_user",
                        lambda **kw: (_ for _ in ()).throw(raised))
    with pytest.raises(AuthError) as ei:
        users_service.create_user(
            _create_data(), actor_id=ACTOR_ID, actor_role="admin",
        )
    _assert_auth(ei, status, code)


def test_create_service_domain_not_allowed(monkeypatch):
    from app.email_domains.errors import EmailDomainNotAllowedError
    monkeypatch.setattr(
        users_service.storage, "create_user",
        lambda **kw: (_ for _ in ()).throw(EmailDomainNotAllowedError("no")),
    )
    with pytest.raises(AuthError) as ei:
        users_service.create_user(
            _create_data(), actor_id=ACTOR_ID, actor_role="admin",
        )
    _assert_auth(ei, 422, "domain_not_allowed")


def test_create_service_general_runtime_not_converted(monkeypatch):
    # commit/postcommit/unknown (plain RuntimeError) НЕ ловится → propagates.
    monkeypatch.setattr(users_service.storage, "create_user",
                        lambda **kw: (_ for _ in ()).throw(RuntimeError("commit")))
    with pytest.raises(RuntimeError):
        users_service.create_user(
            _create_data(), actor_id=ACTOR_ID, actor_role="admin",
        )


@pytest.mark.parametrize("raised, status, code", [
    (UserNotFoundError("nf"), 404, "user_not_found"),
    (InvalidUserRequestError("bad"), 400, "invalid_request"),
    (RoleChangeError("policy", 409, "role_policy_violation"), 409,
     "role_policy_violation"),
    (RoleChangeError("self", 422, "self_admin_protected"), 422,
     "self_admin_protected"),
    (RoleChangeError("lb", 400, "legal_basis_required"), 400,
     "legal_basis_required"),
    (RoleConfigError("cfg"), 500, "internal_error"),
    (ActorContextError("ctx"), 500, "internal_error"),
])
def test_update_service_maps_typed_to_audit_code(monkeypatch, raised, status, code):
    monkeypatch.setattr(users_service.storage, "update_user",
                        lambda **kw: (_ for _ in ()).throw(raised))
    with pytest.raises(AuthError) as ei:
        users_service.update_user(
            "uuid", AdminUserUpdate(full_name="New Name"),
            actor_id=ACTOR_ID, actor_role="admin",
        )
    _assert_auth(ei, status, code)


def test_update_service_empty_patch_invalid_request():
    with pytest.raises(AuthError) as ei:
        users_service.update_user(
            "uuid", AdminUserUpdate(), actor_id=ACTOR_ID, actor_role="admin",
        )
    _assert_auth(ei, 400, "invalid_request")


def test_update_service_general_runtime_not_converted(monkeypatch):
    monkeypatch.setattr(users_service.storage, "update_user",
                        lambda **kw: (_ for _ in ()).throw(RuntimeError("commit")))
    with pytest.raises(RuntimeError):
        users_service.update_user(
            "uuid", AdminUserUpdate(full_name="New Name"),
            actor_id=ACTOR_ID, actor_role="admin",
        )


def test_delete_service_not_found_and_actor_context(monkeypatch):
    monkeypatch.setattr(users_service.storage, "soft_delete_user",
                        lambda *a, **kw: False)
    with pytest.raises(AuthError) as ei:
        users_service.delete_user("uuid", actor_id=ACTOR_ID, actor_role="admin")
    _assert_auth(ei, 404, "user_not_found")

    monkeypatch.setattr(
        users_service.storage, "soft_delete_user",
        lambda *a, **kw: (_ for _ in ()).throw(ActorContextError("ctx")),
    )
    with pytest.raises(AuthError) as ei2:
        users_service.delete_user("uuid", actor_id=ACTOR_ID, actor_role="admin")
    _assert_auth(ei2, 500, "internal_error")


# ══════════════════════════════════════════════════════════════════════════
# 2. Duplicate email контракт (storage.create_user)
# ══════════════════════════════════════════════════════════════════════════

def _mk_orig(constraint_name):
    orig = MagicMock()
    orig.diag.constraint_name = constraint_name
    return orig


def _create_storage_db(existing, flush_exc=None):
    db = MagicMock(name="db")
    db.query.return_value.filter.return_value.first.return_value = existing
    # create_user подтягивает staff-роль + неявную student тем же .all()-запросом.
    role_obj = SimpleNamespace(id=99, name="psychologist")
    student_obj = SimpleNamespace(id=4, name="student")
    db.query.return_value.filter.return_value.all.return_value = [role_obj, student_obj]
    if flush_exc is not None:
        db.flush.side_effect = flush_exc
    return db


def _call_create(monkeypatch, db):
    monkeypatch.setattr(
        "app.email_domains.storage.assert_email_domain_allowed_in_tx",
        lambda db, email: None,
    )
    monkeypatch.setattr(users_storage, "SessionLocal", _mock_session(db))
    monkeypatch.setattr(users_storage, "record_event", lambda **kw: None)
    with patch.object(users_storage, "User",
                      return_value=MagicMock(id=1)):
        users_storage.create_user(
            "new@donnu.ru", "Тест", "hash", ["psychologist"],
            basis_reference="Приказ № 1",
            confirmed_by_user_id=ACTOR_ID, actor_role="admin",
        )


def test_authoritative_softdeleted_duplicate_raises(monkeypatch):
    soft = SimpleNamespace(id=7)
    db = _create_storage_db(existing=soft)   # найден (в т.ч. soft-deleted)
    with pytest.raises(EmailAlreadyExistsError):
        _call_create(monkeypatch, db)
    db.flush.assert_not_called()   # до мутации


def test_flush_allowlisted_constraint_becomes_email_exists(monkeypatch):
    err = IntegrityError("stmt", {}, _mk_orig("ux_users_email_normalized"))
    db = _create_storage_db(existing=None, flush_exc=err)
    with pytest.raises(EmailAlreadyExistsError):
        _call_create(monkeypatch, db)
    db.rollback.assert_called_once()


def test_flush_unknown_constraint_reraised_not_email_exists(monkeypatch):
    err = IntegrityError("stmt", {}, _mk_orig("some_other_fk"))
    db = _create_storage_db(existing=None, flush_exc=err)
    with pytest.raises(IntegrityError):
        _call_create(monkeypatch, db)


def test_flush_no_constraint_name_reraised(monkeypatch):
    err = IntegrityError("stmt", {}, _mk_orig(None))
    db = _create_storage_db(existing=None, flush_exc=err)
    with pytest.raises(IntegrityError):
        _call_create(monkeypatch, db)


# ══════════════════════════════════════════════════════════════════════════
# 3. Route phase-boundary: failure-writer ТОЛЬКО для AuthError (precommit)
# ══════════════════════════════════════════════════════════════════════════

def _req():
    r = MagicMock()
    r.client.host = "203.0.113.7"
    r.headers.get.return_value = "pytest-ua"
    return r


def _admin_cu():
    return {"id": "5", "roles": ["admin"], "role": "admin"}


def _spy_secondary(monkeypatch):
    calls = []
    monkeypatch.setattr(routes_admin, "record_secondary_failure",
                        lambda **kw: calls.append(kw))
    return calls


def test_create_route_auth_error_writes_one_failure(monkeypatch):
    calls = _spy_secondary(monkeypatch)
    monkeypatch.setattr(
        routes_admin.service, "create_user",
        lambda *a, **kw: (_ for _ in ()).throw(
            AuthError("x", 409, audit_code="email_already_exists")),
    )
    with pytest.raises(HTTPException) as ei:
        routes_admin.create_user(
            request=_req(), body=MagicMock(), current_user=_admin_cu(),
        )
    assert ei.value.status_code == 409
    assert len(calls) == 1
    assert calls[0]["event"] == "admin_user_create_failed"
    assert calls[0]["failure_reason_code"] == "email_already_exists"
    assert calls[0]["actor"].user_id == 5 and calls[0]["actor"].role == "admin"


@pytest.mark.parametrize("exc", [
    RuntimeError("commit ambiguous"),
    ValueError("postcommit dto"),
    IntegrityError("s", {}, MagicMock()),
])
def test_create_route_non_autherror_no_failure_writer(monkeypatch, exc):
    # commit-time / postcommit / unknown → НЕ AuthError → secondary НЕ вызывается,
    # исключение всплывает как есть (definitive *_failed не пишется).
    calls = _spy_secondary(monkeypatch)
    monkeypatch.setattr(routes_admin.service, "create_user",
                        lambda *a, **kw: (_ for _ in ()).throw(exc))
    with pytest.raises(type(exc)):
        routes_admin.create_user(
            request=_req(), body=MagicMock(), current_user=_admin_cu(),
        )
    assert calls == []


def test_update_route_auth_error_writes_update_failed(monkeypatch):
    calls = _spy_secondary(monkeypatch)
    monkeypatch.setattr(
        routes_admin.service, "update_user",
        lambda *a, **kw: (_ for _ in ()).throw(
            AuthError("nf", 404, audit_code="user_not_found")),
    )
    with pytest.raises(HTTPException) as ei:
        routes_admin.update_user(
            request=_req(), uuid="u", body=MagicMock(), current_user=_admin_cu(),
        )
    assert ei.value.status_code == 404
    assert len(calls) == 1
    assert calls[0]["event"] == "admin_user_update_failed"
    assert calls[0]["failure_reason_code"] == "user_not_found"


def test_delete_route_auth_error_writes_delete_failed(monkeypatch):
    calls = _spy_secondary(monkeypatch)
    monkeypatch.setattr(
        routes_admin.service, "delete_user",
        lambda *a, **kw: (_ for _ in ()).throw(
            AuthError("nf", 404, audit_code="user_not_found")),
    )
    with pytest.raises(HTTPException) as ei:
        routes_admin.delete_user(
            request=_req(), uuid="u", current_user=_admin_cu(),
        )
    assert ei.value.status_code == 404
    assert len(calls) == 1
    assert calls[0]["event"] == "admin_user_delete_failed"


def test_update_route_non_autherror_no_failure_writer(monkeypatch):
    calls = _spy_secondary(monkeypatch)
    monkeypatch.setattr(routes_admin.service, "update_user",
                        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("x")))
    with pytest.raises(RuntimeError):
        routes_admin.update_user(
            request=_req(), uuid="u", body=MagicMock(), current_user=_admin_cu(),
        )
    assert calls == []


# ══════════════════════════════════════════════════════════════════════════
# 4. ACTUAL commit/postcommit injection (реальный storage, замоканный db):
#    route → service → storage; sentinel в db.commit()/db.refresh()/
#    get_active_role_names(); проверяем фазовые границы и что *_failed НЕ пишется.
# ══════════════════════════════════════════════════════════════════════════

class _Sentinel(Exception):
    """Уникальный не-typed exception — не AuthError и не доменная ошибка."""


# Сообщение sentinel содержит «ПДн-подобные» токены — они НЕ должны попасть в
# commit-диагностику (печатается только класс).
_SENTINEL_PII = "leak@secret.example 550e8400-e29b-41d4 admin psychologist"


def _spies(monkeypatch, storage_mod):
    rec = []
    monkeypatch.setattr(storage_mod, "record_event",
                        lambda **kw: rec.append(kw))
    sec = []
    monkeypatch.setattr(routes_admin, "record_secondary_failure",
                        lambda **kw: sec.append(kw))
    return rec, sec


# ── create ──────────────────────────────────────────────────────────────────

def _setup_create(monkeypatch, *, commit_exc=None, refresh_exc=None,
                  duplicate=False):
    db = MagicMock(name="db")
    db.query.return_value.filter.return_value.first.return_value = (
        SimpleNamespace(id=9) if duplicate else None
    )
    role_obj = SimpleNamespace(id=99, name="psychologist")
    student_obj = SimpleNamespace(id=4, name="student")
    db.query.return_value.filter.return_value.all.return_value = [role_obj, student_obj]
    if commit_exc is not None:
        db.commit.side_effect = commit_exc
    if refresh_exc is not None:
        db.refresh.side_effect = refresh_exc
    monkeypatch.setattr(
        "app.email_domains.storage.assert_email_domain_allowed_in_tx",
        lambda db, email: None,
    )
    monkeypatch.setattr(users_storage, "SessionLocal", _mock_session(db))
    new_user = MagicMock(id=1, email="new@donnu.ru", full_name="Тест",
                         is_active=True, created_at=None)
    monkeypatch.setattr(users_storage, "User", MagicMock(return_value=new_user))
    rec, sec = _spies(monkeypatch, users_storage)
    return db, rec, sec


def _run_create():
    routes_admin.create_user(
        request=_req(), body=_create_data(), current_user=_admin_cu(),
    )


def test_create_commit_failure_propagates_no_secondary(monkeypatch, capsys):
    db, rec, sec = _setup_create(monkeypatch, commit_exc=_Sentinel(_SENTINEL_PII))
    with pytest.raises(_Sentinel):
        _run_create()
    db.refresh.assert_not_called()          # postcommit не выполняется
    assert len(rec) == 1                     # success staged ровно один раз
    assert rec[0]["event"] == "admin_user_created"
    assert rec[0]["outcome"] is Outcome.SUCCESS
    assert sec == []                         # *_failed НЕ пишется
    err = capsys.readouterr().err
    assert "event=admin_user_create phase=commit error=_Sentinel" in err
    for leak in ("leak@secret.example", "550e8400", "psychologist",
                 "new@donnu.ru", _SENTINEL_PII):
        assert leak not in err


def test_create_postcommit_refresh_failure_no_secondary(monkeypatch):
    db, rec, sec = _setup_create(monkeypatch, refresh_exc=_Sentinel("boom"))
    with pytest.raises(_Sentinel):
        _run_create()
    db.commit.assert_called_once()           # commit УСПЕШЕН
    assert len(rec) == 1 and rec[0]["event"] == "admin_user_created"
    assert sec == []                         # success сохранён; *_failed нет


def test_create_precommit_typed_writes_secondary_no_success(monkeypatch):
    # Контроль single-call инварианта: precommit typed (duplicate) → secondary
    # once; success record_event НЕ staged.
    _db, rec, sec = _setup_create(monkeypatch, duplicate=True)
    with pytest.raises(HTTPException) as ei:
        _run_create()
    assert ei.value.status_code == 409
    assert rec == []                         # success НЕ staged
    assert len(sec) == 1
    assert sec[0]["event"] == "admin_user_create_failed"
    assert sec[0]["failure_reason_code"] == "email_already_exists"


# ── update ──────────────────────────────────────────────────────────────────

def _setup_update(monkeypatch, *, commit_exc=None, post_role_exc=None):
    db = MagicMock(name="db")
    user = SimpleNamespace(id=5, full_name="Old", phone=None, is_active=True)
    db.query.return_value.filter.return_value.filter.return_value.first \
        .return_value = user
    if commit_exc is not None:
        db.commit.side_effect = commit_exc
    post = post_role_exc if post_role_exc is not None else ["psychologist"]
    monkeypatch.setattr(
        users_storage, "get_active_role_names",
        MagicMock(side_effect=[["psychologist"], post]),
    )
    monkeypatch.setattr(users_storage, "SessionLocal", _mock_session(db))
    rec, sec = _spies(monkeypatch, users_storage)
    return db, user, rec, sec


def _run_update():
    routes_admin.update_user(
        request=_req(), uuid=str(_uuid.uuid4()),
        body=AdminUserUpdate(full_name="New Name"), current_user=_admin_cu(),
    )


def test_update_commit_failure_propagates_no_secondary(monkeypatch, capsys):
    db, _user, rec, sec = _setup_update(monkeypatch,
                                        commit_exc=_Sentinel(_SENTINEL_PII))
    with pytest.raises(_Sentinel):
        _run_update()
    db.refresh.assert_not_called()
    assert len(rec) == 1 and rec[0]["event"] == "admin_user_updated"
    assert rec[0]["outcome"] is Outcome.SUCCESS
    assert sec == []
    err = capsys.readouterr().err
    assert "event=admin_user_update phase=commit error=_Sentinel" in err
    for leak in ("leak@secret.example", "550e8400", "psychologist",
                 _SENTINEL_PII):
        assert leak not in err


def test_update_postcommit_query_failure_no_secondary(monkeypatch):
    # commit ок; postcommit get_active_role_names (roles_out) бросает sentinel.
    db, _user, rec, sec = _setup_update(monkeypatch,
                                        post_role_exc=_Sentinel("boom"))
    with pytest.raises(_Sentinel):
        _run_update()
    db.commit.assert_called_once()
    assert len(rec) == 1 and rec[0]["event"] == "admin_user_updated"
    assert sec == []


# ── delete (postcommit-шагов нет — только commit) ────────────────────────────

def _setup_delete(monkeypatch, *, commit_exc):
    db = MagicMock(name="db")
    user = SimpleNamespace(id=5, deleted_at=None, is_active=True)
    db.query.return_value.filter.return_value.filter.return_value.first \
        .return_value = user
    db.commit.side_effect = commit_exc
    monkeypatch.setattr(users_storage, "SessionLocal", _mock_session(db))
    rec, sec = _spies(monkeypatch, users_storage)
    return db, rec, sec


def test_delete_commit_failure_propagates_no_secondary(monkeypatch, capsys):
    db, rec, sec = _setup_delete(monkeypatch, commit_exc=_Sentinel(_SENTINEL_PII))
    with pytest.raises(_Sentinel):
        routes_admin.delete_user(
            request=_req(), uuid=str(_uuid.uuid4()), current_user=_admin_cu(),
        )
    assert len(rec) == 1 and rec[0]["event"] == "admin_user_deleted"
    assert rec[0]["outcome"] is Outcome.SUCCESS
    assert sec == []
    err = capsys.readouterr().err
    assert "event=admin_user_delete phase=commit error=_Sentinel" in err
    for leak in ("leak@secret.example", "550e8400", _SENTINEL_PII):
        assert leak not in err
