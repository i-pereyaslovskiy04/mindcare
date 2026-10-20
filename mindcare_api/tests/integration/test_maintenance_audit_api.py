"""
Stage 5C-3 — gated integration: system maintenance audit.

Запуск ТОЛЬКО через Stage 1 isolated runner (scripts/isolated_test_db.py) при
безопасном TEST_DATABASE_URL; dev/prod запрещены.

Проверяет 2 SYSTEM-события (group_session_completed, schedule_auto_extended):
полный success-контракт с `user_id IS NULL` и `user_role='system'`; completion
только через явный job (GET/list/register больше НЕ мутируют status и не пишут
audit); идемпотентность повторного прогона; dry-run auto-extend → 0 сохранённых
строк и 0 мутаций; событие только при фактическом сдвиге. Append-only журналы НЕ
очищаются — уникальные entity id и before/after counts.
"""
import uuid as _uuid
from datetime import date, datetime, timedelta, timezone

import bcrypt

from app.appointments import service as appt_service
from app.auth import storage as auth_storage
from app.db.session import SessionLocal
from app.db.models import (
    AuditLog, GroupSession, MeetingType, ScheduleRule, ScheduleSeries,
)

PASSWORD = "SecurePass42!"
MOSCOW_TZ = timezone(timedelta(hours=3))
GS_URL = "/api/supervisor/group-sessions"
STUDENT_GS_URL = "/api/group-sessions"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _make_user(client, role):
    suffix = _uuid.uuid4().hex[:10]
    email = f"integ_mnt_{role}_{suffix}@example.com"
    user = auth_storage.save_user({
        "name": f"MntTest {role.capitalize()} {_uuid.uuid4().hex[:6]}",
        "email": email,
        "hashed_password": bcrypt.hashpw(
            PASSWORD.encode(), bcrypt.gensalt()).decode(),
        "role": role,
    })
    r = client.post("/api/auth/login",
                    json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["session_token"], int(user["id"])


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


def _assert_system_success(row, entity_type, entity_id):
    """Полный success-контракт SYSTEM-строки."""
    assert row.entity_type == entity_type
    assert row.entity_id == entity_id
    assert row.outcome == "success"
    assert row.failure_reason_code is None
    assert row.description is None
    assert (row.log_metadata or {}) == {}
    assert row.user_id is None                 # system actor
    assert row.user_role == "system"


def _group_meeting_type():
    with SessionLocal() as db:
        mt = MeetingType(
            name=f"integ_mnt_type_{_uuid.uuid4().hex[:6]}", duration_minutes=60,
            buffer_minutes=0, allow_in_person=False, allow_online=True,
            is_group=True, is_active=True, is_bookable=True, display_order=0,
        )
        db.add(mt)
        db.commit()
        return mt.id


def _make_past_group_session(psych_id: int, mt_id: int) -> int:
    """Занятие, время которого уже наступило (прямой INSERT — HTTP не даёт
    создать занятие в прошлом)."""
    past = datetime.now(MOSCOW_TZ) - timedelta(hours=2)
    with SessionLocal() as db:
        gs = GroupSession(
            uuid=_uuid.uuid4(), meeting_type_id=mt_id,
            psychologist_id=psych_id, title=f"past_{_uuid.uuid4().hex[:8]}",
            starts_at=past, format="online", capacity=10,
            booking_enabled=True, status="scheduled",
        )
        db.add(gs)
        db.commit()
        return gs.id


def _gs_state(gs_id: int):
    with SessionLocal() as db:
        row = db.query(
            GroupSession.status, GroupSession.booking_enabled
        ).filter(GroupSession.id == gs_id).first()
        return row.status, row.booking_enabled


# ─── group_session_completed (CLI job) ────────────────────────────────────────

def test_completion_job_writes_system_event_per_transition(client):
    psych = _make_user(client, "psychologist")[1]
    mt_id = _group_meeting_type()
    gs_id = _make_past_group_session(psych, mt_id)

    assert _gs_state(gs_id) == ("scheduled", True)

    result = appt_service.complete_due_group_sessions_job()
    assert result["completed_sessions"] >= 1

    assert _gs_state(gs_id) == ("completed", False)
    rows = _rows("group_session_completed", gs_id)
    assert len(rows) == 1
    _assert_system_success(rows[0], "group_session", gs_id)


def test_completion_job_is_idempotent(client):
    """Повторный прогон не создаёт вторую строку — предикат уже не совпадает."""
    psych = _make_user(client, "psychologist")[1]
    mt_id = _group_meeting_type()
    gs_id = _make_past_group_session(psych, mt_id)

    appt_service.complete_due_group_sessions_job()
    assert len(_rows("group_session_completed", gs_id)) == 1

    appt_service.complete_due_group_sessions_job()
    assert len(_rows("group_session_completed", gs_id)) == 1


def test_future_session_is_not_completed(client):
    """Занятие в будущем не трогается и не аудируется."""
    tok, _ = _make_user(client, "supervisor")
    psych = _make_user(client, "psychologist")[1]
    mt_id = _group_meeting_type()
    future = (datetime.now(MOSCOW_TZ) + timedelta(hours=72)).replace(
        minute=0, second=0, microsecond=0)
    r = client.post(GS_URL, json={
        "meeting_type_id": mt_id, "psychologist_id": psych,
        "title": f"future_{_uuid.uuid4().hex[:8]}",
        "starts_at": future.isoformat(), "format": "online",
        "capacity": 10, "booking_enabled": True,
    }, headers=_auth(tok))
    assert r.status_code == 201, r.text
    with SessionLocal() as db:
        gs_id = db.query(GroupSession.id).filter(
            GroupSession.uuid == r.json()["uuid"]).scalar()

    appt_service.complete_due_group_sessions_job()

    assert _gs_state(gs_id) == ("scheduled", True)
    assert _rows("group_session_completed", gs_id) == []


# ─── GET/list/register больше НЕ мутируют (вариант B) ─────────────────────────

def test_read_paths_do_not_complete_or_audit(client):
    """Просроченное занятие остаётся `scheduled` после GET/list — read-пути
    больше не выполняют maintenance и не пишут audit."""
    tok_sup, _ = _make_user(client, "supervisor")
    tok_psy, psych = _make_user(client, "psychologist")
    tok_stu, _ = _make_user(client, "student")
    mt_id = _group_meeting_type()
    gs_id = _make_past_group_session(psych, mt_id)

    with SessionLocal() as db:
        audit_before = db.query(AuditLog).count()

    assert client.get(GS_URL, headers=_auth(tok_sup)).status_code == 200
    assert client.get("/api/psychologist/group-sessions",
                      headers=_auth(tok_psy)).status_code == 200
    assert client.get(STUDENT_GS_URL,
                      headers=_auth(tok_stu)).status_code == 200

    # статус НЕ изменён read-путями
    assert _gs_state(gs_id) == ("scheduled", True)
    assert _rows("group_session_completed", gs_id) == []
    with SessionLocal() as db:
        assert db.query(AuditLog).count() == audit_before


def test_register_does_not_complete_but_still_rejects_past_session(client):
    """Регистрация не выполняет maintenance, но lead time всё равно защищает:
    запись на начавшееся занятие отклоняется независимо от `status`."""
    tok_stu, _ = _make_user(client, "student")
    psych = _make_user(client, "psychologist")[1]
    mt_id = _group_meeting_type()
    gs_id = _make_past_group_session(psych, mt_id)
    with SessionLocal() as db:
        gs_uuid = str(db.query(GroupSession.uuid).filter(
            GroupSession.id == gs_id).scalar())

    r = client.post(f"{STUDENT_GS_URL}/{gs_uuid}/register",
                    headers=_auth(tok_stu))
    assert r.status_code == 422, r.text        # lead time

    # регистрация не выполнила completion
    assert _gs_state(gs_id) == ("scheduled", True)
    assert _rows("group_session_completed", gs_id) == []


# ─── schedule_auto_extended ───────────────────────────────────────────────────

def _make_auto_extend_series(psych_id: int) -> tuple[str, int]:
    """Активная серия с auto_extend и близкой границей (due)."""
    series_uuid = _uuid.uuid4()
    soon = date.today() + timedelta(days=3)
    with SessionLocal() as db:
        db.add(ScheduleSeries(series_uuid=series_uuid,
                              psychologist_id=psych_id))
        db.flush()
        identity_id = db.query(ScheduleSeries.id).filter(
            ScheduleSeries.series_uuid == series_uuid).scalar()
        db.add(ScheduleRule(
            psychologist_id=psych_id, day_of_week=1,
            start_time="09:00", end_time="10:00", series_id=series_uuid,
            effective_from=date.today() - timedelta(days=1),
            effective_until=soon, is_active=True, auto_extend=True,
        ))
        db.commit()
    return str(series_uuid), identity_id


def test_auto_extend_writes_system_event_on_real_shift(client):
    psych = _make_user(client, "psychologist")[1]
    series_uuid, identity_id = _make_auto_extend_series(psych)

    with SessionLocal() as db:
        before = db.query(ScheduleRule.effective_until).filter(
            ScheduleRule.series_id == series_uuid).scalar()

    result = appt_service.auto_extend_schedules(within_days=14, months=1)
    assert result["dry_run"] is False
    assert result["extended_series"] >= 1

    with SessionLocal() as db:
        after = db.query(ScheduleRule.effective_until).filter(
            ScheduleRule.series_id == series_uuid).scalar()
    assert after > before                        # реальный сдвиг

    rows = _rows("schedule_auto_extended", identity_id)
    assert len(rows) == 1
    _assert_system_success(rows[0], "schedule_series", identity_id)


def test_auto_extend_dry_run_writes_nothing_and_does_not_mutate(client):
    psych = _make_user(client, "psychologist")[1]
    series_uuid, identity_id = _make_auto_extend_series(psych)

    with SessionLocal() as db:
        before = db.query(ScheduleRule.effective_until).filter(
            ScheduleRule.series_id == series_uuid).scalar()
        audit_before = db.query(AuditLog).count()

    result = appt_service.auto_extend_schedules(
        within_days=14, months=1, dry_run=True)
    assert result["dry_run"] is True
    assert result["notified"] == 0

    with SessionLocal() as db:
        after = db.query(ScheduleRule.effective_until).filter(
            ScheduleRule.series_id == series_uuid).scalar()
        # 0 сохранённых audit-строк и 0 мутаций
        assert db.query(AuditLog).count() == audit_before
    assert after == before
    assert _rows("schedule_auto_extended", identity_id) == []


def test_auto_extend_second_run_is_noop(client):
    """После продления серия выпадает из due — второго события нет."""
    psych = _make_user(client, "psychologist")[1]
    series_uuid, identity_id = _make_auto_extend_series(psych)

    appt_service.auto_extend_schedules(within_days=14, months=1)
    assert len(_rows("schedule_auto_extended", identity_id)) == 1

    appt_service.auto_extend_schedules(within_days=14, months=1)
    assert len(_rows("schedule_auto_extended", identity_id)) == 1
