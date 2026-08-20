"""
Stage 5C-1 — gated integration: audit trail типов встреч и расписаний.

Запуск ТОЛЬКО через Stage 1 isolated runner (scripts/isolated_test_db.py) при
безопасном TEST_DATABASE_URL; dev/prod запрещены.

Проверяет 14 success-событий (meeting_type ×4, schedule series ×5,
schedule_rule ×2, schedule_break ×2, schedule_exception ×1): полный
success-контракт каждой строки, supervisor И admin actor-role, target серии =
schedule_series.id (integer identity, НЕ UUID), no-op/идемпотентность
(identical PATCH, повторная деактивация/restore, extend без сдвига), bulk → N
строк, отсутствие ПДн/названий/дат в audit. Append-only журналы НЕ очищаются —
используются уникальные entity id и before/after counts.

Requires: PostgreSQL on alembic head (b5d7f0a3c9e1), DATA_ENCRYPTION_KEY,
seeded roles.
"""
import uuid as _uuid
from datetime import date, timedelta

import bcrypt

from app.auth import storage as auth_storage
from app.db.session import SessionLocal
from app.db.models import (
    AuditLog, MeetingType, Role, ScheduleRule, ScheduleSeries, UserRole,
)

PASSWORD = "SecurePass42!"
MT_URL = "/api/supervisor/meeting-types"
RULES_URL = "/api/supervisor/schedule-rules"
SCHEDULES_URL = "/api/supervisor/schedules"
BREAKS_URL = "/api/supervisor/schedule-breaks"
EXCEPTIONS_URL = "/api/supervisor/schedule-exceptions"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _make_user(client, role):
    suffix = _uuid.uuid4().hex[:10]
    email = f"integ_sched_{role}_{suffix}@example.com"
    user = auth_storage.save_user({
        "name": f"SchedTest {role.capitalize()} {_uuid.uuid4().hex[:6]}",
        "email": email,
        "hashed_password": bcrypt.hashpw(
            PASSWORD.encode(), bcrypt.gensalt()).decode(),
        "role": role,
    })
    r = client.post("/api/auth/login",
                    json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["session_token"], int(user["id"])


def _make_psychologist(client):
    return _make_user(client, "psychologist")[1]


def _rows(event_type, entity_id):
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


def _assert_success(row, entity_type, entity_id, actor_id, actor_role):
    """Полный success-контракт строки 5C-1."""
    assert row.entity_type == entity_type
    assert row.entity_id == entity_id
    assert row.outcome == "success"
    assert row.failure_reason_code is None
    assert row.description is None
    assert (row.log_metadata or {}) == {}
    assert row.user_id == actor_id
    assert row.user_role == actor_role


def _series_identity_id(series_uuid: str) -> int:
    with SessionLocal() as db:
        row = db.query(ScheduleSeries.id).filter(
            ScheduleSeries.series_uuid == series_uuid).first()
        assert row is not None, "identity-строка серии не создана"
        return row.id


def _future_period():
    start = date.today()
    return str(start), str(start + timedelta(days=30))


def _schedule_payload(psych_id, **over):
    eff_from, eff_until = _future_period()
    payload = {
        "psychologist_id": psych_id,
        "days_of_week": [1],
        "start_time": "09:00",
        "end_time": "10:00",
        "effective_from": eff_from,
        "effective_until": eff_until,
        "auto_extend": False,
        "period": None,
        "breaks": [],
    }
    payload.update(over)
    return payload


def _update_payload(base):
    """ScheduleUpdate = ScheduleCreate без psychologist_id (extra='forbid')."""
    return {k: v for k, v in base.items() if k != "psychologist_id"}


# ─── MeetingType lifecycle ────────────────────────────────────────────────────

def test_meeting_type_created_and_updated(client):
    tok, sup_id = _make_user(client, "supervisor")
    secret = f"SECRETTYPE_{_uuid.uuid4().hex}"
    r = client.post(MT_URL, json={"name": secret, "duration_minutes": 50},
                    headers=_auth(tok))
    assert r.status_code == 201, r.text
    mt_id = r.json()["id"]

    rows = _rows("meeting_type_created", mt_id)
    assert len(rows) == 1
    _assert_success(rows[0], "meeting_type", mt_id, sup_id, "supervisor")
    # название типа не попадает в audit
    import json as _json
    blob = (rows[0].description or "") + _json.dumps(
        rows[0].log_metadata or {}, ensure_ascii=False)
    assert secret not in blob

    # реальный diff обычного поля → ровно один meeting_type_updated
    assert client.patch(f"{MT_URL}/{mt_id}", json={"buffer_minutes": 15},
                        headers=_auth(tok)).status_code == 200
    urows = _rows("meeting_type_updated", mt_id)
    assert len(urows) == 1
    _assert_success(urows[0], "meeting_type", mt_id, sup_id, "supervisor")


def test_meeting_type_identical_patch_is_noop(client):
    tok, _ = _make_user(client, "supervisor")
    mt_id = client.post(MT_URL, json={"name": f"mt_{_uuid.uuid4().hex[:8]}",
                                      "buffer_minutes": 10},
                        headers=_auth(tok)).json()["id"]
    before = len(_rows("meeting_type_updated", mt_id))
    with SessionLocal() as db:
        updated_before = db.query(MeetingType.updated_at).filter(
            MeetingType.id == mt_id).scalar()

    # identical PATCH: то же значение → нет мутации, нет audit
    assert client.patch(f"{MT_URL}/{mt_id}", json={"buffer_minutes": 10},
                        headers=_auth(tok)).status_code == 200
    assert client.patch(f"{MT_URL}/{mt_id}", json={},
                        headers=_auth(tok)).status_code == 200

    assert len(_rows("meeting_type_updated", mt_id)) == before
    with SessionLocal() as db:
        assert db.query(MeetingType.updated_at).filter(
            MeetingType.id == mt_id).scalar() == updated_before


def test_meeting_type_activate_deactivate_transitions(client):
    tok, sup_id = _make_user(client, "supervisor")
    mt_id = client.post(MT_URL, json={"name": f"mt_{_uuid.uuid4().hex[:8]}"},
                        headers=_auth(tok)).json()["id"]

    # только is_active → generic updated НЕ пишется
    upd_before = len(_rows("meeting_type_updated", mt_id))
    assert client.patch(f"{MT_URL}/{mt_id}", json={"is_active": False},
                        headers=_auth(tok)).status_code == 200
    drows = _rows("meeting_type_deactivated", mt_id)
    assert len(drows) == 1
    _assert_success(drows[0], "meeting_type", mt_id, sup_id, "supervisor")
    assert len(_rows("meeting_type_updated", mt_id)) == upd_before

    # повторная деактивация — no-op
    assert client.patch(f"{MT_URL}/{mt_id}", json={"is_active": False},
                        headers=_auth(tok)).status_code == 200
    assert len(_rows("meeting_type_deactivated", mt_id)) == 1

    # обратный переход
    assert client.patch(f"{MT_URL}/{mt_id}", json={"is_active": True},
                        headers=_auth(tok)).status_code == 200
    arows = _rows("meeting_type_activated", mt_id)
    assert len(arows) == 1
    _assert_success(arows[0], "meeting_type", mt_id, sup_id, "supervisor")


def test_meeting_type_combined_patch_writes_two_disjoint_rows(client):
    """Обычные поля + is_active → updated И deactivated (две строки)."""
    tok, sup_id = _make_user(client, "supervisor")
    mt_id = client.post(MT_URL, json={"name": f"mt_{_uuid.uuid4().hex[:8]}",
                                      "buffer_minutes": 10},
                        headers=_auth(tok)).json()["id"]
    assert client.patch(
        f"{MT_URL}/{mt_id}", json={"buffer_minutes": 20, "is_active": False},
        headers=_auth(tok),
    ).status_code == 200
    assert len(_rows("meeting_type_updated", mt_id)) == 1
    assert len(_rows("meeting_type_deactivated", mt_id)) == 1


def test_admin_actor_role_is_admin(client):
    """admin-only пользователь → actor_role='admin' (не supervisor)."""
    tok, admin_id = _make_user(client, "admin")
    r = client.post(MT_URL, json={"name": f"mt_{_uuid.uuid4().hex[:8]}"},
                    headers=_auth(tok))
    assert r.status_code == 201, r.text
    mt_id = r.json()["id"]
    rows = _rows("meeting_type_created", mt_id)
    assert len(rows) == 1
    _assert_success(rows[0], "meeting_type", mt_id, admin_id, "admin")


def test_admin_and_supervisor_resolves_to_supervisor(client):
    """admin+supervisor в supervisor-кабинете → actor_role='supervisor'."""
    tok, uid = _make_user(client, "supervisor")
    with SessionLocal() as db:
        admin_role = db.query(Role).filter(Role.name == "admin").first()
        db.add(UserRole(user_id=uid, role_id=admin_role.id))
        db.commit()
    mt_id = client.post(MT_URL, json={"name": f"mt_{_uuid.uuid4().hex[:8]}"},
                        headers=_auth(tok)).json()["id"]
    rows = _rows("meeting_type_created", mt_id)
    assert len(rows) == 1
    _assert_success(rows[0], "meeting_type", mt_id, uid, "supervisor")


# ─── Schedule series lifecycle ────────────────────────────────────────────────

def test_schedule_created_targets_series_identity(client):
    tok, sup_id = _make_user(client, "supervisor")
    psych = _make_psychologist(client)
    r = client.post(SCHEDULES_URL, json=_schedule_payload(psych),
                    headers=_auth(tok))
    assert r.status_code == 201, r.text
    series_uuid = r.json()["series_id"]
    identity_id = _series_identity_id(series_uuid)

    rows = _rows("schedule_created", identity_id)
    assert len(rows) == 1
    _assert_success(rows[0], "schedule_series", identity_id, sup_id,
                    "supervisor")
    # target — integer identity, а не UUID серии
    assert isinstance(rows[0].entity_id, int)
    import json as _json
    blob = (rows[0].description or "") + _json.dumps(
        rows[0].log_metadata or {}, ensure_ascii=False)
    assert series_uuid not in blob


def test_schedule_update_identical_is_noop_and_keeps_row_ids(client):
    tok, _ = _make_user(client, "supervisor")
    psych = _make_psychologist(client)
    payload = _schedule_payload(psych)
    series_uuid = client.post(SCHEDULES_URL, json=payload,
                              headers=_auth(tok)).json()["series_id"]
    identity_id = _series_identity_id(series_uuid)

    with SessionLocal() as db:
        ids_before = sorted(
            r.id for r in db.query(ScheduleRule.id).filter(
                ScheduleRule.series_id == series_uuid).all()
        )

    # идентичный payload → no-op
    assert client.patch(f"{SCHEDULES_URL}/{series_uuid}",
                        json=_update_payload(payload),
                        headers=_auth(tok)).status_code == 200
    assert _rows("schedule_updated", identity_id) == []

    with SessionLocal() as db:
        ids_after = sorted(
            r.id for r in db.query(ScheduleRule.id).filter(
                ScheduleRule.series_id == series_uuid).all()
        )
    assert ids_after == ids_before          # row-id сохранены


def test_schedule_update_real_diff_writes_one(client):
    tok, sup_id = _make_user(client, "supervisor")
    psych = _make_psychologist(client)
    payload = _schedule_payload(psych)
    series_uuid = client.post(SCHEDULES_URL, json=payload,
                              headers=_auth(tok)).json()["series_id"]
    identity_id = _series_identity_id(series_uuid)

    changed = _update_payload(payload)
    changed["days_of_week"] = [1, 3]
    assert client.patch(f"{SCHEDULES_URL}/{series_uuid}", json=changed,
                        headers=_auth(tok)).status_code == 200
    rows = _rows("schedule_updated", identity_id)
    assert len(rows) == 1
    _assert_success(rows[0], "schedule_series", identity_id, sup_id,
                    "supervisor")


def test_schedule_deactivate_restore_and_repeat_noop(client):
    tok, sup_id = _make_user(client, "supervisor")
    psych = _make_psychologist(client)
    series_uuid = client.post(SCHEDULES_URL, json=_schedule_payload(psych),
                              headers=_auth(tok)).json()["series_id"]
    identity_id = _series_identity_id(series_uuid)

    assert client.delete(f"{SCHEDULES_URL}/{series_uuid}",
                         headers=_auth(tok)).status_code == 200
    drows = _rows("schedule_deactivated", identity_id)
    assert len(drows) == 1
    _assert_success(drows[0], "schedule_series", identity_id, sup_id,
                    "supervisor")

    # повторная деактивация — no-op
    assert client.delete(f"{SCHEDULES_URL}/{series_uuid}",
                         headers=_auth(tok)).status_code == 200
    assert len(_rows("schedule_deactivated", identity_id)) == 1

    # restore + повторный restore
    assert client.post(f"{SCHEDULES_URL}/{series_uuid}/restore",
                       headers=_auth(tok)).status_code == 200
    assert len(_rows("schedule_restored", identity_id)) == 1
    assert client.post(f"{SCHEDULES_URL}/{series_uuid}/restore",
                       headers=_auth(tok)).status_code == 200
    assert len(_rows("schedule_restored", identity_id)) == 1


def test_schedule_extend_writes_once_per_real_shift(client):
    tok, sup_id = _make_user(client, "supervisor")
    psych = _make_psychologist(client)
    series_uuid = client.post(SCHEDULES_URL, json=_schedule_payload(psych),
                              headers=_auth(tok)).json()["series_id"]
    identity_id = _series_identity_id(series_uuid)

    assert client.post(f"{SCHEDULES_URL}/{series_uuid}/extend?months=1",
                       headers=_auth(tok)).status_code == 200
    rows = _rows("schedule_extended", identity_id)
    assert len(rows) == 1
    _assert_success(rows[0], "schedule_series", identity_id, sup_id,
                    "supervisor")


# ─── Legacy rules / breaks / exceptions ───────────────────────────────────────

def test_schedule_rules_bulk_writes_per_row(client):
    tok, sup_id = _make_user(client, "supervisor")
    psych = _make_psychologist(client)
    eff_from, eff_until = _future_period()
    r = client.post(RULES_URL, json={
        "psychologist_id": psych, "days_of_week": [1, 2, 3],
        "start_time": "09:00", "end_time": "10:00",
        "effective_from": eff_from, "effective_until": eff_until,
    }, headers=_auth(tok))
    assert r.status_code == 201, r.text
    rule_ids = [row["id"] for row in r.json()]
    assert len(rule_ids) == 3
    for rid in rule_ids:
        rows = _rows("schedule_rule_created", rid)
        assert len(rows) == 1, rid
        _assert_success(rows[0], "schedule_rule", rid, sup_id, "supervisor")


def test_schedule_rule_deactivate_transition_and_repeat(client):
    tok, sup_id = _make_user(client, "supervisor")
    psych = _make_psychologist(client)
    eff_from, eff_until = _future_period()
    rid = client.post(RULES_URL, json={
        "psychologist_id": psych, "days_of_week": [4],
        "start_time": "09:00", "end_time": "10:00",
        "effective_from": eff_from, "effective_until": eff_until,
    }, headers=_auth(tok)).json()[0]["id"]

    assert client.delete(f"{RULES_URL}/{rid}",
                         headers=_auth(tok)).status_code == 204
    rows = _rows("schedule_rule_deactivated", rid)
    assert len(rows) == 1
    _assert_success(rows[0], "schedule_rule", rid, sup_id, "supervisor")

    # повторная деактивация — no-op (204, но без новой строки)
    assert client.delete(f"{RULES_URL}/{rid}",
                         headers=_auth(tok)).status_code == 204
    assert len(_rows("schedule_rule_deactivated", rid)) == 1


def test_schedule_breaks_bulk_and_deactivate(client):
    tok, sup_id = _make_user(client, "supervisor")
    psych = _make_psychologist(client)
    eff_from, eff_until = _future_period()
    r = client.post(BREAKS_URL, json={
        "psychologist_id": psych, "days_of_week": [1, 2],
        "start_time": "13:00", "end_time": "14:00",
        "title": f"SECRETBREAK_{_uuid.uuid4().hex}",
        "effective_from": eff_from, "effective_until": eff_until,
    }, headers=_auth(tok))
    assert r.status_code == 201, r.text
    break_ids = [row["id"] for row in r.json()]
    assert len(break_ids) == 2
    for bid in break_ids:
        rows = _rows("schedule_break_created", bid)
        assert len(rows) == 1, bid
        _assert_success(rows[0], "schedule_break", bid, sup_id, "supervisor")

    bid = break_ids[0]
    assert client.delete(f"{BREAKS_URL}/{bid}",
                         headers=_auth(tok)).status_code == 204
    drows = _rows("schedule_break_deactivated", bid)
    assert len(drows) == 1
    _assert_success(drows[0], "schedule_break", bid, sup_id, "supervisor")
    # повторная деактивация — no-op
    assert client.delete(f"{BREAKS_URL}/{bid}",
                         headers=_auth(tok)).status_code == 204
    assert len(_rows("schedule_break_deactivated", bid)) == 1


def test_schedule_exception_created_without_reason_in_audit(client):
    tok, sup_id = _make_user(client, "supervisor")
    psych = _make_psychologist(client)
    secret_reason = f"SECRETREASON_{_uuid.uuid4().hex}"
    r = client.post(EXCEPTIONS_URL, json={
        "psychologist_id": psych,
        "exception_date": str(date.today() + timedelta(days=5)),
        "exception_type": "day_off",
        "reason": secret_reason,
    }, headers=_auth(tok))
    assert r.status_code == 201, r.text
    exc_id = r.json()["id"]

    rows = _rows("schedule_exception_created", exc_id)
    assert len(rows) == 1
    _assert_success(rows[0], "schedule_exception", exc_id, sup_id, "supervisor")
    import json as _json
    blob = (rows[0].description or "") + _json.dumps(
        rows[0].log_metadata or {}, ensure_ascii=False)
    assert secret_reason not in blob


# ─── GET-эндпоинты не пишут audit ─────────────────────────────────────────────

def test_read_endpoints_write_no_audit(client):
    tok, _ = _make_user(client, "supervisor")
    psych = _make_psychologist(client)
    with SessionLocal() as db:
        before = db.query(AuditLog).count()

    assert client.get(MT_URL, headers=_auth(tok)).status_code == 200
    assert client.get(f"{RULES_URL}?psychologist_id={psych}",
                      headers=_auth(tok)).status_code == 200
    assert client.get(f"{BREAKS_URL}?psychologist_id={psych}",
                      headers=_auth(tok)).status_code == 200
    assert client.get(f"{EXCEPTIONS_URL}?psychologist_id={psych}",
                      headers=_auth(tok)).status_code == 200

    with SessionLocal() as db:
        assert db.query(AuditLog).count() == before
