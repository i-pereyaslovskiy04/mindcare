"""
Stage 4B-2 — no-DB unit-тесты общего safe request-context helper.

Проверяют, что build_request_context санитизирует недоверенные ip/user_agent так,
что строгая facade-валидация (validate_context) их принимает, и что валидные
значения проходят как есть. Реальная БД не используется.
"""
import pytest

from app.audit import validation as audit_validation
from app.audit.request_context import build_request_context

_BAD_UA_LONG = "x" * 600                 # > 512 → facade отверг бы
_BAD_UA_CTRL = "Mozilla\x00\x1f evil"    # control chars → facade отверг бы


@pytest.mark.parametrize("bad_ua", [_BAD_UA_LONG, _BAD_UA_CTRL])
def test_bad_user_agent_dropped_to_none(bad_ua):
    ctx = build_request_context(ip="192.0.2.10", user_agent=bad_ua)
    assert ctx.user_agent is None
    audit_validation.validate_context(ctx)          # facade НЕ бросает


@pytest.mark.parametrize("bad_ip", ["testclient", "not-an-ip", "999.999.999.999", ""])
def test_bad_ip_dropped_to_none(bad_ip):
    ctx = build_request_context(ip=bad_ip, user_agent="pytest-agent")
    assert ctx.ip_address is None
    audit_validation.validate_context(ctx)


def test_valid_values_pass_through():
    ctx = build_request_context(
        ip="203.0.113.7", user_agent="Mozilla/5.0 (pytest)",
    )
    assert ctx.ip_address == "203.0.113.7"
    assert ctx.user_agent == "Mozilla/5.0 (pytest)"
    audit_validation.validate_context(ctx)


def test_ipv6_valid_passes():
    ctx = build_request_context(ip="2001:db8::1", user_agent=None)
    assert ctx.ip_address == "2001:db8::1"
    audit_validation.validate_context(ctx)


def test_none_inputs_yield_empty_context():
    ctx = build_request_context()
    assert ctx.ip_address is None
    assert ctx.user_agent is None
    assert ctx.session_id_hash is None
    audit_validation.validate_context(ctx)


def test_non_str_inputs_dropped():
    ctx = build_request_context(ip=12345, user_agent=object())
    assert ctx.ip_address is None
    assert ctx.user_agent is None
    audit_validation.validate_context(ctx)


def test_session_id_hash_passed_through():
    h = "a" * 64                                     # 64 hex → валиден для facade
    ctx = build_request_context(ip=None, user_agent=None, session_id_hash=h)
    assert ctx.session_id_hash == h
    audit_validation.validate_context(ctx)


def test_raw_bad_user_agent_would_fail_facade():
    # Контроль: без helper'а тот же UA действительно отвергается facade.
    from app.audit.contracts import RequestContext
    with pytest.raises(audit_validation.AuditError):
        audit_validation.validate_context(RequestContext(user_agent=_BAD_UA_LONG))
