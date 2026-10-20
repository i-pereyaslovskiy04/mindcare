"""
Stage 6-B — gated integration: field-level журнал (data_change_log) для
update_meeting_type / update_group_session.

Запуск ТОЛЬКО через Stage 1 isolated runner (scripts/isolated_test_db.py) при
безопасном TEST_DATABASE_URL; dev/prod запрещены.

Проверяет: одна audit_log paired_event + одна data_change_log строка на
generic PATCH; полный контракт DCL-строки (actor_id/actor_role/table_name/
record_id/operation/ip_address); симметрия ключей old_values/new_values;
отсутствие свободного текста/datetime в old_values/new_values; is_active /
booking_enabled / status НЕ попадают в DCL (в т.ч. combined PATCH); identical
PATCH — 0 audit_log и 0 data_change_log; совместный rollback mutation +
audit_log + DCL при failure injection внутри ОДНОЙ бизнес-транзакции.
Append-only журналы НЕ очищаются — уникальные entity id и before/after counts.

Requires: PostgreSQL on alembic head (d4a7b2c9f6e1), DATA_ENCRYPTION_KEY,
seeded roles.
"""
import uuid as _uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import pytest

from app.appointments import service as appt_service
from app.appointments import storage as appt_storage
from app.auth import storage as auth_storage
from app.db.session import SessionLocal
from app.db.models import AuditLog, DataChangeLog, GroupSession, MeetingType

