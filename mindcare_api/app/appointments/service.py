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

import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

from app.core.normalization import normalize_email
from app.db.session import SessionLocal
from app.appointments import storage
from app.audit import Actor
from app.audit.request_context import build_request_context

# Moscow is UTC+3, no DST since 2014
MOSCOW_TZ = timezone(timedelta(hours=3))


def _audit_actor_ctx(actor_id, actor_role, ip, user_agent):
    """Stage 5B-1: строит ОДИН sanitized RequestContext + Actor на операцию
    (route определяет actor id/role; storage получает готовые объекты)."""
    return (
        Actor.user(int(actor_id), actor_role),
        build_request_context(ip=ip, user_agent=user_agent),
    )


class AppointmentError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code


# ── Stage 5B-2: durable failure audit codes + auditable error subclass ───────
# Стабильные snake_case коды для доказанных precommit business-отказов с
# security/compliance-ценностью (audit-worthiness review §3). Обычная input/UX-
# валидация НЕ получает код и остаётся базовым AppointmentError (не аудируется).
AUDIT_CODE_ACCOUNT_INACTIVE = "account_inactive"
AUDIT_CODE_ENGAGEMENT_REQUIRED = "engagement_required"
AUDIT_CODE_ACCESS_DENIED = "access_denied"
AUDIT_CODE_CONSENT_REQUIRED = "consent_required"

