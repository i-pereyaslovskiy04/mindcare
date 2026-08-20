"""
Stage 4B-4 — no-DB unit-тесты переноса admin user CRUD + self-profile audit на
record_event(): app.users.storage.{create_user, soft_delete_user,
_apply_role_and_scalar_changes} и app.auth.storage.update_profile_atomic.

Мокается либо `record_event`/`build_request_context` на уровне модуля (spy),
либо SessionLocal (MagicMock db) — без реальной БД. Authoritative
DB-семантику (реальный commit/rollback, реальные AuditLog-строки) даёт gated
integration (test_admin_user_crud_audit_api.py) при доступном PostgreSQL.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import app.users.storage as users_storage
import app.auth.storage as auth_storage
from app.audit.contracts import AuditStorageError
from app.db.models import UserLegalBasisRecord
from app.users.storage import (
    create_user, soft_delete_user, _apply_role_and_scalar_changes,
)
from app.users.storage import RoleChangeError
from app.users.errors import RoleConfigError
from app.auth.storage import update_profile_atomic, UserNotFoundError

ACTOR_ID = 101
TARGET_ID = 202


def _mock_session(mock_db):
    """Return a mock SessionLocal class that yields mock_db as context manager."""
    m = MagicMock()
    m.return_value.__enter__ = MagicMock(return_value=mock_db)
    m.return_value.__exit__ = MagicMock(return_value=False)
    return m


# ══════════════════════════════════════════════════════════════════════════
# storage.create_user — admin_user_created
# ══════════════════════════════════════════════════════════════════════════

def _create_user_db(role_name="psychologist", role_id=99):
    db = MagicMock(name="db")
    # Stage 5A-2: duplicate-check — один filter (все User, вкл. soft-deleted).
    db.query.return_value.filter.return_value.first.return_value = None
    # Role-lookup for the requested role.
    role_obj = SimpleNamespace(id=role_id, name=role_name)
    db.query.return_value.filter.return_value.all.return_value = [role_obj]
    return db


def test_create_user_missing_actor_context_fails_closed_before_any_query():
    # Guard стоит ДО SessionLocal/domain-check/role-lookup — RuntimeError без
    # какого-либо обращения к БД.
    with pytest.raises(RuntimeError):
        create_user(
            "user@mail.ru", "Test", "hash", ["psychologist"],
            basis_reference="Приказ № 1",
            confirmed_by_user_id=None, actor_role="admin",
        )
    with pytest.raises(RuntimeError):
        create_user(
            "user@mail.ru", "Test", "hash", ["psychologist"],
            basis_reference="Приказ № 1",
            confirmed_by_user_id=ACTOR_ID, actor_role=None,
        )


def test_create_user_stages_admin_user_created_before_commit(monkeypatch):
    calls = []
    monkeypatch.setattr(users_storage, "record_event", lambda **kw: calls.append(kw))

    db = _create_user_db()
    mock_new_user = MagicMock()
    mock_new_user.id = TARGET_ID
    mock_new_user.email = "user@mail.ru"

    with patch("app.users.storage.SessionLocal", _mock_session(db)), \
         patch("app.users.storage.User", return_value=mock_new_user):
        create_user(
            "user@mail.ru", "Test", "hash", ["psychologist"],
            basis_reference="Приказ № 1",
            confirmed_by_user_id=ACTOR_ID, actor_role="admin",
            ip="203.0.113.7", user_agent="pytest-ua",
        )

    assert len(calls) == 1
    kw = calls[0]
    assert kw["event"] == "admin_user_created"
    assert kw["actor"].kind == "user"
    assert kw["actor"].user_id == ACTOR_ID
    assert kw["actor"].role == "admin"
    assert kw["target"].entity_type == "user"
    assert kw["target"].entity_id == TARGET_ID
    assert kw["metadata"] == {}
    assert kw["db"] is db
    # Вызван ДО commit (single commit в конце with-блока).
    db.commit.assert_called_once()


def test_create_user_audit_failure_propagates_not_swallowed(monkeypatch):
    def _boom(**kw):
        raise AuditStorageError("audit storage failure for admin_user_created")
    monkeypatch.setattr(users_storage, "record_event", _boom)

    db = _create_user_db()
    mock_new_user = MagicMock()
    mock_new_user.id = TARGET_ID

    with patch("app.users.storage.SessionLocal", _mock_session(db)), \
         patch("app.users.storage.User", return_value=mock_new_user):
        with pytest.raises(AuditStorageError):
            create_user(
                "user@mail.ru", "Test", "hash", ["psychologist"],
                basis_reference="Приказ № 1",
                confirmed_by_user_id=ACTOR_ID, actor_role="admin",
            )
    db.commit.assert_not_called()


def test_create_user_legal_basis_and_audit_share_one_sanitized_context(monkeypatch):
    calls = []
    monkeypatch.setattr(users_storage, "record_event", lambda **kw: calls.append(kw))
    build_ctx_calls = []
    real_build = users_storage.build_request_context

    def _spy_build(**kw):
        ctx = real_build(**kw)
        build_ctx_calls.append(ctx)
        return ctx
    monkeypatch.setattr(users_storage, "build_request_context", _spy_build)

    db = _create_user_db()
    mock_new_user = MagicMock()
    mock_new_user.id = TARGET_ID

    with patch("app.users.storage.SessionLocal", _mock_session(db)), \
         patch("app.users.storage.User", return_value=mock_new_user):
        create_user(
            "user@mail.ru", "Test", "hash", ["psychologist"],
            basis_reference="Приказ № 1",
            confirmed_by_user_id=ACTOR_ID, actor_role="admin",
            ip="not-an-ip", user_agent="x" * 600,
        )

    # Один build_request_context на всю функцию.
    assert len(build_ctx_calls) == 1
    safe_ctx = build_ctx_calls[0]
    assert safe_ctx.ip_address is None          # invalid ip -> None
    assert safe_ctx.user_agent is None          # UA > 512 -> None

    legal_basis_adds = [
        c.args[0] for c in db.add.call_args_list
        if isinstance(c.args[0], UserLegalBasisRecord)
    ]
    assert len(legal_basis_adds) == 1
    assert legal_basis_adds[0].ip_address is None
    assert legal_basis_adds[0].user_agent is None
    # Тот же safe_ctx объект ушёл в audit context.
    assert calls[0]["context"] is safe_ctx


# ══════════════════════════════════════════════════════════════════════════
# storage.soft_delete_user — admin_user_deleted
# ══════════════════════════════════════════════════════════════════════════

VALID_UUID = "aaaaaaaa-0000-0000-0000-000000000001"


def test_soft_delete_user_missing_actor_context_fails_closed_before_session(monkeypatch):
    # SessionLocal не должен даже открываться, если guard срабатывает раньше.
    def _boom(*a, **kw):
        raise AssertionError("SessionLocal must not be opened before actor guard")
    monkeypatch.setattr(users_storage, "SessionLocal", _boom)

    with pytest.raises(RuntimeError):
        soft_delete_user(VALID_UUID, actor_id=None, actor_role="admin")
    with pytest.raises(RuntimeError):
        soft_delete_user(VALID_UUID, actor_id=ACTOR_ID, actor_role=None)


def test_soft_delete_user_stages_admin_user_deleted_before_commit(monkeypatch):
    calls = []
    monkeypatch.setattr(users_storage, "record_event", lambda **kw: calls.append(kw))

    db = MagicMock(name="db")
    found_user = SimpleNamespace(id=TARGET_ID, deleted_at=None, is_active=True)
    db.query.return_value.filter.return_value.filter.return_value.first.return_value = found_user

    with patch("app.users.storage.SessionLocal", _mock_session(db)):
        result = soft_delete_user(
            VALID_UUID, actor_id=ACTOR_ID, actor_role="admin",
            ip="203.0.113.7", user_agent="pytest-ua",
        )

    assert result is True
    assert len(calls) == 1
    kw = calls[0]
    assert kw["event"] == "admin_user_deleted"
    assert kw["actor"].user_id == ACTOR_ID
    assert kw["actor"].role == "admin"
    assert kw["target"].entity_type == "user"
    assert kw["target"].entity_id == TARGET_ID
    assert kw["metadata"] == {}
    assert kw["db"] is db
    db.commit.assert_called_once()


def test_soft_delete_user_not_found_no_audit(monkeypatch):
    calls = []
    monkeypatch.setattr(users_storage, "record_event", lambda **kw: calls.append(kw))

    db = MagicMock(name="db")
    db.query.return_value.filter.return_value.filter.return_value.first.return_value = None

    with patch("app.users.storage.SessionLocal", _mock_session(db)):
        result = soft_delete_user(VALID_UUID, actor_id=ACTOR_ID, actor_role="admin")

    assert result is False
    assert calls == []
    db.commit.assert_not_called()


def test_soft_delete_user_audit_failure_propagates_not_swallowed(monkeypatch):
    def _boom(**kw):
        raise AuditStorageError("audit storage failure for admin_user_deleted")
    monkeypatch.setattr(users_storage, "record_event", _boom)

    db = MagicMock(name="db")
    found_user = SimpleNamespace(id=TARGET_ID, deleted_at=None, is_active=True)
    db.query.return_value.filter.return_value.filter.return_value.first.return_value = found_user

    with patch("app.users.storage.SessionLocal", _mock_session(db)):
        with pytest.raises(AuditStorageError):
            soft_delete_user(VALID_UUID, actor_id=ACTOR_ID, actor_role="admin")
    db.commit.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════
# _apply_role_and_scalar_changes — admin_user_updated (+ combined with role)
# ══════════════════════════════════════════════════════════════════════════

def _role_lookup_db(role_objs):
    db = MagicMock(name="db")
    chain = db.query.return_value.filter.return_value
    chain.all.return_value = role_objs
    chain.first.return_value = None   # no existing (expired) UserRole row
    return db


def test_scalar_only_real_diff_stages_admin_user_updated():
    calls = []
    # Stage 6-C: record_data_change тоже spy — иначе реальный writer добавил бы
    # свою journal-строку через db.add, и проверка «нет role mutation» ниже
    # перестала бы измерять именно роли.
    dcl = []
    with patch.object(users_storage, "record_event", lambda **kw: calls.append(kw)), \
         patch.object(users_storage, "record_data_change",
                      lambda **kw: dcl.append(kw)):
        db = MagicMock(name="db")
        user = SimpleNamespace(id=TARGET_ID, full_name="Old", phone=None, is_active=True)
        _apply_role_and_scalar_changes(
            db, user,
            current_roles=["student"],
            target_staff=None,
            full_name="New Name", phone=None, is_active=None,
            legal_basis_confirmed=None, basis_type=None, basis_reference=None,
            legal_basis_comment=None, confirmed_by_user_id=None,
            actor_id=ACTOR_ID, actor_role="admin",
            ip=None, user_agent=None,
        )
    assert user.full_name == "New Name"
    assert len(calls) == 1
    assert calls[0]["event"] == "admin_user_updated"
    assert calls[0]["actor"].user_id == ACTOR_ID
    assert calls[0]["target"].entity_id == TARGET_ID
    assert calls[0]["metadata"] == {}
    assert db.add.call_count == 0   # scalar-only: без role mutation
    # Stage 6-C: ровно одна journal-строка, только имя поля, без значений ПДн.
    assert len(dcl) == 1
    assert dcl[0]["table"] == "users"
    assert dcl[0]["record_id"] == TARGET_ID
    assert dcl[0]["changed_fields"] == ["full_name"]
    assert dcl[0]["values"] is None
    assert "New Name" not in repr(dcl[0])


def test_scalar_no_op_no_audit_no_mutation():
    calls = []
    with patch.object(users_storage, "record_event", lambda **kw: calls.append(kw)):
        db = MagicMock(name="db")
        user = SimpleNamespace(id=TARGET_ID, full_name="Old", phone="123", is_active=True)
        _apply_role_and_scalar_changes(
            db, user,
            current_roles=["student"],
            target_staff=None,
            full_name="Old", phone="123", is_active=True,   # identical
            legal_basis_confirmed=None, basis_type=None, basis_reference=None,
            legal_basis_comment=None, confirmed_by_user_id=None,
            actor_id=None, actor_role=None,
            ip=None, user_agent=None,
        )
    assert calls == []
    assert db.add.call_count == 0


def test_role_only_no_op_no_admin_user_updated():
    # Role no-op (target_staff == current staff), никакого scalar diff.
    calls = []
    with patch.object(users_storage, "record_event", lambda **kw: calls.append(kw)):
        db = MagicMock(name="db")
        user = SimpleNamespace(id=TARGET_ID, full_name="Old", phone=None, is_active=True)
        _apply_role_and_scalar_changes(
            db, user,
            current_roles=["psychologist"],
            target_staff={"psychologist"},
            full_name=None, phone=None, is_active=None,
            legal_basis_confirmed=None, basis_type=None, basis_reference=None,
            legal_basis_comment=None, confirmed_by_user_id=None,
            actor_id=None, actor_role=None,
            ip=None, user_agent=None,
        )
    assert calls == []
    assert db.add.call_count == 0


def test_role_only_no_op_but_scalar_real_change_stages_admin_user_updated_only():
    calls = []
    with patch.object(users_storage, "record_event", lambda **kw: calls.append(kw)):
        db = MagicMock(name="db")
        user = SimpleNamespace(id=TARGET_ID, full_name="Old", phone=None, is_active=True)
        _apply_role_and_scalar_changes(
            db, user,
            current_roles=["psychologist"],
            target_staff={"psychologist"},   # role no-op
            full_name="New Name", phone=None, is_active=None,
            legal_basis_confirmed=None, basis_type=None, basis_reference=None,
            legal_basis_comment=None, confirmed_by_user_id=None,
            actor_id=ACTOR_ID, actor_role="admin",
            ip=None, user_agent=None,
        )
    assert user.full_name == "New Name"
    assert len(calls) == 1
    assert calls[0]["event"] == "admin_user_updated"


def test_scalar_and_role_diff_combined_stages_two_rows_one_shared_context():
    calls = []
    # Stage 6-C: record_data_change тоже spy. Реальный writer применяет строгую
    # validate_context и отверг бы sentinel-SimpleNamespace; здесь проверяется
    # ИМЕННО переиспользование одного и того же объекта context, а не его тип.
    dcl = []
    sentinel_ctx = SimpleNamespace(ip_address=None, user_agent=None)
    with patch.object(users_storage, "record_event", lambda **kw: calls.append(kw)), \
         patch.object(users_storage, "record_data_change",
                      lambda **kw: dcl.append(kw)), \
         patch.object(users_storage, "build_request_context", lambda **kw: sentinel_ctx):
        role_obj = SimpleNamespace(id=55, name="supervisor")
        db = _role_lookup_db([role_obj])
        user = SimpleNamespace(id=TARGET_ID, full_name="Old", phone=None, is_active=True)
        _apply_role_and_scalar_changes(
            db, user,
            current_roles=["psychologist"],
            target_staff={"psychologist", "supervisor"},   # added={"supervisor"}
            full_name="New Name", phone=None, is_active=None,
            legal_basis_confirmed=True, basis_type="service_duty",
            basis_reference="Order #1", legal_basis_comment=None,
            confirmed_by_user_id=ACTOR_ID,
            actor_id=ACTOR_ID, actor_role="admin",
            ip="203.0.113.7", user_agent="pytest-ua",
        )

    assert user.full_name == "New Name"   # mutation applied only after validation
    assert len(calls) == 2
    events = {c["event"] for c in calls}
    assert events == {"admin_user_updated", "admin_role_add"}
    for c in calls:
        assert c["context"] is sentinel_ctx        # единый safe_ctx на оба события
        assert c["target"].entity_id == TARGET_ID
    updated_call = next(c for c in calls if c["event"] == "admin_user_updated")
    assert updated_call["metadata"] == {}
    role_call = next(c for c in calls if c["event"] == "admin_role_add")
    assert role_call["metadata"]["added"] == ["supervisor"]

    legal_basis_adds = [
        c.args[0] for c in db.add.call_args_list
        if isinstance(c.args[0], UserLegalBasisRecord)
    ]
    assert len(legal_basis_adds) == 1
    # Legal basis использует тот же sanitized context, что и audit-строки.
    assert legal_basis_adds[0].ip_address is sentinel_ctx.ip_address
    assert legal_basis_adds[0].user_agent is sentinel_ctx.user_agent

    # Stage 6-C: combined scalar+role → ОДНА journal-строка, ТОЛЬКО по scalar
    # полю; роли в неё не попадают и остаются в metadata admin_role_add.
    assert len(dcl) == 1
    assert dcl[0]["changed_fields"] == ["full_name"]
    assert dcl[0]["values"] is None
    assert dcl[0]["context"] is sentinel_ctx     # тот же единый safe_ctx
    assert "supervisor" not in dcl[0]["changed_fields"]


def test_scalar_real_diff_and_missing_added_role_rejects_before_any_mutation():
    # Stage 4B-4 corrective pass: существование Role для added проверяется
    # ДО какой-либо мутации (включая scalar) — не внутри цикла мутации.
    calls = []
    with patch.object(users_storage, "record_event", lambda **kw: calls.append(kw)):
        db = _role_lookup_db([])   # ни одна added-роль не найдена в БД
        user = SimpleNamespace(id=TARGET_ID, full_name="Old", phone=None, is_active=True)
        # Stage 5A-2: отсутствие Role в seed/БД → RoleConfigError (internal_error),
        # НЕ пользовательский invalid_role.
        with pytest.raises(RoleConfigError):
            _apply_role_and_scalar_changes(
                db, user,
                current_roles=["psychologist"],
                target_staff={"psychologist", "supervisor"},
                full_name="New Name", phone=None, is_active=None,
                legal_basis_confirmed=True, basis_type="service_duty",
                basis_reference="Order #1", legal_basis_comment=None,
                confirmed_by_user_id=ACTOR_ID,
                actor_id=ACTOR_ID, actor_role="admin",
                ip=None, user_agent=None,
            )
    # Scalar-мутация НЕ применена — validate-before-mutate для всего PATCH.
    assert user.full_name == "Old"
    assert db.add.call_count == 0
    assert db.query.return_value.filter.return_value.delete.call_count == 0
    assert calls == []


def test_role_audit_failure_rolls_back_together_with_scalar(monkeypatch):
    # scalar admin_user_updated успешен, admin_role_add бросает AuditStorageError
    # → обе staged-строки "откатываются вместе" (caller не достигает commit;
    # здесь проверяем, что исключение пробрасывается наружу без проглатывания).
    def _record_event(**kw):
        if kw["event"] == "admin_role_add":
            raise AuditStorageError("audit storage failure for admin_role_add")
    with patch.object(users_storage, "record_event", _record_event):
        role_obj = SimpleNamespace(id=55, name="supervisor")
        db = _role_lookup_db([role_obj])
        user = SimpleNamespace(id=TARGET_ID, full_name="Old", phone=None, is_active=True)
        with pytest.raises(AuditStorageError):
            _apply_role_and_scalar_changes(
                db, user,
                current_roles=["psychologist"],
                target_staff={"psychologist", "supervisor"},
                full_name="New Name", phone=None, is_active=None,
                legal_basis_confirmed=True, basis_type="service_duty",
                basis_reference="Order #1", legal_basis_comment=None,
                confirmed_by_user_id=ACTOR_ID,
                actor_id=ACTOR_ID, actor_role="admin",
                ip=None, user_agent=None,
            )


# ══════════════════════════════════════════════════════════════════════════
# Stage 5A-1: lifecycle is_active — admin_user_activated / admin_user_deactivated
# ══════════════════════════════════════════════════════════════════════════

def _revoke_update_calls(db):
    """Вызовы UserSession-revoke: .update({"is_revoked": True}, ...)."""
    return [
        c for c in db.query.return_value.filter.return_value.update.call_args_list
        if c.args and c.args[0] == {"is_revoked": True}
    ]


def test_is_active_true_to_false_stages_deactivated_and_revokes_sessions():
    calls = []
    with patch.object(users_storage, "record_event", lambda **kw: calls.append(kw)):
        db = MagicMock(name="db")
        user = SimpleNamespace(id=TARGET_ID, full_name="X", phone=None, is_active=True)
        _apply_role_and_scalar_changes(
            db, user,
            current_roles=["student"], target_staff=None,
            full_name=None, phone=None, is_active=False,
            legal_basis_confirmed=None, basis_type=None, basis_reference=None,
            legal_basis_comment=None, confirmed_by_user_id=None,
            actor_id=ACTOR_ID, actor_role="admin", ip=None, user_agent=None,
        )
    assert user.is_active is False
    assert len(calls) == 1
    kw = calls[0]
    assert kw["event"] == "admin_user_deactivated"
    assert kw["actor"].user_id == ACTOR_ID and kw["actor"].role == "admin"
    assert kw["target"].entity_type == "user" and kw["target"].entity_id == TARGET_ID
    assert kw["metadata"] == {}
    # Отзыв активных сессий выполнен (True→False).
    assert len(_revoke_update_calls(db)) == 1


def test_is_active_false_to_true_stages_activated_no_revoke():
    calls = []
    with patch.object(users_storage, "record_event", lambda **kw: calls.append(kw)):
        db = MagicMock(name="db")
        user = SimpleNamespace(id=TARGET_ID, full_name="X", phone=None, is_active=False)
        _apply_role_and_scalar_changes(
            db, user,
            current_roles=["student"], target_staff=None,
            full_name=None, phone=None, is_active=True,
            legal_basis_confirmed=None, basis_type=None, basis_reference=None,
            legal_basis_comment=None, confirmed_by_user_id=None,
            actor_id=ACTOR_ID, actor_role="admin", ip=None, user_agent=None,
        )
    assert user.is_active is True
    assert len(calls) == 1
    assert calls[0]["event"] == "admin_user_activated"
    # Активация сессии НЕ отзывает.
    assert _revoke_update_calls(db) == []


def test_is_active_same_value_no_lifecycle_event_no_revoke():
    calls = []
    with patch.object(users_storage, "record_event", lambda **kw: calls.append(kw)):
        db = MagicMock(name="db")
        user = SimpleNamespace(id=TARGET_ID, full_name="X", phone=None, is_active=True)
        _apply_role_and_scalar_changes(
            db, user,
            current_roles=["student"], target_staff=None,
            full_name=None, phone=None, is_active=True,   # state → same
            legal_basis_confirmed=None, basis_type=None, basis_reference=None,
            legal_basis_comment=None, confirmed_by_user_id=None,
            actor_id=None, actor_role=None, ip=None, user_agent=None,
        )
    assert calls == []
    assert _revoke_update_calls(db) == []


def test_is_active_only_does_not_stage_admin_user_updated():
    calls = []
    with patch.object(users_storage, "record_event", lambda **kw: calls.append(kw)):
        db = MagicMock(name="db")
        user = SimpleNamespace(id=TARGET_ID, full_name="X", phone=None, is_active=True)
        _apply_role_and_scalar_changes(
            db, user,
            current_roles=["student"], target_staff=None,
            full_name=None, phone=None, is_active=False,
            legal_basis_confirmed=None, basis_type=None, basis_reference=None,
            legal_basis_comment=None, confirmed_by_user_id=None,
            actor_id=ACTOR_ID, actor_role="admin", ip=None, user_agent=None,
        )
    events = {c["event"] for c in calls}
    assert "admin_user_updated" not in events
    assert events == {"admin_user_deactivated"}


def test_scalar_and_is_active_stage_two_disjoint_events():
    calls = []
    with patch.object(users_storage, "record_event", lambda **kw: calls.append(kw)):
        db = MagicMock(name="db")
        user = SimpleNamespace(id=TARGET_ID, full_name="Old", phone=None, is_active=True)
        _apply_role_and_scalar_changes(
            db, user,
            current_roles=["student"], target_staff=None,
            full_name="New Name", phone=None, is_active=False,
            legal_basis_confirmed=None, basis_type=None, basis_reference=None,
            legal_basis_comment=None, confirmed_by_user_id=None,
            actor_id=ACTOR_ID, actor_role="admin", ip=None, user_agent=None,
        )
    assert user.full_name == "New Name" and user.is_active is False
    events = [c["event"] for c in calls]
    assert sorted(events) == ["admin_user_deactivated", "admin_user_updated"]
    # admin_user_updated — только scalar; is_active в его metadata не участвует.
    upd = next(c for c in calls if c["event"] == "admin_user_updated")
    assert upd["metadata"] == {}


def test_role_and_is_active_both_in_one_caller_session():
    calls = []
    sentinel_ctx = SimpleNamespace(ip_address=None, user_agent=None)
    with patch.object(users_storage, "record_event", lambda **kw: calls.append(kw)), \
         patch.object(users_storage, "build_request_context", lambda **kw: sentinel_ctx):
        role_obj = SimpleNamespace(id=55, name="supervisor")
        db = _role_lookup_db([role_obj])
        user = SimpleNamespace(id=TARGET_ID, full_name="X", phone=None, is_active=True)
        _apply_role_and_scalar_changes(
            db, user,
            current_roles=["psychologist"],
            target_staff={"psychologist", "supervisor"},   # added supervisor
            full_name=None, phone=None, is_active=False,     # + deactivate
            legal_basis_confirmed=True, basis_type="service_duty",
            basis_reference="Order #1", legal_basis_comment=None,
            confirmed_by_user_id=ACTOR_ID,
            actor_id=ACTOR_ID, actor_role="admin", ip=None, user_agent=None,
        )
    events = {c["event"] for c in calls}
    assert events == {"admin_role_add", "admin_user_deactivated"}
    assert "admin_user_updated" not in events   # full_name/phone не менялись
    for c in calls:
        assert c["target"].entity_id == TARGET_ID


def test_lifecycle_audit_failure_propagates_not_swallowed():
    def _boom(**kw):
        raise AuditStorageError("audit storage failure for admin_user_deactivated")
    with patch.object(users_storage, "record_event", _boom):
        db = MagicMock(name="db")
        user = SimpleNamespace(id=TARGET_ID, full_name="X", phone=None, is_active=True)
        with pytest.raises(AuditStorageError):
            _apply_role_and_scalar_changes(
                db, user,
                current_roles=["student"], target_staff=None,
                full_name=None, phone=None, is_active=False,
                legal_basis_confirmed=None, basis_type=None, basis_reference=None,
                legal_basis_comment=None, confirmed_by_user_id=None,
                actor_id=ACTOR_ID, actor_role="admin", ip=None, user_agent=None,
            )


# ══════════════════════════════════════════════════════════════════════════
# auth.storage.update_profile_atomic — profile_updated
# ══════════════════════════════════════════════════════════════════════════

def _profile_db(user):
    db = MagicMock(name="db")
    db.query.return_value.filter.return_value.first.return_value = user
    return db


def test_profile_missing_actor_role_fails_closed_before_session(monkeypatch):
    def _boom(*a, **kw):
        raise AssertionError("SessionLocal must not be opened before actor guard")
    monkeypatch.setattr(auth_storage, "SessionLocal", _boom)

    with pytest.raises(RuntimeError):
        update_profile_atomic("1", {"full_name": "New"}, actor_role=None)


def test_profile_self_actor_equals_target_and_exact_changed_fields(monkeypatch):
    calls = []
    monkeypatch.setattr(auth_storage, "record_event", lambda **kw: calls.append(kw))

    user = SimpleNamespace(
        id=TARGET_ID, full_name="Old Name", phone="+70000000000",
        ui_theme_palette="classic", ui_theme_mode="light", updated_at=None,
    )
    db = _profile_db(user)
    with patch.object(auth_storage, "SessionLocal", _mock_session(db)), \
         patch.object(auth_storage, "_profile_to_dict", lambda u, d: {"id": u.id}):
        update_profile_atomic(
            str(TARGET_ID),
            {"full_name": "New Name", "phone": "+70000000000"},  # phone same
            actor_role="student", ip=None, user_agent=None,
        )

    assert user.full_name == "New Name"      # только full_name реально изменился
    assert user.updated_at is not None
    assert len(calls) == 1
    kw = calls[0]
    assert kw["event"] == "profile_updated"
    assert kw["actor"].user_id == TARGET_ID
    assert kw["actor"].role == "student"
    assert kw["target"].entity_id == TARGET_ID   # self-action: actor == target
    assert kw["metadata"] == {"fields": ["full_name"]}   # phone не включён (no-op)
    # Значения ФИО/телефона нигде не попадают в kwargs record_event.
    assert "New Name" not in repr(kw)
    assert "+70000000000" not in repr(kw)


def test_profile_theme_only_real_change_mutates_but_no_audit(monkeypatch):
    calls = []
    monkeypatch.setattr(auth_storage, "record_event", lambda **kw: calls.append(kw))

    user = SimpleNamespace(
        id=TARGET_ID, full_name="Old Name", phone=None,
        ui_theme_palette="classic", ui_theme_mode="light", updated_at=None,
    )
    db = _profile_db(user)
    with patch.object(auth_storage, "SessionLocal", _mock_session(db)), \
         patch.object(auth_storage, "_profile_to_dict", lambda u, d: {"id": u.id}):
        update_profile_atomic(
            str(TARGET_ID), {"ui_theme_palette": "nature"},
            actor_role="student",
        )

    assert user.ui_theme_palette == "nature"   # тема сохраняется
    assert user.updated_at is not None          # updated_at бампается
    assert calls == []                          # но profile_updated не пишется


def test_profile_empty_patch_true_no_op(monkeypatch):
    calls = []
    monkeypatch.setattr(auth_storage, "record_event", lambda **kw: calls.append(kw))

    user = SimpleNamespace(
        id=TARGET_ID, full_name="Old Name", phone=None,
        ui_theme_palette="classic", ui_theme_mode="light", updated_at=None,
    )
    db = _profile_db(user)
    with patch.object(auth_storage, "SessionLocal", _mock_session(db)), \
         patch.object(auth_storage, "_profile_to_dict", lambda u, d: {"id": u.id}):
        update_profile_atomic(str(TARGET_ID), {}, actor_role="student")

    assert user.full_name == "Old Name"
    assert user.updated_at is None    # НЕ бампается на true no-op (Stage 4B-4)
    assert calls == []


def test_profile_identical_values_patch_true_no_op(monkeypatch):
    calls = []
    monkeypatch.setattr(auth_storage, "record_event", lambda **kw: calls.append(kw))

    user = SimpleNamespace(
        id=TARGET_ID, full_name="Old Name", phone=None,
        ui_theme_palette="classic", ui_theme_mode="light", updated_at=None,
    )
    db = _profile_db(user)
    with patch.object(auth_storage, "SessionLocal", _mock_session(db)), \
         patch.object(auth_storage, "_profile_to_dict", lambda u, d: {"id": u.id}):
        update_profile_atomic(
            str(TARGET_ID), {"full_name": "Old Name"}, actor_role="student",
        )

    assert user.updated_at is None
    assert calls == []


def test_profile_audit_failure_propagates_not_swallowed(monkeypatch):
    def _boom(**kw):
        raise AuditStorageError("audit storage failure for profile_updated")
    monkeypatch.setattr(auth_storage, "record_event", _boom)

    user = SimpleNamespace(
        id=TARGET_ID, full_name="Old Name", phone=None,
        ui_theme_palette="classic", ui_theme_mode="light", updated_at=None,
    )
    db = _profile_db(user)
    with patch.object(auth_storage, "SessionLocal", _mock_session(db)), \
         patch.object(auth_storage, "_profile_to_dict", lambda u, d: {"id": u.id}):
        with pytest.raises(AuditStorageError):
            update_profile_atomic(
                str(TARGET_ID), {"full_name": "New Name"}, actor_role="student",
            )
    db.commit.assert_not_called()


def test_profile_not_found_raises_user_not_found_error():
    db = _profile_db(None)
    with patch.object(auth_storage, "SessionLocal", _mock_session(db)):
        with pytest.raises(UserNotFoundError):
            update_profile_atomic(
                str(TARGET_ID), {"full_name": "New Name"}, actor_role="student",
            )


# ══════════════════════════════════════════════════════════════════════════
# Static: no legacy log_auth_event / dynamic event strings left in scope
# ══════════════════════════════════════════════════════════════════════════

def test_routes_admin_no_log_auth_event():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "app" / "users" / "routes_admin.py"
           ).read_text(encoding="utf-8")
    assert "log_auth_event(" not in src
    assert "from app.auth import audit" not in src
    assert "admin_create_user:" not in src
    assert "admin_update_user:" not in src
    assert "admin_delete_user:" not in src


def test_auth_routes_no_log_auth_event_at_all():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "app" / "auth" / "routes.py"
           ).read_text(encoding="utf-8")
    assert "log_auth_event(" not in src
    assert 'event="profile_update"' not in src


def test_welcome_email_diagnostic_minimized(monkeypatch, caplog):
    import logging
    from app.users import service as users_service

    def _boom_email(**kw):
        raise RuntimeError("SMTP rejected recipient user@secret.example.com")
    monkeypatch.setattr(users_service, "send_welcome_staff", _boom_email)
    monkeypatch.setattr(
        users_service.storage, "create_user",
        lambda **kw: {
            "id": TARGET_ID, "uuid": "u", "email": "user@secret.example.com",
            "full_name": "Test", "roles": ["psychologist"], "role": "psychologist",
            "is_active": True, "created_at": None,
        },
    )
    monkeypatch.setattr(
        "app.chat.system_publisher.publish_system_message", lambda **kw: None,
    )

    with caplog.at_level(logging.WARNING):
        from app.users.schemas import AdminUserCreate
        data = AdminUserCreate(
            email="user@secret.example.com", full_name="Test",
            role="psychologist", basis_type="service_duty",
            basis_reference="Order #1", legal_basis_confirmed=True,
        )
        users_service.create_user(data, actor_id=ACTOR_ID, actor_role="admin")

    text = caplog.text
    assert "user@secret.example.com" not in text
    assert "SMTP rejected recipient" not in text
    assert "phase=welcome_email" in text
    assert "RuntimeError" in text
