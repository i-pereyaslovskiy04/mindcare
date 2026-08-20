"""
Stage 6-0 — контракт RequestContext в record_data_change.

Применяется СУЩЕСТВУЮЩАЯ строгая validation.validate_context (та же, что у
record_event). Невалидный context обязан давать DataChangeError ДО db.add:
частичной записи журнала не бывает.

Из контекста в строку попадает ТОЛЬКО ip_address — в data_change_log нет колонок
user_agent / session_id / request_url / request_method.
"""
import pytest

from app.audit.contracts import Actor, AuditError, RequestContext
from app.audit.change_contracts import DataChangeError, Operation
from app.audit.data_change import record_data_change
from app.audit.request_context import build_request_context


class _FakeSession:
    def __init__(self):
        self.added = []

    def add(self, row):
        self.added.append(row)


_ADMIN = Actor.user(7, "admin")
_HASH = "a" * 64


def _call(context, db=None):
    return record_data_change(
        table="users", record_id=1, operation=Operation.UPDATE, actor=_ADMIN,
        changed_fields=["full_name"], context=context,
        db=db if db is not None else _FakeSession(),
    )


def test_context_is_optional():
    db = _FakeSession()
    _call(None, db=db)
    assert db.added[0].ip_address is None


def test_context_must_be_request_context_instance():
    for bad in ({"ip_address": "1.2.3.4"}, "1.2.3.4", 42):
        db = _FakeSession()
        with pytest.raises(DataChangeError, match="RequestContext or None"):
            _call(bad, db=db)
        assert db.added == []


def test_valid_context_writes_only_ip_address():
    ctx = RequestContext(
        ip_address="10.0.0.7",
        user_agent="Mozilla/5.0",
        session_id_hash=_HASH,
        request_path="/api/admin/users/1",
        request_method="PATCH",
    )
    db = _FakeSession()
    _call(ctx, db=db)
    row = db.added[0]
    assert row.ip_address == "10.0.0.7"
    # В data_change_log попросту нет этих колонок — остальной контекст живёт
    # на парной строке audit_log.
    for absent in ("user_agent", "session_id", "request_url", "request_method"):
        assert not hasattr(row, absent) or getattr(row, absent) is None


def test_ipv6_is_accepted():
    db = _FakeSession()
    _call(RequestContext(ip_address="2001:db8::1"), db=db)
    assert db.added[0].ip_address == "2001:db8::1"


# ── Строгая валидация переиспользуется целиком ───────────────────────────────

@pytest.mark.parametrize("ctx", [
    RequestContext(ip_address="not-an-ip"),
    RequestContext(ip_address="999.1.1.1"),
    RequestContext(user_agent="x" * 513),
    RequestContext(user_agent="bad\x00agent"),
    RequestContext(session_id_hash="short"),
    RequestContext(session_id_hash="z" * 64),
    RequestContext(request_path="no-leading-slash"),
    RequestContext(request_path="/api/x?token=1"),
    RequestContext(request_path="/api/x#frag"),
    RequestContext(request_method="TRACE"),
    RequestContext(request_method="patch"),
])
def test_invalid_context_is_rejected_before_db_add(ctx):
    db = _FakeSession()
    with pytest.raises(DataChangeError):
        _call(ctx, db=db)
    assert db.added == []


def test_data_change_error_is_an_audit_error():
    """Caller'ы, ловящие AuditError, продолжают работать без правок."""
    assert issubclass(DataChangeError, AuditError)


def test_build_request_context_helper_is_compatible():
    """Санитизирующий helper Stage 4B-2 даёт контекст, пригодный для DCL:
    мусорные ip/UA становятся None, а не роняют журнал."""
    ctx = build_request_context(ip="junk", user_agent="x" * 999)
    assert ctx.ip_address is None
    assert ctx.user_agent is None
    db = _FakeSession()
    _call(ctx, db=db)
    assert db.added[0].ip_address is None
