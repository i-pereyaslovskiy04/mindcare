"""
Stage 6-C — gated integration: field-level журнал (data_change_log) для
ПДн-таблиц в СТРОГО name-only режиме.

Запуск ТОЛЬКО через Stage 1 isolated runner (scripts/isolated_test_db.py) при
безопасном TEST_DATABASE_URL; dev/prod запрещены.

Проверяет:
  users  — full_name-only / phone-only / оба поля; scalar+is_active+role
           combined; lifecycle-only и role-only → 0 DCL; no-op → 0 audit/DCL;
  cards  — каждое из шести публичных полей; email → changed_fields=["email"]
           без normalized_email; derived-only repair → 0 DCL; no-op → 0
           audit/DCL и updated_at не меняется;
  общее  — контракт строки (actor_id/actor_role/table_name/record_id/
           operation/ip_address); old_values/new_values ВСЕГДА NULL;
           синтетические ПДн отсутствуют во ВСЕЙ сериализованной строке;
           совместный rollback mutation + audit_log + DCL при failure
           injection через реальные service/storage boundaries.

Append-only журналы НЕ очищаются — уникальные entity id и before/after counts.

Requires: PostgreSQL on alembic head (d4a7b2c9f6e1), DATA_ENCRYPTION_KEY,
seeded roles.
"""
import uuid as _uuid

import bcrypt
import pytest

from app.appointments import service as appt_service
from app.appointments import storage as appt_storage
from app.auth import storage as auth_storage
from app.db.session import SessionLocal
from app.db.models import (
    AuditLog, DataChangeLog, UnregisteredStudentCard, User,
)
from app.users import storage as users_storage
from tests.integration.conftest import ALLOWED_TEST_DOMAIN, create_multi_role_user

PASSWORD = "SecurePass42!"
CARDS_URL = "/api/supervisor/unregistered-student-cards"

# Синтетические ПДн-маркеры: не должны встречаться НИ В ОДНОЙ колонке DCL.
PII_NAME = f"Секретов Секрет {_uuid.uuid4().hex[:8]}"
PII_PHONE = "+79995550001"
PII_COMMENT = f"СЕКРЕТКОММЕНТ{_uuid.uuid4().hex[:8]}"
PII_CONCERN = f"СЕКРЕТЗАПРОС{_uuid.uuid4().hex[:8]}"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _new_email(prefix="dcl6c"):
    return f"integ_{prefix}_{_uuid.uuid4().hex[:10]}@{ALLOWED_TEST_DOMAIN}"


