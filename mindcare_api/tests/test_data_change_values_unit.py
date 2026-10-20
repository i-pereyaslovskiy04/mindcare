"""
Stage 6-0 — семантика ChangeValue и симметрия old_values/new_values.

Ключевые инварианты:
  - old и new проверяются ОДНОЙ и той же ChangeFieldSpec;
  - old_values и new_values всегда имеют ОДИНАКОВЫЙ набор ключей;
  - old == new запрещено (в т.ч. как детектор snapshot'а после мутации ORM);
  - name-only поле не может нести значение — защита ПДн;
  - отсутствие values → обе колонки NULL, а не {}.
"""
import pytest

from app.audit.contracts import Actor
from app.audit.change_contracts import (
    ChangeValue, DataChangeError, Operation,
)
from app.audit.data_change import record_data_change


class _FakeSession:
    def __init__(self):
        self.added = []

    def add(self, row):
        self.added.append(row)


_SUP = Actor.user(3, "supervisor")
_ADMIN = Actor.user(7, "admin")


def _gs(changed_fields, values=None, db=None):
    return record_data_change(
        table="group_sessions", record_id=11, operation=Operation.UPDATE,
        actor=_SUP, changed_fields=changed_fields, values=values,
        db=db if db is not None else _FakeSession(),
    )


def _mt(changed_fields, values=None, db=None):
    return record_data_change(
        table="meeting_types", record_id=5, operation=Operation.UPDATE,
        actor=_SUP, changed_fields=changed_fields, values=values,
        db=db if db is not None else _FakeSession(),
    )


# ── Отсутствие значений ──────────────────────────────────────────────────────

def test_no_values_writes_null_columns_not_empty_dicts():
    db = _FakeSession()
    _gs(["title"], db=db)
    row = db.added[0]
    assert row.old_values is None
    assert row.new_values is None
    assert row.changed_fields == ["title"]


def test_empty_values_mapping_is_treated_as_absence():
    db = _FakeSession()
    _gs(["title"], values={}, db=db)
    assert db.added[0].old_values is None
    assert db.added[0].new_values is None


# ── Симметрия ключей ─────────────────────────────────────────────────────────

def test_old_and_new_values_always_share_the_same_key_set():
    db = _FakeSession()
    _gs(
        ["capacity", "format", "title"],
        values={
            "capacity": ChangeValue(old=10, new=20),
            "format": ChangeValue(old="online", new="in_person"),
        },
        db=db,
    )
    row = db.added[0]
    assert set(row.old_values) == set(row.new_values) == {"capacity", "format"}
    assert row.old_values == {"capacity": 10, "format": "online"}
    assert row.new_values == {"capacity": 20, "format": "in_person"}
    # name-only поле присутствует в changed_fields, но не в значениях
    assert row.changed_fields == ["capacity", "format", "title"]
    assert "title" not in row.old_values


def test_partial_values_subset_is_allowed_but_stays_symmetric():
    db = _FakeSession()
    _gs(["capacity", "format"],
        values={"capacity": ChangeValue(old=1, new=2)}, db=db)
    row = db.added[0]
    assert set(row.old_values) == set(row.new_values) == {"capacity"}


# ── old != new / snapshot ordering ───────────────────────────────────────────

def test_identical_old_and_new_is_rejected():
    with pytest.raises(DataChangeError, match="must differ"):
        _gs(["capacity"], values={"capacity": ChangeValue(old=5, new=5)})


def test_snapshot_taken_after_mutation_is_detected():
    """Симуляция бага: snapshot снят ПОСЛЕ setattr, поэтому old == new."""
    class _Obj:
        capacity = 10

    obj = _Obj()
    obj.capacity = 25                 # мутация
    old_snapshot = obj.capacity       # ошибка: snapshot после мутации
    with pytest.raises(DataChangeError, match="must differ"):
        _gs(["capacity"],
            values={"capacity": ChangeValue(old=old_snapshot, new=obj.capacity)})


def test_correct_snapshot_order_is_accepted():
    class _Obj:
        capacity = 10

    obj = _Obj()
    old_snapshot = obj.capacity       # snapshot ДО мутации
    obj.capacity = 25
    db = _FakeSession()
    _gs(["capacity"],
        values={"capacity": ChangeValue(old=old_snapshot, new=obj.capacity)},
        db=db)
    assert db.added[0].old_values == {"capacity": 10}
    assert db.added[0].new_values == {"capacity": 25}


# ── name-only защита ПДн ─────────────────────────────────────────────────────

