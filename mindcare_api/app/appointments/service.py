"""
Бизнес-логика модуля appointments.

Правила:
- Студент записывается только к своему психологу (active TherapyEngagement).
- Запись создаётся со статусом pending_confirmation.
- Студент может отменить запись только до дня записи (UTC+3/Moscow).
- Слоты генерируются из ScheduleRule + ScheduleException.
- Lazy-expire: pending_confirmation после starts_at не блокирует слоты.
- Групповые занятия не требуют подтверждения психолога.
- Системные уведомления — soft-fail после основной транзакции.
- Блокировки: advisory lock для индивидуальных слотов; FOR UPDATE для
  ёмкости групповых занятий.
"""

from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

from sqlalchemy.exc import IntegrityError

from app.core.normalization import normalize_email
from app.db.session import SessionLocal
from app.appointments import storage

# Moscow is UTC+3, no DST since 2014
MOSCOW_TZ = timezone(timedelta(hours=3))


class AppointmentError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code


# ── MeetingType / modality helpers ─────────────────────────────────────────

def _load_individual_meeting_type(meeting_type_id: Optional[int], db):
    """Load + validate an individual (non-group) bookable meeting type."""
    if not meeting_type_id:
        raise AppointmentError(
            "Укажите тип встречи (meeting_type_id)", status_code=422
        )
    from app.db.models import MeetingType
    mt = (
        db.query(MeetingType)
        .filter(MeetingType.id == meeting_type_id)
        .first()
    )
    if mt is None or not mt.is_active:
        raise AppointmentError(
            "Тип встречи не найден или недоступен", status_code=404
        )
    if not mt.is_bookable:
        raise AppointmentError(
            "Данный тип встречи недоступен для записи", status_code=422
        )
    if mt.is_group:
        raise AppointmentError(
            "Групповые занятия записываются отдельно", status_code=422
        )
    return mt


def _validate_modality(modality: str, mt) -> None:
    if modality == "in_person" and not mt.allow_in_person:
        raise AppointmentError(
            "Тип встречи не поддерживает очный формат", status_code=422
        )
    if modality == "online" and not mt.allow_online:
        raise AppointmentError(
            "Тип встречи не поддерживает онлайн-формат", status_code=422
        )


# ── Slots ──────────────────────────────────────────────────────────────────

def get_slots(
    psychologist_id: int,
    target_date: date,
    meeting_type_id: int,
    modality: str,
) -> dict:
    with SessionLocal() as db:
        mt = _load_individual_meeting_type(meeting_type_id, db)
        _validate_modality(modality, mt)
        slots = storage.get_available_slots(
            psychologist_id, target_date, mt, db
        )
    return {
        "psychologist_id": psychologist_id,
        "meeting_type_id": meeting_type_id,
        "modality": modality,
        "date": str(target_date),
        "slots": slots,
    }


# ── Create appointment ──────────────────────────────────────────────────────

def book_appointment(
    student_user: dict,
    starts_at: datetime,
    modality: str,
    topic: Optional[str],
    meeting_type_id: Optional[int],
) -> dict:
    now_msk = datetime.now(MOSCOW_TZ)
    cutoff = now_msk + timedelta(hours=1)

    if not student_user.get("is_active", True):
        raise AppointmentError(
            "Ваш аккаунт неактивен", status_code=403
        )

    if starts_at.tzinfo is None:
        raise AppointmentError("starts_at must be timezone-aware")

    if starts_at <= cutoff:
        raise AppointmentError(
            "Запись возможна минимум за 1 час до начала",
            status_code=422,
        )

    with SessionLocal() as db:
        engagement = storage.get_active_engagement(
            client_id=student_user["id"], db=db
        )
        if engagement is None:
            raise AppointmentError(
                "У вас нет активного назначенного психолога",
                status_code=403,
            )

        mt = _load_individual_meeting_type(meeting_type_id, db)
        _validate_modality(modality, mt)
        duration = mt.duration_minutes
        psych_id = engagement.psychologist_id

        # The chosen time must be a real slot in the psychologist's schedule.
        if not storage.is_valid_structural_slot(
            psych_id, starts_at, mt, db
        ):
            raise AppointmentError(
                "Выбранное время вне доступного расписания",
                status_code=422,
            )

        # Advisory lock: prevents concurrent booking of the same slot.
        storage.acquire_slot_lock(psych_id, starts_at, db)

        if (
            storage.is_slot_blocked(psych_id, starts_at, duration, db)
            or storage.is_group_session_overlap(
                psych_id, starts_at, duration, db
            )
        ):
            raise AppointmentError(
                "Выбранное время уже занято", status_code=409
            )

        appt = storage.create_appointment(
            client_id=student_user["id"],
            psychologist_id=psych_id,
            engagement_id=engagement.id,
            starts_at=starts_at,
            duration_minutes=duration,
            modality=modality,
            topic=topic,
            meeting_type_id=meeting_type_id,
            db=db,
            booking_source="student_self",
            created_by=int(student_user["id"]),
        )
        db.commit()

    _notify_new_appointment(
        psychologist_id=psych_id,
        appt=appt,
        student_user=student_user,
    )
    return appt


