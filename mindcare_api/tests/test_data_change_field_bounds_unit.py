"""
Stage 6-0 — границы value-enabled INT-полей.

Правило: journal НЕ вводит новых бизнес-лимитов. ChangeValue.old читается ИЗ БД,
а не из запроса, поэтому диапазон обязан покрывать любое уже существующее
значение — иначе штатный PATCH откатывался бы из-за записи в журнал.

Отдельная регрессия сверяет min_value/max_value registry с ge/le реальных
Pydantic Create/Update-схем: изменение схемы без правки registry роняет тест.
"""
import pytest

from app.appointments.schemas import (
    GroupSessionCreate, GroupSessionUpdate, MeetingTypeCreate, MeetingTypeUpdate,
)
from app.audit.contracts import Actor
from app.audit.change_contracts import (
    PG_INT32_MAX, PG_INT32_MIN, ChangeValue, DataChangeError, Operation,
    ValuePolicy,
)
from app.audit.change_registry import CHANGE_REGISTRY
from app.audit.data_change import record_data_change


class _FakeSession:
    def __init__(self):
        self.added = []

    def add(self, row):
        self.added.append(row)


_SUP = Actor.user(3, "supervisor")

_TABLE_OF = {
    "duration_minutes": "meeting_types",
    "buffer_minutes": "meeting_types",
    "display_order": "meeting_types",
    "capacity": "group_sessions",
    "meeting_type_id": "group_sessions",
}


def _write(field, old, new, db=None):
    table = _TABLE_OF[field]
    return record_data_change(
        table=table, record_id=1, operation=Operation.UPDATE, actor=_SUP,
        changed_fields=[field], values={field: ChangeValue(old=old, new=new)},
        db=db if db is not None else _FakeSession(),
    )


# ── Заявленные диапазоны ─────────────────────────────────────────────────────

_EXPECTED_BOUNDS = {
    ("meeting_types", "duration_minutes"): (10, 480),
    ("meeting_types", "buffer_minutes"): (0, 120),
    ("meeting_types", "display_order"): (PG_INT32_MIN, PG_INT32_MAX),
    ("group_sessions", "capacity"): (1, 500),
    ("group_sessions", "meeting_type_id"): (1, PG_INT32_MAX),
}


def test_declared_bounds_are_exact():
    for (table, field), expected in _EXPECTED_BOUNDS.items():
        fs = CHANGE_REGISTRY[table].fields[field]
        assert fs.policy is ValuePolicy.INT
        assert (fs.min_value, fs.max_value) == expected, (table, field)


def test_every_int_field_is_covered_by_this_test():
    declared = {
        (t, f)
        for t, spec in CHANGE_REGISTRY.items()
        for f, fs in spec.fields.items()
        if fs.policy is ValuePolicy.INT
    }
    assert declared == set(_EXPECTED_BOUNDS)


# ── Граничные значения принимаются ───────────────────────────────────────────

@pytest.mark.parametrize("field,low,high", [
    ("duration_minutes", 10, 480),
    ("buffer_minutes", 0, 120),
    ("capacity", 1, 500),
    ("meeting_type_id", 1, PG_INT32_MAX),
    ("display_order", PG_INT32_MIN, PG_INT32_MAX),
])
def test_boundary_values_are_accepted(field, low, high):
    db = _FakeSession()
    _write(field, old=low, new=high, db=db)
    assert db.added[0].old_values == {field: low}
    assert db.added[0].new_values == {field: high}


# ── За границей — отказ ──────────────────────────────────────────────────────

@pytest.mark.parametrize("field,below,above", [
    ("duration_minutes", 9, 481),
    ("buffer_minutes", -1, 121),
    ("capacity", 0, 501),
    ("meeting_type_id", 0, PG_INT32_MAX + 1),
    ("display_order", PG_INT32_MIN - 1, PG_INT32_MAX + 1),
])
def test_out_of_range_values_are_rejected(field, below, above):
    with pytest.raises(DataChangeError, match="below min_value"):
        _write(field, old=below, new=10)
    with pytest.raises(DataChangeError, match="above max_value"):
        _write(field, old=10, new=above)


