"""
Storage layer для модуля appointments.
Все запросы к БД изолированы здесь.
"""

from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

import hashlib

import sqlalchemy as sa
from sqlalchemy import or_

from app.core.normalization import normalize_email
from app.db.models import (
    Appointment,
    GroupSession,
    GroupSessionRegistration,
    MeetingType,
    ScheduleBreak,
    ScheduleException,
    ScheduleRule,
    TherapyEngagement,
    UnregisteredStudentCard,
    User,
)

# Moscow is UTC+3, no DST since 2014
MOSCOW_TZ = timezone(timedelta(hours=3))

# Статусы, блокирующие слот
BLOCKING_STATUSES = ("pending_confirmation", "scheduled", "confirmed")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now_moscow() -> datetime:
    return datetime.now(MOSCOW_TZ)


def _appointment_to_dict(appt: Appointment, db) -> dict:
    """Convert ORM Appointment to serialisable dict with embedded refs.

    Субъект записи — либо зарегистрированный студент (client_id), либо карточка
    незарегистрированного студента (unregistered_student_card_id); ровно один.
    """
    student = (
        db.query(User).filter(User.id == appt.client_id).first()
        if appt.client_id else None
    )
    psych = db.query(User).filter(User.id == appt.psychologist_id).first()
    card = (
        db.query(UnregisteredStudentCard)
        .filter(UnregisteredStudentCard.id == appt.unregistered_student_card_id)
        .first()
        if appt.unregistered_student_card_id else None
    )
    mt = (
        db.query(MeetingType).filter(MeetingType.id == appt.meeting_type_id).first()
        if appt.meeting_type_id else None
    )
    return {
        "uuid":                str(appt.uuid),
        "client_id":           appt.client_id,
        "unregistered_student_card_id": appt.unregistered_student_card_id,
        "psychologist_id":     appt.psychologist_id,
        "engagement_id":       appt.engagement_id,
        "meeting_type_id":     appt.meeting_type_id,
        "meeting_type_name":   mt.name if mt else None,
        "meeting_type_duration_minutes": mt.duration_minutes if mt else None,
        "starts_at":           appt.starts_at,
        "ends_at":             appt.ends_at,
        "duration_minutes":    appt.duration_minutes,
        "modality":            appt.modality,
        "topic":               appt.topic,
        "status":              appt.status,
        "cancellation_reason": appt.cancellation_reason,
        "decline_reason":      appt.decline_reason,
        "booking_source":      appt.booking_source,
        "created_by":          appt.created_by,
        "created_at":          appt.created_at,
        "updated_at":          appt.updated_at,
        "student": {
            "id":        student.id,
            "uuid":      str(student.uuid),
            "full_name": student.full_name,
            "email":     student.email,
        } if student else None,
        "psychologist": {
            "id":        psych.id,
            "uuid":      str(psych.uuid),
            "full_name": psych.full_name,
            "email":     psych.email,
        } if psych else None,
        "unregistered_student_card": _card_brief(card) if card else None,
    }


# ── Engagement lookup ─────────────────────────────────────────────────────────

def get_active_engagement(client_id: int, db) -> Optional[TherapyEngagement]:
    """Return active TherapyEngagement for a student, or None."""
    return (
        db.query(TherapyEngagement)
        .filter(
            TherapyEngagement.client_id == client_id,
            TherapyEngagement.status == "active",
            TherapyEngagement.ended_at.is_(None),
        )
        .first()
    )


def get_active_engagement_with(
    client_id: int, psychologist_id: int, db
) -> Optional[TherapyEngagement]:
    """Active engagement between a specific student and psychologist, or None."""
    return (
        db.query(TherapyEngagement)
        .filter(
            TherapyEngagement.client_id == client_id,
            TherapyEngagement.psychologist_id == psychologist_id,
            TherapyEngagement.status == "active",
            TherapyEngagement.ended_at.is_(None),
        )
        .first()
    )


def get_user(user_id: int, db) -> Optional[User]:
    return (
        db.query(User)
        .filter(User.id == int(user_id), User.deleted_at.is_(None))
        .first()
    )


# ── Slot generation ────────────────────────────────────────────────────────────
#
# Модель (важно):
#   - длительность слота и буфер берутся из MeetingType, НЕ из расписания;
#   - ScheduleRule задаёт только рабочие окна (доступность);
#   - ScheduleBreak (повтор по дню недели) и ScheduleException 'unavailable'
#     вырезают часть окна; 'extra_availability' добавляет окно; 'day_off' —
#     день полностью нерабочий;
#   - структурные слоты (валидность по расписанию) НЕ учитывают занятость;
#     занятость (записи + групповые занятия) фильтруется отдельно для отображения
#     и проверяется через is_slot_blocked / is_group_session_overlap при записи.

def _combine_msk(target_date: date, t: time) -> datetime:
    return datetime.combine(target_date, t).replace(tzinfo=MOSCOW_TZ)


def _overlaps(a_start, a_end, ranges) -> bool:
    return any(
        a_start < r_end and a_end > r_start for r_start, r_end in ranges
    )


def _working_windows(
    psychologist_id: int,
    target_date: date,
    db,
) -> list[tuple[datetime, datetime]]:
    """Availability windows (Moscow-aware) for a date.

    Schedule v3: working windows are NOT tied to a meeting type — all active
    ScheduleRules for the weekday count as availability (legacy rules with a
    meeting_type_id are treated the same way). Empty list if a day_off exception
    exists. Adds extra_availability exceptions for the date.
    """
    day_of_week = target_date.weekday()

    exceptions = (
        db.query(ScheduleException)
        .filter(
            ScheduleException.psychologist_id == psychologist_id,
            ScheduleException.exception_date == target_date,
        )
        .all()
    )
    if any(e.exception_type == "day_off" for e in exceptions):
        return []

    rules = (
        db.query(ScheduleRule)
        .filter(
            ScheduleRule.psychologist_id == psychologist_id,
            ScheduleRule.day_of_week == day_of_week,
            ScheduleRule.is_active.is_(True),
            ScheduleRule.effective_from <= target_date,
            or_(
                ScheduleRule.effective_until.is_(None),
                ScheduleRule.effective_until >= target_date,
            ),
        )
        .all()
    )

    windows = [
        (_combine_msk(target_date, r.start_time),
         _combine_msk(target_date, r.end_time))
        for r in rules
    ]
    for e in exceptions:
        if (e.exception_type == "extra_availability"
                and e.start_time and e.end_time):
            windows.append(
                (_combine_msk(target_date, e.start_time),
                 _combine_msk(target_date, e.end_time))
            )
    return windows


