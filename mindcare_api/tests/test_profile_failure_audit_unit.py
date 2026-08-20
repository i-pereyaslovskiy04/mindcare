"""
Stage 5A-2 — no-DB unit-тесты self-profile failure: service typed mapping и
route profile_update_failed writer. Реальная БД не используется.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

import app.auth.service as auth_service
import app.auth.routes as auth_routes
import app.auth.storage as auth_storage
from app.audit import Outcome
from app.auth.service import AuthError
from app.auth.errors import ProfileActorContextError
from app.auth.storage import UserNotFoundError
from app.auth.schemas import ProfileUpdate

UID = "9"


def _assert_auth(ei, status, code):
    assert ei.value.status_code == status
    assert ei.value.audit_code == code


def test_profile_service_full_name_too_short_invalid_request():
    with pytest.raises(AuthError) as ei:
        auth_service.update_profile(
            user_id=UID, fields={"full_name": "X"}, actor_role="student",
        )
    _assert_auth(ei, 422, "invalid_request")


def test_profile_service_user_not_found(monkeypatch):
    monkeypatch.setattr(
        auth_service.storage, "update_profile_atomic",
        lambda *a, **kw: (_ for _ in ()).throw(UserNotFoundError("nf")),
    )
    with pytest.raises(AuthError) as ei:
        auth_service.update_profile(
            user_id=UID, fields={"full_name": "Good Name"}, actor_role="student",
        )
    _assert_auth(ei, 404, "user_not_found")


def test_profile_service_actor_context_internal_error(monkeypatch):
    monkeypatch.setattr(
        auth_service.storage, "update_profile_atomic",
        lambda *a, **kw: (_ for _ in ()).throw(ProfileActorContextError("ctx")),
    )
    with pytest.raises(AuthError) as ei:
        auth_service.update_profile(
            user_id=UID, fields={"phone": "+70000000000"}, actor_role="student",
        )
    _assert_auth(ei, 500, "internal_error")


def test_profile_service_general_runtime_not_converted(monkeypatch):
    monkeypatch.setattr(
        auth_service.storage, "update_profile_atomic",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("commit")),
    )
    with pytest.raises(RuntimeError):
        auth_service.update_profile(
            user_id=UID, fields={"phone": "+70000000000"}, actor_role="student",
        )


# ── route ─────────────────────────────────────────────────────────────────────

def _req():
    r = MagicMock()
    r.client.host = "203.0.113.7"
    r.headers.get.return_value = "pytest-ua"
    return r


def test_profile_route_auth_error_writes_profile_update_failed(monkeypatch):
    calls = []
    monkeypatch.setattr(auth_routes, "record_secondary_failure",
                        lambda **kw: calls.append(kw))
    monkeypatch.setattr(
        auth_routes.service, "update_profile",
        lambda **kw: (_ for _ in ()).throw(
            AuthError("bad", 422, audit_code="invalid_request")),
    )
    cu = {"id": "9", "role": "student", "roles": ["student"]}
    with pytest.raises(HTTPException) as ei:
        auth_routes.update_profile(
            body=ProfileUpdate(full_name="Ok Name"), request=_req(),
            current_user=cu,
        )
    assert ei.value.status_code == 422
    assert len(calls) == 1
    assert calls[0]["event"] == "profile_update_failed"
    assert calls[0]["failure_reason_code"] == "invalid_request"
    assert calls[0]["actor"].user_id == 9 and calls[0]["actor"].role == "student"


def test_profile_route_non_autherror_no_failure_writer(monkeypatch):
    calls = []
    monkeypatch.setattr(auth_routes, "record_secondary_failure",
                        lambda **kw: calls.append(kw))
    monkeypatch.setattr(auth_routes.service, "update_profile",
                        lambda **kw: (_ for _ in ()).throw(RuntimeError("x")))
    cu = {"id": "9", "role": "student", "roles": ["student"]}
    with pytest.raises(RuntimeError):
        auth_routes.update_profile(
            body=ProfileUpdate(full_name="Ok Name"), request=_req(),
            current_user=cu,
        )
    assert calls == []


# ══════════════════════════════════════════════════════════════════════════
# ACTUAL commit/postcommit injection (реальный storage.update_profile_atomic):
#   route → service → storage; sentinel в db.commit()/db.refresh()/
#   _profile_to_dict(). Проверяем фазовые границы; profile_update_failed НЕ пишется.
# ══════════════════════════════════════════════════════════════════════════

class _Sentinel(Exception):
    pass


_SENTINEL_PII = "leak@secret.example 550e8400-e29b-41d4 student"

_STUDENT_CU = {"id": "9", "role": "student", "roles": ["student"]}


def _mock_session(db):
    m = MagicMock()
    m.return_value.__enter__ = MagicMock(return_value=db)
    m.return_value.__exit__ = MagicMock(return_value=False)
    return m


def _setup_profile(monkeypatch, *, commit_exc=None, refresh_exc=None,
                   dto_exc=None):
    db = MagicMock(name="db")
    user = SimpleNamespace(
        id=9, full_name="Old Name", phone=None,
        ui_theme_palette="classic", ui_theme_mode="light", updated_at=None,
    )
    db.query.return_value.filter.return_value.first.return_value = user
    if commit_exc is not None:
        db.commit.side_effect = commit_exc
    if refresh_exc is not None:
        db.refresh.side_effect = refresh_exc
    monkeypatch.setattr(auth_storage, "SessionLocal", _mock_session(db))
    rec = []
    monkeypatch.setattr(auth_storage, "record_event",
                        lambda **kw: rec.append(kw))
    if dto_exc is not None:
        monkeypatch.setattr(
            auth_storage, "_profile_to_dict",
            lambda u, d: (_ for _ in ()).throw(dto_exc),
        )
    else:
        monkeypatch.setattr(auth_storage, "_profile_to_dict",
                            lambda u, d: {"id": u.id})
    sec = []
    monkeypatch.setattr(auth_routes, "record_secondary_failure",
                        lambda **kw: sec.append(kw))
    return db, rec, sec


def _run_profile():
    auth_routes.update_profile(
        body=ProfileUpdate(full_name="New Name"), request=_req(),
        current_user=_STUDENT_CU,
    )


def test_profile_commit_failure_propagates_no_secondary(monkeypatch, capsys):
    db, rec, sec = _setup_profile(monkeypatch,
                                  commit_exc=_Sentinel(_SENTINEL_PII))
    with pytest.raises(_Sentinel):
        _run_profile()
    db.refresh.assert_not_called()               # postcommit не выполняется
    assert len(rec) == 1 and rec[0]["event"] == "profile_updated"
    assert rec[0]["outcome"] is Outcome.SUCCESS
    assert sec == []                              # profile_update_failed НЕ пишется
    err = capsys.readouterr().err
    assert "event=self_profile_update phase=commit error=_Sentinel" in err
    for leak in ("leak@secret.example", "550e8400", "student", _SENTINEL_PII):
        assert leak not in err


def test_profile_postcommit_refresh_failure_no_secondary(monkeypatch):
    db, rec, sec = _setup_profile(monkeypatch, refresh_exc=_Sentinel("boom"))
    with pytest.raises(_Sentinel):
        _run_profile()
    db.commit.assert_called_once()               # commit УСПЕШЕН
    assert len(rec) == 1 and rec[0]["event"] == "profile_updated"
    assert sec == []


def test_profile_postcommit_dto_failure_no_secondary(monkeypatch):
    db, rec, sec = _setup_profile(monkeypatch, dto_exc=_Sentinel("boom"))
    with pytest.raises(_Sentinel):
        _run_profile()
    db.commit.assert_called_once()
    db.refresh.assert_called_once()              # refresh прошёл, DTO упал
    assert len(rec) == 1 and rec[0]["event"] == "profile_updated"
    assert sec == []