# Локальная копия формата стабильного имени (не импортируем приватную
# app.audit.registry._STABLE_NAME_RE — appointments/service.py не должен
# зависеть от внутренностей registry). Совпадает по смыслу: lowercase
# snake_case, начинается с буквы.
_AUDIT_CODE_MAX_LEN = 100
_AUDIT_CODE_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class AuditableAppointmentError(AppointmentError):
    """Precommit business-отказ, подлежащий durable failure-аудиту.

    audit_code обязателен и должен быть стабильным snake_case-идентификатором
    (str, длина 1..100, ^[a-z][a-z0-9_]*$) — иначе это programming contract
    error (fail-fast: фиксированный RuntimeError без самого audit_code/
    message/UUID/ролей/иных данных). Auditability определяется ТИПОМ (route:
    isinstance), не строкой и не ambiguous None.
    """

    def __init__(self, message: str, status_code: int, *, audit_code: str):
        if (
            not isinstance(audit_code, str)
            or not (1 <= len(audit_code) <= _AUDIT_CODE_MAX_LEN)
            or not _AUDIT_CODE_RE.fullmatch(audit_code)
        ):
            raise RuntimeError(
                "AuditableAppointmentError requires a stable snake_case "
                "audit_code (^[a-z][a-z0-9_]*$, length 1..100)"
            )
        super().__init__(message, status_code)
        self.audit_code = audit_code


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
    *,
    actor_role: str,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    now_msk = datetime.now(MOSCOW_TZ)
    cutoff = now_msk + timedelta(hours=1)

    if not student_user.get("is_active", True):
        raise AuditableAppointmentError(
            "Ваш аккаунт неактивен", 403,
            audit_code=AUDIT_CODE_ACCOUNT_INACTIVE,
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
            raise AuditableAppointmentError(
                "У вас нет активного назначенного психолога", 403,
                audit_code=AUDIT_CODE_ENGAGEMENT_REQUIRED,
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

        actor, ctx = _audit_actor_ctx(
            student_user["id"], actor_role, ip, user_agent
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
            actor=actor,
            context=ctx,
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
    *,
    current_user: dict,
    actor_role: str,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
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
                raise AuditableAppointmentError(
                    "Студент не закреплён за этим психологом", 422,
                    audit_code=AUDIT_CODE_ENGAGEMENT_REQUIRED,
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
        actor, ctx = _audit_actor_ctx(booker_id, actor_role, ip, user_agent)
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
            actor=actor,
            context=ctx,
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
    data: dict, current_user: dict,
    *, actor_role: str,
    ip: Optional[str] = None, user_agent: Optional[str] = None,
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
        raise AuditableAppointmentError(
            "Требуется согласие на обработку персональных данных", 422,
            audit_code=AUDIT_CODE_CONSENT_REQUIRED,
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
        actor, ctx = _audit_actor_ctx(
            current_user["id"], actor_role, ip, user_agent
        )
        result = storage.create_unregistered_student_card(
            record, db, actor=actor, context=ctx
        )
        db.commit()
    return result


_CARD_EDITABLE_FIELDS = (
    "full_name", "phone", "email", "birth_date", "comment", "primary_concern",
)


def update_unregistered_student_card(
    card_id: int, updates: dict,
    *, current_user: dict, actor_role: str,
    ip: Optional[str] = None, user_agent: Optional[str] = None,
) -> dict:
    """Частичное обновление карточки (только личные поля).

    service лишь НОРМАЛИЗУЕТ разрешённые входные поля; решение mutation/no-op и
    diff — на storage (единственный владелец). Audit/consent/linked_user_id не
    редактируются. При смене email пересчитывается normalized_email.
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
        actor, ctx = _audit_actor_ctx(
            current_user["id"], actor_role, ip, user_agent
        )
        result = storage.update_unregistered_student_card(
            card, clean, db, actor=actor, context=ctx
        )
        db.commit()
    return result


def archive_unregistered_student_card(
    card_id: int,
    *, current_user: dict, actor_role: str,
    ip: Optional[str] = None, user_agent: Optional[str] = None,
) -> dict:
    with SessionLocal() as db:
        card = storage.get_unregistered_student_card(card_id, db)
        if card is None:
            raise AppointmentError("Карточка не найдена", status_code=404)
        actor, ctx = _audit_actor_ctx(
            current_user["id"], actor_role, ip, user_agent
        )
        result = storage.archive_unregistered_student_card(
            card, db, actor=actor, context=ctx
        )
        db.commit()
    return result


def link_unregistered_cards_to_user(
    user_id, email: str,
    *, actor_id, actor_role: str,
    ip: Optional[str] = None, user_agent: Optional[str] = None,
) -> int:
    """Привязать карточки незарегистрированного студента к аккаунту (этап 2).

    Два caller (разный actor): self-registration (actor=созданный/восстановленный
    student) и staff-created student (actor=исходный supervisor/admin). Один
    Actor + один RequestContext + один SessionLocal + один commit. storage
    возвращает список id привязанных карточек; audit per-card в той же транзакции.
    Идемпотентна: повторный вызов → 0 карточек → 0 audit-строк. Карточка,
    привязанная к другому пользователю, не перепривязывается и не аудируется.
    ПДн не логируются. Возвращает число привязанных карточек (linked_cards_count).
    """
    with SessionLocal() as db:
        actor, ctx = _audit_actor_ctx(actor_id, actor_role, ip, user_agent)
        card_ids = storage.link_unregistered_cards_to_user(
            int(user_id), email, db, actor=actor, context=ctx
        )
        db.commit()
    return len(card_ids)


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
    *,
    actor_role: str,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
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
            raise AuditableAppointmentError(
                "Нет доступа", 403, audit_code=AUDIT_CODE_ACCESS_DENIED,
            )
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

        actor, ctx = _audit_actor_ctx(
            student_user["id"], actor_role, ip, user_agent
        )
        result = storage.cancel_appointment(
            appt=appt,
            canceled_by=int(student_user["id"]),
            reason=reason,
            db=db,
            soft_delete=not was_confirmed,
            actor=actor,
            context=ctx,
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


def psychologist_confirm(
    uuid: str, psychologist_user: dict,
    *, actor_role: str,
    ip: Optional[str] = None, user_agent: Optional[str] = None,
) -> dict:
    with SessionLocal() as db:
        appt = storage.get_appointment_by_uuid(uuid, db)
        if appt is None:
            raise AppointmentError("Запись не найдена", status_code=404)
        if appt.psychologist_id != int(psychologist_user["id"]):
            raise AuditableAppointmentError(
                "Нет доступа", 403, audit_code=AUDIT_CODE_ACCESS_DENIED,
            )
        if appt.status != "pending_confirmation":
            raise AppointmentError(
                f"Нельзя подтвердить статус {appt.status}",
                status_code=422,
            )
        # Получатель уведомления: прямой студент или привязанный к карточке user
        # (захватываем ДО commit, пока appt в сессии).
        recipient_id = _appt_student_recipient(appt, db)
        actor, ctx = _audit_actor_ctx(
            psychologist_user["id"], actor_role, ip, user_agent
        )
        result = storage.confirm_appointment(appt, db, actor=actor, context=ctx)
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
    *,
    actor_role: str,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    with SessionLocal() as db:
        appt = storage.get_appointment_by_uuid(uuid, db)
        if appt is None:
            raise AppointmentError("Запись не найдена", status_code=404)
        if appt.psychologist_id != int(psychologist_user["id"]):
            raise AuditableAppointmentError(
                "Нет доступа", 403, audit_code=AUDIT_CODE_ACCESS_DENIED,
            )
        if appt.status not in ("pending_confirmation", "confirmed"):
            raise AppointmentError(
                f"Нельзя отклонить статус {appt.status}",
                status_code=422,
            )
        # Получатель уведомления: прямой студент или привязанный к карточке user
        # (захватываем ДО commit, пока appt в сессии).
        recipient_id = _appt_student_recipient(appt, db)
        actor, ctx = _audit_actor_ctx(
            psychologist_user["id"], actor_role, ip, user_agent
        )
        result = storage.decline_appointment(
            appt, reason, db, actor=actor, context=ctx
        )
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


def create_meeting_type(
    data: dict, *, actor_id, actor_role: str,
    ip: Optional[str] = None, user_agent: Optional[str] = None,
) -> dict:
    _validate_group_formats(data)
    with SessionLocal() as db:
        actor, ctx = _audit_actor_ctx(actor_id, actor_role, ip, user_agent)
        result = storage.create_meeting_type(
            data, db, actor=actor, context=ctx
        )
        db.commit()
    return result


def update_meeting_type(
    mt_id: int, updates: dict, *, actor_id, actor_role: str,
    ip: Optional[str] = None, user_agent: Optional[str] = None,
) -> dict:
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
        actor, ctx = _audit_actor_ctx(actor_id, actor_role, ip, user_agent)
        result = storage.update_meeting_type(
            mt, updates, db, actor=actor, context=ctx
        )
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


def create_schedule_rules(
    data: dict, *, actor_id, actor_role: str,
    ip: Optional[str] = None, user_agent: Optional[str] = None,
) -> list[dict]:
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
        actor, ctx = _audit_actor_ctx(actor_id, actor_role, ip, user_agent)
        result = storage.create_schedule_rules_bulk(
            data, db, actor=actor, context=ctx
        )
        db.commit()
    return result


def deactivate_schedule_rule(
    rule_id: int, *, actor_id, actor_role: str,
    ip: Optional[str] = None, user_agent: Optional[str] = None,
) -> None:
    with SessionLocal() as db:
        actor, ctx = _audit_actor_ctx(actor_id, actor_role, ip, user_agent)
        found = storage.deactivate_schedule_rule(
            rule_id, db, actor=actor, context=ctx
        )
        if not found:
            raise AppointmentError(
                "Правило расписания не найдено", status_code=404
            )
        db.commit()


# ── Unified schedule (series) management (supervisor) ──────────────────────

def create_schedule(
    data: dict, *, actor_id, actor_role: str,
    ip: Optional[str] = None, user_agent: Optional[str] = None,
) -> dict:
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
        actor, ctx = _audit_actor_ctx(actor_id, actor_role, ip, user_agent)
        result = storage.create_schedule_series(
            data, db, actor=actor, context=ctx
        )
        db.commit()
    return result


def _series_or_404(series_id: str, db) -> list:
    rules = storage.get_series_rules(series_id, db)
    if not rules:
        raise AppointmentError("Расписание не найдено", status_code=404)
    return rules


def update_schedule(
    series_id, data: dict, *, actor_id, actor_role: str,
    ip: Optional[str] = None, user_agent: Optional[str] = None,
) -> dict:
    """Отредактировать серию расписания атомарно (один commit).

    Психолог серии и существующие записи не меняются (см. storage). auto_extend
    требует effective_until; время правил и перерывов валидируется как в create.
    is_active серии сохраняется (PATCH не активирует деактивированную серию).
    Идентичный payload — no-op: строки не пересоздаются, audit не пишется.
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
        actor, ctx = _audit_actor_ctx(actor_id, actor_role, ip, user_agent)
        result = storage.update_schedule_series(
            series_id, data, db, actor=actor, context=ctx
        )
        db.commit()
    return result


def schedule_impact(series_id: str) -> dict:
    """Сколько будущих записей попадает в период серии (предупреждение)."""
    with SessionLocal() as db:
        rules = _series_or_404(series_id, db)
        future = storage.count_future_appointments_for_series(rules, db)
    return {"series_id": str(series_id), "future_appointments": future}


def soft_delete_schedule(
    series_id: str, *, actor_id, actor_role: str,
    ip: Optional[str] = None, user_agent: Optional[str] = None,
) -> dict:
    """Деактивировать расписание (серию). Записи НЕ удаляются.

    Возвращает счётчики и количество будущих записей в периоде как
    предупреждение (записи остаются и продолжают занимать слоты).
    Повторная деактивация — no-op без audit.
    """
    with SessionLocal() as db:
        rules = _series_or_404(series_id, db)
        future = storage.count_future_appointments_for_series(rules, db)
        actor, ctx = _audit_actor_ctx(actor_id, actor_role, ip, user_agent)
        r_count, b_count = storage.soft_delete_series(
            series_id, db, actor=actor, context=ctx
        )
        db.commit()
    return {
        "series_id":         str(series_id),
        "deactivated_rules": r_count,
        "deactivated_breaks": b_count,
        "future_appointments": future,
    }


def restore_schedule(
    series_id: str, *, actor_id, actor_role: str,
    ip: Optional[str] = None, user_agent: Optional[str] = None,
) -> dict:
    """Восстановить ранее деактивированное расписание (серию).

    Повторный restore уже активной серии — no-op без audit.
    """
    with SessionLocal() as db:
        _series_or_404(series_id, db)
        actor, ctx = _audit_actor_ctx(actor_id, actor_role, ip, user_agent)
        storage.restore_series(series_id, db, actor=actor, context=ctx)
        db.commit()
        rules = storage.get_series_rules(series_id, db)
        breaks = storage.get_series_breaks(series_id, db)
        return _series_to_dict(series_id, rules, breaks)


def extend_schedule(
    series_id: str, months: int = 1, *, actor_id, actor_role: str,
    ip: Optional[str] = None, user_agent: Optional[str] = None,
) -> dict:
    """Быстрое действие «продлить на месяц»: двигает effective_until серии.

    Событие пишется только при фактическом сдвиге effective_until.
    """
    with SessionLocal() as db:
        rules = _series_or_404(series_id, db)
        today = datetime.now(MOSCOW_TZ).date()
        current = rules[0].effective_until
        base = current if current is not None else max(today, rules[0].effective_from)
        new_until = _add_months(base, months)
        actor, ctx = _audit_actor_ctx(actor_id, actor_role, ip, user_agent)
        storage.extend_series(
            series_id, new_until, db, actor=actor, context=ctx
        )
        db.commit()
        rules = storage.get_series_rules(series_id, db)
        breaks = storage.get_series_breaks(series_id, db)
        return _series_to_dict(series_id, rules, breaks)


def complete_due_group_sessions_job() -> dict:
    """Stage 5C-3: явный maintenance-переход групповых занятий в `completed`.

    Заменяет прежний lazy-вызов из GET/list и из регистрации — read-пути больше
    не мутируют. Один атомарный `UPDATE … RETURNING id` + per-row
    `group_session_completed` (Actor.system(), context=None) в ТОЙ ЖЕ
    транзакции: сбой аудита откатывает переход, ложного success не возникает.
    Пустой результат → 0 строк, 0 событий, один согласованный no-op commit.

    ЭКСПЛУАТАЦИОННОЕ ТРЕБОВАНИЕ: job обязан запускаться внешним планировщиком
    (cron / systemd timer / Task Scheduler) — без него `status` групповых
    занятий перестаёт актуализироваться. Исключения наружу не подавляются:
    вызывающий скрипт обязан завершиться ненулевым кодом.
    """
    now_msk = datetime.now(MOSCOW_TZ)
    with SessionLocal() as db:
        completed_ids = storage.complete_due_group_sessions(
            db, now_msk, actor=Actor.system(), context=None
        )
        db.commit()
    return {"completed_sessions": len(completed_ids)}


def auto_extend_schedules(
    within_days: int = 14, months: int = 1, dry_run: bool = False
) -> dict:
    """Автопродление расписаний (maintenance, НЕ из FastAPI lifespan).

    Продлевает effective_until на `months` для активных серий с auto_extend,
    у которых окно заканчивается в пределах `within_days`. После продления
    отправляет system-сообщение создавшему серию supervisor'у (soft-fail).

    Stage 5C-3:
    - **per-series транзакция** (не batch): ограничивает время удержания
      блокировок и не откатывает весь прогон из-за одной серии;
    - блокировка по стабильной identity `FOR UPDATE SKIP LOCKED` — второй
      параллельный worker серию пропускает, двойного продления нет;
    - предикат due **перепроверяется ПОСЛЕ** блокировки — если первый worker уже
      сдвинул границу, второй ничего не делает;
    - событие `schedule_auto_extended` (Actor.system()) пишется только при
      фактическом сдвиге; сбой аудита откатывает продление ЭТОЙ серии;
    - **dry_run вообще не вызывает `record_event`**: ветка только читает и
      считает, не берёт блокировок, не мутирует и не шлёт уведомлений — превью
      не зависит от доступности audit storage.

    Возвращает сводку {extended_series, notified, dry_run}.
    """
    today = datetime.now(MOSCOW_TZ).date()
    threshold = today + timedelta(days=within_days)

    with SessionLocal() as db:
        series_ids = storage.get_auto_extend_series_due(threshold, db)

    if dry_run:
        # Preview: только чтение. Ни мутаций, ни блокировок, ни record_event.
        preview = 0
        with SessionLocal() as db:
            for series_id in series_ids:
                rules = storage.get_series_rules(series_id, db)
                if not rules or rules[0].effective_until is None:
                    continue
                if _add_months(rules[0].effective_until, months) != \
                        rules[0].effective_until:
                    preview += 1
        return {"extended_series": preview, "notified": 0, "dry_run": True}

    notifications: list[tuple[int, str, str]] = []
    extended = 0
    for series_id in series_ids:
        # Отдельная транзакция на серию.
        with SessionLocal() as db:
            if storage.lock_series_for_maintenance(series_id, db) is None:
                continue          # SKIP LOCKED: серию обрабатывает другой worker
            rules = storage.get_series_rules(series_id, db)
            if not rules:
                continue
            head = rules[0]
            # Перепроверка предиката ПОСЛЕ блокировки — защита от двойного
            # продления, если первый worker уже сдвинул effective_until.
            if not (head.auto_extend and head.is_active
                    and head.effective_until is not None
                    and head.effective_until <= threshold):
                continue
            new_until = _add_months(head.effective_until, months)
            changed = storage.auto_extend_series(
                series_id, new_until, db, actor=Actor.system(), context=None
            )
            if changed:
                extended += 1
                if head.created_by:
                    notifications.append(
                        (head.created_by, str(series_id), str(new_until))
                    )
            db.commit()

    # System-уведомления — soft-fail, вне транзакций.
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


def create_schedule_breaks(
    data: dict, *, actor_id, actor_role: str,
    ip: Optional[str] = None, user_agent: Optional[str] = None,
) -> list[dict]:
    """Bulk-создание повторяющихся перерывов (например обед)."""
    _validate_time_range(data.get("start_time"), data.get("end_time"))
    with SessionLocal() as db:
        actor, ctx = _audit_actor_ctx(actor_id, actor_role, ip, user_agent)
        result = storage.create_schedule_breaks_bulk(
            data, db, actor=actor, context=ctx
        )
        db.commit()
    return result


def deactivate_schedule_break(
    break_id: int, *, actor_id, actor_role: str,
    ip: Optional[str] = None, user_agent: Optional[str] = None,
) -> None:
    with SessionLocal() as db:
        actor, ctx = _audit_actor_ctx(actor_id, actor_role, ip, user_agent)
        found = storage.deactivate_schedule_break(
            break_id, db, actor=actor, context=ctx
        )
        if not found:
            raise AppointmentError(
                "Перерыв не найден", status_code=404
            )
        db.commit()


# ── Schedule exceptions (supervisor) ────────────────────────────────────────

_EXCEPTION_TYPES = ("day_off", "unavailable", "extra_availability")


def create_schedule_exception(
    data: dict, *, actor_id, actor_role: str,
    ip: Optional[str] = None, user_agent: Optional[str] = None,
) -> dict:
    """Создать разовое исключение расписания.

    Corrective (Stage 5C): выдуманный доменный 409 «Конфликт исключения
    расписания» УДАЛЁН — у `schedule_exceptions` нет unique-констрейнтов
    (уникальность снята миграцией 9e193b84bba8), поэтому такого конфликта не
    существует. Под него маскировалась FK-ошибка на несуществующего психолога;
    теперь она проверяется явно и даёт правдивый 422 (как в `create_schedule`).
    IntegrityError больше не переименовывается в бизнес-конфликт;
    `AuditError`/`AuditStorageError` по-прежнему всплывают и откатывают мутацию.
    """
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
        if not storage.is_psychologist(data["psychologist_id"], db):
            raise AppointmentError("Психолог не найден", status_code=422)
        actor, ctx = _audit_actor_ctx(actor_id, actor_role, ip, user_agent)
        result = storage.create_schedule_exception(
            data, db, actor=actor, context=ctx
        )
        db.commit()
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
    include_past: bool = True,
    open_only: bool = False,
) -> tuple[list[dict], int]:
    with SessionLocal() as db:
        return storage.get_group_sessions_list(
            db,
            page=page,
            size=size,
            include_past=include_past,
            open_only=open_only,
            statuses=("scheduled", "completed", "cancelled"),
            order_by="created_at_desc",
        )


def list_group_sessions_psychologist(
    psychologist_id: int,
    page: int = 1,
    size: int = 20,
    include_past: bool = True,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
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
            date_from=date_from,
            date_to=date_to,
            statuses=("scheduled", "completed", "cancelled"),
        )


def create_group_session(
    data: dict, *, actor_id, actor_role: str,
    ip: Optional[str] = None, user_agent: Optional[str] = None,
) -> dict:
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
        actor, ctx = _audit_actor_ctx(actor_id, actor_role, ip, user_agent)
        result = storage.create_group_session(
            data, db, actor=actor, context=ctx
        )
        db.commit()
    return result


# Stage 5C-2: явный transition-контракт статуса группового занятия.
# `completed` принадлежит system maintenance (5C-3) и через generic PATCH
# запрещён; `cancelled→scheduled` (восстановление) требует отдельного
# спроектированного события и молча не вводится.
_GS_ALLOWED_STATUS_TRANSITIONS = {
    ("scheduled", "cancelled"),
}

# NOT NULL-колонки group_sessions, представленные в GroupSessionUpdate. Явный
# `null` для любой из них раньше доходил до setattr и падал NOT NULL violation
# (500). Corrective: контролируемый 422 ДО мутации. `exclude_unset=True` не
# отбрасывает явно переданный null — только неуказанные поля.
_GS_NOT_NULL_FIELDS = (
    "status", "booking_enabled", "meeting_type_id", "psychologist_id",
    "starts_at", "format", "capacity",
)


def _reject_explicit_nulls(updates: dict) -> None:
    """Явный null для NOT NULL-поля → 422 до любой мутации и до audit."""
    for field in _GS_NOT_NULL_FIELDS:
        if field in updates and updates[field] is None:
            raise AppointmentError(
                f"Поле '{field}' не может быть null", status_code=422
            )


def _validate_group_status_transition(current: str, target: str) -> None:
    if current == target:
        return                      # identical — no-op, проверять нечего
    if target == "completed":
        raise AppointmentError(
            "Статус 'completed' выставляется только системным обслуживанием",
            status_code=422,
        )
    if (current, target) not in _GS_ALLOWED_STATUS_TRANSITIONS:
        raise AppointmentError(
            f"Недопустимый переход статуса: {current} → {target}",
            status_code=422,
        )


def update_group_session(
    uuid: str, updates: dict, *, actor_id, actor_role: str,
    ip: Optional[str] = None, user_agent: Optional[str] = None,
) -> dict:
    with SessionLocal() as db:
        gs = storage.get_group_session_by_uuid(uuid, db)
        if gs is None:
            raise AppointmentError(
                "Групповое занятие не найдено", status_code=404
            )
        _reject_explicit_nulls(updates)
        if "status" in updates:
            _validate_group_status_transition(gs.status, updates["status"])
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
        actor, ctx = _audit_actor_ctx(actor_id, actor_role, ip, user_agent)
        result = storage.update_group_session(
            gs, updates, db, actor=actor, context=ctx
        )
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


def set_group_session_booking(
    uuid: str, enabled: bool, *, actor_id, actor_role: str,
    ip: Optional[str] = None, user_agent: Optional[str] = None,
) -> dict:
    with SessionLocal() as db:
        gs = storage.get_group_session_by_uuid(uuid, db)
        if gs is None:
            raise AppointmentError(
                "Групповое занятие не найдено", status_code=404
            )
        actor, ctx = _audit_actor_ctx(actor_id, actor_role, ip, user_agent)
        result = storage.set_group_session_booking(
            gs, enabled, db, actor=actor, context=ctx
        )
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
            statuses=("scheduled",),
        )


def student_register_group(
    uuid: str, student_user: dict, *, actor_role: str,
    ip: Optional[str] = None, user_agent: Optional[str] = None,
) -> dict:
    """Записать студента на групповое занятие.

    Corrective (concurrency gap, Stage 5C): раньше `status`, `booking_enabled`,
    lead time и тип встречи проверялись ОДИН РАЗ до `FOR UPDATE` и не
    перепроверялись после. Под конкуренцией supervisor мог закрыть booking,
    отменить занятие или сдвинуть `starts_at` внутрь lead time, пока студент
    ждал блокировку строки, — регистрация проходила по устаревшему состоянию и
    создавала ложное success audit-событие (`group_session_registered`) для
    занятия, которое к моменту commit уже недоступно для записи.

    Теперь состояние занятия читается РОВНО ОДИН РАЗ — тем же запросом, что
    берёт `SELECT ... FOR UPDATE` (`storage.lock_group_session_by_uuid`,
    обязательный `populate_existing()`) — и является ЕДИНСТВЕННЫМ источником
    истины для всех проверок ниже: `status`, `booking_enabled`, lead time,
    активность/бронируемость типа встречи, существующая регистрация студента,
    заполненность. Ни один из этих фактов не читается заранее и повторно не
    используется. Отказ на любой из проверок означает: мутации
    `GroupSessionRegistration` не было, `group_session_registered` не
    записан, commit не выполнен (сессия закрывается через `with` без
    незакоммиченных изменений — эквивалент rollback).

    Corrective (остаточный lead-time race): `datetime.now()` / `cutoff`
    БОЛЬШЕ НЕ вычисляются до открытия сессии. Ожидание `FOR UPDATE` может
    занять произвольное время — если бы "сейчас" было прочитано ДО него, а
    строка пересекла бы границу `starts_at - 1h` за время ожидания, проверка
    шла бы по устаревшему моменту времени. `now`/`cutoff` читаются ПОСЛЕ
    получения лока И после остальных DB-проверок, вплотную к
    `storage.register_student_group_session` — актуальнее эту границу
    сделать уже нельзя без совмещения с самой мутацией.

    Stage 5C-3: lazy-maintenance удалён отсюда — регистрация выполняется в ОДНОЙ
    транзакции с единственным commit, и audit регистрации принадлежит именно ей.
    Актуализация `status` перенесена в явный CLI-job — безопасно именно
    благодаря lead time проверке ниже, читаемой из того же locked-состояния.
    """
    # Только активный аккаунт студента может записываться на занятия.
    if not student_user.get("is_active", True):
        raise AppointmentError(
            "Ваш аккаунт неактивен", status_code=403
        )

    with SessionLocal() as db:
        # Единственное чтение состояния занятия — сразу под блокировкой строки.
        # Всё, что решает исход регистрации, проверяется ТОЛЬКО по этому объекту.
        gs = storage.lock_group_session_by_uuid(uuid, db)
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

        # Тип встречи читается ПОСЛЕ получения лока по gs.meeting_type_id —
        # тоже мог измениться конкурентным PATCH группового занятия.
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

        existing = storage.get_student_registration(
            gs.id, int(student_user["id"]), db
        )
        if existing and existing.status == "registered":
            raise AppointmentError(
                "Вы уже зарегистрированы на это занятие",
                status_code=409,
            )

        # capacity — из того же locked-объекта, count — свежий запрос под локом.
        count = storage.count_active_registrations(gs.id, db)
        if count >= gs.capacity:
            raise AppointmentError(
                "Нет свободных мест", status_code=409
            )

        # Lead time — читаем "сейчас" максимально поздно, вплотную к мутации:
        # ожидание FOR UPDATE и предыдущие DB-checks могли занять произвольное
        # время, и значение, прочитанное раньше (до лока), к этому моменту
        # устарело бы. Проверяется по locked gs.starts_at — supervisor мог
        # сдвинуть время занятия, пока эта транзакция ждала блокировку строки.
        now_msk = datetime.now(MOSCOW_TZ)
        cutoff = now_msk + timedelta(hours=1)
        if gs.starts_at <= cutoff:
            raise AppointmentError(
                "Запись возможна минимум за 1 час до начала занятия",
                status_code=422,
            )

        actor, ctx = _audit_actor_ctx(
            student_user["id"], actor_role, ip, user_agent
        )
        try:
            result = storage.register_student_group_session(
                gs, int(student_user["id"]), db, actor=actor, context=ctx
            )
        except storage.GroupRegistrationConflict:
            # Конкурентная регистрация того же студента опережает эту
            # транзакцию между re-check выше и условным UPDATE/insert; отказ
            # приходит из условного UPDATE или partial unique ux_gsr_active.
            # Ни мутации, ни audit не было.
            db.rollback()
            raise AppointmentError(
                "Вы уже зарегистрированы на это занятие", status_code=409
            ) from None
        db.commit()

    return result


def student_cancel_group(
    uuid: str, student_user: dict, *, actor_role: str,
    ip: Optional[str] = None, user_agent: Optional[str] = None,
) -> None:
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
        actor, ctx = _audit_actor_ctx(
            student_user["id"], actor_role, ip, user_agent
        )
        cancelled = storage.cancel_student_group_session(
            uuid, int(student_user["id"]), db, actor=actor, context=ctx
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