def _break_unavailable_ranges(
    psychologist_id: int,
    target_date: date,
    db,
) -> list[tuple[datetime, datetime]]:
    """Ranges cut out of availability: recurring breaks + 'unavailable'."""
    day_of_week = target_date.weekday()
    ranges = []

    breaks = (
        db.query(ScheduleBreak)
        .filter(
            ScheduleBreak.psychologist_id == psychologist_id,
            ScheduleBreak.day_of_week == day_of_week,
            ScheduleBreak.is_active.is_(True),
            ScheduleBreak.effective_from <= target_date,
            or_(
                ScheduleBreak.effective_until.is_(None),
                ScheduleBreak.effective_until >= target_date,
            ),
        )
        .all()
    )
    for b in breaks:
        ranges.append(
            (_combine_msk(target_date, b.start_time),
             _combine_msk(target_date, b.end_time))
        )

    unavail = (
        db.query(ScheduleException)
        .filter(
            ScheduleException.psychologist_id == psychologist_id,
            ScheduleException.exception_date == target_date,
            ScheduleException.exception_type == "unavailable",
        )
        .all()
    )
    for e in unavail:
        if e.start_time and e.end_time:
            ranges.append(
                (_combine_msk(target_date, e.start_time),
                 _combine_msk(target_date, e.end_time))
            )
    return ranges


def _group_session_ranges(
    psychologist_id: int,
    start_dt: datetime,
    end_dt: datetime,
    db,
) -> list[tuple[datetime, datetime]]:
    """Scheduled group sessions for a psychologist block individual slots."""
    rows = (
        db.query(GroupSession)
        .filter(
            GroupSession.psychologist_id == psychologist_id,
            GroupSession.status == "scheduled",
            GroupSession.starts_at >= start_dt,
            GroupSession.starts_at < end_dt,
        )
        .all()
    )
    out = []
    for gs in rows:
        if gs.ends_at:
            end = gs.ends_at
        else:
            mt = (
                db.query(MeetingType)
                .filter(MeetingType.id == gs.meeting_type_id)
                .first()
            )
            dur = mt.duration_minutes if mt else 50
            end = gs.starts_at + timedelta(minutes=dur)
        out.append((gs.starts_at, end))
    return out


def _booked_appointment_ranges(
    psychologist_id: int,
    start_of_day: datetime,
    end_of_day: datetime,
    db,
) -> list[tuple[datetime, datetime]]:
    now_msk = _now_moscow()
    booked = (
        db.query(Appointment.starts_at, Appointment.duration_minutes)
        .filter(
            Appointment.psychologist_id == psychologist_id,
            Appointment.starts_at >= start_of_day,
            Appointment.starts_at < end_of_day,
            Appointment.status.in_(BLOCKING_STATUSES),
            Appointment.deleted_at.is_(None),
            # Lazy-expire: pending_confirmation past start_time not blocking
            or_(
                Appointment.status != "pending_confirmation",
                Appointment.starts_at > now_msk,
            ),
        )
        .all()
    )
    return [
        (row.starts_at, row.starts_at + timedelta(minutes=row.duration_minutes))
        for row in booked
    ]


def _generate_slots_in_window(
    w_start: datetime,
    w_end: datetime,
    duration: int,
    buffer: int,
) -> list[tuple[datetime, datetime]]:
    """Slots inside a window: each slot = duration; next = +duration+buffer."""
    slots = []
    dur = timedelta(minutes=duration)
    step = timedelta(minutes=duration + buffer)
    cur = w_start
    while cur + dur <= w_end:
        slots.append((cur, cur + dur))
        cur = cur + step
    return slots


def _structural_slots(
    psychologist_id: int,
    target_date: date,
    meeting_type: MeetingType,
    db,
) -> list[tuple[datetime, datetime]]:
    """Slots valid per the schedule (windows minus breaks/unavailable, ≥ cutoff).

    Does NOT consider existing bookings / group sessions — those are handled
    separately so booking can distinguish 422 (out of schedule) from 409 (busy).
    """
    windows = _working_windows(
        psychologist_id, target_date, db
    )
    if not windows:
        return []

    cut_ranges = _break_unavailable_ranges(psychologist_id, target_date, db)
    cutoff = _now_moscow() + timedelta(hours=1)
    duration = meeting_type.duration_minutes
    buffer = meeting_type.buffer_minutes

    result = []
    seen = set()
    for w_start, w_end in windows:
        for s, e in _generate_slots_in_window(w_start, w_end, duration, buffer):
            if s < cutoff:
                continue
            if _overlaps(s, e, cut_ranges):
                continue
            if s in seen:
                continue
            seen.add(s)
            result.append((s, e))
    result.sort(key=lambda x: x[0])
    return result


def get_available_slots(
    psychologist_id: int,
    target_date: date,
    meeting_type: MeetingType,
    db,
) -> list[dict]:
    """Bookable slots: structural slots minus existing bookings/group sessions."""
    structural = _structural_slots(
        psychologist_id, target_date, meeting_type, db
    )
    if not structural:
        return []

    start_of_day = _combine_msk(target_date, time(0, 0))
    end_of_day = start_of_day + timedelta(days=1)
    busy = _booked_appointment_ranges(
        psychologist_id, start_of_day, end_of_day, db
    )
    busy += _group_session_ranges(
        psychologist_id, start_of_day, end_of_day, db
    )

    duration = meeting_type.duration_minutes
    out = []
    for s, e in structural:
        if _overlaps(s, e, busy):
            continue
        out.append({
            "starts_at":        s,
            "ends_at":          e,
            "duration_minutes": duration,
        })
    return out