def _make_supervisor(client):
    suffix = _uuid.uuid4().hex[:10]
    email = f"integ_dcl6c_sup_{suffix}@example.com"
    user = auth_storage.save_user({
        "name": f"Dcl6cSup {_uuid.uuid4().hex[:6]}",
        "email": email,
        "hashed_password": bcrypt.hashpw(
            PASSWORD.encode(), bcrypt.gensalt()).decode(),
        "role": "supervisor",
    })
    r = client.post("/api/auth/login",
                    json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["session_token"], int(user["id"])


def _audit_rows(event_type, entity_id, entity_type):
    with SessionLocal() as db:
        rows = (
            db.query(AuditLog)
            .filter(AuditLog.event_type == event_type,
                    AuditLog.entity_type == entity_type,
                    AuditLog.entity_id == entity_id)
            .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
            .all()
        )
        for r in rows:
            db.expunge(r)
        return rows


def _dcl_rows(table_name, record_id):
    with SessionLocal() as db:
        rows = (
            db.query(DataChangeLog)
            .filter(DataChangeLog.table_name == table_name,
                    DataChangeLog.record_id == record_id)
            .order_by(DataChangeLog.created_at.asc(), DataChangeLog.id.asc())
            .all()
        )
        for r in rows:
            db.expunge(r)
        return rows


def _assert_dcl_contract(row, table_name, record_id, actor_id, actor_role):
    """Полный контракт name-only journal-строки Stage 6-C."""
    assert row.table_name == table_name
    assert row.record_id == record_id
    assert row.operation == "UPDATE"
    assert row.actor_id == actor_id
    assert row.actor_role == actor_role
    # str(...) — INET может вернуться как ipaddress.IPv4Address.
    assert str(row.ip_address) == "127.0.0.1"
    # ПДн НИКОГДА не копируются: обе value-колонки NULL.
    assert row.old_values is None
    assert row.new_values is None


def _serialized(row) -> str:
    """Вся строка в виде текста — для проверки отсутствия ПДн целиком."""
    return " | ".join(str(v) for v in (
        row.table_name, row.record_id, row.operation, row.actor_id,
        row.actor_role, row.changed_fields, row.old_values, row.new_values,
        row.ip_address,
    ))


def _uuid_for(user_id):
    with SessionLocal() as db:
        row = db.query(User.uuid).filter(User.id == user_id).first()
        return str(row.uuid)


def _user_id_by_email(email):
    with SessionLocal() as db:
        row = db.query(User.id).filter(User.email == email).first()
        return row.id if row else None


BODY_STAFF = {
    "full_name": "Базовый Сотрудник",
    "role": "psychologist",
    "legal_basis_confirmed": True,
    "basis_type": "employment",
    "basis_reference": "Приказ № 42-к",
}


def _make_staff_target(client, admin_token):
    email = _new_email("target")
    r = client.post("/api/admin/users/", headers=_auth(admin_token),
                    json={**BODY_STAFF, "email": email})
    assert r.status_code == 201, r.text
    return _user_id_by_email(email)


def _card_payload(**over):
    suffix = _uuid.uuid4().hex[:8]
    payload = {
        "full_name": f"integ_dcl6c_card_{suffix}",
        "phone": "+70000000001",
        "email": f"integ_dcl6c_card_{suffix}@example.com",
        "personal_data_consent": True,
    }
    payload.update(over)
    return payload


def _create_card(client, token, **over):
    r = client.post(CARDS_URL, json=_card_payload(**over), headers=_auth(token))
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _card_field(card_id, field):
    with SessionLocal() as db:
        return db.query(getattr(UnregisteredStudentCard, field)).filter(
            UnregisteredStudentCard.id == card_id).scalar()


# ══════════════════════════════════════════════════════════════════════════
# 1. users — scalar-only варианты
# ══════════════════════════════════════════════════════════════════════════

def test_user_full_name_only_writes_one_event_and_one_name_only_dcl(client):
    token, admin_id, _ = create_multi_role_user(client, ["admin"])
    target_id = _make_staff_target(client, token)

    r = client.patch(f"/api/admin/users/{_uuid_for(target_id)}",
                     headers=_auth(token), json={"full_name": PII_NAME})
    assert r.status_code == 200, r.text

    assert len(_audit_rows("admin_user_updated", target_id, "user")) == 1
    drows = _dcl_rows("users", target_id)
    assert len(drows) == 1
    row = drows[0]
    _assert_dcl_contract(row, "users", target_id, admin_id, "admin")
    assert row.changed_fields == ["full_name"]
    assert PII_NAME not in _serialized(row)


def test_user_phone_only_writes_phone_field(client):
    token, admin_id, _ = create_multi_role_user(client, ["admin"])
    target_id = _make_staff_target(client, token)

    r = client.patch(f"/api/admin/users/{_uuid_for(target_id)}",
                     headers=_auth(token), json={"phone": PII_PHONE})
    assert r.status_code == 200, r.text

    drows = _dcl_rows("users", target_id)
    assert len(drows) == 1
    row = drows[0]
    _assert_dcl_contract(row, "users", target_id, admin_id, "admin")
    assert row.changed_fields == ["phone"]
    assert PII_PHONE not in _serialized(row)


def test_user_both_scalar_fields_write_one_sorted_dcl(client):
    token, admin_id, _ = create_multi_role_user(client, ["admin"])
    target_id = _make_staff_target(client, token)

    r = client.patch(
        f"/api/admin/users/{_uuid_for(target_id)}", headers=_auth(token),
        json={"full_name": PII_NAME, "phone": PII_PHONE},
    )
    assert r.status_code == 200, r.text

    drows = _dcl_rows("users", target_id)
    assert len(drows) == 1
    row = drows[0]
    _assert_dcl_contract(row, "users", target_id, admin_id, "admin")
    assert row.changed_fields == ["full_name", "phone"]
    blob = _serialized(row)
    assert PII_NAME not in blob
    assert PII_PHONE not in blob


# ══════════════════════════════════════════════════════════════════════════
# 2. users — границы: lifecycle-only, role-only, combined, no-op
# ══════════════════════════════════════════════════════════════════════════

def test_user_lifecycle_only_writes_zero_dcl(client):
    token, _admin_id, _ = create_multi_role_user(client, ["admin"])
    target_id = _make_staff_target(client, token)

    before = len(_dcl_rows("users", target_id))
    r = client.patch(f"/api/admin/users/{_uuid_for(target_id)}",
                     headers=_auth(token), json={"is_active": False})
    assert r.status_code == 200, r.text

    assert len(_audit_rows("admin_user_deactivated", target_id, "user")) == 1
    assert len(_dcl_rows("users", target_id)) == before      # 0 добавлено


def test_user_role_only_writes_zero_dcl(client):
    token, _admin_id, _ = create_multi_role_user(client, ["admin"])
    target_id = _make_staff_target(client, token)

    before = len(_dcl_rows("users", target_id))
    r = client.patch(
        f"/api/admin/users/{_uuid_for(target_id)}", headers=_auth(token),
        json={
            "roles": ["psychologist", "supervisor"],
            "legal_basis_confirmed": True,
            "basis_type": "employment",
            "basis_reference": "Приказ № 7",
        },
    )
    assert r.status_code == 200, r.text

    assert len(_audit_rows("admin_role_add", target_id, "user")) == 1
    assert _audit_rows("admin_user_updated", target_id, "user") == []
    assert len(_dcl_rows("users", target_id)) == before      # 0 добавлено


def test_user_combined_scalar_lifecycle_role_writes_one_scalar_only_dcl(client):
    token, admin_id, _ = create_multi_role_user(client, ["admin"])
    target_id = _make_staff_target(client, token)

    r = client.patch(
        f"/api/admin/users/{_uuid_for(target_id)}", headers=_auth(token),
        json={
            "full_name": PII_NAME,
            "is_active": False,
            "roles": ["psychologist", "supervisor"],
            "legal_basis_confirmed": True,
            "basis_type": "employment",
            "basis_reference": "Приказ № 8",
        },
    )
    assert r.status_code == 200, r.text

    # Три непересекающихся audit-события.
    assert len(_audit_rows("admin_user_updated", target_id, "user")) == 1
    assert len(_audit_rows("admin_user_deactivated", target_id, "user")) == 1
    assert len(_audit_rows("admin_role_add", target_id, "user")) == 1
    # РОВНО ОДНА journal-строка, только по scalar-полю.
    drows = _dcl_rows("users", target_id)
    assert len(drows) == 1
    row = drows[0]
    _assert_dcl_contract(row, "users", target_id, admin_id, "admin")
    assert row.changed_fields == ["full_name"]
    blob = _serialized(row)
    assert "is_active" not in blob
    assert "supervisor" not in blob
    assert PII_NAME not in blob


def test_user_noop_writes_zero_audit_and_zero_dcl(client):
    token, _admin_id, _ = create_multi_role_user(client, ["admin"])
    target_id = _make_staff_target(client, token)

    # Зафиксировать текущее имя, затем прислать его же.
    with SessionLocal() as db:
        current_name = db.query(User.full_name).filter(
            User.id == target_id).scalar()

    audit_before = len(_audit_rows("admin_user_updated", target_id, "user"))
    dcl_before = len(_dcl_rows("users", target_id))

    r = client.patch(f"/api/admin/users/{_uuid_for(target_id)}",
                     headers=_auth(token), json={"full_name": current_name})
    assert r.status_code == 200, r.text

    assert len(
        _audit_rows("admin_user_updated", target_id, "user")) == audit_before
    assert len(_dcl_rows("users", target_id)) == dcl_before


# ══════════════════════════════════════════════════════════════════════════
# 3. cards — каждое из шести публичных полей
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("field,value", [
    ("full_name", PII_NAME),
    ("phone", PII_PHONE),
    ("birth_date", "1990-01-01"),
    ("comment", PII_COMMENT),
    ("primary_concern", PII_CONCERN),
])
def test_card_each_public_field_writes_name_only_dcl(client, field, value):
    token, sup_id = _make_supervisor(client)
    card_id = _create_card(client, token)

    r = client.patch(f"{CARDS_URL}/{card_id}", headers=_auth(token),
                     json={field: value})
    assert r.status_code == 200, r.text

    assert len(_audit_rows(
        "unregistered_student_card_updated", card_id,
        "unregistered_student_card")) == 1
    drows = _dcl_rows("unregistered_student_cards", card_id)
    assert len(drows) == 1
    row = drows[0]
    _assert_dcl_contract(
        row, "unregistered_student_cards", card_id, sup_id, "supervisor")
    assert row.changed_fields == [field]
    assert str(value) not in _serialized(row)


def test_card_multiple_fields_write_one_sorted_dcl(client):
    token, sup_id = _make_supervisor(client)
    card_id = _create_card(client, token)

    r = client.patch(
        f"{CARDS_URL}/{card_id}", headers=_auth(token),
        json={"full_name": PII_NAME, "phone": PII_PHONE,
              "comment": PII_COMMENT},
    )
    assert r.status_code == 200, r.text

    drows = _dcl_rows("unregistered_student_cards", card_id)
    assert len(drows) == 1
    row = drows[0]
    _assert_dcl_contract(
        row, "unregistered_student_cards", card_id, sup_id, "supervisor")
    assert row.changed_fields == ["comment", "full_name", "phone"]
    blob = _serialized(row)
    for pii in (PII_NAME, PII_PHONE, PII_COMMENT):
        assert pii not in blob


# ══════════════════════════════════════════════════════════════════════════
# 4. cards — email/normalized_email проекция и derived-only случай
# ══════════════════════════════════════════════════════════════════════════

def test_card_email_change_projects_to_email_only(client):
    """service пересчитывает normalized_email; оно попадает в storage-дифф,
    но ЯВНО отбрасывается проекцией и не журналируется."""
    token, sup_id = _make_supervisor(client)
    card_id = _create_card(client, token)

    new_email = f"NEW.Secret.{_uuid.uuid4().hex[:8]}@Example.COM"
    r = client.patch(f"{CARDS_URL}/{card_id}", headers=_auth(token),
                     json={"email": new_email})
    assert r.status_code == 200, r.text

    # Техническая мутация derived-поля применена.
    assert _card_field(card_id, "normalized_email") == new_email.lower().strip()

    drows = _dcl_rows("unregistered_student_cards", card_id)
    assert len(drows) == 1
    row = drows[0]
    _assert_dcl_contract(
        row, "unregistered_student_cards", card_id, sup_id, "supervisor")
    assert row.changed_fields == ["email"]
    assert "normalized_email" not in row.changed_fields
    blob = _serialized(row)
    assert "normalized_email" not in blob
    assert new_email not in blob
    assert new_email.lower() not in blob


def test_card_derived_only_repair_writes_audit_but_zero_dcl(client):
    """Рассинхрон normalized_email чинится без правки email: публичная
    проекция пуста → generic audit остаётся, journal-строка не пишется."""
    token, _sup_id = _make_supervisor(client)
    card_id = _create_card(client, token)

    # Ломаем derived-поле напрямую в БД, не трогая email.
    with SessionLocal() as db:
        card = db.query(UnregisteredStudentCard).filter(
            UnregisteredStudentCard.id == card_id).first()
        real_email = card.email
        card.normalized_email = "stale-desynced-value@example.com"
        db.commit()

    audit_before = len(_audit_rows(
        "unregistered_student_card_updated", card_id,
        "unregistered_student_card"))
    dcl_before = len(_dcl_rows("unregistered_student_cards", card_id))

    # PATCH тем же email → email не меняется, normalized_email пересчитывается
    # и ОТЛИЧАЕТСЯ от испорченного значения → changed непуст, проекция пуста.
    r = client.patch(f"{CARDS_URL}/{card_id}", headers=_auth(token),
                     json={"email": real_email})
    assert r.status_code == 200, r.text

    assert _card_field(card_id, "normalized_email") == real_email.lower().strip()
    # generic audit записан (техническая мутация состоялась)...
    assert len(_audit_rows(
        "unregistered_student_card_updated", card_id,
        "unregistered_student_card")) == audit_before + 1
    # ...а journal-строки нет: публично не изменилось ни одно поле.
    assert len(_dcl_rows("unregistered_student_cards", card_id)) == dcl_before


def test_card_noop_writes_zero_audit_zero_dcl_and_keeps_updated_at(client):
    token, _sup_id = _make_supervisor(client)
    card_id = _create_card(client, token)

    current_name = _card_field(card_id, "full_name")
    updated_before = _card_field(card_id, "updated_at")
    audit_before = len(_audit_rows(
        "unregistered_student_card_updated", card_id,
        "unregistered_student_card"))
    dcl_before = len(_dcl_rows("unregistered_student_cards", card_id))

    r = client.patch(f"{CARDS_URL}/{card_id}", headers=_auth(token),
                     json={"full_name": current_name})
    assert r.status_code == 200, r.text

    assert len(_audit_rows(
        "unregistered_student_card_updated", card_id,
        "unregistered_student_card")) == audit_before
    assert len(_dcl_rows("unregistered_student_cards", card_id)) == dcl_before
    assert _card_field(card_id, "updated_at") == updated_before


# ══════════════════════════════════════════════════════════════════════════
# 5. Совместный rollback mutation + audit_log + DCL (failure injection)
# ══════════════════════════════════════════════════════════════════════════

def test_user_dcl_failure_rolls_back_mutation_and_audit_together(
    client, monkeypatch,
):
    """Сбой journal-writer'а ПОСЛЕ admin_user_updated, но ДО commit внутри
    update_user → откатывается ВСЁ. Вызов через users_storage (владелец
    SessionLocal/_commit_or_diag), чтобы получить исходный тип исключения."""
    token, admin_id, _ = create_multi_role_user(client, ["admin"])
    target_id = _make_staff_target(client, token)
    target_uuid = _uuid_for(target_id)

    with SessionLocal() as db:
        name_before = db.query(User.full_name).filter(
            User.id == target_id).scalar()

    audit_before = len(_audit_rows("admin_user_updated", target_id, "user"))
    dcl_before = len(_dcl_rows("users", target_id))

    def boom(**kw):
        raise RuntimeError("inject: user dcl failure")

    monkeypatch.setattr(users_storage, "record_data_change", boom)

    with pytest.raises(RuntimeError, match="inject: user dcl failure"):
        users_storage.update_user(
            target_uuid, full_name=PII_NAME,
            actor_id=admin_id, actor_role="admin",
        )

    with SessionLocal() as db:
        assert db.query(User.full_name).filter(
            User.id == target_id).scalar() == name_before   # мутация откатана

    assert len(
        _audit_rows("admin_user_updated", target_id, "user")) == audit_before
    assert len(_dcl_rows("users", target_id)) == dcl_before


def test_card_dcl_failure_rolls_back_mutation_and_audit_together(
    client, monkeypatch,
):
    """Тот же инвариант для второй транзакционной модели: commit принадлежит
    appointments.service."""
    token, sup_id = _make_supervisor(client)
    card_id = _create_card(client, token)

    name_before = _card_field(card_id, "full_name")
    audit_before = len(_audit_rows(
        "unregistered_student_card_updated", card_id,
        "unregistered_student_card"))
    dcl_before = len(_dcl_rows("unregistered_student_cards", card_id))

    def boom(**kw):
        raise RuntimeError("inject: card dcl failure")

    monkeypatch.setattr(appt_storage, "record_data_change", boom)

    with pytest.raises(RuntimeError, match="inject: card dcl failure"):
        appt_service.update_unregistered_student_card(
            card_id, {"full_name": PII_NAME},
            current_user={"id": sup_id}, actor_role="supervisor",
        )

    assert _card_field(card_id, "full_name") == name_before   # мутация откатана
    assert len(_audit_rows(
        "unregistered_student_card_updated", card_id,
        "unregistered_student_card")) == audit_before
    assert len(_dcl_rows("unregistered_student_cards", card_id)) == dcl_before


# ══════════════════════════════════════════════════════════════════════════
# 6. Глобальная минимизация: ни одна DCL-строка не содержит значений
# ══════════════════════════════════════════════════════════════════════════

def test_no_dcl_row_for_pii_tables_ever_carries_values(client):
    """Сквозная проверка по ВСЕМ строкам обеих ПДн-таблиц в этой БД:
    old_values/new_values всегда NULL — значения ПДн не копируются."""
    token, _admin_id, _ = create_multi_role_user(client, ["admin"])
    target_id = _make_staff_target(client, token)
    client.patch(f"/api/admin/users/{_uuid_for(target_id)}",
                 headers=_auth(token), json={"full_name": PII_NAME})

    sup_token, _sup_id = _make_supervisor(client)
    card_id = _create_card(client, sup_token)
    client.patch(f"{CARDS_URL}/{card_id}", headers=_auth(sup_token),
                 json={"comment": PII_COMMENT})

    with SessionLocal() as db:
        rows = (
            db.query(DataChangeLog)
            .filter(DataChangeLog.table_name.in_(
                ["users", "unregistered_student_cards"]))
            .all()
        )
        for r in rows:
            db.expunge(r)

    assert rows, "ожидаются journal-строки для ПДн-таблиц"
    for row in rows:
        assert row.old_values is None, row.table_name
        assert row.new_values is None, row.table_name
        assert row.changed_fields                    # только имена, непусто