PASSWORD = "SecurePass42!"
MOSCOW_TZ = timezone(timedelta(hours=3))
MT_URL = "/api/supervisor/meeting-types"
GS_URL = "/api/supervisor/group-sessions"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _make_user(client, role):
    suffix = _uuid.uuid4().hex[:10]
    email = f"integ_dcl_{role}_{suffix}@example.com"
    user = auth_storage.save_user({
        "name": f"DCLTest {role.capitalize()} {_uuid.uuid4().hex[:6]}",
        "email": email,
        "hashed_password": bcrypt.hashpw(
            PASSWORD.encode(), bcrypt.gensalt()).decode(),
        "role": role,
    })
    r = client.post("/api/auth/login",
                    json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["session_token"], int(user["id"])


def _audit_rows(event_type, entity_id):
    with SessionLocal() as db:
        rows = (
            db.query(AuditLog)
            .filter(AuditLog.event_type == event_type,
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
    assert row.table_name == table_name
    assert row.record_id == record_id
    assert row.operation == "UPDATE"
    assert row.actor_id == actor_id
    assert row.actor_role == actor_role
    # TestClient(client=("127.0.0.1", 50000)) → request.client.host.
    # str(...) — INET-колонка может вернуться как ipaddress.IPv4Address, а не
    # как plain str, в зависимости от адаптера psycopg2/SQLAlchemy.
    assert str(row.ip_address) == "127.0.0.1"


def _group_meeting_type():
    with SessionLocal() as db:
        mt = MeetingType(
            name=f"integ_dcl_grp_type_{_uuid.uuid4().hex[:6]}",
            duration_minutes=60, buffer_minutes=0, allow_in_person=False,
            allow_online=True, is_group=True, is_active=True,
            is_bookable=True, display_order=0,
        )
        db.add(mt)
        db.commit()
        return mt.id


def _future(hours=72):
    return (datetime.now(MOSCOW_TZ) + timedelta(hours=hours)).replace(
        minute=0, second=0, microsecond=0)


def _create_gs(client, tok, mt_id, psych_id, **over):
    payload = {
        "meeting_type_id": mt_id,
        "psychologist_id": psych_id,
        "title": f"integ_dcl_grp_{_uuid.uuid4().hex[:8]}",
        "starts_at": _future().isoformat(),
        "format": "online",
        "capacity": 10,
        "booking_enabled": True,
    }
    payload.update(over)
    return client.post(GS_URL, json=payload, headers=_auth(tok))


def _gs_id(gs_uuid: str) -> int:
    """GroupSessionRead отдаёт наружу только uuid (PATCH-путь — тоже по uuid);
    внутренний integer id — то, чем адресуются AuditLog.entity_id и
    DataChangeLog.record_id, поэтому его нужно разрешать отдельным запросом."""
    with SessionLocal() as db:
        return db.query(GroupSession.id).filter(
            GroupSession.uuid == gs_uuid).scalar()


# ══════════════════════════════════════════════════════════════════════════
# 1. meeting_types — name-only / value-enabled / combined / no-op
# ══════════════════════════════════════════════════════════════════════════

def test_mt_name_only_patch_writes_one_event_and_one_dcl_without_values(client):
    tok, sup_id = _make_user(client, "supervisor")
    secret = f"SECRETNAME_{_uuid.uuid4().hex}"
    mt_id = client.post(
        MT_URL, json={"name": f"mt_{_uuid.uuid4().hex[:8]}"},
        headers=_auth(tok),
    ).json()["id"]

    assert client.patch(
        f"{MT_URL}/{mt_id}", json={"name": secret, "description": "d"},
        headers=_auth(tok),
    ).status_code == 200

    arows = _audit_rows("meeting_type_updated", mt_id)
    assert len(arows) == 1
    drows = _dcl_rows("meeting_types", mt_id)
    assert len(drows) == 1

    row = drows[0]
    _assert_dcl_contract(row, "meeting_types", mt_id, sup_id, "supervisor")
    assert row.changed_fields == ["description", "name"]
    assert row.old_values is None
    assert row.new_values is None
    # свободный текст (название) не утекает в journal
    assert secret not in (row.changed_fields or [])
    assert secret != str(row.old_values)
    assert secret != str(row.new_values)


def test_mt_value_enabled_patch_writes_symmetric_old_new(client):
    tok, sup_id = _make_user(client, "supervisor")
    mt_id = client.post(
        MT_URL,
        json={"name": f"mt_{_uuid.uuid4().hex[:8]}", "duration_minutes": 50,
              "is_bookable": True},
        headers=_auth(tok),
    ).json()["id"]

    assert client.patch(
        f"{MT_URL}/{mt_id}",
        json={"duration_minutes": 75, "is_bookable": False},
        headers=_auth(tok),
    ).status_code == 200

    drows = _dcl_rows("meeting_types", mt_id)
    assert len(drows) == 1
    row = drows[0]
    _assert_dcl_contract(row, "meeting_types", mt_id, sup_id, "supervisor")
    assert row.changed_fields == ["duration_minutes", "is_bookable"]
    assert set(row.old_values) == set(row.new_values) == {
        "duration_minutes", "is_bookable",
    }
    assert row.old_values == {"duration_minutes": 50, "is_bookable": True}
    assert row.new_values == {"duration_minutes": 75, "is_bookable": False}


def test_mt_combined_patch_with_is_active_excludes_it_from_dcl(client):
    tok, sup_id = _make_user(client, "supervisor")
    mt_id = client.post(
        MT_URL,
        json={"name": f"mt_{_uuid.uuid4().hex[:8]}", "buffer_minutes": 10},
        headers=_auth(tok),
    ).json()["id"]

    assert client.patch(
        f"{MT_URL}/{mt_id}",
        json={"buffer_minutes": 25, "is_active": False},
        headers=_auth(tok),
    ).status_code == 200

    # ДВЕ непересекающиеся audit-строки (уже покрыто 5C-1), ОДНА DCL-строка.
    assert len(_audit_rows("meeting_type_updated", mt_id)) == 1
    assert len(_audit_rows("meeting_type_deactivated", mt_id)) == 1
    drows = _dcl_rows("meeting_types", mt_id)
    assert len(drows) == 1
    row = drows[0]
    assert row.changed_fields == ["buffer_minutes"]
    assert "is_active" not in row.changed_fields
    assert row.old_values == {"buffer_minutes": 10}
    assert row.new_values == {"buffer_minutes": 25}


def test_mt_transition_only_writes_zero_dcl(client):
    tok, _ = _make_user(client, "supervisor")
    mt_id = client.post(
        MT_URL, json={"name": f"mt_{_uuid.uuid4().hex[:8]}"},
        headers=_auth(tok),
    ).json()["id"]

    dcl_before = len(_dcl_rows("meeting_types", mt_id))
    assert client.patch(
        f"{MT_URL}/{mt_id}", json={"is_active": False}, headers=_auth(tok),
    ).status_code == 200
    assert len(_audit_rows("meeting_type_deactivated", mt_id)) == 1
    assert len(_dcl_rows("meeting_types", mt_id)) == dcl_before   # 0 добавлено


def test_mt_identical_patch_writes_zero_audit_and_zero_dcl(client):
    tok, _ = _make_user(client, "supervisor")
    mt_id = client.post(
        MT_URL,
        json={"name": f"mt_{_uuid.uuid4().hex[:8]}", "buffer_minutes": 10},
        headers=_auth(tok),
    ).json()["id"]

    audit_before = len(_audit_rows("meeting_type_updated", mt_id))
    dcl_before = len(_dcl_rows("meeting_types", mt_id))
    with SessionLocal() as db:
        updated_before = db.query(MeetingType.updated_at).filter(
            MeetingType.id == mt_id).scalar()

    assert client.patch(
        f"{MT_URL}/{mt_id}", json={"buffer_minutes": 10}, headers=_auth(tok),
    ).status_code == 200
    assert client.patch(
        f"{MT_URL}/{mt_id}", json={}, headers=_auth(tok),
    ).status_code == 200

    assert len(_audit_rows("meeting_type_updated", mt_id)) == audit_before
    assert len(_dcl_rows("meeting_types", mt_id)) == dcl_before
    with SessionLocal() as db:
        assert db.query(MeetingType.updated_at).filter(
            MeetingType.id == mt_id).scalar() == updated_before


def test_mt_datetime_and_free_text_never_appear_in_dcl_values(client):
    """description — свободный текст (name-only); updated_at — datetime,
    ни то, ни другое не должно попасть в old_values/new_values ни для какого
    поля этой таблицы."""
    tok, _ = _make_user(client, "supervisor")
    secret = f"FREE TEXT SECRET {_uuid.uuid4().hex}"
    mt_id = client.post(
        MT_URL, json={"name": f"mt_{_uuid.uuid4().hex[:8]}"},
        headers=_auth(tok),
    ).json()["id"]

    assert client.patch(
        f"{MT_URL}/{mt_id}",
        json={"description": secret, "duration_minutes": 90},
        headers=_auth(tok),
    ).status_code == 200

    row = _dcl_rows("meeting_types", mt_id)[-1]
    assert row.old_values == {"duration_minutes": 50}
    assert row.new_values == {"duration_minutes": 90}
    assert secret not in str(row.old_values)
    assert secret not in str(row.new_values)
    assert "updated_at" not in row.old_values
    assert "updated_at" not in row.new_values


# ══════════════════════════════════════════════════════════════════════════
# 2. group_sessions — name-only / value-enabled / combined / no-op
# ══════════════════════════════════════════════════════════════════════════

def test_gs_name_only_patch_writes_one_event_and_one_dcl_without_values(client):
    tok, sup_id = _make_user(client, "supervisor")
    psych = _make_user(client, "psychologist")[1]
    mt_id = _group_meeting_type()
    gs_uuid = _create_gs(client, tok, mt_id, psych).json()["uuid"]
    gs_id = _gs_id(gs_uuid)

    secret = f"SECRETTITLE_{_uuid.uuid4().hex}"
    assert client.patch(
        f"{GS_URL}/{gs_uuid}", json={"title": secret, "description": "d"},
        headers=_auth(tok),
    ).status_code == 200

    arows = _audit_rows("group_session_updated", gs_id)
    assert len(arows) == 1
    drows = _dcl_rows("group_sessions", gs_id)
    assert len(drows) == 1
    row = drows[0]
    _assert_dcl_contract(row, "group_sessions", gs_id, sup_id, "supervisor")
    assert row.changed_fields == ["description", "title"]
    assert row.old_values is None
    assert row.new_values is None
    assert secret not in str(row.old_values)
    assert secret not in str(row.new_values)


def test_gs_value_enabled_patch_writes_symmetric_old_new(client):
    tok, sup_id = _make_user(client, "supervisor")
    psych = _make_user(client, "psychologist")[1]
    mt_id = _group_meeting_type()
    mt2_id = _group_meeting_type()
    gs_uuid = _create_gs(
        client, tok, mt_id, psych, format="online", capacity=10,
    ).json()["uuid"]
    gs_id = _gs_id(gs_uuid)

    assert client.patch(
        f"{GS_URL}/{gs_uuid}",
        json={"capacity": 25, "meeting_type_id": mt2_id},
        headers=_auth(tok),
    ).status_code == 200

    drows = _dcl_rows("group_sessions", gs_id)
    assert len(drows) == 1
    row = drows[0]
    _assert_dcl_contract(row, "group_sessions", gs_id, sup_id, "supervisor")
    assert row.changed_fields == ["capacity", "meeting_type_id"]
    assert set(row.old_values) == set(row.new_values) == {
        "capacity", "meeting_type_id",
    }
    assert row.old_values == {"capacity": 10, "meeting_type_id": mt_id}
    assert row.new_values == {"capacity": 25, "meeting_type_id": mt2_id}


def test_gs_combined_patch_with_booking_and_status_excludes_them_from_dcl(client):
    tok, sup_id = _make_user(client, "supervisor")
    psych = _make_user(client, "psychologist")[1]
    mt_id = _group_meeting_type()
    gs_uuid = _create_gs(
        client, tok, mt_id, psych, booking_enabled=True,
    ).json()["uuid"]
    gs_id = _gs_id(gs_uuid)

    assert client.patch(
        f"{GS_URL}/{gs_uuid}",
        json={"capacity": 30, "booking_enabled": False, "status": "cancelled"},
        headers=_auth(tok),
    ).status_code == 200

    assert len(_audit_rows("group_session_updated", gs_id)) == 1
    assert len(_audit_rows("group_session_booking_closed", gs_id)) == 1
    assert len(_audit_rows("group_session_cancelled", gs_id)) == 1
    drows = _dcl_rows("group_sessions", gs_id)
    assert len(drows) == 1
    row = drows[0]
    assert row.changed_fields == ["capacity"]
    for leaked in ("booking_enabled", "status"):
        assert leaked not in row.changed_fields
    assert row.old_values == {"capacity": 10}
    assert row.new_values == {"capacity": 30}


def test_gs_transition_only_writes_zero_dcl(client):
    tok, _ = _make_user(client, "supervisor")
    psych = _make_user(client, "psychologist")[1]
    mt_id = _group_meeting_type()
    gs_uuid = _create_gs(
        client, tok, mt_id, psych, booking_enabled=True,
    ).json()["uuid"]
    gs_id = _gs_id(gs_uuid)

    dcl_before = len(_dcl_rows("group_sessions", gs_id))
    assert client.patch(
        f"{GS_URL}/{gs_uuid}", json={"booking_enabled": False},
        headers=_auth(tok),
    ).status_code == 200
    assert len(_audit_rows("group_session_booking_closed", gs_id)) == 1
    assert len(_dcl_rows("group_sessions", gs_id)) == dcl_before


def test_gs_identical_patch_writes_zero_audit_and_zero_dcl(client):
    tok, _ = _make_user(client, "supervisor")
    psych = _make_user(client, "psychologist")[1]
    mt_id = _group_meeting_type()
    r = _create_gs(
        client, tok, mt_id, psych, title="orig_title", capacity=10,
        booking_enabled=True,
    )
    gs_uuid = r.json()["uuid"]
    gs_id = _gs_id(gs_uuid)

    audit_before = len(_audit_rows("group_session_updated", gs_id))
    dcl_before = len(_dcl_rows("group_sessions", gs_id))
    with SessionLocal() as db:
        updated_before = db.query(GroupSession.updated_at).filter(
            GroupSession.id == gs_id).scalar()

    assert client.patch(
        f"{GS_URL}/{gs_uuid}",
        json={"title": "orig_title", "capacity": 10, "booking_enabled": True},
        headers=_auth(tok),
    ).status_code == 200

    assert len(_audit_rows("group_session_updated", gs_id)) == audit_before
    assert len(_dcl_rows("group_sessions", gs_id)) == dcl_before
    with SessionLocal() as db:
        assert db.query(GroupSession.updated_at).filter(
            GroupSession.id == gs_id).scalar() == updated_before


def test_gs_datetime_and_free_text_never_appear_in_dcl_values(client):
    """starts_at — datetime (name-only); title — свободный текст (name-only);
    ни то, ни другое не должно попасть в old_values/new_values."""
    tok, _ = _make_user(client, "supervisor")
    psych = _make_user(client, "psychologist")[1]
    mt_id = _group_meeting_type()
    gs_uuid = _create_gs(client, tok, mt_id, psych, capacity=10).json()["uuid"]
    gs_id = _gs_id(gs_uuid)

    secret = f"FREE TEXT SECRET {_uuid.uuid4().hex}"
    new_starts_at = _future(hours=200)
    assert client.patch(
        f"{GS_URL}/{gs_uuid}",
        json={"title": secret, "starts_at": new_starts_at.isoformat(),
              "capacity": 42},
        headers=_auth(tok),
    ).status_code == 200

    row = _dcl_rows("group_sessions", gs_id)[-1]
    assert row.old_values == {"capacity": 10}
    assert row.new_values == {"capacity": 42}
    assert secret not in str(row.old_values)
    assert secret not in str(row.new_values)
    assert "starts_at" not in row.old_values
    assert "starts_at" not in row.new_values


# ══════════════════════════════════════════════════════════════════════════
# 3. Совместный rollback mutation + audit_log + DCL (failure injection)
# ══════════════════════════════════════════════════════════════════════════

def test_mt_dcl_storage_failure_rolls_back_mutation_and_audit_together(
    client, monkeypatch,
):
    """DataChangeStorageError ПОСЛЕ generic record_event, но ДО commit сервиса
    → ВСЯ бизнес-транзакция откатывается: ни мутация, ни audit_log, ни DCL не
    сохраняются. Вызов ЧЕРЕЗ appt_service (владелец SessionLocal/commit) — не
    через HTTP, чтобы получить прямое исключение, а не HTTP 500 с потерянным
    типом ошибки."""
    tok, sup_id = _make_user(client, "supervisor")
    mt_id = client.post(
        MT_URL,
        json={"name": f"mt_{_uuid.uuid4().hex[:8]}", "duration_minutes": 50},
        headers=_auth(tok),
    ).json()["id"]

    def boom(**kw):
        raise RuntimeError("inject: dcl storage failure")

    monkeypatch.setattr(appt_storage, "record_data_change", boom)

    with pytest.raises(RuntimeError, match="inject: dcl storage failure"):
        appt_service.update_meeting_type(
            mt_id, {"duration_minutes": 999},
            actor_id=sup_id, actor_role="supervisor",
        )

    with SessionLocal() as db:
        current = db.query(MeetingType.duration_minutes).filter(
            MeetingType.id == mt_id).scalar()
        assert current == 50                      # мутация НЕ сохранена

    assert _audit_rows("meeting_type_updated", mt_id) == []   # audit НЕ сохранён
    assert _dcl_rows("meeting_types", mt_id) == []             # DCL НЕ сохранён


def test_gs_dcl_storage_failure_rolls_back_mutation_and_audit_together(
    client, monkeypatch,
):
    tok, sup_id = _make_user(client, "supervisor")
    psych = _make_user(client, "psychologist")[1]
    mt_id = _group_meeting_type()
    gs_uuid = _create_gs(client, tok, mt_id, psych, capacity=10).json()["uuid"]
    gs_id = _gs_id(gs_uuid)

    def boom(**kw):
        raise RuntimeError("inject: dcl storage failure")

    monkeypatch.setattr(appt_storage, "record_data_change", boom)

    with pytest.raises(RuntimeError, match="inject: dcl storage failure"):
        appt_service.update_group_session(
            gs_uuid, {"capacity": 999},
            actor_id=sup_id, actor_role="supervisor",
        )

    with SessionLocal() as db:
        current = db.query(GroupSession.capacity).filter(
            GroupSession.id == gs_id).scalar()
        assert current == 10                        # мутация НЕ сохранена

    assert _audit_rows("group_session_updated", gs_id) == []   # audit НЕ сохранён
    assert _dcl_rows("group_sessions", gs_id) == []              # DCL НЕ сохранён