def test_name_only_field_must_not_carry_values():
    with pytest.raises(DataChangeError, match="name-only"):
        record_data_change(
            table="users", record_id=1, operation=Operation.UPDATE,
            actor=_ADMIN, changed_fields=["full_name"],
            values={"full_name": ChangeValue(old="Иванов", new="Петров")},
            db=_FakeSession(),
        )


def test_name_only_rejection_happens_before_db_add():
    db = _FakeSession()
    with pytest.raises(DataChangeError):
        record_data_change(
            table="unregistered_student_cards", record_id=1,
            operation=Operation.UPDATE, actor=_SUP,
            changed_fields=["email"],
            values={"email": ChangeValue(old="a@x.ru", new="b@x.ru")},
            db=db,
        )
    assert db.added == []


def test_every_pii_field_is_name_only_in_practice():
    for table, field in (
        ("users", "full_name"), ("users", "phone"),
        ("unregistered_student_cards", "full_name"),
        ("unregistered_student_cards", "phone"),
        ("unregistered_student_cards", "email"),
        ("unregistered_student_cards", "birth_date"),
        ("unregistered_student_cards", "comment"),
        ("unregistered_student_cards", "primary_concern"),
        ("group_sessions", "psychologist_id"),
    ):
        actor = _ADMIN if table == "users" else _SUP
        with pytest.raises(DataChangeError, match="name-only"):
            record_data_change(
                table=table, record_id=1, operation=Operation.UPDATE,
                actor=actor, changed_fields=[field],
                values={field: ChangeValue(old="x", new="y")},
                db=_FakeSession(),
            )


# ── Ключи values ─────────────────────────────────────────────────────────────

def test_value_key_must_be_in_changed_fields():
    with pytest.raises(DataChangeError, match="not present in changed_fields"):
        _gs(["title"], values={"capacity": ChangeValue(old=1, new=2)})


def test_value_key_must_be_known_field():
    with pytest.raises(DataChangeError, match="unknown field"):
        _gs(["capacity", "status"], values={"capacity": ChangeValue(1, 2)})


# ── Типы значений по политике ────────────────────────────────────────────────

def test_bool_policy_accepts_only_bool():
    db = _FakeSession()
    _mt(["is_group"], values={"is_group": ChangeValue(old=False, new=True)},
        db=db)
    assert db.added[0].old_values == {"is_group": False}
    for bad in (0, 1, "true", None):
        with pytest.raises(DataChangeError):
            _mt(["is_group"], values={"is_group": ChangeValue(old=bad, new=True)})


def test_int_policy_rejects_bool_and_non_int():
    for bad in (True, False, "10", 10.0):
        with pytest.raises(DataChangeError):
            _gs(["capacity"], values={"capacity": ChangeValue(old=bad, new=20)})


def test_enum_policy_rejects_unknown_value_and_non_string():
    with pytest.raises(DataChangeError, match="not in allowed enum"):
        _gs(["format"], values={"format": ChangeValue(old="online",
                                                      new="hybrid")})
    with pytest.raises(DataChangeError, match="expected string"):
        _gs(["format"], values={"format": ChangeValue(old=1, new="online")})


def test_enum_policy_validates_old_with_the_same_spec_as_new():
    """old проверяется той же спецификацией — некорректный old тоже отвергается."""
    with pytest.raises(DataChangeError, match="not in allowed enum"):
        _gs(["format"], values={"format": ChangeValue(old="offline",
                                                      new="online")})


# ── nullable ─────────────────────────────────────────────────────────────────

def test_null_is_rejected_when_field_is_not_nullable():
    with pytest.raises(DataChangeError, match="null not allowed"):
        _gs(["capacity"], values={"capacity": ChangeValue(old=None, new=5)})
    with pytest.raises(DataChangeError, match="null not allowed"):
        _gs(["capacity"], values={"capacity": ChangeValue(old=5, new=None)})


def test_all_stage6_value_fields_are_non_nullable():
    """В Stage 6 ни одно value-enabled поле не объявлено nullable, поэтому
    ветка «оба None» недостижима через production registry — инвариант
    фиксируется явно, чтобы его снятие потребовало осознанного решения."""
    from app.audit.change_registry import CHANGE_REGISTRY
    from app.audit.change_contracts import ValuePolicy

    for spec in CHANGE_REGISTRY.values():
        for fs in spec.fields.values():
            if fs.policy is not ValuePolicy.NAME_ONLY:
                assert fs.nullable is False