def is_valid_structural_slot(
    psychologist_id: int,
    starts_at: datetime,
    meeting_type: MeetingType,
    db,
) -> bool:
    """True if starts_at matches a schedule-generated slot (ignoring busy)."""
    target_date = starts_at.astimezone(MOSCOW_TZ).date()
    structural = _structural_slots(
        psychologist_id, target_date, meeting_type, db
    )
    return any(s == starts_at for s, _ in structural)


def is_group_session_overlap(
    psychologist_id: int,
    starts_at: datetime,
    duration_minutes: int,
    db,
) -> bool:
    """True if a scheduled group session overlaps the requested slot."""
    ends_at = starts_at + timedelta(minutes=duration_minutes)
    day = starts_at.astimezone(MOSCOW_TZ).date()
    start_of_day = _combine_msk(day, time(0, 0))
    end_of_day = start_of_day + timedelta(days=1)
    ranges = _group_session_ranges(
        psychologist_id, start_of_day, end_of_day, db
    )
    return _overlaps(starts_at, ends_at, ranges)


# ── Appointment CRUD ──────────────────────────────────────────────────────────

def create_appointment(
    psychologist_id: int,
    starts_at: datetime,
    duration_minutes: int,
    modality: str,
    topic: Optional[str],
    meeting_type_id: Optional[int],
    db,
    client_id: Optional[int] = None,
    engagement_id: Optional[int] = None,
    unregistered_student_card_id: Optional[int] = None,
    booking_source: str = "student_self",
    created_by: Optional[int] = None,
) -> dict:
    """Create an appointment.

    Субъект — ровно один: client_id (зарегистрированный студент) ИЛИ
    unregistered_student_card_id (карточка незарегистрированного студента).
    DB CHECK chk_appointment_subject_exactly_one гарантирует инвариант.
    """
    now = datetime.now(MOSCOW_TZ)
    ends_at = starts_at + timedelta(minutes=duration_minutes)
    appt = Appointment(
        client_id=client_id,
        unregistered_student_card_id=unregistered_student_card_id,
        psychologist_id=psychologist_id,
        engagement_id=engagement_id,
        meeting_type_id=meeting_type_id,
        starts_at=starts_at,
        duration_minutes=duration_minutes,
        ends_at=ends_at,
        modality=modality,
        topic=topic,
        status="pending_confirmation",
        booking_source=booking_source,
        created_by=created_by,
        created_at=now,
        updated_at=now,
    )
    db.add(appt)
    db.flush()
    db.refresh(appt)
    return _appointment_to_dict(appt, db)


def get_appointment_by_uuid(uuid_str: str, db) -> Optional[Appointment]:
    return (
        db.query(Appointment)
        .filter(
            Appointment.uuid == uuid_str,
            Appointment.deleted_at.is_(None),
        )
        .first()
    )


def acquire_slot_lock(
    psychologist_id: int, starts_at: datetime, db
) -> None:
    """Advisory transaction lock: one booking per (psychologist, slot).

    Uses pg_advisory_xact_lock(int, int) so the lock is automatically
    released when the transaction commits or rolls back.
    """
    slot_hash = int(
        hashlib.sha256(
            f"{psychologist_id}:{starts_at.isoformat()}".encode()
        ).hexdigest()[:8],
        16,
    ) % (2 ** 31 - 1)
    db.execute(
        sa.text(
            "SELECT pg_advisory_xact_lock(:key1, :key2)"
        ),
        {"key1": psychologist_id % (2 ** 31 - 1), "key2": slot_hash},
    )


def is_slot_blocked(
    psychologist_id: int,
    starts_at: datetime,
    duration_minutes: int,
    db,
    exclude_uuid: Optional[str] = None,
) -> bool:
    """Return True if the slot overlaps with a blocking appointment.

    Acquires row-level locks on any conflicting rows so concurrent
    transactions wait rather than racing.
    """
    ends_at = starts_at + timedelta(minutes=duration_minutes)
    now_msk = _now_moscow()

    q = db.query(Appointment.id).filter(
        Appointment.psychologist_id == psychologist_id,
        Appointment.status.in_(BLOCKING_STATUSES),
        Appointment.deleted_at.is_(None),
        # Overlap: existing_start < new_end AND existing_end > new_start
        Appointment.starts_at < ends_at,
        Appointment.ends_at > starts_at,
        # Lazy-expire: pending past start not blocking
        or_(
            Appointment.status != "pending_confirmation",
            Appointment.starts_at > now_msk,
        ),
    ).with_for_update()
    if exclude_uuid:
        q = q.filter(Appointment.uuid != exclude_uuid)
    return q.first() is not None


