"""
Stage 6-C — no-DB unit-тесты подключения record_data_change к ПДн-таблицам
в СТРОГО name-only режиме:
  * app/users/storage.py :: _apply_role_and_scalar_changes  (users)
  * app/appointments/storage.py :: update_unregistered_student_card (cards)

Покрывает: точный scalar diff (full_name/phone); границы (is_active и роли
никогда не попадают в DCL); combined scalar+lifecycle+role; проекцию
email+normalized_email; derived-only случай (0 DCL при непустом changed);
values ВСЕГДА None (значения ПДн не копируются); неизвестное поле → ошибка
ДО ORM-мутации; распространение DataChangeError/DataChangeStorageError и
недостижимость owner-commit; две РАЗНЫЕ транзакционные модели
(users: commit у update_user; cards: commit у appointments.service).

Реальная БД не используется.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import app.appointments.service as appt_service
import app.appointments.storage as appt_storage
import app.users.service as users_service
import app.users.storage as users_storage
from app.audit import Actor, Operation, RequestContext
from app.audit.change_contracts import DataChangeError, DataChangeStorageError
from app.users.storage import _apply_role_and_scalar_changes

ACTOR_ID = 11
TARGET_ID = 42
SUP = Actor.user(9, "supervisor")
CTX = RequestContext(ip_address="203.0.113.7", user_agent="ua")

# Синтетические ПДн-маркеры: не должны появляться НИГДЕ в journal-вызове.
PII_NAME = "Иванов Иван Иванович"
PII_PHONE = "+79991234567"
PII_EMAIL = "ivanov.secret@example.com"
PII_COMMENT = "СЕКРЕТНЫЙ КОММЕНТАРИЙ О КЛИЕНТЕ"
PII_CONCERN = "СЕКРЕТНЫЙ ЗАПРОС КЛИЕНТА"


# ══════════════════════════════════════════════════════════════════════════
# Хелперы
# ══════════════════════════════════════════════════════════════════════════

def _user(**over):
    base = dict(id=TARGET_ID, full_name="Old Name", phone=None, is_active=True)
    base.update(over)
    return SimpleNamespace(**base)


def _card(**over):
    base = dict(id=5, full_name="Old Name", phone=None, email=None,
                normalized_email=None, birth_date=None, comment=None,
                primary_concern=None, updated_at=None)
    base.update(over)
    return SimpleNamespace(**base)


def _role_lookup_db(roles):
    db = MagicMock(name="db")
    chain = db.query.return_value.filter.return_value
    chain.all.return_value = roles
    chain.first.return_value = None
    return db


def _apply(db, user, spies, **over):
    """Вызывает _apply_role_and_scalar_changes со spy на record_event и
    record_data_change; spies — (events, dcl)."""
    events, dcl = spies
    kwargs = dict(
        current_roles=["student"],
        target_staff=None,
        full_name=None, phone=None, is_active=None,
        legal_basis_confirmed=None, basis_type=None, basis_reference=None,
        legal_basis_comment=None, confirmed_by_user_id=None,
        actor_id=ACTOR_ID, actor_role="admin",
        ip=None, user_agent=None,
    )
    kwargs.update(over)
    with patch.object(users_storage, "record_event",
                      lambda **kw: events.append(kw)), \
         patch.object(users_storage, "record_data_change",
                      lambda **kw: dcl.append(kw)):
        _apply_role_and_scalar_changes(db, user, **kwargs)


def _spies():
    return ([], [])


def _card_spies(monkeypatch):
    events, dcl = [], []
    monkeypatch.setattr(appt_storage, "record_event",
                        lambda **kw: events.append(kw))
    monkeypatch.setattr(appt_storage, "record_data_change",
                        lambda **kw: dcl.append(kw))
    monkeypatch.setattr(appt_storage, "_card_to_dict", lambda c: {"id": c.id})
    return events, dcl


def _ordered_card_spy(monkeypatch):
    calls = []
    monkeypatch.setattr(appt_storage, "record_event",
                        lambda **kw: calls.append(("event", kw["event"])))
    monkeypatch.setattr(appt_storage, "record_data_change",
                        lambda **kw: calls.append(("dcl", kw["table"])))
    monkeypatch.setattr(appt_storage, "_card_to_dict", lambda c: {"id": c.id})
    return calls


# ══════════════════════════════════════════════════════════════════════════
# 1. users — точный scalar diff
# ══════════════════════════════════════════════════════════════════════════

def test_user_full_name_only_writes_one_dcl_with_name_only_field():
    spies = _spies()
    db = MagicMock(name="db")
    user = _user(full_name="Old Name")
    _apply(db, user, spies, full_name=PII_NAME)

    events, dcl = spies
    assert [e["event"] for e in events] == ["admin_user_updated"]
    assert len(dcl) == 1
    kw = dcl[0]
    assert kw["table"] == "users"
    assert kw["record_id"] == TARGET_ID
    assert kw["operation"] is Operation.UPDATE
    assert kw["actor"].user_id == ACTOR_ID
    assert kw["actor"].role == "admin"
    assert kw["db"] is db
    assert kw["changed_fields"] == ["full_name"]
    assert kw["values"] is None


def test_user_phone_only_writes_phone_field_only():
    spies = _spies()
    db = MagicMock(name="db")
    user = _user(phone="+70000000000")
    _apply(db, user, spies, phone=PII_PHONE)

    events, dcl = spies
    assert [e["event"] for e in events] == ["admin_user_updated"]
    assert dcl[0]["changed_fields"] == ["phone"]
    assert dcl[0]["values"] is None


def test_user_both_scalar_fields_are_sorted():
    spies = _spies()
    db = MagicMock(name="db")
    user = _user(full_name="Old Name", phone=None)
    _apply(db, user, spies, full_name=PII_NAME, phone=PII_PHONE)

    _events, dcl = spies
    assert dcl[0]["changed_fields"] == ["full_name", "phone"]
    assert dcl[0]["values"] is None


def test_user_pii_values_never_appear_anywhere_in_the_dcl_call():
    """Ни ФИО, ни телефон не копируются: values=None, а changed_fields
    содержит только ИМЕНА полей."""
    spies = _spies()
    db = MagicMock(name="db")
    user = _user(full_name="Old Name", phone=None)
    _apply(db, user, spies, full_name=PII_NAME, phone=PII_PHONE)

    _events, dcl = spies
    blob = repr(dcl[0])
    assert PII_NAME not in blob
    assert PII_PHONE not in blob
    assert "Old Name" not in blob


def test_user_phone_normalization_is_respected_in_diff():
    """phone='' → None; если текущий phone уже None, diff отсутствует."""
    spies = _spies()
    db = MagicMock(name="db")
    user = _user(phone=None)
    _apply(db, user, spies, phone="   ")

    events, dcl = spies
    assert events == []          # нет реального diff
    assert dcl == []


def test_user_identical_scalar_values_produce_no_dcl():
    spies = _spies()
    db = MagicMock(name="db")
    user = _user(full_name="Same", phone="+7999")
    _apply(db, user, spies, full_name="Same", phone="+7999")

    events, dcl = spies
    assert events == []
    assert dcl == []


# ══════════════════════════════════════════════════════════════════════════
# 2. users — границы: is_active и роли НЕ попадают в DCL
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("before,after,expected_event", [
    (True, False, "admin_user_deactivated"),
    (False, True, "admin_user_activated"),
])
def test_user_lifecycle_only_writes_zero_dcl(before, after, expected_event):
    spies = _spies()
    db = MagicMock(name="db")
    user = _user(is_active=before)
    _apply(db, user, spies, is_active=after)

    events, dcl = spies
    assert [e["event"] for e in events] == [expected_event]
    assert dcl == []


def test_user_role_only_writes_zero_dcl():
    spies = _spies()
    role_obj = SimpleNamespace(id=55, name="supervisor")
    db = _role_lookup_db([role_obj])
    user = _user()
    _apply(
        db, user, spies,
        current_roles=["psychologist"],
        target_staff={"psychologist", "supervisor"},
        legal_basis_confirmed=True, basis_type="service_duty",
        basis_reference="Order #1", confirmed_by_user_id=ACTOR_ID,
    )

    events, dcl = spies
    assert [e["event"] for e in events] == ["admin_role_add"]
    assert dcl == []


def test_user_combined_scalar_lifecycle_role_writes_one_dcl_for_scalar_only():
    """Три непересекающихся audit-события, но РОВНО ОДНА journal-строка —
    и только по scalar-полям."""
    spies = _spies()
    role_obj = SimpleNamespace(id=55, name="supervisor")
    db = _role_lookup_db([role_obj])
    user = _user(full_name="Old Name", is_active=True)
    _apply(
        db, user, spies,
        full_name=PII_NAME,
        is_active=False,
        current_roles=["psychologist"],
        target_staff={"psychologist", "supervisor"},
        legal_basis_confirmed=True, basis_type="service_duty",
        basis_reference="Order #1", confirmed_by_user_id=ACTOR_ID,
    )

    events, dcl = spies
    assert [e["event"] for e in events] == [
        "admin_user_updated", "admin_user_deactivated", "admin_role_add",
    ]
    assert len(dcl) == 1
    kw = dcl[0]
    assert kw["changed_fields"] == ["full_name"]
    assert "is_active" not in kw["changed_fields"]
    assert "supervisor" not in repr(kw["changed_fields"])
    assert kw["values"] is None


def test_user_dcl_is_written_right_after_generic_event_before_lifecycle():
    """Порядок: admin_user_updated → DCL → lifecycle → role."""
    calls = []
    role_obj = SimpleNamespace(id=55, name="supervisor")
    db = _role_lookup_db([role_obj])
    user = _user(full_name="Old Name", is_active=True)
    with patch.object(users_storage, "record_event",
                      lambda **kw: calls.append(("event", kw["event"]))), \
         patch.object(users_storage, "record_data_change",
                      lambda **kw: calls.append(("dcl", kw["table"]))):
        _apply_role_and_scalar_changes(
            db, user,
            current_roles=["psychologist"],
            target_staff={"psychologist", "supervisor"},
            full_name="New Name", phone=None, is_active=False,
            legal_basis_confirmed=True, basis_type="service_duty",
            basis_reference="Order #1", legal_basis_comment=None,
            confirmed_by_user_id=ACTOR_ID,
            actor_id=ACTOR_ID, actor_role="admin",
            ip=None, user_agent=None,
        )
    assert calls == [
        ("event", "admin_user_updated"),
        ("dcl", "users"),
        ("event", "admin_user_deactivated"),
        ("event", "admin_role_add"),
    ]


def test_user_true_noop_writes_nothing():
    spies = _spies()
    db = MagicMock(name="db")
    user = _user(full_name="Same", is_active=True)
    _apply(db, user, spies, full_name="Same", is_active=True)

    events, dcl = spies
    assert events == []
    assert dcl == []


# ══════════════════════════════════════════════════════════════════════════
# 3. users — fail-closed и транзакционная модель
# ══════════════════════════════════════════════════════════════════════════

def test_user_dcl_error_propagates_after_generic_event():
    events = []

    def _boom(**kw):
        raise DataChangeStorageError("dcl storage down")

    db = MagicMock(name="db")
    user = _user(full_name="Old Name")
    with patch.object(users_storage, "record_event",
                      lambda **kw: events.append(kw)), \
         patch.object(users_storage, "record_data_change", _boom):
        with pytest.raises(DataChangeStorageError):
            _apply_role_and_scalar_changes(
                db, user,
                current_roles=["student"], target_staff=None,
                full_name="New Name", phone=None, is_active=None,
                legal_basis_confirmed=None, basis_type=None,
                basis_reference=None, legal_basis_comment=None,
                confirmed_by_user_id=None,
                actor_id=ACTOR_ID, actor_role="admin",
                ip=None, user_agent=None,
            )
    assert [e["event"] for e in events] == ["admin_user_updated"]


def test_user_core_never_manages_the_transaction():
    """_apply_role_and_scalar_changes не коммитит и не открывает сессию —
    SessionLocal/commit принадлежат update_user."""
    spies = _spies()
    db = MagicMock(name="db")
    user = _user(full_name="Old Name")
    _apply(db, user, spies, full_name="New Name")

    db.commit.assert_not_called()
    db.rollback.assert_not_called()
    db.close.assert_not_called()
    # Stage 6-C не добавляет flush/refresh в user-flow.
    db.flush.assert_not_called()
    db.refresh.assert_not_called()


def test_user_service_commit_not_reached_on_dcl_error(monkeypatch):
    """Owner-commit boundary: сбой journal-writer'а не даёт дойти до
    _commit_or_diag внутри update_user."""
    db = MagicMock(name="db")
    user = _user(full_name="Old Name", is_active=True)
    db.query.return_value.filter.return_value.filter.return_value.first \
        .return_value = user
    monkeypatch.setattr(users_storage, "SessionLocal", _mock_sessionlocal(db))
    monkeypatch.setattr(users_storage, "get_active_role_names",
                        lambda db_, uid: ["student"])

    def _boom(**kw):
        raise DataChangeStorageError("dcl storage down")

    monkeypatch.setattr(users_storage, "record_data_change", _boom)
    monkeypatch.setattr(users_storage, "record_event", lambda **kw: None)

    with pytest.raises(DataChangeStorageError):
        users_storage.update_user(
            "11111111-1111-1111-1111-111111111111",
            full_name="New Name",
            actor_id=ACTOR_ID, actor_role="admin",
        )
    db.commit.assert_not_called()


def _mock_sessionlocal(db):
    m = MagicMock(name="SessionLocal")
    m.return_value.__enter__ = MagicMock(return_value=db)
    m.return_value.__exit__ = MagicMock(return_value=False)
    return m


# ══════════════════════════════════════════════════════════════════════════
# 4. cards — все шесть публичных полей name-only
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("field,before,after", [
    ("full_name", "Old Name", PII_NAME),
    ("phone", None, PII_PHONE),
    ("email", None, PII_EMAIL),
    ("birth_date", None, "1990-01-01"),
    ("comment", None, PII_COMMENT),
    ("primary_concern", None, PII_CONCERN),
])
def test_card_each_public_field_is_name_only(monkeypatch, field, before, after):
    events, dcl = _card_spies(monkeypatch)
    db = MagicMock(name="db")
    card = _card(**{field: before})
    appt_storage.update_unregistered_student_card(
        card, {field: after}, db, actor=SUP, context=CTX,
    )
    assert [e["event"] for e in events] == [
        "unregistered_student_card_updated",
    ]
    assert len(dcl) == 1
    kw = dcl[0]
    assert kw["table"] == "unregistered_student_cards"
    assert kw["record_id"] == 5
    assert kw["operation"] is Operation.UPDATE
    assert kw["actor"] is SUP
    assert kw["context"] is CTX
    assert kw["db"] is db
    assert kw["changed_fields"] == [field]
    assert kw["values"] is None
    # значение ПДн не попало ни в один аргумент journal-вызова
    assert str(after) not in repr(kw)


def test_card_multiple_fields_are_sorted_and_valueless(monkeypatch):
    _events, dcl = _card_spies(monkeypatch)
    db = MagicMock(name="db")
    card = _card(full_name="Old Name", phone=None, comment=None)
    appt_storage.update_unregistered_student_card(
        card, {"phone": PII_PHONE, "full_name": PII_NAME,
               "comment": PII_COMMENT},
        db, actor=SUP, context=CTX,
    )
    kw = dcl[0]
    assert kw["changed_fields"] == ["comment", "full_name", "phone"]
    assert kw["values"] is None
    blob = repr(kw)
    for pii in (PII_NAME, PII_PHONE, PII_COMMENT):
        assert pii not in blob


# ══════════════════════════════════════════════════════════════════════════
# 5. cards — проекция email + normalized_email и derived-only случай
# ══════════════════════════════════════════════════════════════════════════

def test_card_email_change_projects_to_email_only(monkeypatch):
    """service пересчитывает normalized_email при смене email; оно попадает в
    changed, но ЯВНО отбрасывается проекцией."""
    _events, dcl = _card_spies(monkeypatch)
    db = MagicMock(name="db")
    card = _card(email=None, normalized_email=None)
    appt_storage.update_unregistered_student_card(
        card,
        {"email": PII_EMAIL, "normalized_email": PII_EMAIL.lower()},
        db, actor=SUP, context=CTX,
    )
    assert len(dcl) == 1
    kw = dcl[0]
    assert kw["changed_fields"] == ["email"]
    assert "normalized_email" not in kw["changed_fields"]
    assert kw["values"] is None
    assert PII_EMAIL not in repr(kw)
    assert PII_EMAIL.lower() not in repr(kw)
    # техническая мутация всё равно применена
    assert card.normalized_email == PII_EMAIL.lower()


def test_card_derived_only_change_mutates_and_audits_but_writes_zero_dcl(
    monkeypatch,
):
    """Repair рассинхрона normalized_email без правки самого email: публичная
    проекция ПУСТА → generic audit остаётся, journal-строка не пишется
    (record_data_change с [] запрещён контрактом)."""
    events, dcl = _card_spies(monkeypatch)
    db = MagicMock(name="db")
    card = _card(email="a@x.ru", normalized_email=None)
    appt_storage.update_unregistered_student_card(
        card, {"normalized_email": "a@x.ru"}, db, actor=SUP, context=CTX,
    )
    # мутация и generic audit сохраняются
    assert card.normalized_email == "a@x.ru"
    assert card.updated_at is not None
    assert [e["event"] for e in events] == [
        "unregistered_student_card_updated",
    ]
    # journal-строки нет
    assert dcl == []


def test_card_dcl_called_after_generic_event(monkeypatch):
    calls = _ordered_card_spy(monkeypatch)
    db = MagicMock(name="db")
    card = _card(full_name="Old Name")
    appt_storage.update_unregistered_student_card(
        card, {"full_name": PII_NAME}, db, actor=SUP, context=CTX,
    )
    assert calls == [
        ("event", "unregistered_student_card_updated"),
        ("dcl", "unregistered_student_cards"),
    ]


@pytest.mark.parametrize("updates", [{}, {"full_name": "Same"}])
def test_card_noop_writes_zero_audit_and_zero_dcl(monkeypatch, updates):
    events, dcl = _card_spies(monkeypatch)
    db = MagicMock(name="db")
    card = _card(full_name="Same", updated_at=None)
    appt_storage.update_unregistered_student_card(
        card, updates, db, actor=SUP, context=CTX,
    )
    assert card.updated_at is None
    assert events == []
    assert dcl == []
    db.flush.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════
# 6. cards — fail-closed и транзакционная модель
# ══════════════════════════════════════════════════════════════════════════

def test_card_unknown_field_raises_before_orm_mutation(monkeypatch):
    events, _dcl = _card_spies(monkeypatch)
    db = MagicMock(name="db")
    card = _card(full_name="Old Name")
    card.secret_field = "before"
    with pytest.raises(DataChangeError):
        appt_storage.update_unregistered_student_card(
            card, {"secret_field": "after"}, db, actor=SUP, context=CTX,
        )
    assert card.secret_field == "before"    # мутация НЕ произошла
    assert card.updated_at is None
    assert events == []
    db.flush.assert_not_called()
    db.refresh.assert_not_called()
    db.add.assert_not_called()


def test_card_dcl_error_propagates_after_generic_event(monkeypatch):
    events = []
    monkeypatch.setattr(appt_storage, "record_event",
                        lambda **kw: events.append(kw))
    monkeypatch.setattr(appt_storage, "_card_to_dict", lambda c: {"id": c.id})

    def _boom(**kw):
        raise DataChangeError("contract violation")

    monkeypatch.setattr(appt_storage, "record_data_change", _boom)
    db = MagicMock(name="db")
    with pytest.raises(DataChangeError):
        appt_storage.update_unregistered_student_card(
            _card(full_name="Old Name"), {"full_name": PII_NAME}, db,
            actor=SUP, context=CTX,
        )
    assert [e["event"] for e in events] == [
        "unregistered_student_card_updated",
    ]


def test_card_storage_never_manages_the_transaction(monkeypatch):
    _card_spies(monkeypatch)
    db = MagicMock(name="db")
    appt_storage.update_unregistered_student_card(
        _card(full_name="Old Name"), {"full_name": PII_NAME}, db,
        actor=SUP, context=CTX,
    )
    db.commit.assert_not_called()
    db.rollback.assert_not_called()
    db.close.assert_not_called()


def test_card_service_commit_not_reached_on_dcl_error(monkeypatch):
    """Owner-commit boundary для карточек: commit принадлежит
    appointments.service, а не storage."""
    db = MagicMock(name="db")
    sess = MagicMock(name="SessionLocal")
    sess.return_value.__enter__ = MagicMock(return_value=db)
    sess.return_value.__exit__ = MagicMock(return_value=False)
    monkeypatch.setattr(appt_service, "SessionLocal", sess)
    monkeypatch.setattr(
        appt_service.storage, "get_unregistered_student_card",
        lambda card_id, db_: _card(full_name="Old Name"),
    )
    monkeypatch.setattr(appt_storage, "_card_to_dict", lambda c: {"id": c.id})
    monkeypatch.setattr(appt_storage, "record_event", lambda **kw: None)

    def _boom(**kw):
        raise DataChangeStorageError("dcl storage down")

    monkeypatch.setattr(appt_storage, "record_data_change", _boom)

    with pytest.raises(DataChangeStorageError):
        appt_service.update_unregistered_student_card(
            5, {"full_name": PII_NAME},
            current_user={"id": 9}, actor_role="supervisor",
        )
    db.commit.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════
# 7. Статическая проверка: значения ПДн не попадают в journal ни для одной
#    из двух ПДн-таблиц (registry-инвариант, продублированный на call-site)
# ══════════════════════════════════════════════════════════════════════════

def test_both_pii_tables_are_declared_fully_name_only():
    from app.audit.change_contracts import ValuePolicy
    from app.audit.change_registry import CHANGE_REGISTRY

    for table in ("users", "unregistered_student_cards"):
        spec = CHANGE_REGISTRY[table]
        for fname, fs in spec.fields.items():
            assert fs.policy is ValuePolicy.NAME_ONLY, (table, fname)


def test_users_service_module_is_importable_for_boundary_tests():
    """Guard: тестовый модуль ссылается на users_service — импорт не должен
    тянуть за собой БД."""
    assert users_service is not None


# ══════════════════════════════════════════════════════════════════════════
# 8. commit failure распространяется (обе транзакционные модели)
# ══════════════════════════════════════════════════════════════════════════

def test_user_commit_failure_propagates(monkeypatch):
    """users: commit принадлежит update_user (_commit_or_diag) — его сбой
    пробрасывается наружу, не поглощается."""
    db = MagicMock(name="db")
    user = _user(full_name="Old Name", is_active=True)
    db.query.return_value.filter.return_value.filter.return_value.first \
        .return_value = user
    db.commit.side_effect = RuntimeError("commit boom")
    monkeypatch.setattr(users_storage, "SessionLocal", _mock_sessionlocal(db))
    monkeypatch.setattr(users_storage, "get_active_role_names",
                        lambda db_, uid: ["student"])
    monkeypatch.setattr(users_storage, "record_event", lambda **kw: None)
    monkeypatch.setattr(users_storage, "record_data_change", lambda **kw: None)

    with pytest.raises(RuntimeError, match="commit boom"):
        users_storage.update_user(
            "11111111-1111-1111-1111-111111111111",
            full_name="New Name",
            actor_id=ACTOR_ID, actor_role="admin",
        )
    db.commit.assert_called_once()


def test_card_commit_failure_propagates(monkeypatch):
    """cards: commit принадлежит appointments.service — его сбой
    пробрасывается наружу, не поглощается."""
    db = MagicMock(name="db")
    db.commit.side_effect = RuntimeError("commit boom")
    sess = MagicMock(name="SessionLocal")
    sess.return_value.__enter__ = MagicMock(return_value=db)
    sess.return_value.__exit__ = MagicMock(return_value=False)
    monkeypatch.setattr(appt_service, "SessionLocal", sess)
    monkeypatch.setattr(
        appt_service.storage, "get_unregistered_student_card",
        lambda card_id, db_: _card(full_name="Old Name"),
    )
    monkeypatch.setattr(appt_storage, "_card_to_dict", lambda c: {"id": c.id})
    monkeypatch.setattr(appt_storage, "record_event", lambda **kw: None)
    monkeypatch.setattr(appt_storage, "record_data_change", lambda **kw: None)

    with pytest.raises(RuntimeError, match="commit boom"):
        appt_service.update_unregistered_student_card(
            5, {"full_name": PII_NAME},
            current_user={"id": 9}, actor_role="supervisor",
        )
    db.commit.assert_called_once()
