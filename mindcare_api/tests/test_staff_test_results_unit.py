"""
Staff-доступ к результатам (ADR-016, дополнение 2026-10-29) — service без БД:
выбор роли, отказ области, fail-closed аудит и отсутствие содержимого в событии.
"""
import pytest

from app.audit import AuditStorageError
from app.tests import service

DATA = {"uuid": "r", "total_score": 7, "scales": [], "recommendations": "секрет"}


def _user(roles, uid=5):
    return {"id": str(uid), "roles": roles}


@pytest.fixture
def events(monkeypatch):
    calls = []

    def _record(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(service, "record_event", _record)
    return calls


def test_detail_records_content_read_after_scope_check(monkeypatch, events):
    seen = {}

    def _read(**kw):
        seen.update(kw)
        return {"result_id": 42, "data": DATA}

    monkeypatch.setattr(service.storage, "read_result_for_staff", _read)
    out = service.get_staff_result(
        current_user=_user(["psychologist", "student"]), requested_role=None,
        result_uuid="u",
    )
    assert out is DATA
    assert seen == {"role": "psychologist", "actor_id": 5, "result_uuid": "u"}
    assert len(events) == 1
    ev = events[0]
    assert ev["event"] == "test_result_content_read"
    assert (ev["actor"].user_id, ev["actor"].role) == (5, "psychologist")
    assert (ev["target"].entity_type, ev["target"].entity_id) == ("test_result", 42)
    assert ev["metadata"] == {} and "db" not in ev
    assert "секрет" not in repr(ev)


def test_psychologist_scope_denial_is_not_available(monkeypatch, events):
    monkeypatch.setattr(service.storage, "read_result_for_staff", lambda **kw: None)
    with pytest.raises(service.ResultNotAvailable):
        service.get_staff_result(
            current_user=_user(["psychologist"]), requested_role=None, result_uuid="u",
        )
    assert events == []


def test_supervisor_not_found_is_plain_404(monkeypatch, events):
    monkeypatch.setattr(service.storage, "read_result_for_staff", lambda **kw: None)
    with pytest.raises(service.ResultNotFound):
        service.get_staff_result(
            current_user=_user(["supervisor"]), requested_role=None, result_uuid="u",
        )
    assert events == []


def test_audit_failure_propagates_and_content_not_returned(monkeypatch):
    monkeypatch.setattr(
        service.storage, "read_result_for_staff",
        lambda **kw: {"result_id": 1, "data": DATA},
    )

    def _boom(**kwargs):
        raise AuditStorageError("audit storage failure")

    monkeypatch.setattr(service, "record_event", _boom)
    with pytest.raises(AuditStorageError):
        service.get_staff_result_answers(
            current_user=_user(["psychologist"]), requested_role=None, result_uuid="u",
        )


def test_answers_only_for_psychologist_acting_role(monkeypatch, events):
    called = []
    monkeypatch.setattr(
        service.storage, "read_result_for_staff", lambda **kw: called.append(kw),
    )
    with pytest.raises(service.ResultAccessError):
        service.get_staff_result_answers(
            current_user=_user(["supervisor"]), requested_role=None, result_uuid="u",
        )
    with pytest.raises(service.ResultAccessError):
        service.get_staff_result_answers(
            current_user=_user(["psychologist", "supervisor"]),
            requested_role="supervisor", result_uuid="u",
        )
    assert called == [] and events == []


def test_answers_pass_with_answers_flag(monkeypatch, events):
    seen = {}

    def _read(**kw):
        seen.update(kw)
        return {"result_id": 3, "data": {"items": []}}

    monkeypatch.setattr(service.storage, "read_result_for_staff", _read)
    service.get_staff_result_answers(
        current_user=_user(["psychologist", "supervisor"]), requested_role="psychologist",
        result_uuid="u",
    )
    assert seen["with_answers"] is True and seen["role"] == "psychologist"
    assert [e["event"] for e in events] == ["test_result_content_read"]


def test_list_routes_by_role(monkeypatch):
    monkeypatch.setattr(
        service.storage, "list_results_for_psychologist",
        lambda pid, su, page, size: None,
    )
    monkeypatch.setattr(
        service.storage, "list_results_for_supervisor",
        lambda su, page, size: ([{"uuid": "x"}], 1),
    )
    with pytest.raises(service.ResultNotAvailable):
        service.list_student_results(
            current_user=_user(["psychologist"]), requested_role=None,
            student_uuid="s", page=1, size=20,
        )
    assert service.list_student_results(
        current_user=_user(["supervisor"]), requested_role=None,
        student_uuid="s", page=1, size=20,
    ) == ([{"uuid": "x"}], 1)
