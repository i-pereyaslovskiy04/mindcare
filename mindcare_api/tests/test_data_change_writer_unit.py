"""
Stage 6-0 — writer record_data_change: actor, маппинг строки, ATOMIC-контракт,
fail-closed поведение и безопасность диагностики.

Сессия здесь фейковая: тест проверяет, что writer делает ТОЛЬКО db.add и не
трогает commit/rollback/close, а также что при сбое add ничего не утекает
в stderr.
"""
import pytest

from app.audit.contracts import (
    SYSTEM_ROLE, Actor, RequestContext, WriteState,
)
from app.audit.change_contracts import (
    ChangeValue, DataChangeError, DataChangeStorageError, Operation,
)
from app.audit.data_change import project_changed_fields, record_data_change


class _FakeSession:
    """Фиксирует add и любые попытки управления транзакцией."""

    def __init__(self, fail_on_add=None):
        self.added = []
        self.fail_on_add = fail_on_add
        self.tx_calls = []

    def add(self, row):
        if self.fail_on_add is not None:
            raise self.fail_on_add
        self.added.append(row)

    def commit(self):
        self.tx_calls.append("commit")

    def rollback(self):
        self.tx_calls.append("rollback")

    def close(self):
        self.tx_calls.append("close")

    def flush(self):
        self.tx_calls.append("flush")


_ADMIN = Actor.user(7, "admin")
_SUP = Actor.user(3, "supervisor")


def _users(db, **over):
    kwargs = dict(
        table="users", record_id=42, operation=Operation.UPDATE, actor=_ADMIN,
        changed_fields=["full_name", "phone"], db=db,
    )
    kwargs.update(over)
    return record_data_change(**kwargs)


# ── Успешный путь и маппинг строки ───────────────────────────────────────────

def test_row_is_staged_and_result_is_staged():
    db = _FakeSession()
    result = _users(db)
    assert result.state is WriteState.STAGED
    assert result.table == "users"
    assert len(db.added) == 1


def test_writer_never_manages_the_transaction():
    """ATOMIC-контракт: только db.add, коммитит владелец транзакции."""
    db = _FakeSession()
    _users(db)
    assert db.tx_calls == []


def test_row_columns_are_mapped_exactly():
    db = _FakeSession()
    _users(db, context=RequestContext(ip_address="192.168.1.10"))
    row = db.added[0]
    assert row.actor_id == 7
    assert row.actor_role == "admin"
    assert row.table_name == "users"
    assert row.record_id == 42
    assert row.operation == "UPDATE"
    assert row.changed_fields == ["full_name", "phone"]
    assert row.old_values is None
    assert row.new_values is None
    assert row.ip_address == "192.168.1.10"


def test_operation_is_stored_as_uppercase_string():
    db = _FakeSession()
    _users(db)
    assert db.added[0].operation == "UPDATE"
    assert db.added[0].operation == Operation.UPDATE.value


# ── Actor ────────────────────────────────────────────────────────────────────

def test_actor_role_must_be_permitted_for_table():
    for role in ("supervisor", "psychologist", "student"):
        with pytest.raises(DataChangeError, match="not permitted"):
            _users(_FakeSession(), actor=Actor.user(1, role))


def test_supervisor_and_admin_both_allowed_for_cards():
    for actor in (_SUP, _ADMIN):
        db = _FakeSession()
        record_data_change(
            table="unregistered_student_cards", record_id=5,
            operation=Operation.UPDATE, actor=actor,
            changed_fields=["full_name"], db=db,
        )
        assert db.added[0].actor_role == actor.role


def test_anonymous_actor_is_rejected():
    with pytest.raises(DataChangeError, match="authenticated user actor"):
        _users(_FakeSession(), actor=Actor.anonymous())


def test_system_actor_is_rejected_for_user_required_table():
    with pytest.raises(DataChangeError, match="authenticated user actor"):
        _users(_FakeSession(), actor=Actor.system())


def test_actor_must_be_actor_instance():
    for bad in ({"user_id": 1, "role": "admin"}, None, 7):
        with pytest.raises(DataChangeError, match="must be an Actor"):
            _users(_FakeSession(), actor=bad)


