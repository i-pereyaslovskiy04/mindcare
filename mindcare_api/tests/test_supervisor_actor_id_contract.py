"""
Stage 4B-2 — route-boundary unit-тесты actor_id contract для supervisor.

current_user["id"] приходит СТРОКОЙ (_user_to_dict → str(user.id)), а audit-facade
требует int actor_id. Проверяем, что route-helper _actor и все четыре mutating route
конвертируют actor_id в int ДО передачи в service, для ролей supervisor и admin.
Реальная БД не используется — service замокан, ловим переданные аргументы.
"""
from types import SimpleNamespace

import pytest

from app.audit.contracts import Actor
from app.audit.validation import validate_actor
from app.audit.registry import get_spec
from app.supervisor import routes
from app.supervisor.schemas import (
    EngagementClose, EngagementCreate, EngagementTransfer, SupervisorStudentCreate,
)


def _fake_request(ip="192.0.2.10", ua="pytest-agent"):
    return SimpleNamespace(
        client=SimpleNamespace(host=ip),
        headers={"user-agent": ua},
    )


def _cu(role):
    # id — СТРОКА, как реально отдаёт _user_to_dict.
    return {"id": "42", "email": "s@e.com", "roles": [role], "role": role}


def _capture(monkeypatch, method_name):
    calls = {}

    def _spy(**kw):
        calls.update(kw)
        return {"id": 1}
    monkeypatch.setattr(routes.service, method_name, _spy)
    return calls


# ── _actor helper: str id → int ──────────────────────────────────────────────

@pytest.mark.parametrize("role", ["supervisor", "admin"])
def test_actor_helper_converts_id_to_int(role):
    actor_id, actor_role = routes._actor(_cu(role))
    assert type(actor_id) is int and actor_id == 42
    assert actor_role == role


# ── Все четыре mutating route: service получает int actor_id ──────────────────

@pytest.mark.parametrize("role", ["supervisor", "admin"])
def test_create_student_passes_int_actor_id(monkeypatch, role):
    calls = _capture(monkeypatch, "create_student")
    routes.create_student(
        request=_fake_request(),
        body=SupervisorStudentCreate(
            full_name="Иван Иванов", email="new@donnu.ru",
            personal_data_consent=True,
        ),
        current_user=_cu(role),
    )
    assert type(calls["actor_id"]) is int and calls["actor_id"] == 42
    assert calls["actor_role"] == role


@pytest.mark.parametrize("role", ["supervisor", "admin"])
def test_assign_passes_int_actor_id(monkeypatch, role):
    calls = _capture(monkeypatch, "assign_psychologist")
    routes.create_engagement(
        body=EngagementCreate(client_id=1, psychologist_id=2),
        current_user=_cu(role),
    )
    assert type(calls["actor_id"]) is int and calls["actor_id"] == 42
    assert calls["actor_role"] == role


@pytest.mark.parametrize("role", ["supervisor", "admin"])
def test_transfer_passes_int_actor_id(monkeypatch, role):
    calls = _capture(monkeypatch, "transfer_psychologist")
    routes.transfer_engagement(
        engagement_id=5,
        body=EngagementTransfer(new_psychologist_id=3),
        current_user=_cu(role),
    )
    assert type(calls["actor_id"]) is int and calls["actor_id"] == 42
    assert calls["actor_role"] == role


@pytest.mark.parametrize("role", ["supervisor", "admin"])
def test_close_passes_int_actor_id(monkeypatch, role):
    calls = _capture(monkeypatch, "close_engagement")
    routes.close_engagement(
        engagement_id=5,
        body=EngagementClose(),
        current_user=_cu(role),
    )
    assert type(calls["actor_id"]) is int and calls["actor_id"] == 42
    assert calls["actor_role"] == role


# ── Facade принимает такой actor (int id) для supervisor-событий ──────────────

@pytest.mark.parametrize("role", ["supervisor", "admin"])
def test_facade_accepts_int_actor_for_supervisor_events(role):
    # int actor_id + роль supervisor/admin проходят validate_actor (admin не 500).
    actor = Actor.user(42, role)
    for event in (
        "supervisor_create_student", "supervisor_assign_psychologist",
        "supervisor_reactivate_psychologist", "supervisor_transfer_psychologist",
        "supervisor_close_engagement",
    ):
        validate_actor(get_spec(event), actor)     # не бросает


def test_facade_rejects_str_actor_id():
    # Контроль: строковый actor_id действительно отвергается facade.
    from app.audit.contracts import AuditError
    with pytest.raises(AuditError):
        validate_actor(get_spec("supervisor_assign_psychologist"),
                       Actor.user("42", "supervisor"))