def test_negative_meeting_type_id_is_rejected():
    with pytest.raises(DataChangeError, match="below min_value"):
        _write("meeting_type_id", old=-1, new=2)


# ── display_order: сценарий, который упал бы при лимите 0..10000 ─────────────

def test_display_order_accepts_negative_existing_value():
    """Сегодня API допускает отрицательный display_order (ge/le нет ни в Create,
    ни в Update). Journal обязан такую строку принять, а не откатить PATCH."""
    db = _FakeSession()
    _write("display_order", old=-5, new=0, db=db)
    assert db.added[0].old_values == {"display_order": -5}
    assert db.added[0].new_values == {"display_order": 0}


def test_display_order_accepts_value_far_above_ten_thousand():
    db = _FakeSession()
    _write("display_order", old=10_000, new=999_999, db=db)
    assert db.added[0].new_values == {"display_order": 999_999}


# ── Регрессия: не вводить новый бизнес-лимит ─────────────────────────────────

def _pydantic_bounds(model, field):
    """Извлекает (ge, le) из Pydantic v2 FieldInfo.metadata."""
    info = model.model_fields[field]
    ge = le = None
    for meta in info.metadata:
        ge = getattr(meta, "ge", ge)
        le = getattr(meta, "le", le)
    return ge, le


# (table, field) -> (CreateModel, UpdateModel) либо None, если поля нет в API.
_API_MODELS = {
    ("meeting_types", "duration_minutes"): (MeetingTypeCreate, MeetingTypeUpdate),
    ("meeting_types", "buffer_minutes"): (MeetingTypeCreate, MeetingTypeUpdate),
    ("meeting_types", "display_order"): (MeetingTypeCreate, MeetingTypeUpdate),
    ("group_sessions", "capacity"): (GroupSessionCreate, GroupSessionUpdate),
    ("group_sessions", "meeting_type_id"): (GroupSessionCreate,
                                            GroupSessionUpdate),
}

# Поля без API-границ: registry обязан использовать диапазон физического типа
# (для FK нижняя граница 1 — гарантирована существованием SERIAL-объекта).
_NO_API_BOUNDS = {
    ("meeting_types", "display_order"): (PG_INT32_MIN, PG_INT32_MAX),
    ("group_sessions", "meeting_type_id"): (1, PG_INT32_MAX),
}


def test_registry_bounds_match_pydantic_create_and_update():
    for (table, field), (create, update) in _API_MODELS.items():
        fs = CHANGE_REGISTRY[table].fields[field]
        create_ge, create_le = _pydantic_bounds(create, field)
        update_ge, update_le = _pydantic_bounds(update, field)

        # Create и Update обязаны быть согласованы между собой.
        assert (create_ge, create_le) == (update_ge, update_le), (table, field)

        if (table, field) in _NO_API_BOUNDS:
            # Границ в API нет — registry берёт диапазон физического типа.
            assert create_ge is None and create_le is None, (table, field)
            assert (fs.min_value, fs.max_value) == _NO_API_BOUNDS[(table, field)]
        else:
            # Границы в API есть — registry обязан их ПОВТОРЯТЬ, не сужая
            # и не расширяя (иначе journal изменил бы поведение API).
            assert (fs.min_value, fs.max_value) == (create_ge, create_le), (
                table, field,
            )


def test_display_order_has_no_api_bounds_today():
    """Явная фиксация факта, из которого следует выбор PG INTEGER-диапазона."""
    assert _pydantic_bounds(MeetingTypeCreate, "display_order") == (None, None)
    assert _pydantic_bounds(MeetingTypeUpdate, "display_order") == (None, None)
