"""
No-DB unit-тесты actor/target semantics role-change AuditLog (Stage 3).

Вызывают ТОЛЬКО app/users/storage.py::_apply_role_and_scalar_changes с минимальным
fake `db` (MagicMock). НЕ мокают HTTP/SessionLocal. Мокаются лишь терминалы query-
chain, реально используемые remove-путём (`.all()` для lookup снятой роли, `.delete()`
для удаления UserRole) + перехватывается `db.add(...)`. Это точечная проверка field-
mapping и fail-closed guard, а не фиксация внутренностей SQLAlchemy; authoritative
DB-семантику даёт integration (test_admin_role_audit_actor.py) при доступном
PostgreSQL.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import app.users.storage as users_storage
from app.audit.contracts import AuditStorageError
from app.db.models import AuditLog
from app.users.storage import _apply_role_and_scalar_changes

ACTOR_ID = 101
TARGET_ID = 202


def _fake_db(removed_role_id: int = 99):
    """MagicMock db: query(...).filter(...).all() -> [role], .delete() -> 1."""
    db = MagicMock(name="db")
    chain = db.query.return_value.filter.return_value
    chain.all.return_value = [SimpleNamespace(id=removed_role_id)]
    chain.delete.return_value = 1
    return db


def _call_remove(db, *, actor_id, actor_role, user_id=TARGET_ID):
    """Remove-сценарий: у пользователя psychologist+supervisor, снимаем supervisor.
    added пуст → legal basis не требуется."""
    user = SimpleNamespace(id=user_id)
    _apply_role_and_scalar_changes(
        db, user,
        current_roles=["psychologist", "supervisor"],
        target_staff={"psychologist"},
        full_name=None, phone=None, is_active=None,
        legal_basis_confirmed=None, basis_type=None, basis_reference=None,
        legal_basis_comment=None, confirmed_by_user_id=None,
        actor_id=actor_id, actor_role=actor_role,
        ip="203.0.113.7", user_agent="pytest-ua",
    )


def _added_audit_logs(db) -> list:
    return [
        c.args[0] for c in db.add.call_args_list
        if isinstance(c.args[0], AuditLog)
    ]


# ── A. Field mapping (remove, actor != target) ───────────────────────────────

def test_role_remove_audit_actor_target_mapping():
    db = _fake_db()
    _call_remove(db, actor_id=ACTOR_ID, actor_role="admin")

    audits = _added_audit_logs(db)
    assert len(audits) == 1
    a = audits[0]
    assert a.user_id == ACTOR_ID            # actor
    assert a.entity_id == TARGET_ID         # target
    assert a.user_id != TARGET_ID
    assert a.entity_type == "user"
    assert a.user_role == "admin"
    assert a.event_type == "admin_role_remove"
    # description больше не пишется (facade description_policy=NONE, Stage 4B-2)
    assert a.description is None
    # точный набор ключей metadata, без ПДн
    assert set(a.log_metadata.keys()) == {
        "roles_before", "roles_after", "added", "removed",
    }
    assert a.log_metadata["removed"] == ["supervisor"]


# ── B. Fail-closed guard: реальный diff без actor context → RuntimeError ──────

@pytest.mark.parametrize("actor_id,actor_role", [
    (None, "admin"),      # нет actor_id
    (ACTOR_ID, None),     # нет actor_role
])
def test_role_change_without_actor_context_fails_closed(actor_id, actor_role):
    db = _fake_db()
    with pytest.raises(RuntimeError):
        _call_remove(db, actor_id=actor_id, actor_role=actor_role)

    # Ни AuditLog, ни UserLegalBasisRecord не добавлены; UserRole не удалялся/не
    # вставлялся — guard сработал до всех мутаций.
    assert db.add.call_count == 0
    db.query.assert_not_called()


def test_added_or_removed_empty_no_actor_guard_noop():
    # No-op по ролям (target_staff == current staff) не требует actor context и
    # не пишет audit: RuntimeError не возникает даже при actor_id=None.
    db = MagicMock(name="db")
    user = SimpleNamespace(id=TARGET_ID)
    _apply_role_and_scalar_changes(
        db, user,
        current_roles=["psychologist"],
        target_staff={"psychologist"},   # added=removed=пусто
        full_name=None, phone=None, is_active=None,
        legal_basis_confirmed=None, basis_type=None, basis_reference=None,
        legal_basis_comment=None, confirmed_by_user_id=None,
        actor_id=None, actor_role=None,
        ip=None, user_agent=None,
    )
    assert db.add.call_count == 0  # no-op: ни ролей, ни audit


# ── C. Failure-injection: audit-сбой не проглатывается (path A) ───────────────

def test_role_audit_failure_propagates_not_swallowed(monkeypatch):
    # record_event падает (AuditStorageError до commit) → исключение всплывает из
    # writer'а; business-транзакция (commit в update_user) не достигается.
    db = _fake_db()

    def _boom(**kw):
        raise AuditStorageError("audit storage failure for admin_role_remove")
    monkeypatch.setattr(users_storage, "record_event", _boom)

    with pytest.raises(AuditStorageError):
        _call_remove(db, actor_id=ACTOR_ID, actor_role="admin")

    db.commit.assert_not_called()   # writer не коммитит; сбой не проглочен


def test_scalar_real_diff_without_actor_context_fails_closed():
    # Stage 4B-4: реальный scalar-diff (target_staff=None) БЕЗ actor context
    # теперь fail-closed, симметрично role-diff — раньше проходил молча.
    db = MagicMock(name="db")
    user = SimpleNamespace(id=TARGET_ID, full_name="Old", phone=None, is_active=True)
    with pytest.raises(RuntimeError):
        _apply_role_and_scalar_changes(
            db, user,
            current_roles=["student"],
            target_staff=None,                # только scalar
            full_name="Новое Имя", phone=None, is_active=False,
            legal_basis_confirmed=None, basis_type=None, basis_reference=None,
            legal_basis_comment=None, confirmed_by_user_id=None,
            actor_id=None, actor_role=None,
            ip=None, user_agent=None,
        )
    # Guard сработал ДО мутации: значения объекта не изменены.
    assert user.full_name == "Old"
    assert user.is_active is True
    assert db.add.call_count == 0


def test_scalar_no_op_without_actor_context_allowed():
    # Proposed-значения совпадают с текущими (реального diff нет) → guard не
    # срабатывает даже при actor_id=None/actor_role=None — мутировать нечего.
    db = MagicMock(name="db")
    user = SimpleNamespace(id=TARGET_ID, full_name="Old", phone=None, is_active=True)
    _apply_role_and_scalar_changes(
        db, user,
        current_roles=["student"],
        target_staff=None,
        full_name="Old", phone=None, is_active=True,   # совпадает с текущим
        legal_basis_confirmed=None, basis_type=None, basis_reference=None,
        legal_basis_comment=None, confirmed_by_user_id=None,
        actor_id=None, actor_role=None,
        ip=None, user_agent=None,
    )
    assert user.full_name == "Old"
    assert user.is_active is True
    assert db.add.call_count == 0  # ни мутации, ни audit