def get_student_appointments(
    client_id: int,
    page: int,
    size: int,
    db,
    status_filter: Optional[str] = None,
) -> tuple[list[dict], int]:
    """Записи студента: прямые (client_id) + по привязанным карточкам.

    После привязки карточки (linked_user_id) студент видит и свои старые
    card-appointments. Unlinked-карточки и карточки, привязанные к другому
    пользователю, в выборку не попадают.
    """
    cid = int(client_id)
    linked_card_ids = (
        db.query(UnregisteredStudentCard.id)
        .filter(UnregisteredStudentCard.linked_user_id == cid)
    )
    q = db.query(Appointment).filter(
        Appointment.deleted_at.is_(None),
        or_(
            Appointment.client_id == cid,
            Appointment.unregistered_student_card_id.in_(linked_card_ids),
        ),
    )
    if status_filter:
        q = q.filter(Appointment.status == status_filter)
    total = q.count()
    rows = (
        q.order_by(Appointment.starts_at.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )
    return [_appointment_to_dict(a, db) for a in rows], total


def get_psychologist_appointments(
    psychologist_id: int,
    page: int,
    size: int,
    db,
    status_filter: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> tuple[list[dict], int]:
    q = db.query(Appointment).filter(
        Appointment.psychologist_id == psychologist_id,
        Appointment.deleted_at.is_(None),
    )
    if status_filter:
        q = q.filter(Appointment.status == status_filter)
    if date_from:
        dt_from = datetime.combine(date_from, time(0, 0)).replace(
            tzinfo=MOSCOW_TZ
        )
        q = q.filter(Appointment.starts_at >= dt_from)
    if date_to:
        dt_to = datetime.combine(date_to, time(23, 59, 59)).replace(
            tzinfo=MOSCOW_TZ
        )
        q = q.filter(Appointment.starts_at <= dt_to)
    total = q.count()
    rows = (
        q.order_by(Appointment.created_at.desc(), Appointment.id.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )
    return [_appointment_to_dict(a, db) for a in rows], total


def confirm_appointment(appt: Appointment, db) -> dict:
    now = datetime.now(MOSCOW_TZ)
    appt.status = "confirmed"
    appt.updated_at = now
    db.flush()
    db.refresh(appt)
    return _appointment_to_dict(appt, db)


def decline_appointment(
    appt: Appointment, reason: Optional[str], db
) -> dict:
    now = datetime.now(MOSCOW_TZ)
    appt.status = "declined"
    appt.decline_reason = reason
    appt.updated_at = now
    db.flush()
    db.refresh(appt)
    return _appointment_to_dict(appt, db)


def cancel_appointment(
    appt: Appointment,
    canceled_by: int,
    reason: Optional[str],
    db,
    soft_delete: bool = False,
) -> dict:
    """Cancel an appointment.

    soft_delete=True (отмена ещё не подтверждённой записи) — дополнительно
    проставляет deleted_at, чтобы запись исчезла из списков. Подтверждённые
    записи отменяются без soft-delete (остаются видны как cancelled).
    """
    now = datetime.now(MOSCOW_TZ)
    appt.status = "cancelled"
    appt.cancellation_reason = reason
    appt.canceled_by = canceled_by
    appt.updated_at = now
    if soft_delete:
        appt.deleted_at = now
    db.flush()
    result = _appointment_to_dict(appt, db)
    return result


# ── MeetingType CRUD ──────────────────────────────────────────────────────────

def _mt_to_dict(mt: MeetingType) -> dict:
    return {
        "id":               mt.id,
        "name":             mt.name,
        "description":      mt.description,
        "duration_minutes": mt.duration_minutes,
        "buffer_minutes":   mt.buffer_minutes,
        "allow_in_person":  mt.allow_in_person,
        "allow_online":     mt.allow_online,
        "is_group":         mt.is_group,
        "is_active":        mt.is_active,
        "is_bookable":      mt.is_bookable,
        "display_order":    mt.display_order,
        "created_at":       mt.created_at,
        "updated_at":       mt.updated_at,
    }


def get_meeting_types(db, include_inactive: bool = False) -> list[dict]:
    q = db.query(MeetingType)
    if not include_inactive:
        q = q.filter(MeetingType.is_active.is_(True))
    rows = q.order_by(MeetingType.display_order, MeetingType.id).all()
    return [_mt_to_dict(mt) for mt in rows]


def get_meeting_type(mt_id: int, db) -> Optional[MeetingType]:
    return db.query(MeetingType).filter(MeetingType.id == mt_id).first()


def create_meeting_type(data: dict, db) -> dict:
    now = datetime.now(MOSCOW_TZ)
    mt = MeetingType(**data, created_at=now, updated_at=now)
    db.add(mt)
    db.flush()
    db.refresh(mt)
    return _mt_to_dict(mt)


def update_meeting_type(mt: MeetingType, updates: dict, db) -> dict:
    for k, v in updates.items():
        setattr(mt, k, v)
    mt.updated_at = datetime.now(MOSCOW_TZ)
    db.flush()
    db.refresh(mt)
    return _mt_to_dict(mt)


# ── ScheduleRule CRUD ─────────────────────────────────────────────────────────

def _rule_to_dict(rule: ScheduleRule) -> dict:
    return {
        "id":              rule.id,
        "psychologist_id": rule.psychologist_id,
        "meeting_type_id": rule.meeting_type_id,
        "day_of_week":     rule.day_of_week,
        "start_time":      str(rule.start_time)[:5],
        "end_time":        str(rule.end_time)[:5],
        "period":          rule.period,
        "series_id":       str(rule.series_id) if rule.series_id else None,
        "is_active":       rule.is_active,
        "auto_extend":     rule.auto_extend,
        "effective_from":  str(rule.effective_from),
        "effective_until": str(rule.effective_until)
                           if rule.effective_until else None,
        "created_by":      rule.created_by,
        "created_at":      rule.created_at,
    }


def get_schedule_rules(
    psychologist_id: int, db, include_inactive: bool = False
) -> list[dict]:
    """Schedule rules for a psychologist.

    By default только активные (не soft-deleted) правила — это «активный
    список». include_inactive=True показывает и деактивированные серии.
    """
    q = db.query(ScheduleRule).filter(
        ScheduleRule.psychologist_id == psychologist_id
    )
    if not include_inactive:
        q = q.filter(ScheduleRule.is_active.is_(True))
    rows = q.order_by(
        ScheduleRule.day_of_week, ScheduleRule.start_time
    ).all()
    return [_rule_to_dict(r) for r in rows]


def create_schedule_rules_bulk(data: dict, db) -> list[dict]:
    """Create one rule per day in data['days_of_week'], sharing a series_id."""
    import uuid as _uuid_module
    series_id = _uuid_module.uuid4()
    created = []
    for dow in data["days_of_week"]:
        rule = ScheduleRule(
            psychologist_id=data["psychologist_id"],
            meeting_type_id=data.get("meeting_type_id"),
            day_of_week=dow,
            start_time=data["start_time"],
            end_time=data["end_time"],
            period=data.get("period"),
            series_id=series_id,
            effective_from=data["effective_from"],
            effective_until=data.get("effective_until"),
            auto_extend=bool(data.get("auto_extend", False)),
            created_by=data.get("created_by"),
            is_active=True,
        )
        db.add(rule)
        db.flush()
        db.refresh(rule)
        created.append(_rule_to_dict(rule))
    return created


def create_schedule_series(data: dict, db) -> dict:
    """Create a full schedule (rules + recurring breaks) in one series.

    Rules and breaks share one series_id and the same effective period so the
    series can be soft-deleted / restored / extended as a unit.
    """
    import uuid as _uuid_module
    series_id = _uuid_module.uuid4()

    rules = []
    for dow in data["days_of_week"]:
        rule = ScheduleRule(
            psychologist_id=data["psychologist_id"],
            meeting_type_id=data.get("meeting_type_id"),
            day_of_week=dow,
            start_time=data["start_time"],
            end_time=data["end_time"],
            period=data.get("period"),
            series_id=series_id,
            effective_from=data["effective_from"],
            effective_until=data.get("effective_until"),
            auto_extend=bool(data.get("auto_extend", False)),
            created_by=data.get("created_by"),
            is_active=True,
        )
        db.add(rule)
        rules.append(rule)

    breaks = []
    for brk in data.get("breaks", []):
        for dow in data["days_of_week"]:
            br = ScheduleBreak(
                psychologist_id=data["psychologist_id"],
                day_of_week=dow,
                start_time=brk["start_time"],
                end_time=brk["end_time"],
                title=brk.get("title"),
                series_id=series_id,
                effective_from=data["effective_from"],
                effective_until=data.get("effective_until"),
                is_active=True,
            )
            db.add(br)
            breaks.append(br)

    db.flush()
    for r in rules:
        db.refresh(r)
    for b in breaks:
        db.refresh(b)

    return {
        "series_id":       str(series_id),
        "psychologist_id": data["psychologist_id"],
        "meeting_type_id": data.get("meeting_type_id"),
        "auto_extend":     bool(data.get("auto_extend", False)),
        "effective_from":  str(data["effective_from"]),
        "effective_until": str(data["effective_until"])
                           if data.get("effective_until") else None,
        "is_active":       True,
        "rules":           [_rule_to_dict(r) for r in rules],
        "breaks":          [_break_to_dict(b) for b in breaks],
    }


def update_schedule_series(series_id, data: dict, db) -> dict:
    """Update a schedule series in place (recreate rules+breaks, same series_id).

    Existing rules/breaks of the series are physically removed and recreated
    within the same transaction, keeping the same series_id. psychologist_id,
    is_active (soft-delete state) and created_by are preserved from the current
    series — they are NOT taken from the payload. Appointments have no FK to
    schedule_rules, so they are untouched (existing bookings keep their slots).

    Schedule v3: recreated rules carry no meeting_type_id (working window).
    Caller must ensure the series exists (404 handled in service).
    """
    existing = get_series_rules(series_id, db)
    head = existing[0]
    psychologist_id = head.psychologist_id
    is_active = head.is_active
    created_by = head.created_by

    # series_id здесь — тот же тип (UUID), что и колонка ScheduleRule.series_id,
    # поэтому bulk delete реально находит строки. Записи (appointments) не трогаем.
    db.query(ScheduleBreak).filter(
        ScheduleBreak.series_id == series_id
    ).delete(synchronize_session=False)
    db.query(ScheduleRule).filter(
        ScheduleRule.series_id == series_id
    ).delete(synchronize_session=False)
    db.flush()

    rules = []
    for dow in data["days_of_week"]:
        rule = ScheduleRule(
            psychologist_id=psychologist_id,
            meeting_type_id=None,
            day_of_week=dow,
            start_time=data["start_time"],
            end_time=data["end_time"],
            period=data.get("period"),
            series_id=series_id,
            effective_from=data["effective_from"],
            effective_until=data.get("effective_until"),
            auto_extend=bool(data.get("auto_extend", False)),
            created_by=created_by,
            is_active=is_active,
        )
        db.add(rule)
        rules.append(rule)

    breaks = []
    for brk in data.get("breaks", []):
        for dow in data["days_of_week"]:
            br = ScheduleBreak(
                psychologist_id=psychologist_id,
                day_of_week=dow,
                start_time=brk["start_time"],
                end_time=brk["end_time"],
                title=brk.get("title"),
                series_id=series_id,
                effective_from=data["effective_from"],
                effective_until=data.get("effective_until"),
                is_active=is_active,
            )
            db.add(br)
            breaks.append(br)

    db.flush()
    for r in rules:
        db.refresh(r)
    for b in breaks:
        db.refresh(b)

    return {
        "series_id":       str(series_id),
        "psychologist_id": psychologist_id,
        "meeting_type_id": None,
        "auto_extend":     bool(data.get("auto_extend", False)),
        "effective_from":  str(data["effective_from"]),
        "effective_until": str(data["effective_until"])
                           if data.get("effective_until") else None,
        "is_active":       is_active,
        "rules":           [_rule_to_dict(r) for r in rules],
        "breaks":          [_break_to_dict(b) for b in breaks],
    }


def get_series_rules(series_id, db) -> list[ScheduleRule]:
    return (
        db.query(ScheduleRule)
        .filter(ScheduleRule.series_id == series_id)
        .order_by(ScheduleRule.day_of_week, ScheduleRule.start_time)
        .all()
    )


def get_series_breaks(series_id, db) -> list[ScheduleBreak]:
    return (
        db.query(ScheduleBreak)
        .filter(ScheduleBreak.series_id == series_id)
        .order_by(ScheduleBreak.day_of_week, ScheduleBreak.start_time)
        .all()
    )


def soft_delete_series(series_id, db) -> tuple[int, int]:
    """Deactivate all rules and breaks of a series (is_active=False).

    Returns (deactivated_rules, deactivated_breaks). Appointments untouched.
    """
    rules = get_series_rules(series_id, db)
    breaks = get_series_breaks(series_id, db)
    r_count = 0
    for r in rules:
        if r.is_active:
            r.is_active = False
            r_count += 1
    b_count = 0
    for b in breaks:
        if b.is_active:
            b.is_active = False
            b_count += 1
    db.flush()
    return r_count, b_count


def restore_series(series_id, db) -> tuple[int, int]:
    """Re-activate all rules and breaks of a series (is_active=True)."""
    rules = get_series_rules(series_id, db)
    breaks = get_series_breaks(series_id, db)
    r_count = 0
    for r in rules:
        if not r.is_active:
            r.is_active = True
            r_count += 1
    b_count = 0
    for b in breaks:
        if not b.is_active:
            b.is_active = True
            b_count += 1
    db.flush()
    return r_count, b_count


def extend_series(series_id, new_until: date, db) -> None:
    """Set effective_until on all rules and breaks of a series."""
    for r in get_series_rules(series_id, db):
        r.effective_until = new_until
    for b in get_series_breaks(series_id, db):
        b.effective_until = new_until
    db.flush()


def count_future_appointments_for_series(
    rules: list[ScheduleRule], db
) -> int:
    """Future blocking appointments that fall under a schedule series.

    Used as a warning before deactivation. Schedule v3: working windows are not
    tied to a meeting type, so appointments of ANY meeting type are counted as
    long as they match the series' psychologist, future starts_at, weekday, date
    range AND time window of the rule (appointments outside the rule's
    start_time–end_time are excluded).
    """
    if not rules:
        return 0
    psych_id = rules[0].psychologist_id
    # Per-day-of-week time windows from the series rules
    dow_windows: dict[int, list[tuple]] = {}
    for r in rules:
        dow_windows.setdefault(r.day_of_week, []).append(
            (r.start_time, r.end_time)
        )
    eff_from = min(r.effective_from for r in rules)
    untils = [r.effective_until for r in rules]
    eff_until = None if any(u is None for u in untils) else max(untils)
    now = _now_moscow()

    rows = (
        db.query(Appointment.starts_at)
        .filter(
            Appointment.psychologist_id == psych_id,
            Appointment.status.in_(BLOCKING_STATUSES),
            Appointment.deleted_at.is_(None),
            Appointment.starts_at > now,
        )
        .all()
    )
    count = 0
    for (starts_at,) in rows:
        d = starts_at.astimezone(MOSCOW_TZ)
        if d.date() < eff_from:
            continue
        if eff_until is not None and d.date() > eff_until:
            continue
        dow = d.weekday()
        if dow not in dow_windows:
            continue
        appt_time = d.time()
        if not any(ws <= appt_time < we for ws, we in dow_windows[dow]):
            continue
        count += 1
    return count


def get_auto_extend_series_due(threshold: date, db) -> list:
    """series_id values eligible for auto-extension.

    Active series with auto_extend=True whose effective_until is not NULL and
    falls on or before the threshold date.
    """
    rows = (
        db.query(ScheduleRule.series_id)
        .filter(
            ScheduleRule.auto_extend.is_(True),
            ScheduleRule.is_active.is_(True),
            ScheduleRule.series_id.isnot(None),
            ScheduleRule.effective_until.isnot(None),
            ScheduleRule.effective_until <= threshold,
        )
        .distinct()
        .all()
    )
    return [r[0] for r in rows]


def deactivate_schedule_rule(rule_id: int, db) -> bool:
    rule = db.query(ScheduleRule).filter(ScheduleRule.id == rule_id).first()
    if not rule:
        return False
    rule.is_active = False
    db.flush()
    return True


# ── ScheduleBreak CRUD ────────────────────────────────────────────────────────

def _break_to_dict(b: ScheduleBreak) -> dict:
    return {
        "id":              b.id,
        "psychologist_id": b.psychologist_id,
        "day_of_week":     b.day_of_week,
        "start_time":      str(b.start_time)[:5],
        "end_time":        str(b.end_time)[:5],
        "title":           b.title,
        "series_id":       str(b.series_id) if b.series_id else None,
        "effective_from":  str(b.effective_from),
        "effective_until": str(b.effective_until)
                           if b.effective_until else None,
        "is_active":       b.is_active,
        "created_at":      b.created_at,
    }


def get_schedule_breaks(psychologist_id: int, db) -> list[dict]:
    rows = (
        db.query(ScheduleBreak)
        .filter(ScheduleBreak.psychologist_id == psychologist_id)
        .order_by(ScheduleBreak.day_of_week, ScheduleBreak.start_time)
        .all()
    )
    return [_break_to_dict(b) for b in rows]


def create_schedule_breaks_bulk(data: dict, db) -> list[dict]:
    """Create one break per day in data['days_of_week'], sharing a series_id."""
    import uuid as _uuid_module
    series_id = _uuid_module.uuid4()
    created = []
    for dow in data["days_of_week"]:
        br = ScheduleBreak(
            psychologist_id=data["psychologist_id"],
            day_of_week=dow,
            start_time=data["start_time"],
            end_time=data["end_time"],
            title=data.get("title"),
            series_id=series_id,
            effective_from=data["effective_from"],
            effective_until=data.get("effective_until"),
            is_active=True,
        )
        db.add(br)
        db.flush()
        db.refresh(br)
        created.append(_break_to_dict(br))
    return created


def deactivate_schedule_break(break_id: int, db) -> bool:
    br = db.query(ScheduleBreak).filter(ScheduleBreak.id == break_id).first()
    if not br:
        return False
    br.is_active = False
    db.flush()
    return True


def _exception_to_dict(e: ScheduleException) -> dict:
    return {
        "id":               e.id,
        "psychologist_id":  e.psychologist_id,
        "exception_date":   str(e.exception_date),
        "exception_type":   e.exception_type,
        "start_time":       str(e.start_time)[:5] if e.start_time else None,
        "end_time":         str(e.end_time)[:5] if e.end_time else None,
        "reason":           e.reason,
        "created_at":       e.created_at,
    }


def create_schedule_exception(data: dict, db) -> dict:
    exc = ScheduleException(**data)
    db.add(exc)
    db.flush()
    db.refresh(exc)
    return _exception_to_dict(exc)


def get_schedule_exceptions(
    psychologist_id: int,
    date_from: Optional[date],
    date_to: Optional[date],
    db,
) -> list[dict]:
    """Разовые изменения психолога, новейшая дата первой.

    Сортировка: exception_date DESC, start_time ASC (NULLS LAST в PG → day_off
    без времени после timed на ту же дату), id DESC.
    """
    q = db.query(ScheduleException).filter(
        ScheduleException.psychologist_id == psychologist_id
    )
    if date_from is not None:
        q = q.filter(ScheduleException.exception_date >= date_from)
    if date_to is not None:
        q = q.filter(ScheduleException.exception_date <= date_to)
    rows = (
        q.order_by(
            ScheduleException.exception_date.desc(),
            ScheduleException.start_time.asc(),
            ScheduleException.id.desc(),
        )
        .all()
    )
    return [_exception_to_dict(e) for e in rows]


# ── GroupSession CRUD ─────────────────────────────────────────────────────────

def _gs_to_dict(gs: GroupSession, db, student_id: Optional[int] = None) -> dict:
    mt = db.query(MeetingType).filter(
        MeetingType.id == gs.meeting_type_id
    ).first()
    psych = db.query(User).filter(User.id == gs.psychologist_id).first()

    active_count = (
        db.query(GroupSessionRegistration)
        .filter(
            GroupSessionRegistration.group_session_id == gs.id,
            GroupSessionRegistration.status == "registered",
        )
        .count()
    )

    is_registered = False
    if student_id:
        reg = (
            db.query(GroupSessionRegistration)
            .filter(
                GroupSessionRegistration.group_session_id == gs.id,
                GroupSessionRegistration.student_id == student_id,
                GroupSessionRegistration.status == "registered",
            )
            .first()
        )
        is_registered = reg is not None

    return {
        "uuid":              str(gs.uuid),
        "meeting_type_id":   gs.meeting_type_id,
        "meeting_type_name": mt.name if mt else None,
        "psychologist_id":   gs.psychologist_id,
        "psychologist_name": psych.full_name if psych else None,
        "title":             gs.title,
        "description":       gs.description,
        "starts_at":         gs.starts_at,
        "ends_at":           gs.ends_at,
        "format":            gs.format,
        "capacity":          gs.capacity,
        "booking_enabled":   gs.booking_enabled,
        "status":            gs.status,
        "registered_count":  active_count,
        "is_registered":     is_registered,
        "created_at":        gs.created_at,
    }


def is_psychologist(user_id: int, db) -> bool:
    """True if the user exists, is not deleted, and has the psychologist role."""
    from app.db.models import Role, UserRole
    row = (
        db.query(User.id)
        .join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .filter(
            User.id == int(user_id),
            User.deleted_at.is_(None),
            Role.name == "psychologist",
        )
        .first()
    )
    return row is not None


def get_group_sessions_list(
    db,
    page: int = 1,
    size: int = 20,
    include_past: bool = False,
    open_only: bool = False,
    student_id: Optional[int] = None,
    psychologist_id_filter: Optional[int] = None,
) -> tuple[list[dict], int]:
    now = datetime.now(MOSCOW_TZ)
    q = db.query(GroupSession).filter(
        GroupSession.status == "scheduled"
    )
    if not include_past:
        q = q.filter(GroupSession.starts_at > now)
    if open_only:
        q = q.filter(GroupSession.booking_enabled.is_(True))
    if psychologist_id_filter is not None:
        q = q.filter(
            GroupSession.psychologist_id == psychologist_id_filter
        )
    total = q.count()
    rows = (
        q.order_by(GroupSession.starts_at.asc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )
    return [_gs_to_dict(gs, db, student_id) for gs in rows], total


def get_group_session_by_uuid(uuid_str: str, db) -> Optional[GroupSession]:
    return (
        db.query(GroupSession)
        .filter(GroupSession.uuid == uuid_str)
        .first()
    )


def create_group_session(data: dict, db) -> dict:
    import uuid as _uuid_module
    now = datetime.now(MOSCOW_TZ)
    gs = GroupSession(
        uuid=_uuid_module.uuid4(),
        **data,
        created_at=now,
        updated_at=now,
    )
    db.add(gs)
    db.flush()
    db.refresh(gs)
    return _gs_to_dict(gs, db)


def update_group_session(gs: GroupSession, updates: dict, db) -> dict:
    for k, v in updates.items():
        setattr(gs, k, v)
    gs.updated_at = datetime.now(MOSCOW_TZ)
    db.flush()
    db.refresh(gs)
    return _gs_to_dict(gs, db)


def set_group_session_booking(
    gs: GroupSession, enabled: bool, db
) -> dict:
    gs.booking_enabled = enabled
    gs.updated_at = datetime.now(MOSCOW_TZ)
    db.flush()
    db.refresh(gs)
    return _gs_to_dict(gs, db)


def lock_group_session_for_update(
    gs_id: int, db
) -> Optional[GroupSession]:
    """Lock the group session row to serialise concurrent registrations."""
    return (
        db.query(GroupSession)
        .filter(GroupSession.id == gs_id)
        .with_for_update()
        .first()
    )


def register_student_group_session(
    gs: GroupSession, student_id: int, db
) -> dict:
    """Register student, reusing a cancelled row if one exists."""
    import uuid as _uuid_module
    now = datetime.now(MOSCOW_TZ)

    # Reuse an existing cancelled registration to avoid violating the
    # partial unique index (only one 'registered' row per session+student).
    existing = (
        db.query(GroupSessionRegistration)
        .filter(
            GroupSessionRegistration.group_session_id == gs.id,
            GroupSessionRegistration.student_id == student_id,
        )
        .first()
    )
    if existing:
        existing.status = "registered"
        existing.updated_at = now
        db.flush()
        db.refresh(existing)
        return {
            "uuid":             str(existing.uuid),
            "group_session_id": existing.group_session_id,
            "student_id":       existing.student_id,
            "status":           existing.status,
            "created_at":       existing.created_at,
        }

    reg = GroupSessionRegistration(
        uuid=_uuid_module.uuid4(),
        group_session_id=gs.id,
        student_id=student_id,
        status="registered",
        created_at=now,
        updated_at=now,
    )
    db.add(reg)
    db.flush()
    db.refresh(reg)
    return {
        "uuid":             str(reg.uuid),
        "group_session_id": reg.group_session_id,
        "student_id":       reg.student_id,
        "status":           reg.status,
        "created_at":       reg.created_at,
    }


def cancel_student_group_session(
    gs_uuid: str, student_id: int, db
) -> bool:
    gs = get_group_session_by_uuid(gs_uuid, db)
    if not gs:
        return False
    reg = (
        db.query(GroupSessionRegistration)
        .filter(
            GroupSessionRegistration.group_session_id == gs.id,
            GroupSessionRegistration.student_id == student_id,
            GroupSessionRegistration.status == "registered",
        )
        .first()
    )
    if not reg:
        return False
    reg.status = "cancelled"
    reg.updated_at = datetime.now(MOSCOW_TZ)
    db.flush()
    return True


def count_active_registrations(gs_id: int, db) -> int:
    return (
        db.query(GroupSessionRegistration)
        .filter(
            GroupSessionRegistration.group_session_id == gs_id,
            GroupSessionRegistration.status == "registered",
        )
        .count()
    )


def get_student_registration(
    gs_id: int, student_id: int, db
) -> Optional[GroupSessionRegistration]:
    return (
        db.query(GroupSessionRegistration)
        .filter(
            GroupSessionRegistration.group_session_id == gs_id,
            GroupSessionRegistration.student_id == student_id,
        )
        .first()
    )


# ── UnregisteredStudentCard CRUD ──────────────────────────────────────────────

def _card_to_dict(card: UnregisteredStudentCard) -> dict:
    return {
        "id":                    card.id,
        "uuid":                  str(card.uuid),
        "full_name":             card.full_name,
        "phone":                 card.phone,
        "email":                 card.email,
        "normalized_email":      card.normalized_email,
        "birth_date":            card.birth_date,
        "comment":               card.comment,
        "primary_concern":       card.primary_concern,
        "personal_data_consent": card.personal_data_consent,
        "consent_obtained_at":   card.consent_obtained_at,
        "consent_source":        card.consent_source,
        "linked_user_id":        card.linked_user_id,
        "created_by":            card.created_by,
        "created_at":            card.created_at,
        "updated_at":            card.updated_at,
        "archived_at":           card.archived_at,
    }


def _card_brief(card: UnregisteredStudentCard) -> dict:
    """Minimal card embedded into appointment reads (psychologist view)."""
    return {
        "id":        card.id,
        "uuid":      str(card.uuid),
        "full_name": card.full_name,
        "phone":     card.phone,
        "email":     card.email,
    }


def get_unregistered_student_card(
    card_id: int, db
) -> Optional[UnregisteredStudentCard]:
    return (
        db.query(UnregisteredStudentCard)
        .filter(UnregisteredStudentCard.id == int(card_id))
        .first()
    )


def create_unregistered_student_card(data: dict, db) -> dict:
    now = datetime.now(MOSCOW_TZ)
    card = UnregisteredStudentCard(**data, created_at=now, updated_at=now)
    db.add(card)
    db.flush()
    db.refresh(card)
    return _card_to_dict(card)


def update_unregistered_student_card(
    card: UnregisteredStudentCard, updates: dict, db
) -> dict:
    for k, v in updates.items():
        setattr(card, k, v)
    card.updated_at = datetime.now(MOSCOW_TZ)
    db.flush()
    db.refresh(card)
    return _card_to_dict(card)


def archive_unregistered_student_card(
    card: UnregisteredStudentCard, db
) -> dict:
    if card.archived_at is None:
        now = datetime.now(MOSCOW_TZ)
        card.archived_at = now
        card.updated_at = now
        db.flush()
        db.refresh(card)
    return _card_to_dict(card)


def link_unregistered_cards_to_user(user_id: int, email: str, db) -> int:
    """Привязать все UNLINKED карточки с этим email к пользователю.

    Этап 2: вызывается после подтверждения владения email (регистрация confirm).
    Правила:
      - сравнение по normalized_email (канонический lower/trim);
      - привязываются только карточки с linked_user_id IS NULL — карточка, уже
        привязанная к другому пользователю, НЕ перепривязывается;
      - несколько unlinked карточек с одним email привязываются все (email
        подтверждён владельцем; карточки не объединяются и не удаляются);
      - archived-карточки тоже привязываются: архивность запрещает новую ручную
        запись, но не должна мешать исторической связке уже созданных
        appointments.

    Возвращает количество привязанных карточек. ПДн не логируются.
    """
    if not email:
        return 0
    normalized = normalize_email(email)
    cards = (
        db.query(UnregisteredStudentCard)
        .filter(
            UnregisteredStudentCard.normalized_email == normalized,
            UnregisteredStudentCard.linked_user_id.is_(None),
        )
        .all()
    )
    now = datetime.now(MOSCOW_TZ)
    for card in cards:
        card.linked_user_id = int(user_id)
        card.updated_at = now
    db.flush()
    return len(cards)


def list_unregistered_student_cards(
    db,
    page: int = 1,
    size: int = 20,
    query: Optional[str] = None,
    include_archived: bool = False,
) -> tuple[list[dict], int]:
    q = db.query(UnregisteredStudentCard)
    if not include_archived:
        q = q.filter(UnregisteredStudentCard.archived_at.is_(None))
    if query:
        pattern = f"%{query.strip()}%"
        q = q.filter(
            or_(
                UnregisteredStudentCard.full_name.ilike(pattern),
                UnregisteredStudentCard.email.ilike(pattern),
                UnregisteredStudentCard.normalized_email.ilike(pattern),
                UnregisteredStudentCard.phone.ilike(pattern),
            )
        )
    total = q.count()
    rows = (
        q.order_by(UnregisteredStudentCard.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )
    return [_card_to_dict(c) for c in rows], total
