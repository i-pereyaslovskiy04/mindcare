"""
Stage 6-0 — type-strict контракт record_data_change / project_changed_fields.

Центральный кейс: строка формально является Sequence[str] и молча развалилась бы
на отдельные символы ("email" -> ['e','m','a','i','l']). Такой вход обязан
отвергаться ДО любой итерации и ДО db.add.
"""
import pytest

from app.audit.contracts import Actor
from app.audit.change_contracts import (
    ChangeValue, DataChangeError, Operation,
)
from app.audit.data_change import project_changed_fields, record_data_change


class _FakeSession:
    """Минимальная сессия: фиксирует db.add и ничего не коммитит."""

    def __init__(self):
        self.added = []

    def add(self, row):
        self.added.append(row)


_ADMIN = Actor.user(7, "admin")


def _call(**over):
    kwargs = dict(
        table="users",
        record_id=42,
        operation=Operation.UPDATE,
        actor=_ADMIN,
        changed_fields=["full_name"],
        db=_FakeSession(),
    )
    kwargs.update(over)
    return record_data_change(**kwargs)


# ── changed_fields: строка недопустима ───────────────────────────────────────

def test_changed_fields_rejects_plain_string():
    db = _FakeSession()
    with pytest.raises(DataChangeError, match="not a string"):
        _call(changed_fields="full_name", db=db)
    assert db.added == []          # ни одной строки не застейджено


def test_changed_fields_rejects_single_char_field_name_as_string():
    """Даже строка, состоящая из одного допустимого символа, не Sequence имён."""
    db = _FakeSession()
    with pytest.raises(DataChangeError):
        _call(changed_fields="a", db=db)
    assert db.added == []


def test_changed_fields_rejects_bytes_and_bytearray():
    for bad in (b"full_name", bytearray(b"full_name")):
        with pytest.raises(DataChangeError):
            _call(changed_fields=bad)


def test_changed_fields_rejects_set_dict_and_generator():
    for bad in ({"full_name"}, {"full_name": 1}, (n for n in ["full_name"])):
        with pytest.raises(DataChangeError, match="list or tuple"):
            _call(changed_fields=bad)


def test_changed_fields_accepts_list_and_tuple():
    for good in (["full_name"], ("full_name",)):
        db = _FakeSession()
        _call(changed_fields=good, db=db)
        assert len(db.added) == 1
        assert db.added[0].changed_fields == ["full_name"]


def test_changed_fields_rejects_non_string_members():
    with pytest.raises(DataChangeError, match="must be strings"):
        _call(changed_fields=["full_name", 5])


def test_changed_fields_rejects_empty_and_duplicates():
    with pytest.raises(DataChangeError, match="must not be empty"):
        _call(changed_fields=[])
    with pytest.raises(DataChangeError, match="duplicates"):
        _call(changed_fields=["full_name", "full_name"])


def test_changed_fields_rejects_unknown_field():
    with pytest.raises(DataChangeError, match="unknown field"):
        _call(changed_fields=["is_active"])


def test_changed_fields_is_sorted_deterministically():
    db = _FakeSession()
    _call(changed_fields=["phone", "full_name"], db=db)
    assert db.added[0].changed_fields == ["full_name", "phone"]


# ── values: только Mapping ───────────────────────────────────────────────────

def test_values_must_be_mapping():
    for bad in ([("capacity", ChangeValue(1, 2))], "capacity", 5):
        with pytest.raises(DataChangeError, match="values must be a mapping"):
            record_data_change(
                table="group_sessions", record_id=1,
                operation=Operation.UPDATE,
                actor=Actor.user(1, "supervisor"),
                changed_fields=["capacity"], values=bad, db=_FakeSession(),
            )


def test_values_entries_must_be_change_value():
    with pytest.raises(DataChangeError, match="ChangeValue"):
        record_data_change(
            table="group_sessions", record_id=1, operation=Operation.UPDATE,
            actor=Actor.user(1, "supervisor"), changed_fields=["capacity"],
            values={"capacity": (1, 2)}, db=_FakeSession(),
        )


def test_values_keys_must_be_strings():
    with pytest.raises(DataChangeError, match="value keys must be strings"):
        record_data_change(
            table="group_sessions", record_id=1, operation=Operation.UPDATE,
            actor=Actor.user(1, "supervisor"), changed_fields=["capacity"],
            values={5: ChangeValue(1, 2)}, db=_FakeSession(),
        )


# ── operation / record_id ────────────────────────────────────────────────────

def test_operation_must_be_enum_member():
    for bad in ("UPDATE", 1, None):
        with pytest.raises(DataChangeError, match="operation must be"):
            _call(operation=bad)


def test_operation_must_be_permitted_for_table():
    for op in (Operation.INSERT, Operation.DELETE):
        with pytest.raises(DataChangeError, match="not permitted"):
            _call(operation=op)


def test_record_id_must_be_positive_int_and_reject_bool():
    for bad in (0, -1, "42", 4.0, None, True):
        with pytest.raises(DataChangeError, match="record_id"):
            _call(record_id=bad)


def test_table_must_be_known_and_string():
    with pytest.raises(DataChangeError, match="unknown data-change table"):
        _call(table="session_notes")
    with pytest.raises(DataChangeError, match="table must be a string"):
        _call(table=None)


def test_db_is_required():
    with pytest.raises(DataChangeError, match="requires a caller db session"):
        _call(db=None)


# ── project_changed_fields ───────────────────────────────────────────────────

def test_project_rejects_string_input():
    with pytest.raises(DataChangeError, match="not a string"):
        project_changed_fields("users", "full_name")


def test_project_rejects_non_string_members_and_unknown_keys():
    with pytest.raises(DataChangeError, match="must be strings"):
        project_changed_fields("users", [1])
    with pytest.raises(DataChangeError, match="unknown field"):
        project_changed_fields("users", ["is_active"])


def test_project_accepts_any_non_string_iterable():
    assert project_changed_fields("users", {"phone", "full_name"}) == [
        "full_name", "phone",
    ]
    assert project_changed_fields("users", ["phone"]) == ["phone"]
    assert project_changed_fields(
        "users", {"phone": 1, "full_name": 2}.keys(),
    ) == ["full_name", "phone"]
