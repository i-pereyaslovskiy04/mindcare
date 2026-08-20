"""
Stage 5B-2 — no-DB unit-тесты durable best-effort failure audit для individual
appointments и walk-in cards. Проверяет: registry contract 5 failure-событий +
allowlists + count 70; AuditableAppointmentError fail-fast; raise-site → класс/код
(без строкового matching); route-level writer (isinstance-gated, ровно один вызов,
без target/db/user_email); secondary-writer failure не меняет HTTP; неаудируемые
отказы и не-AppointmentError не пишут *_failed. Реальная БД не используется.
"""
import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import app.appointments.service as appt_service
import app.appointments.routes_student as r_student
import app.appointments.routes_psychologist as r_psy
import app.appointments.routes_supervisor as r_sup
from app.appointments.service import (
    AppointmentError, AuditableAppointmentError,
    AUDIT_CODE_ACCOUNT_INACTIVE, AUDIT_CODE_ENGAGEMENT_REQUIRED,
    AUDIT_CODE_ACCESS_DENIED, AUDIT_CODE_CONSENT_REQUIRED,
)
from app.audit import Actor
from app.audit.contracts import AuditError, AuditStorageError
from app.audit.registry import REGISTRY
from fastapi import HTTPException


# ══════════════════════════════════════════════════════════════════════════
# 1. Registry contract — 5 failure-событий, allowlists, count
# ══════════════════════════════════════════════════════════════════════════

_FAIL_EVENTS = {
    "appointment_create_failed": (
        {"student", "supervisor", "admin"},
        {"account_inactive", "engagement_required"}),
    "appointment_cancel_failed": ({"student"}, {"access_denied"}),
    "appointment_confirm_failed": ({"psychologist"}, {"access_denied"}),
    "appointment_decline_failed": ({"psychologist"}, {"access_denied"}),
    "unregistered_student_card_create_failed": (
        {"supervisor", "admin"}, {"consent_required"}),
}


def test_registry_failure_events_contract_and_count():
    assert len(REGISTRY) == 93
    for name, (roles, codes) in _FAIL_EVENTS.items():
        s = REGISTRY[name]
        assert s.destination.value == "audit_log"
        assert s.allowed_actor_roles == frozenset(roles), name
        assert {o.value for o in s.allowed_outcomes} == {"failure"}, name
        assert s.allowed_failure_codes == frozenset(codes), name
        assert s.target_policy.value == "forbidden"
        assert s.entity_type is None
        assert dict(s.metadata_schema) == {}
        assert s.tx_mode.value == "independent"
        assert s.failure_policy.value == "soft"


def test_no_internal_error_code_in_failure_events():
    for name in _FAIL_EVENTS:
        assert "internal_error" not in REGISTRY[name].allowed_failure_codes


def test_update_archive_failure_events_absent():
    # Карточка update/archive не имеют auditable-пути → событий нет.
    assert "unregistered_student_card_update_failed" not in REGISTRY
    assert "unregistered_student_card_archive_failed" not in REGISTRY


# ══════════════════════════════════════════════════════════════════════════
# 2. AuditableAppointmentError fail-fast (no PII)
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("bad", [
    None,
    "",
    0,
    "   ",                 # только пробелы
    "Bad Code",             # пробел + uppercase
    "UPPER_CASE",           # uppercase
    "1_invalid",            # начинается не с буквы
    "bad-code",             # дефис не разрешён
    "a" + "b" * 100,        # длина 101 > max
    "access\ndenied",       # control char (LF)
    "access\rdenied",       # control char (CR)
], ids=[
    "none", "empty", "non_str_int", "whitespace_only", "space_and_upper",
    "upper_case", "leading_digit", "hyphen", "length_101", "cr_lf_newline",
    "cr_lf_carriage",
])
def test_auditable_error_rejects_invalid_code(bad):
    with pytest.raises(RuntimeError) as ei:
        AuditableAppointmentError("m", 403, audit_code=bad)
    # Сообщение об ошибке не содержит сам код (для str-значений).
    if isinstance(bad, str) and bad:
        assert bad not in str(ei.value)