def _notify_new_appointment(
    psychologist_id: int,
    appt: dict,
    student_user: dict,
) -> None:
    try:
        from app.chat.system_publisher import publish_system_message
        name = (
            student_user.get("full_name")
            or student_user.get("email", "студент")
        )
        publish_system_message(
            recipient_id=psychologist_id,
            event_key=f"appointment_new:{appt['uuid']}",
            text=(
                f"Новая запись от {name} "
                f"на {_fmt_dt(appt['starts_at'])}"
            ),
        )
    except Exception:
        pass


# ── Supervisor manual booking ───────────────────────────────────────────────

def supervisor_book_appointment(
    psychologist_id: int,
    meeting_type_id: int,
    starts_at: datetime,
    modality: str,
    topic: Optional[str],
    student_id: Optional[int] = None,
    unregistered_student_card_id: Optional[int] = None,
    current_user: Optional[dict] = None,
) -> dict:
    """Ручная запись супервизором на свободный слот психолога.

    Субъект — РОВНО один из двух:
      - student_id                    — зарегистрированный студент; требует
                                        активной связи студент↔психолог;
      - unregistered_student_card_id  — карточка незарегистрированного студента;
                                        engagement не требуется, client_id=NULL.

    Создаёт обычный Appointment в статусе pending_confirmation (психолог
    подтверждает как обычно). Психолог получает system-уведомление о записи,
    созданной супервизором.
    """
    if (student_id is None) == (unregistered_student_card_id is None):
        raise AppointmentError(
            "Укажите ровно одно: student_id или "
            "unregistered_student_card_id",
            status_code=422,
        )

    now_msk = datetime.now(MOSCOW_TZ)
    cutoff = now_msk + timedelta(hours=1)

    if starts_at.tzinfo is None:
        raise AppointmentError("starts_at must be timezone-aware")
    if starts_at <= cutoff:
        raise AppointmentError(
            "Запись возможна минимум за 1 час до начала", status_code=422
        )

    with SessionLocal() as db:
        if not storage.is_psychologist(psychologist_id, db):
            raise AppointmentError("Психолог не найден", status_code=422)

        engagement_id = None
        card_id = None
        if student_id is not None:
            student = storage.get_user(student_id, db)
            if student is None:
                raise AppointmentError("Студент не найден", status_code=404)
            if not student.is_active:
                raise AppointmentError(
                    "Аккаунт студента неактивен", status_code=422
                )
            engagement = storage.get_active_engagement_with(
                student_id, psychologist_id, db
            )
            if engagement is None:
                raise AppointmentError(
                    "Студент не закреплён за этим психологом",
                    status_code=422,
                )
            engagement_id = engagement.id
        else:
            card = storage.get_unregistered_student_card(
                unregistered_student_card_id, db
            )
            if card is None:
                raise AppointmentError(
                    "Карточка студента не найдена", status_code=404
                )
            if card.archived_at is not None:
                raise AppointmentError(
                    "Карточка студента архивирована", status_code=422
                )
            card_id = card.id

        mt = _load_individual_meeting_type(meeting_type_id, db)
        _validate_modality(modality, mt)
        duration = mt.duration_minutes

        if not storage.is_valid_structural_slot(
            psychologist_id, starts_at, mt, db
        ):
            raise AppointmentError(
                "Выбранное время вне доступного расписания",
                status_code=422,
            )

        storage.acquire_slot_lock(psychologist_id, starts_at, db)

        if (
            storage.is_slot_blocked(psychologist_id, starts_at, duration, db)
            or storage.is_group_session_overlap(
                psychologist_id, starts_at, duration, db
            )
        ):
            raise AppointmentError(
                "Выбранное время уже занято", status_code=409
            )

        booker_id = int(current_user["id"]) if current_user else None
        appt = storage.create_appointment(
            client_id=student_id,
            unregistered_student_card_id=card_id,
            psychologist_id=psychologist_id,
            engagement_id=engagement_id,
            starts_at=starts_at,
            duration_minutes=duration,
            modality=modality,
            topic=topic,
            meeting_type_id=meeting_type_id,
            db=db,
            booking_source="supervisor",
            created_by=booker_id,
        )
        db.commit()

    _notify_supervisor_appointment(psychologist_id, appt)
    return appt


def _notify_supervisor_appointment(psychologist_id: int, appt: dict) -> None:
    try:
        from app.chat.system_publisher import publish_system_message
        student = appt.get("student") or {}
        card = appt.get("unregistered_student_card") or {}
        name = (
            student.get("full_name")
            or student.get("email")
            or card.get("full_name")
            or "студент"
        )
        publish_system_message(
            recipient_id=psychologist_id,
            event_key=f"appointment_supervisor_new:{appt['uuid']}",
            text=(
                f"Супервизор записал {name} "
                f"на {_fmt_dt(appt['starts_at'])}"
            ),
        )
    except Exception:
        pass


# ── Unregistered student cards (supervisor) ─────────────────────────────────

def list_unregistered_student_cards(
    page: int = 1,
    size: int = 20,
    query: Optional[str] = None,
    include_archived: bool = False,
) -> tuple[list[dict], int]:
    with SessionLocal() as db:
        return storage.list_unregistered_student_cards(
            db,
            page=page,
            size=size,
            query=query,
            include_archived=include_archived,
        )