def test_actor_user_id_must_be_positive_int_and_reject_bool():
    for bad in (0, -1, True, "7", None):
        with pytest.raises(DataChangeError, match="user_id"):
            _users(_FakeSession(), actor=Actor(kind="user", user_id=bad,
                                               role="admin"))


def test_actor_role_is_always_required_unlike_auth_log():
    """В auth_log роль не хранится и допускается None (ADR-018); в DCL
    actor_role записывается, поэтому исключения нет."""
    with pytest.raises(DataChangeError, match="not a valid user role"):
        _users(_FakeSession(), actor=Actor(kind="user", user_id=7, role=None))


def test_unknown_role_is_rejected():
    with pytest.raises(DataChangeError, match="not a valid user role"):
        _users(_FakeSession(), actor=Actor(kind="user", user_id=7,
                                           role="superuser"))


def test_system_role_constant_is_reused():
    """Регресс-защита: если появится SYSTEM-таблица, роль пишется как 'system'."""
    assert SYSTEM_ROLE == "system"


# ── Значения ─────────────────────────────────────────────────────────────────

def test_values_are_written_for_value_enabled_fields():
    db = _FakeSession()
    record_data_change(
        table="meeting_types", record_id=5, operation=Operation.UPDATE,
        actor=_SUP, changed_fields=["duration_minutes", "name"],
        values={"duration_minutes": ChangeValue(old=50, new=60)}, db=db,
    )
    row = db.added[0]
    assert row.changed_fields == ["duration_minutes", "name"]
    assert row.old_values == {"duration_minutes": 50}
    assert row.new_values == {"duration_minutes": 60}


# ── fail-closed ──────────────────────────────────────────────────────────────

def test_storage_failure_raises_sanitized_error(capsys):
    secret = "Иванов Иван /db/url password=hunter2"
    db = _FakeSession(fail_on_add=RuntimeError(secret))
    with pytest.raises(DataChangeStorageError) as excinfo:
        _users(db)

    message = str(excinfo.value)
    assert "data change storage failure for users" == message
    assert secret not in message
    assert "hunter2" not in message

    captured = capsys.readouterr()
    assert "table=users phase=add error=RuntimeError" in captured.err
    assert secret not in captured.err
    assert "hunter2" not in captured.err


def test_storage_failure_does_not_chain_original_exception():
    db = _FakeSession(fail_on_add=RuntimeError("raw text"))
    with pytest.raises(DataChangeStorageError) as excinfo:
        _users(db)
    # `raise ... from None` — исходное исключение не тянется в traceback.
    assert excinfo.value.__cause__ is None


def test_storage_error_is_a_data_change_error():
    assert issubclass(DataChangeStorageError, DataChangeError)


def test_no_soft_mode_exists():
    """У этого журнала нет fail-open режима: любой сбой всегда бросает."""
    db = _FakeSession(fail_on_add=ValueError("x"))
    with pytest.raises(DataChangeStorageError):
        _users(db)
    assert db.added == []


def test_contract_violations_never_reach_db_add():
    for over in (
        {"table": "session_notes"},
        {"record_id": 0},
        {"operation": Operation.DELETE},
        {"changed_fields": []},
        {"changed_fields": ["is_active"]},
        {"actor": Actor.anonymous()},
    ):
        db = _FakeSession()
        with pytest.raises(DataChangeError):
            _users(db, **over)
        assert db.added == []
        assert db.tx_calls == []


# ── project_changed_fields: карточка ─────────────────────────────────────────

def test_card_email_change_projects_to_email_only():
    """service добавляет normalized_email в дифф; журнал его не видит."""
    projected = project_changed_fields(
        "unregistered_student_cards", {"email", "normalized_email"},
    )
    assert projected == ["email"]

    db = _FakeSession()
    record_data_change(
        table="unregistered_student_cards", record_id=9,
        operation=Operation.UPDATE, actor=_SUP, changed_fields=projected, db=db,
    )
    row = db.added[0]
    assert row.changed_fields == ["email"]
    assert "normalized_email" not in row.changed_fields
    assert row.old_values is None and row.new_values is None


def test_derived_field_alone_projects_to_empty_list():
    assert project_changed_fields(
        "unregistered_student_cards", ["normalized_email"],
    ) == []


def test_projection_is_sorted_and_deduplicated():
    assert project_changed_fields(
        "unregistered_student_cards",
        ["phone", "email", "normalized_email", "birth_date"],
    ) == ["birth_date", "email", "phone"]