@pytest.mark.parametrize("good", [
    "access_denied",
    "account_inactive",
    "a" + "b" * 99,   # ровно 100 символов, допустимый формат
])
def test_auditable_error_accepts_valid_code(good):
    e = AuditableAppointmentError("m", 403, audit_code=good)
    assert e.audit_code == good
    assert len(good) <= 100


def test_auditable_error_sets_code_and_is_appointment_error():
    e = AuditableAppointmentError("m", 403, audit_code="access_denied")
    assert e.audit_code == "access_denied"
    assert e.status_code == 403 and e.message == "m"
    assert isinstance(e, AppointmentError)   # ловится общим except


# ══════════════════════════════════════════════════════════════════════════
# 3. Raise-site → класс/код (без строкового matching)
# ══════════════════════════════════════════════════════════════════════════

def _mock_session(monkeypatch):
    db = MagicMock(name="db")
    sess = MagicMock(name="SessionLocal")
    sess.return_value.__enter__ = MagicMock(return_value=db)
    sess.return_value.__exit__ = MagicMock(return_value=False)
    monkeypatch.setattr(appt_service, "SessionLocal", sess)
    return db


def _future():
    from datetime import datetime, timezone, timedelta
    return datetime.now(timezone.utc) + timedelta(hours=5)


def test_book_account_inactive_is_auditable(monkeypatch):
    with pytest.raises(AuditableAppointmentError) as ei:
        appt_service.book_appointment(
            {"id": 50, "is_active": False}, _future(), "in_person", None, 1,
            actor_role="student",
        )
    assert ei.value.audit_code == AUDIT_CODE_ACCOUNT_INACTIVE


def test_book_engagement_required_is_auditable(monkeypatch):
    _mock_session(monkeypatch)
    monkeypatch.setattr(appt_service.storage, "get_active_engagement",
                        lambda **kw: None)
    with pytest.raises(AuditableAppointmentError) as ei:
        appt_service.book_appointment(
            {"id": 50, "is_active": True}, _future(), "in_person", None, 1,
            actor_role="student",
        )
    assert ei.value.audit_code == AUDIT_CODE_ENGAGEMENT_REQUIRED


def test_supervisor_book_engagement_required_is_auditable(monkeypatch):
    _mock_session(monkeypatch)
    monkeypatch.setattr(appt_service.storage, "is_psychologist",
                        lambda *a, **kw: True)
    monkeypatch.setattr(appt_service.storage, "get_user",
                        lambda *a, **kw: SimpleNamespace(is_active=True))
    monkeypatch.setattr(appt_service.storage, "get_active_engagement_with",
                        lambda *a, **kw: None)
    with pytest.raises(AuditableAppointmentError) as ei:
        appt_service.supervisor_book_appointment(
            psychologist_id=7, meeting_type_id=1, starts_at=_future(),
            modality="in_person", topic=None, student_id=50,
            current_user={"id": 9}, actor_role="supervisor",
        )
    assert ei.value.audit_code == AUDIT_CODE_ENGAGEMENT_REQUIRED


def test_student_cancel_access_denied_is_auditable(monkeypatch):
    _mock_session(monkeypatch)
    appt = SimpleNamespace(client_id=999, unregistered_student_card_id=None,
                           status="pending_confirmation")
    monkeypatch.setattr(appt_service.storage, "get_appointment_by_uuid",
                        lambda *a, **kw: appt)
    with pytest.raises(AuditableAppointmentError) as ei:
        appt_service.student_cancel(
            "u", {"id": 50}, "r", actor_role="student",
        )
    assert ei.value.audit_code == AUDIT_CODE_ACCESS_DENIED


def test_confirm_access_denied_is_auditable(monkeypatch):
    _mock_session(monkeypatch)
    monkeypatch.setattr(appt_service.storage, "get_appointment_by_uuid",
                        lambda *a, **kw: SimpleNamespace(psychologist_id=999,
                                                         status="pending_confirmation"))
    with pytest.raises(AuditableAppointmentError) as ei:
        appt_service.psychologist_confirm(
            "u", {"id": 7}, actor_role="psychologist",
        )
    assert ei.value.audit_code == AUDIT_CODE_ACCESS_DENIED