def create_unregistered_student_card(
    data: dict, current_user: dict
) -> dict:
    """Создать карточку незарегистрированного студента.

    full_name обязателен и непустой; personal_data_consent должен быть True
    (активная карточка создаётся только с согласием). normalized_email
    вычисляется на backend; consent_obtained_at фиксируется сервером.
    """
    full_name = (data.get("full_name") or "").strip()
    if not full_name:
        raise AppointmentError("Укажите ФИО (full_name)", status_code=422)
    if data.get("personal_data_consent") is not True:
        raise AppointmentError(
            "Требуется согласие на обработку персональных данных",
            status_code=422,
        )

    email = data.get("email")
    record = {
        "full_name":             full_name,
        "phone":                 data.get("phone"),
        "email":                 email,
        "normalized_email":      normalize_email(email) if email else None,
        "birth_date":            data.get("birth_date"),
        "comment":               data.get("comment"),
        "primary_concern":       data.get("primary_concern"),
        "personal_data_consent": True,
        "consent_obtained_at":   datetime.now(MOSCOW_TZ),
        "consent_source":        data.get("consent_source") or "in_person",
        "created_by":            int(current_user["id"]),
    }
    with SessionLocal() as db:
        result = storage.create_unregistered_student_card(record, db)
        db.commit()
    return result


_CARD_EDITABLE_FIELDS = (
    "full_name", "phone", "email", "birth_date", "comment", "primary_concern",
)


def update_unregistered_student_card(card_id: int, updates: dict) -> dict:
    """Частичное обновление карточки (только личные поля).

    Audit/consent/linked_user_id не редактируются. При смене email
    пересчитывается normalized_email.
    """
    clean = {k: v for k, v in updates.items() if k in _CARD_EDITABLE_FIELDS}
    if "full_name" in clean:
        fn = (clean["full_name"] or "").strip()
        if not fn:
            raise AppointmentError("ФИО не может быть пустым", status_code=422)
        clean["full_name"] = fn
    if "email" in clean:
        email = clean["email"]
        clean["normalized_email"] = normalize_email(email) if email else None

    with SessionLocal() as db:
        card = storage.get_unregistered_student_card(card_id, db)
        if card is None:
            raise AppointmentError("Карточка не найдена", status_code=404)
        result = storage.update_unregistered_student_card(card, clean, db)
        db.commit()
    return result


def archive_unregistered_student_card(card_id: int) -> dict:
    with SessionLocal() as db:
        card = storage.get_unregistered_student_card(card_id, db)
        if card is None:
            raise AppointmentError("Карточка не найдена", status_code=404)
        result = storage.archive_unregistered_student_card(card, db)
        db.commit()
    return result


def link_unregistered_cards_to_user(user_id, email: str) -> int:
    """Привязать карточки незарегистрированного студента к аккаунту (этап 2).

    Вызывается из auth-сервиса ПОСЛЕ подтверждения владения email (registration
    confirm). Идемпотентна: привязывает только ещё не привязанные карточки с
    совпавшим normalized_email; повторный вызов ничего не делает. Карточка,
    привязанная к другому пользователю, не перепривязывается. ПДн не логируются.

    Возвращает число привязанных карточек.
    """
    with SessionLocal() as db:
        linked = storage.link_unregistered_cards_to_user(
            int(user_id), email, db
        )
        db.commit()
    return linked


def _student_owns_appointment(appt, user_id: int, db) -> bool:
    """True, если запись принадлежит студенту: напрямую (client_id) или через
    привязанную к нему карточку (card.linked_user_id == user_id)."""
    if appt.client_id is not None:
        return appt.client_id == user_id
    if appt.unregistered_student_card_id is not None:
        card = storage.get_unregistered_student_card(
            appt.unregistered_student_card_id, db
        )
        return card is not None and card.linked_user_id == user_id
    return False


def _appt_student_recipient(appt, db) -> Optional[int]:
    """Кому из студентов отправлять уведомление по записи: client_id, либо
    linked_user_id привязанной карточки. None — если карточка ещё не привязана
    (уведомление студенту не отправляется)."""
    if appt.client_id is not None:
        return appt.client_id
    if appt.unregistered_student_card_id is not None:
        card = storage.get_unregistered_student_card(
            appt.unregistered_student_card_id, db
        )
        if card is not None:
            return card.linked_user_id
    return None


# ── Student list ──────────────────────────────────────────────────────────────

def list_student_appointments(
    student_id: int,
    page: int = 1,
    size: int = 20,
    status_filter: Optional[str] = None,
) -> tuple[list[dict], int]:
    with SessionLocal() as db:
        return storage.get_student_appointments(
            client_id=student_id,
            page=page,
            size=size,
            db=db,
            status_filter=status_filter,
        )


# ── Student cancel ────────────────────────────────────────────────────────────