def test_combined_generic_and_transition_diff_keeps_only_generic():
    """Combined PATCH: transition-поля отсутствуют в allowlist, поэтому caller
    обязан передавать только generic-дифф — иначе fail closed."""
    assert project_changed_fields("group_sessions", ["capacity"]) == ["capacity"]
    with pytest.raises(DataChangeError, match="unknown field"):
        project_changed_fields("group_sessions", ["capacity", "status"])
    with pytest.raises(DataChangeError, match="unknown field"):
        project_changed_fields("meeting_types", ["name", "is_active"])


# ── Corrective pass: actor.role runtime type hardening ───────────────────────
#
# isinstance(role, str) обязана идти ПЕРВОЙ, до `role in USER_ROLES`: list/dict
# как role иначе роняют membership-проверку необработанным TypeError
# (unhashable type), а не DataChangeError. bool/int/float — hashable, но всё
# равно не валидные роли и обязаны давать тот же фиксированный DataChangeError.

@pytest.mark.parametrize("bad_role", [
    ["admin"],              # list — unhashable, без isinstance(str) уронил бы TypeError
    {"admin"},               # set — unhashable
    {"role": "admin"},       # dict — unhashable
    5,                        # int — hashable, но не valid role
    5.0,                      # float — hashable
    True,                     # bool — hashable, не str
    b"admin",                 # bytes — не str
    object(),                 # произвольный unhashable-по-умолчанию объект
])
def test_actor_role_bad_types_raise_data_change_error_not_type_error(bad_role):
    db = _FakeSession()
    with pytest.raises(DataChangeError, match="not a valid user role"):
        _users(db, actor=Actor(kind="user", user_id=7, role=bad_role))
    assert db.added == []
    assert db.tx_calls == []


def test_actor_role_bad_types_do_not_leak_repr_in_message():
    db = _FakeSession()
    with pytest.raises(DataChangeError) as excinfo:
        _users(db, actor=Actor(kind="user", user_id=7, role=["admin", "secret"]))
    assert "secret" not in str(excinfo.value)
    assert "admin" not in str(excinfo.value)


def test_actor_role_empty_string_is_rejected():
    with pytest.raises(DataChangeError, match="not a valid user role"):
        _users(_FakeSession(), actor=Actor(kind="user", user_id=7, role=""))


def test_actor_role_valid_string_still_works_after_hardening():
    """Регресс: усиление типовой проверки не ломает штатный путь."""
    db = _FakeSession()
    _users(db, actor=Actor(kind="user", user_id=7, role="admin"))
    assert db.added[0].actor_role == "admin"


# ── Corrective pass: project_changed_fields non-iterable input ───────────────

@pytest.mark.parametrize("bad_input", [None, 5, 5.0, True, object()])
def test_project_changed_fields_rejects_non_iterable(bad_input):
    with pytest.raises(DataChangeError, match="must be an iterable"):
        project_changed_fields("users", bad_input)


def test_project_changed_fields_non_iterable_error_has_fixed_message():
    with pytest.raises(DataChangeError) as excinfo:
        project_changed_fields("users", 42)
    assert str(excinfo.value) == "changed_keys must be an iterable of field names"


def test_project_changed_fields_does_not_swallow_errors_from_user_iterable():
    """Требуется проверять только ТИП входа — ошибка, возникшая ВНУТРИ
    пользовательского iterable (например генератора), обязана пробрасываться
    как есть, а не подменяться DataChangeError."""
    def _broken():
        yield "full_name"
        raise RuntimeError("boom from caller's generator")

    with pytest.raises(RuntimeError, match="boom from caller's generator"):
        project_changed_fields("users", _broken())


def test_record_data_change_rejects_non_iterable_changed_fields_before_db_add():
    """changed_fields в record_data_change сам по себе type-strict к list/tuple
    (Stage 6-0 исходно), поэтому None/int там уже отражены — regression guard,
    что это поведение не задето corrective pass'ом."""
    db = _FakeSession()
    with pytest.raises(DataChangeError):
        _users(db, changed_fields=None)
    assert db.added == []
    db2 = _FakeSession()
    with pytest.raises(DataChangeError):
        _users(db2, changed_fields=5)
    assert db2.added == []