def test_decline_access_denied_is_auditable(monkeypatch):
    _mock_session(monkeypatch)
    monkeypatch.setattr(appt_service.storage, "get_appointment_by_uuid",
                        lambda *a, **kw: SimpleNamespace(psychologist_id=999,
                                                         status="pending_confirmation"))
    with pytest.raises(AuditableAppointmentError) as ei:
        appt_service.psychologist_decline(
            "u", {"id": 7}, "r", actor_role="psychologist",
        )
    assert ei.value.audit_code == AUDIT_CODE_ACCESS_DENIED


def test_card_create_consent_required_is_auditable():
    with pytest.raises(AuditableAppointmentError) as ei:
        appt_service.create_unregistered_student_card(
            {"full_name": "N", "personal_data_consent": False},
            {"id": 9}, actor_role="supervisor",
        )
    assert ei.value.audit_code == AUDIT_CODE_CONSENT_REQUIRED


# ── неаудируемые отказы: базовый класс, НЕ Auditable, без audit_code ──────────

def test_book_lead_time_not_auditable():
    from datetime import datetime, timezone
    with pytest.raises(AppointmentError) as ei:
        appt_service.book_appointment(
            {"id": 50, "is_active": True}, datetime.now(timezone.utc),
            "in_person", None, 1, actor_role="student",
        )
    assert not isinstance(ei.value, AuditableAppointmentError)


def test_card_create_full_name_empty_not_auditable():
    with pytest.raises(AppointmentError) as ei:
        appt_service.create_unregistered_student_card(
            {"full_name": "  ", "personal_data_consent": True},
            {"id": 9}, actor_role="supervisor",
        )
    assert not isinstance(ei.value, AuditableAppointmentError)


def test_cancel_not_found_not_auditable(monkeypatch):
    _mock_session(monkeypatch)
    monkeypatch.setattr(appt_service.storage, "get_appointment_by_uuid",
                        lambda *a, **kw: None)
    with pytest.raises(AppointmentError) as ei:
        appt_service.student_cancel("u", {"id": 50}, None,
                                    actor_role="student")
    assert not isinstance(ei.value, AuditableAppointmentError)


# ══════════════════════════════════════════════════════════════════════════
# 4. Route-level writer: isinstance-gated, ровно один вызов, без target/db
# ══════════════════════════════════════════════════════════════════════════

def _req():
    return SimpleNamespace(
        client=SimpleNamespace(host="203.0.113.7"),
        headers={"user-agent": "ua"},
    )


# SimpleNamespace.headers is a dict; routes call .headers.get(...) → dict.get ok.

def _spy(monkeypatch, module):
    calls = []
    monkeypatch.setattr(module, "record_secondary_failure",
                        lambda **kw: calls.append(kw))
    return calls


def test_book_route_writes_failed_for_auditable(monkeypatch):
    calls = _spy(monkeypatch, r_student)
    monkeypatch.setattr(
        r_student.service, "book_appointment",
        MagicMock(side_effect=AuditableAppointmentError(
            "x", 403, audit_code=AUDIT_CODE_ENGAGEMENT_REQUIRED)))
    body = SimpleNamespace(starts_at=_future(), modality="in_person",
                           topic=None, meeting_type_id=1)
    with pytest.raises(HTTPException) as ei:
        r_student.book_appointment(
            body=body, request=_req(),
            current_user={"id": "50", "roles": ["student"]})
    assert ei.value.status_code == 403
    assert len(calls) == 1
    kw = calls[0]
    assert kw["event"] == "appointment_create_failed"
    assert isinstance(kw["actor"], Actor)
    assert kw["actor"].user_id == 50 and kw["actor"].role == "student"
    assert kw["failure_reason_code"] == AUDIT_CODE_ENGAGEMENT_REQUIRED
    assert "target" not in kw and "db" not in kw and "user_email" not in kw
    assert "metadata" not in kw