def student_cancel(
    uuid: str,
    student_user: dict,
    reason: Optional[str],
) -> dict:
    now_msk = datetime.now(MOSCOW_TZ)
    today_msk = now_msk.date()

    with SessionLocal() as db:
        appt = storage.get_appointment_by_uuid(uuid, db)
        if appt is None:
            raise AppointmentError("Запись не найдена", status_code=404)
        # Доступ: прямой студент (client_id) ИЛИ владелец привязанной карточки.
        # Unlinked/чужая card-запись → 403.
        if not _student_owns_appointment(
            appt, int(student_user["id"]), db
        ):
            raise AppointmentError("Нет доступа", status_code=403)
        if appt.status not in ("pending_confirmation", "confirmed"):
            raise AppointmentError(
                f"Нельзя отменить запись со статусом {appt.status}",
                status_code=422,
            )

        appt_day_msk = appt.starts_at.astimezone(MOSCOW_TZ).date()
        if appt_day_msk <= today_msk:
            raise AppointmentError(
                "Отмена возможна только до дня записи",
                status_code=422,
            )

        # Отмена ещё не подтверждённой записи: soft-delete (исчезает из списков),
        # психолог её не видел — уведомление не нужно.
        # Отмена подтверждённой записи: остаётся видна как cancelled, психолог
        # получает system-уведомление (soft-fail после commit).
        was_confirmed = appt.status == "confirmed"
        psych_id = appt.psychologist_id
        starts_at = appt.starts_at

        result = storage.cancel_appointment(
            appt=appt,
            canceled_by=int(student_user["id"]),
            reason=reason,
            db=db,
            soft_delete=not was_confirmed,
        )
        db.commit()

    if was_confirmed:
        _notify_cancelled(
            psychologist_id=psych_id,
            appt_uuid=uuid,
            starts_at=starts_at,
            student_user=student_user,
            reason=reason,
        )

    return result


def _notify_cancelled(
    psychologist_id: int,
    appt_uuid: str,
    starts_at: datetime,
    student_user: dict,
    reason: Optional[str],
) -> None:
    try:
        from app.chat.system_publisher import publish_system_message
        name = (
            student_user.get("full_name")
            or student_user.get("email", "студент")
        )
        text = (
            f"{name} отменил(а) подтверждённую запись "
            f"на {_fmt_dt(starts_at)}"
        )
        if reason:
            text += f": {reason}"
        publish_system_message(
            recipient_id=psychologist_id,
            event_key=f"appointment_cancelled:{appt_uuid}",
            text=text,
        )
    except Exception:
        pass


# ── Psychologist actions ────────────────────────────────────────────────────

