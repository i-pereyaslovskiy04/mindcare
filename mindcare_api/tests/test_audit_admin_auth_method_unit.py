"""
Stage Social Auth 3A — проекция auth_log.auth_method в admin viewer (без БД).

Наружу — только значение из allowlist (password/yandex/vk) и только у события,
политика которого способ допускает (login/failed_login). Иначе None +
details_redacted, как у непрошедшего allowlist failure-кода.
"""
from __future__ import annotations

import pytest

from app.audit import admin_policy as pol
from app.audit import admin_service as svc
from app.audit.admin_schemas import AuthEventOut
from app.audit.contracts import AuthMethod
from tests.audit_admin_rows import auth_row


@pytest.fixture
def rows(monkeypatch):
    holder = {"rows": []}
    monkeypatch.setattr(
        svc.storage, "list_auth_events",
        lambda **kw: (holder["rows"], len(holder["rows"])),
    )
    monkeypatch.setattr(svc, "record_event", lambda **kw: None)
    return holder


def _list(holder, *rows_):
    holder["rows"] = list(rows_)
    return svc.list_auth_events(
        actor_id=1, actor_role="admin", ip=None, user_agent=None,
        session_id_hash=None,
    ).items


def test_allowlist_is_derived_from_contract():
    assert pol.AUTH_METHOD_VALUES == frozenset(m.value for m in AuthMethod)


@pytest.mark.parametrize("method", ["password", "yandex", "vk"])
def test_login_method_projected(rows, method):
    item, = _list(rows, auth_row(event="login", auth_method=method))
    assert item.auth_method == method
    assert item.details_redacted is False


def test_failed_login_method_projected(rows):
    item, = _list(rows, auth_row(
        event="failed_login", actor_id=None, success=False,
        failure_reason="oauth_identity_unknown", auth_method="yandex",
    ))
    assert item.auth_method == "yandex" and item.failure_code == "oauth_identity_unknown"
    assert item.details_redacted is False


def test_null_method_is_not_redaction(rows):
    item, = _list(rows, auth_row(
        event="failed_login", actor_id=None, success=False,
        failure_reason="oauth_ticket_invalid", auth_method=None,
    ))
    assert item.auth_method is None and item.details_redacted is False


@pytest.mark.parametrize("raw", ["totp", "google", "PASSWORD", " yandex", ""])
def test_unknown_value_is_dropped_and_redacted(rows, raw):
    item, = _list(rows, auth_row(event="login", auth_method=raw))
    assert item.auth_method is None
    assert item.details_redacted is True


@pytest.mark.parametrize("event", ["logout", "password_change"])
def test_method_on_forbidden_event_is_dropped_and_redacted(rows, event):
    item, = _list(rows, auth_row(event=event, auth_method="password"))
    assert item.auth_method is None
    assert item.details_redacted is True


def test_legacy_unknown_event_drops_method(rows):
    item, = _list(rows, auth_row(event="register", auth_method="password"))
    assert item.known_event is False
    assert item.auth_method is None and item.details_redacted is True


def test_dto_field_is_closed_literal():
    with pytest.raises(Exception):
        AuthEventOut(
            entry_id="1", occurred_at=auth_row().occurred_at, event_code="login",
            known_event=True, actor={"kind": "anonymous"}, success=True,
            auth_method="google", details_redacted=False,
        )


# ── Stage Social Auth 3B: фильтр /auth-events?auth_method=… ──────────────────

class _FilterSpy:
    def __init__(self):
        self.storage_kwargs = None
        self.audit = []

    def storage(self, **kwargs):
        self.storage_kwargs = kwargs
        return [], 0

    def record_event(self, **kwargs):
        self.audit.append(kwargs)


@pytest.fixture
def filter_spy(monkeypatch):
    spy = _FilterSpy()
    monkeypatch.setattr(svc.storage, "list_auth_events", spy.storage)
    monkeypatch.setattr(svc, "record_event", spy.record_event)
    return spy


_ADMIN = dict(actor_id=1, actor_role="admin", ip=None, user_agent=None,
              session_id_hash=None)


@pytest.mark.parametrize("method", ["password", "yandex", "vk"])
def test_auth_method_filter_reaches_storage(filter_spy, method):
    svc.list_auth_events(**_ADMIN, auth_method=method)
    assert filter_spy.storage_kwargs["auth_method"] == method


def test_auth_method_filter_omitted_is_none(filter_spy):
    svc.list_auth_events(**_ADMIN)
    assert filter_spy.storage_kwargs["auth_method"] is None
    assert "auth_method" not in filter_spy.audit[-1]["metadata"]["filter_keys"]


@pytest.mark.parametrize("raw", ["google", "PASSWORD", " yandex", "", "telegram",
                                 "password' OR 1=1 --"])
def test_auth_method_filter_rejects_unknown_before_storage(filter_spy, raw):
    with pytest.raises(svc.AuditQueryError):
        svc.list_auth_events(**_ADMIN, auth_method=raw)
    assert filter_spy.storage_kwargs is None      # до обращения к журналу
    assert filter_spy.audit == []                 # и без access-события


def test_access_event_records_filter_name_not_value(filter_spy):
    svc.list_auth_events(**_ADMIN, auth_method="yandex")
    meta = filter_spy.audit[-1]["metadata"]
    assert "auth_method" in meta["filter_keys"]
    assert "yandex" not in repr(meta)


def test_filter_key_is_registered_for_access_event():
    from app.audit.registry import AUDIT_FILTER_KEYS
    assert "auth_method" in AUDIT_FILTER_KEYS


def test_options_expose_all_schema_methods_in_enum_order():
    assert svc.build_options().auth_methods == [m.value for m in AuthMethod]
    assert svc.build_options().auth_methods == ["password", "yandex", "vk"]