def test_book_route_no_write_for_non_auditable(monkeypatch):
    calls = _spy(monkeypatch, r_student)
    monkeypatch.setattr(
        r_student.service, "book_appointment",
        MagicMock(side_effect=AppointmentError("busy", 409)))
    body = SimpleNamespace(starts_at=_future(), modality="in_person",
                           topic=None, meeting_type_id=1)
    with pytest.raises(HTTPException) as ei:
        r_student.book_appointment(
            body=body, request=_req(),
            current_user={"id": "50", "roles": ["student"]})
    assert ei.value.status_code == 409
    assert calls == []


def test_cancel_route_writes_failed(monkeypatch):
    calls = _spy(monkeypatch, r_student)
    monkeypatch.setattr(
        r_student.service, "student_cancel",
        MagicMock(side_effect=AuditableAppointmentError(
            "x", 403, audit_code=AUDIT_CODE_ACCESS_DENIED)))
    with pytest.raises(HTTPException):
        r_student.cancel_appointment(
            uuid="u", body=SimpleNamespace(reason="r"), request=_req(),
            current_user={"id": "50", "roles": ["student"]})
    assert len(calls) == 1
    assert calls[0]["event"] == "appointment_cancel_failed"
    assert calls[0]["failure_reason_code"] == AUDIT_CODE_ACCESS_DENIED


def test_confirm_route_writes_failed(monkeypatch):
    calls = _spy(monkeypatch, r_psy)
    monkeypatch.setattr(
        r_psy.service, "psychologist_confirm",
        MagicMock(side_effect=AuditableAppointmentError(
            "x", 403, audit_code=AUDIT_CODE_ACCESS_DENIED)))
    with pytest.raises(HTTPException):
        r_psy.confirm_appointment(
            uuid="u", request=_req(),
            current_user={"id": "7", "roles": ["psychologist"]})
    assert len(calls) == 1
    assert calls[0]["event"] == "appointment_confirm_failed"
    assert calls[0]["actor"].role == "psychologist"


def test_decline_route_writes_failed(monkeypatch):
    calls = _spy(monkeypatch, r_psy)
    monkeypatch.setattr(
        r_psy.service, "psychologist_decline",
        MagicMock(side_effect=AuditableAppointmentError(
            "x", 403, audit_code=AUDIT_CODE_ACCESS_DENIED)))
    with pytest.raises(HTTPException):
        r_psy.decline_appointment(
            uuid="u", body=SimpleNamespace(reason="r"), request=_req(),
            current_user={"id": "7", "roles": ["psychologist"]})
    assert len(calls) == 1
    assert calls[0]["event"] == "appointment_decline_failed"


def test_supervisor_book_route_writes_failed(monkeypatch):
    calls = _spy(monkeypatch, r_sup)
    monkeypatch.setattr(
        r_sup.service, "supervisor_book_appointment",
        MagicMock(side_effect=AuditableAppointmentError(
            "x", 422, audit_code=AUDIT_CODE_ENGAGEMENT_REQUIRED)))
    body = SimpleNamespace(student_id=50, unregistered_student_card_id=None,
                           psychologist_id=7, meeting_type_id=1,
                           starts_at=_future(), modality="in_person",
                           topic=None)
    with pytest.raises(HTTPException):
        r_sup.supervisor_book_appointment(
            body=body, request=_req(),
            current_user={"id": "9", "roles": ["supervisor"]})
    assert len(calls) == 1
    assert calls[0]["event"] == "appointment_create_failed"
    assert calls[0]["actor"].role == "supervisor"