def list_psychologist_appointments(
    psychologist_id: int,
    page: int = 1,
    size: int = 20,
    status_filter: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> tuple[list[dict], int]:
    with SessionLocal() as db:
        return storage.get_psychologist_appointments(
            psychologist_id=psychologist_id,
            page=page,
            size=size,
            db=db,
            status_filter=status_filter,
            date_from=date_from,
            date_to=date_to,
        )


def psychologist_confirm(uuid: str, psychologist_user: dict) -> dict:
    with SessionLocal() as db:
        appt = storage.get_appointment_by_uuid(uuid, db)
        if appt is None:
            raise AppointmentError("Запись не найдена", status_code=404)
        if appt.psychologist_id != int(psychologist_user["id"]):
            raise AppointmentError("Нет доступа", status_code=403)
        if appt.status != "pending_confirmation":
            raise AppointmentError(
                f"Нельзя подтвердить статус {appt.status}",
                status_code=422,
            )
        # Получатель уведомления: прямой студент или привязанный к карточке user
        # (захватываем ДО commit, пока appt в сессии).
        recipient_id = _appt_student_recipient(appt, db)
        result = storage.confirm_appointment(appt, db)
        db.commit()

    # Уведомление студенту: есть либо у прямой записи, либо у привязанной
    # карточки. Unlinked card-запись (recipient_id is None) — не шлём, не падаем.
    if recipient_id is not None:
        _notify_confirmed(
            client_id=recipient_id,
            appt_uuid=uuid,
            starts_at=result["starts_at"],
            psychologist_user=psychologist_user,
        )
    return result


def _notify_confirmed(
    client_id: int,
    appt_uuid: str,
    starts_at: datetime,
    psychologist_user: dict,
) -> None:
    try:
        from app.chat.system_publisher import publish_system_message
        name = (
            psychologist_user.get("full_name")
            or psychologist_user.get("email", "психолог")
        )
        publish_system_message(
            recipient_id=client_id,
            event_key=f"appointment_confirmed:{appt_uuid}",
            text=(
                f"Ваша запись на {_fmt_dt(starts_at)} "
                f"подтверждена психологом {name}"
            ),
        )
    except Exception:
        pass


def psychologist_decline(
    uuid: str,
    psychologist_user: dict,
    reason: Optional[str],
) -> dict:
    with SessionLocal() as db:
        appt = storage.get_appointment_by_uuid(uuid, db)
        if appt is None:
            raise AppointmentError("Запись не найдена", status_code=404)
        if appt.psychologist_id != int(psychologist_user["id"]):
            raise AppointmentError("Нет доступа", status_code=403)
        if appt.status not in ("pending_confirmation", "confirmed"):
            raise AppointmentError(
                f"Нельзя отклонить статус {appt.status}",
                status_code=422,
            )
        # Получатель уведомления: прямой студент или привязанный к карточке user
        # (захватываем ДО commit, пока appt в сессии).
        recipient_id = _appt_student_recipient(appt, db)
        result = storage.decline_appointment(appt, reason, db)
        db.commit()

    # Уведомление студенту: есть либо у прямой записи, либо у привязанной
    # карточки. Unlinked card-запись (recipient_id is None) — не шлём, не падаем.
    if recipient_id is not None:
        _notify_declined(
            client_id=recipient_id,
            appt_uuid=uuid,
            starts_at=result["starts_at"],
            reason=reason,
        )
    return result


def _notify_declined(
    client_id: int,
    appt_uuid: str,
    starts_at: datetime,
    reason: Optional[str],
) -> None:
    try:
        from app.chat.system_publisher import publish_system_message
        text = f"Ваша запись на {_fmt_dt(starts_at)} отклонена"
        if reason:
            text += f": {reason}"
        publish_system_message(
            recipient_id=client_id,
            event_key=f"appointment_declined:{appt_uuid}",
            text=text,
        )
    except Exception:
        pass


# ── MeetingType management (supervisor) ────────────────────────────────────

def _validate_group_formats(data: dict) -> None:
    """Group meeting types must have exactly one allowed format (XOR)."""
    if not data.get("is_group"):
        return
    in_person = bool(data.get("allow_in_person", False))
    online = bool(data.get("allow_online", False))
    if in_person == online:  # both True or both False
        raise AppointmentError(
            "Групповой тип встречи должен иметь ровно один формат: "
            "очно или онлайн (не оба и не ни одного)",
            status_code=422,
        )


def list_meeting_types(include_inactive: bool = False) -> list[dict]:
    with SessionLocal() as db:
        return storage.get_meeting_types(
            db, include_inactive=include_inactive
        )


def list_student_meeting_types() -> list[dict]:
    """Bookable individual meeting types visible to a student.

    Только активные (is_active), доступные для записи (is_bookable) и
    индивидуальные (не групповые) — групповые занятия записываются отдельно.
    """
    with SessionLocal() as db:
        all_types = storage.get_meeting_types(db, include_inactive=False)
    return [
        mt for mt in all_types
        if mt["is_bookable"] and not mt["is_group"]
    ]


def create_meeting_type(data: dict) -> dict:
    _validate_group_formats(data)
    with SessionLocal() as db:
        result = storage.create_meeting_type(data, db)
        db.commit()
    return result


def update_meeting_type(mt_id: int, updates: dict) -> dict:
    with SessionLocal() as db:
        mt = storage.get_meeting_type(mt_id, db)
        if mt is None:
            raise AppointmentError(
                "Тип встречи не найден", status_code=404
            )
        # Merge current values with updates for XOR validation
        merged = {
            "is_group":       mt.is_group,
            "allow_in_person": mt.allow_in_person,
            "allow_online":   mt.allow_online,
        }
        for k in list(merged):
            if k in updates:
                merged[k] = updates[k]
        _validate_group_formats(merged)
        result = storage.update_meeting_type(mt, updates, db)
        db.commit()
    return result


# ── Schedule management (supervisor) ──────────────────────────────────────

def list_schedule_rules(
    psychologist_id: int, include_inactive: bool = False
) -> list[dict]:
    with SessionLocal() as db:
        return storage.get_schedule_rules(
            psychologist_id, db, include_inactive=include_inactive
        )


def get_psychologist_schedule(psychologist_id: int) -> dict:
    """Read-only расписание психолога: активные рабочие окна + активные перерывы.

    Schedule v3: рабочие окна не привязаны к типу встречи, поэтому расписание
    самодостаточно (дни/время/период). meeting_types сохранено в ответе для
    обратной совместимости и заполняется только типами legacy-правил (если у
    правила сохранён meeting_type_id); для новых окон список пуст. Фронт
    психолога НЕ должен зависеть от meeting_types при показе расписания.
    """
    with SessionLocal() as db:
        rules = storage.get_schedule_rules(
            psychologist_id, db, include_inactive=False
        )
        all_breaks = storage.get_schedule_breaks(psychologist_id, db)
        all_types = storage.get_meeting_types(db, include_inactive=True)
    breaks = [b for b in all_breaks if b["is_active"]]
    used_type_ids = {
        r["meeting_type_id"] for r in rules
        if r["meeting_type_id"] is not None
    }
    meeting_types = [mt for mt in all_types if mt["id"] in used_type_ids]
    return {
        "rules": rules,
        "breaks": breaks,
        "meeting_types": meeting_types,
    }


def create_schedule_rules(data: dict) -> list[dict]:
    """Bulk-создание рабочих окон (один или несколько дней, общий series_id).

    Schedule v3: meeting_type_id НЕОБЯЗАТЕЛЕН. Принимается для обратной
    совместимости (legacy-клиент), и если передан — проверяется на существование,
    но при расчёте слотов значение игнорируется.
    """
    _validate_time_range(data.get("start_time"), data.get("end_time"))
    meeting_type_id = data.get("meeting_type_id")
    with SessionLocal() as db:
        if meeting_type_id is not None:
            mt = storage.get_meeting_type(meeting_type_id, db)
            if mt is None:
                raise AppointmentError(
                    "Тип встречи не найден", status_code=404
                )
        result = storage.create_schedule_rules_bulk(data, db)
        db.commit()
    return result


def deactivate_schedule_rule(rule_id: int) -> None:
    with SessionLocal() as db:
        found = storage.deactivate_schedule_rule(rule_id, db)
        if not found:
            raise AppointmentError(
                "Правило расписания не найдено", status_code=404
            )
        db.commit()


# ── Unified schedule (series) management (supervisor) ──────────────────────

def create_schedule(data: dict) -> dict:
    """Создать расписание (серию): рабочие окна + перерывы за одну операцию.

    Schedule v3: тип встречи НЕ задаётся — рабочее окно не привязано к типу.
    auto_extend=True требует effective_until. Перерывы создаются с тем же
    series_id и периодом, что и правила.
    """
    _validate_time_range(data.get("start_time"), data.get("end_time"))
    if data.get("auto_extend") and not data.get("effective_until"):
        raise AppointmentError(
            "Для авто-продления укажите дату окончания (effective_until)",
            status_code=422,
        )
    for brk in data.get("breaks", []):
        _validate_time_range(brk.get("start_time"), brk.get("end_time"))

    with SessionLocal() as db:
        if not storage.is_psychologist(data["psychologist_id"], db):
            raise AppointmentError("Психолог не найден", status_code=422)
        result = storage.create_schedule_series(data, db)
        db.commit()
    return result


def _series_or_404(series_id: str, db) -> list:
    rules = storage.get_series_rules(series_id, db)
    if not rules:
        raise AppointmentError("Расписание не найдено", status_code=404)
    return rules


def update_schedule(series_id, data: dict) -> dict:
    """Отредактировать серию расписания атомарно (один commit).

    Психолог серии и существующие записи не меняются (см. storage). auto_extend
    требует effective_until; время правил и перерывов валидируется как в create.
    is_active серии сохраняется (PATCH не активирует деактивированную серию).
    """
    _validate_time_range(data.get("start_time"), data.get("end_time"))
    if data.get("auto_extend") and not data.get("effective_until"):
        raise AppointmentError(
            "Для авто-продления укажите дату окончания (effective_until)",
            status_code=422,
        )
    for brk in data.get("breaks", []):
        _validate_time_range(brk.get("start_time"), brk.get("end_time"))

    with SessionLocal() as db:
        _series_or_404(series_id, db)
        result = storage.update_schedule_series(series_id, data, db)
        db.commit()
    return result


def schedule_impact(series_id: str) -> dict:
    """Сколько будущих записей попадает в период серии (предупреждение)."""
    with SessionLocal() as db:
        rules = _series_or_404(series_id, db)
        future = storage.count_future_appointments_for_series(rules, db)
    return {"series_id": str(series_id), "future_appointments": future}


def soft_delete_schedule(series_id: str) -> dict:
    """Деактивировать расписание (серию). Записи НЕ удаляются.

    Возвращает счётчики и количество будущих записей в периоде как
    предупреждение (записи остаются и продолжают занимать слоты).
    """
    with SessionLocal() as db:
        rules = _series_or_404(series_id, db)
        future = storage.count_future_appointments_for_series(rules, db)
        r_count, b_count = storage.soft_delete_series(series_id, db)
        db.commit()
    return {
        "series_id":         str(series_id),
        "deactivated_rules": r_count,
        "deactivated_breaks": b_count,
        "future_appointments": future,
    }


def restore_schedule(series_id: str) -> dict:
    """Восстановить ранее деактивированное расписание (серию)."""
    with SessionLocal() as db:
        _series_or_404(series_id, db)
        storage.restore_series(series_id, db)
        db.commit()
        rules = storage.get_series_rules(series_id, db)
        breaks = storage.get_series_breaks(series_id, db)
        return _series_to_dict(series_id, rules, breaks)


def extend_schedule(series_id: str, months: int = 1) -> dict:
    """Быстрое действие «продлить на месяц»: двигает effective_until серии."""
    with SessionLocal() as db:
        rules = _series_or_404(series_id, db)
        today = datetime.now(MOSCOW_TZ).date()
        current = rules[0].effective_until
        base = current if current is not None else max(today, rules[0].effective_from)
        new_until = _add_months(base, months)
        storage.extend_series(series_id, new_until, db)
        db.commit()
        rules = storage.get_series_rules(series_id, db)
        breaks = storage.get_series_breaks(series_id, db)
        return _series_to_dict(series_id, rules, breaks)


def auto_extend_schedules(
    within_days: int = 14, months: int = 1, dry_run: bool = False
) -> dict:
    """Автопродление расписаний (maintenance, НЕ из FastAPI lifespan).

    Продлевает effective_until на `months` для активных серий с auto_extend,
    у которых окно заканчивается в пределах `within_days`. После продления
    отправляет system-сообщение создавшему серию supervisor'у (soft-fail).

    dry_run=True откатывает изменения и не шлёт уведомления (только подсчёт).
    Возвращает сводку {extended_series, notified, dry_run}.
    """
    today = datetime.now(MOSCOW_TZ).date()
    threshold = today + timedelta(days=within_days)

    notifications: list[tuple[int, str, str]] = []
    extended = 0
    with SessionLocal() as db:
        series_ids = storage.get_auto_extend_series_due(threshold, db)
        for series_id in series_ids:
            rules = storage.get_series_rules(series_id, db)
            if not rules:
                continue
            base = rules[0].effective_until or today
            new_until = _add_months(base, months)
            storage.extend_series(series_id, new_until, db)
            extended += 1
            creator = rules[0].created_by
            if creator:
                notifications.append(
                    (creator, str(series_id), str(new_until))
                )
        if dry_run:
            db.rollback()
        else:
            db.commit()

    if dry_run:
        return {"extended_series": extended, "notified": 0, "dry_run": True}

    # System-уведомления — soft-fail, вне основной транзакции.
    notified = 0
    for creator_id, sid, new_until in notifications:
        if _notify_schedule_extended(creator_id, sid, new_until):
            notified += 1

    return {"extended_series": extended, "notified": notified, "dry_run": False}


def _notify_schedule_extended(
    supervisor_id: int, series_id: str, new_until: str
) -> bool:
    try:
        from app.chat.system_publisher import publish_system_message
        result = publish_system_message(
            recipient_id=supervisor_id,
            event_key=f"schedule_auto_extended:{series_id}:{new_until}",
            text=(
                f"Расписание продлено автоматически до {new_until}"
            ),
        )
        return result is not None
    except Exception:
        return False


def _series_to_dict(series_id: str, rules: list, breaks: list) -> dict:
    """Собрать ScheduleSeriesRead-совместимый dict из ORM rules/breaks."""
    head = rules[0]
    return {
        "series_id":       str(series_id),
        "psychologist_id": head.psychologist_id,
        "meeting_type_id": head.meeting_type_id,
        "auto_extend":     head.auto_extend,
        "effective_from":  str(head.effective_from),
        "effective_until": str(head.effective_until)
                           if head.effective_until else None,
        "is_active":       head.is_active,
        "rules":           [storage._rule_to_dict(r) for r in rules],
        "breaks":          [storage._break_to_dict(b) for b in breaks],
    }


def _add_months(d: date, months: int) -> date:
    """Прибавить months месяцев к дате, обрезая день до конца месяца."""
    import calendar
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


# ── Schedule breaks (supervisor) ────────────────────────────────────────────

def list_schedule_breaks(psychologist_id: int) -> list[dict]:
    with SessionLocal() as db:
        return storage.get_schedule_breaks(psychologist_id, db)


def create_schedule_breaks(data: dict) -> list[dict]:
    """Bulk-создание повторяющихся перерывов (например обед)."""
    _validate_time_range(data.get("start_time"), data.get("end_time"))
    with SessionLocal() as db:
        result = storage.create_schedule_breaks_bulk(data, db)
        db.commit()
    return result


def deactivate_schedule_break(break_id: int) -> None:
    with SessionLocal() as db:
        found = storage.deactivate_schedule_break(break_id, db)
        if not found:
            raise AppointmentError(
                "Перерыв не найден", status_code=404
            )
        db.commit()


# ── Schedule exceptions (supervisor) ────────────────────────────────────────

_EXCEPTION_TYPES = ("day_off", "unavailable", "extra_availability")


def create_schedule_exception(data: dict) -> dict:
    etype = data.get("exception_type")
    if etype not in _EXCEPTION_TYPES:
        raise AppointmentError(
            "Неверный тип исключения "
            "(day_off / unavailable / extra_availability)",
            status_code=422,
        )
    if etype in ("unavailable", "extra_availability"):
        _validate_time_range(data.get("start_time"), data.get("end_time"))
    with SessionLocal() as db:
        try:
            result = storage.create_schedule_exception(data, db)
            db.commit()
        except IntegrityError:
            db.rollback()
            raise AppointmentError(
                "Конфликт исключения расписания", status_code=409
            )
    return result


def list_schedule_exceptions(
    psychologist_id: int,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> list[dict]:
    """Список разовых изменений психолога (с опц. фильтром по периоду)."""
    with SessionLocal() as db:
        return storage.get_schedule_exceptions(
            psychologist_id, date_from, date_to, db
        )


# ── GroupSession management (supervisor) ──────────────────────────────────

def list_group_sessions(
    page: int = 1,
    size: int = 20,
    include_past: bool = False,
    open_only: bool = False,
) -> tuple[list[dict], int]:
    with SessionLocal() as db:
        return storage.get_group_sessions_list(
            db,
            page=page,
            size=size,
            include_past=include_past,
            open_only=open_only,
        )


def list_group_sessions_psychologist(
    psychologist_id: int,
    page: int = 1,
    size: int = 20,
    include_past: bool = False,
) -> tuple[list[dict], int]:
    """Group sessions assigned to a given psychologist."""
    with SessionLocal() as db:
        return storage.get_group_sessions_list(
            db,
            page=page,
            size=size,
            include_past=include_past,
            open_only=False,
            psychologist_id_filter=int(psychologist_id),
        )


def create_group_session(data: dict) -> dict:
    with SessionLocal() as db:
        mt = storage.get_meeting_type(data["meeting_type_id"], db)
        if mt is None:
            raise AppointmentError(
                "Тип встречи не найден", status_code=404
            )
        if not mt.is_group:
            raise AppointmentError(
                "Для группового занятия нужен групповой тип встречи",
                status_code=422,
            )
        if not storage.is_psychologist(data["psychologist_id"], db):
            raise AppointmentError(
                "Психолог не найден", status_code=422
            )
        _validate_group_session_format(data.get("format"), mt)
        result = storage.create_group_session(data, db)
        db.commit()
    return result


def update_group_session(uuid: str, updates: dict) -> dict:
    with SessionLocal() as db:
        gs = storage.get_group_session_by_uuid(uuid, db)
        if gs is None:
            raise AppointmentError(
                "Групповое занятие не найдено", status_code=404
            )
        if "format" in updates or "meeting_type_id" in updates:
            mt_id = updates.get("meeting_type_id", gs.meeting_type_id)
            mt = storage.get_meeting_type(mt_id, db)
            if mt is None:
                raise AppointmentError(
                    "Тип встречи не найден", status_code=404
                )
            if not mt.is_group:
                raise AppointmentError(
                    "Для группового занятия нужен групповой тип встречи",
                    status_code=422,
                )
            fmt = updates.get("format", gs.format)
            _validate_group_session_format(fmt, mt)
        if "psychologist_id" in updates:
            if not storage.is_psychologist(updates["psychologist_id"], db):
                raise AppointmentError(
                    "Психолог не найден", status_code=422
                )
        result = storage.update_group_session(gs, updates, db)
        db.commit()
    return result


def _validate_group_session_format(fmt: Optional[str], mt) -> None:
    """Format of a group session must be allowed by its meeting type."""
    if fmt is None:
        return
    if fmt == "in_person" and not mt.allow_in_person:
        raise AppointmentError(
            "Тип встречи не поддерживает очный формат",
            status_code=422,
        )
    if fmt == "online" and not mt.allow_online:
        raise AppointmentError(
            "Тип встречи не поддерживает онлайн-формат",
            status_code=422,
        )


def set_group_session_booking(uuid: str, enabled: bool) -> dict:
    with SessionLocal() as db:
        gs = storage.get_group_session_by_uuid(uuid, db)
        if gs is None:
            raise AppointmentError(
                "Групповое занятие не найдено", status_code=404
            )
        result = storage.set_group_session_booking(gs, enabled, db)
        db.commit()
    return result


# ── Group session registration (student) ──────────────────────────────────

def list_group_sessions_student(
    student_id: int,
    page: int = 1,
    size: int = 20,
) -> tuple[list[dict], int]:
    with SessionLocal() as db:
        return storage.get_group_sessions_list(
            db,
            page=page,
            size=size,
            include_past=False,
            open_only=False,
            student_id=student_id,
        )


def student_register_group(uuid: str, student_user: dict) -> dict:
    now_msk = datetime.now(MOSCOW_TZ)
    cutoff = now_msk + timedelta(hours=1)

    # Только активный аккаунт студента может записываться на занятия.
    if not student_user.get("is_active", True):
        raise AppointmentError(
            "Ваш аккаунт неактивен", status_code=403
        )

    with SessionLocal() as db:
        gs = storage.get_group_session_by_uuid(uuid, db)
        if gs is None:
            raise AppointmentError(
                "Групповое занятие не найдено", status_code=404
            )
        if gs.status != "scheduled":
            raise AppointmentError(
                "Занятие недоступно для записи", status_code=422
            )
        if not gs.booking_enabled:
            raise AppointmentError(
                "Запись на это занятие закрыта", status_code=422
            )

        # Check meeting type is active and bookable
        from app.db.models import MeetingType
        mt = db.query(MeetingType).filter(
            MeetingType.id == gs.meeting_type_id
        ).first()
        if mt is None or not mt.is_active:
            raise AppointmentError(
                "Тип занятия недоступен", status_code=422
            )
        if not mt.is_bookable:
            raise AppointmentError(
                "Данный тип занятия недоступен для записи",
                status_code=422,
            )

        # Must register at least 1 hour before start
        if gs.starts_at <= cutoff:
            raise AppointmentError(
                "Запись возможна минимум за 1 час до начала занятия",
                status_code=422,
            )

        existing = storage.get_student_registration(
            gs.id, int(student_user["id"]), db
        )
        if existing and existing.status == "registered":
            raise AppointmentError(
                "Вы уже зарегистрированы на это занятие",
                status_code=409,
            )

        # Lock group session row to serialise concurrent registrations
        gs_locked = storage.lock_group_session_for_update(gs.id, db)
        count = storage.count_active_registrations(gs_locked.id, db)
        if count >= gs_locked.capacity:
            raise AppointmentError(
                "Нет свободных мест", status_code=409
            )

        result = storage.register_student_group_session(
            gs_locked, int(student_user["id"]), db
        )
        db.commit()

    return result


def student_cancel_group(uuid: str, student_user: dict) -> None:
    now_msk = datetime.now(MOSCOW_TZ)
    today_msk = now_msk.date()

    with SessionLocal() as db:
        gs = storage.get_group_session_by_uuid(uuid, db)
        if gs is None:
            raise AppointmentError(
                "Групповое занятие не найдено", status_code=404
            )
        # Cancel only before the day of the session
        gs_day_msk = gs.starts_at.astimezone(MOSCOW_TZ).date()
        if gs_day_msk <= today_msk:
            raise AppointmentError(
                "Отмена возможна только до дня занятия",
                status_code=422,
            )
        cancelled = storage.cancel_student_group_session(
            uuid, int(student_user["id"]), db
        )
        if not cancelled:
            raise AppointmentError(
                "Регистрация не найдена", status_code=404
            )
        db.commit()


# ── Internal helpers ──────────────────────────────────────────────────────

def _fmt_dt(dt: datetime) -> str:
    msk = dt.astimezone(MOSCOW_TZ)
    return msk.strftime("%d.%m.%Y %H:%M")


def _validate_time_range(start_val, end_val) -> None:
    """Проверяет start < end.

    Принимает как строки 'HH:MM', так и уже распарсенные datetime.time
    (роутер парсит строки в time перед вызовом сервиса).
    """
    if start_val is None or end_val is None or start_val == "" or end_val == "":
        raise AppointmentError(
            "Укажите start_time и end_time", status_code=422
        )
    try:
        start = (
            time.fromisoformat(start_val)
            if isinstance(start_val, str) else start_val
        )
        end = (
            time.fromisoformat(end_val)
            if isinstance(end_val, str) else end_val
        )
    except ValueError:
        raise AppointmentError(
            "Неверный формат времени (HH:MM)", status_code=422
        )
    if start >= end:
        raise AppointmentError(
            "start_time должен быть раньше end_time", status_code=422
        )