def test_card_create_route_writes_failed(monkeypatch):
    calls = _spy(monkeypatch, r_sup)
    monkeypatch.setattr(
        r_sup.service, "create_unregistered_student_card",
        MagicMock(side_effect=AuditableAppointmentError(
            "x", 422, audit_code=AUDIT_CODE_CONSENT_REQUIRED)))
    body = SimpleNamespace(model_dump=lambda: {"full_name": "N"})
    with pytest.raises(HTTPException):
        r_sup.create_unregistered_student_card(
            body=body, request=_req(),
            current_user={"id": "9", "roles": ["admin"]})
    assert len(calls) == 1
    assert calls[0]["event"] == "unregistered_student_card_create_failed"
    assert calls[0]["actor"].role == "admin"
    assert calls[0]["failure_reason_code"] == AUDIT_CODE_CONSENT_REQUIRED


def test_role_resolution_403_before_business_no_write(monkeypatch):
    # supervisor-only failure event недоступен student'у: resolve роли до try;
    # 403 поднимается до вызова service → record_secondary_failure не вызывается.
    calls = _spy(monkeypatch, r_psy)
    called = {"n": 0}
    monkeypatch.setattr(r_psy.service, "psychologist_confirm",
                        lambda **kw: called.__setitem__("n", called["n"] + 1))
    with pytest.raises(HTTPException) as ei:
        r_psy.confirm_appointment(
            uuid="u", request=_req(),
            current_user={"id": "7", "roles": ["student"]})   # нет psychologist
    assert ei.value.status_code == 403
    assert calls == [] and called["n"] == 0


# ══════════════════════════════════════════════════════════════════════════
# 5. Secondary-writer failure: real writer, record_event бросает → HTTP цел
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("exc", [
    AuditError("boom"), AuditStorageError("boom"), RuntimeError("boom"),
])
def test_secondary_writer_failure_does_not_change_http(monkeypatch, exc, caplog):
    import app.audit.failsafe as failsafe
    # реальный record_secondary_failure; ломаем нижележащий record_event
    monkeypatch.setattr(
        failsafe, "record_event",
        MagicMock(side_effect=exc))
    monkeypatch.setattr(
        r_student.service, "book_appointment",
        MagicMock(side_effect=AuditableAppointmentError(
            "no engagement", 403, audit_code=AUDIT_CODE_ENGAGEMENT_REQUIRED)))
    body = SimpleNamespace(starts_at=_future(), modality="in_person",
                           topic=None, meeting_type_id=1)
    with caplog.at_level(logging.ERROR):
        with pytest.raises(HTTPException) as ei:
            r_student.book_appointment(
                body=body, request=_req(),
                current_user={"id": "50", "roles": ["student"]})
    # исходный business HTTP сохранён, secondary-сбой поглощён
    assert ei.value.status_code == 403
    assert ei.value.detail == "no engagement"


def test_secondary_writer_returns_soft_failed(monkeypatch):
    import app.audit.failsafe as failsafe
    from app.audit import WriteState
    monkeypatch.setattr(failsafe, "record_event",
                        MagicMock(side_effect=AuditStorageError("down")))
    res = failsafe.record_secondary_failure(
        event="appointment_create_failed",
        actor=Actor.user(50, "student"),
        failure_reason_code="engagement_required",
        context=None,
    )
    assert res.state is WriteState.SOFT_FAILED
    assert res.event == "appointment_create_failed"


# ══════════════════════════════════════════════════════════════════════════
# 6. Диагностика минимизирована — только event/phase/error class
# ══════════════════════════════════════════════════════════════════════════

def test_secondary_diagnostic_has_no_pii(monkeypatch, capsys):
    import app.audit.failsafe as failsafe

    class _Leaky(AuditStorageError):
        def __str__(self):
            return "leak@x.example 550e8400 SELECT * secret"
    monkeypatch.setattr(failsafe, "record_event",
                        MagicMock(side_effect=_Leaky()))
    failsafe.record_secondary_failure(
        event="appointment_cancel_failed",
        actor=Actor.user(50, "student"),
        failure_reason_code="access_denied", context=None,
    )
    err = capsys.readouterr().err
    assert "appointment_cancel_failed" in err and "_Leaky" in err
    for leak in ("leak@x.example", "550e8400", "SELECT", "secret"):
        assert leak not in err
