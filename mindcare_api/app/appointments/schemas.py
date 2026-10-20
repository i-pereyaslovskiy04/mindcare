"""Pydantic-схемы модуля appointments."""

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


# ── Slots ─────────────────────────────────────────────────────────────────────

class SlotRead(BaseModel):
    starts_at: datetime
    ends_at: datetime
    duration_minutes: int


class SlotsResponse(BaseModel):
    psychologist_id: int
    meeting_type_id: int
    modality: str
    date: str           # YYYY-MM-DD
    slots: list[SlotRead]


# ── Appointment ────────────────────────────────────────────────────────────────

class AppointmentCreate(BaseModel):
    starts_at: datetime = Field(description="UTC datetime of appointment start")
    modality: str = Field(
        default="in_person", description="in_person | online | video | phone | chat"
    )
    topic: Optional[str] = Field(default=None, max_length=2000)
    meeting_type_id: Optional[int] = None


class PsychologistRef(BaseModel):
    id: int
    uuid: str
    full_name: str
    email: str

    model_config = {"from_attributes": True}


class StudentRef(BaseModel):
    id: int
    uuid: str
    full_name: str
    email: str

    model_config = {"from_attributes": True}


class UnregisteredStudentCardBrief(BaseModel):
    """Минимальная карточка для встраивания в appointment (вид психолога)."""
    id: int
    uuid: str
    full_name: str
    phone: Optional[str] = None
    email: Optional[str] = None

    model_config = {"from_attributes": True}


class AppointmentRead(BaseModel):
    uuid: str
    client_id: Optional[int] = None
    unregistered_student_card_id: Optional[int] = None
    psychologist_id: int
    engagement_id: Optional[int] = None
    meeting_type_id: Optional[int] = None
    meeting_type_name: Optional[str] = None
    meeting_type_duration_minutes: Optional[int] = None
    starts_at: datetime
    ends_at: Optional[datetime] = None
    duration_minutes: int
    modality: str
    topic: Optional[str] = None
    status: str
    cancellation_reason: Optional[str] = None
    decline_reason: Optional[str] = None
    booking_source: str = "student_self"
    created_by: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AppointmentDetailRead(AppointmentRead):
    """Appointment with embedded student/psychologist info."""
    student: Optional[StudentRef] = None
    psychologist: Optional[PsychologistRef] = None
    unregistered_student_card: Optional[UnregisteredStudentCardBrief] = None


class AppointmentDecline(BaseModel):
    reason: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="Причина отклонения записи",
    )


class AppointmentCancelBody(BaseModel):
    reason: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="Причина отмены записи",
    )


class PaginatedAppointmentsResponse(BaseModel):
    items: list[AppointmentDetailRead]
    total: int
    page: int
    size: int


# ── Schedule rules (supervisor) ─────────────────────────────────────────────

class ScheduleRuleCreate(BaseModel):
    """Bulk-создание рабочих окон на один или несколько дней.

    Длительность слота и буфер НЕ задаются здесь — из MeetingType.
    meeting_type_id НЕОБЯЗАТЕЛЕН (schedule v3): рабочее окно не привязано к типу
    встречи. Принимается для обратной совместимости со старым клиентом, но при
    расчёте слотов значение игнорируется.
    Правила одного запроса на несколько дней разделяют series_id.
    """
    psychologist_id: int
    days_of_week: list[int] = Field(
        min_length=1, description="Список дней 0=Mon…6=Sun"
    )
    start_time: str = Field(description="HH:MM")
    end_time: str = Field(description="HH:MM")
    meeting_type_id: Optional[int] = Field(
        default=None,
        description="ID типа встречи (опц., legacy — игнорируется)",
    )
    period: Optional[str] = Field(
        default=None, max_length=20,
        description="morning/afternoon/… (опц.)",
    )
    effective_from: str = Field(description="YYYY-MM-DD")
    effective_until: Optional[str] = Field(
        default=None, description="YYYY-MM-DD"
    )


class ScheduleRuleRead(BaseModel):
    id: int
    psychologist_id: int
    meeting_type_id: Optional[int] = None
    day_of_week: int
    start_time: str
    end_time: str
    period: Optional[str] = None
    series_id: Optional[str] = None
    is_active: bool
    auto_extend: bool = False
    effective_from: str
    effective_until: Optional[str] = None
    created_by: Optional[int] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Unified schedule create (rules + recurring breaks in one series) ─────────

def _validate_days_of_week(v):
    """Общая проверка списка дней недели (0=Mon…6=Sun) для create и update."""
    if any(d < 0 or d > 6 for d in v):
        raise ValueError("day_of_week должен быть в диапазоне 0..6")
    return v


class ScheduleBreakInput(BaseModel):
    """Один повторяющийся перерыв внутри создаваемого расписания."""
    start_time: str = Field(description="HH:MM")
    end_time: str = Field(description="HH:MM")
    title: Optional[str] = Field(default=None, max_length=255)


class ScheduleCreate(BaseModel):
    """Создание расписания психолога одной операцией (серия).

    Создаёт рабочие окна (ScheduleRule) на выбранные дни недели и, опционально,
    повторяющиеся перерывы (ScheduleBreak) — всё с общим series_id и единым
    периодом effective_from/effective_until.

    Schedule v3: тип встречи здесь НЕ задаётся — рабочее окно не привязано к
    типу. Тип выбирается только при поиске/создании записи.

    auto_extend=True требует effective_until (его двигает maintenance-скрипт).
    """
    psychologist_id: int
    days_of_week: list[int] = Field(
        min_length=1, description="Список дней 0=Mon…6=Sun"
    )
    start_time: str = Field(description="HH:MM")
    end_time: str = Field(description="HH:MM")
    effective_from: str = Field(description="YYYY-MM-DD")
    effective_until: Optional[str] = Field(
        default=None, description="YYYY-MM-DD (обязателен при auto_extend)"
    )
    auto_extend: bool = Field(
        default=False,
        description="Ежемесячное автопродление (требует effective_until)",
    )
    period: Optional[str] = Field(
        default=None, max_length=20,
        description="morning/afternoon/… (опц.)",
    )
    breaks: list[ScheduleBreakInput] = Field(
        default_factory=list,
        description="Повторяющиеся перерывы (общие для всех дней серии)",
    )

    @field_validator("days_of_week")
    @classmethod
    def _days_in_range(cls, v):
        return _validate_days_of_week(v)


class ScheduleUpdate(BaseModel):
    """Редактирование серии расписания.

    Как ScheduleCreate, но БЕЗ psychologist_id и meeting_type_id (schedule v3 =
    рабочее окно без типа). Психолог серии не меняется. extra='forbid' — лишний
    psychologist_id или любое другое поле в body даёт 422 (ошибка не скрывается).
    """
    model_config = {"extra": "forbid"}
    days_of_week: list[int] = Field(
        min_length=1, description="Список дней 0=Mon…6=Sun"
    )
    start_time: str = Field(description="HH:MM")
    end_time: str = Field(description="HH:MM")
    effective_from: str = Field(description="YYYY-MM-DD")
    effective_until: Optional[str] = Field(
        default=None, description="YYYY-MM-DD (обязателен при auto_extend)"
    )
    auto_extend: bool = Field(default=False)
    period: Optional[str] = Field(default=None, max_length=20)
    breaks: list[ScheduleBreakInput] = Field(default_factory=list)

    @field_validator("days_of_week")
    @classmethod
    def _days_in_range(cls, v):
        return _validate_days_of_week(v)


class ScheduleImpactRead(BaseModel):
    """Предупреждение перед деактивацией: будущие записи в периоде серии."""
    series_id: str
    future_appointments: int


class ScheduleDeleteResult(BaseModel):
    """Итог soft-delete серии расписания (записи не удаляются)."""
    series_id: str
    deactivated_rules: int
    deactivated_breaks: int
    future_appointments: int


class SupervisorAppointmentCreate(BaseModel):
    """Ручная запись на слот, созданная супервизором.

    Субъект записи — ровно один из двух (проверка в сервисе):
      - student_id                    — зарегистрированный студент (нужен active
                                        engagement с психологом);
      - unregistered_student_card_id  — карточка незарегистрированного студента
                                        (engagement не требуется).
    """
    student_id: Optional[int] = None
    unregistered_student_card_id: Optional[int] = None
    psychologist_id: int
    meeting_type_id: int = Field(description="ID типа встречи (обязателен)")
    starts_at: datetime = Field(description="UTC datetime начала слота")
    modality: str = Field(
        default="in_person", description="in_person | online"
    )
    topic: Optional[str] = Field(default=None, max_length=2000)


# ── Unregistered student cards (supervisor) ─────────────────────────────────

class UnregisteredStudentCardCreate(BaseModel):
    """Создание карточки незарегистрированного студента.

    full_name обязателен; personal_data_consent должен быть true (проверка в
    сервисе). normalized_email вычисляется на backend.
    """
    full_name: str = Field(min_length=1, max_length=255)
    phone: Optional[str] = Field(default=None, max_length=50)
    email: Optional[str] = Field(default=None, max_length=255)
    birth_date: Optional[date] = None
    comment: Optional[str] = Field(default=None, max_length=2000)
    primary_concern: Optional[str] = Field(default=None, max_length=2000)
    personal_data_consent: bool = Field(
        description="Согласие субъекта на обработку ПДн (обязательно true)"
    )
    consent_source: Optional[str] = Field(
        default="in_person", max_length=30
    )


class UnregisteredStudentCardUpdate(BaseModel):
    """Частичное обновление карточки (только личные поля).

    Согласие/audit-поля/linked_user_id здесь НЕ редактируются.
    """
    full_name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    phone: Optional[str] = Field(default=None, max_length=50)
    email: Optional[str] = Field(default=None, max_length=255)
    birth_date: Optional[date] = None
    comment: Optional[str] = Field(default=None, max_length=2000)
    primary_concern: Optional[str] = Field(default=None, max_length=2000)


class UnregisteredStudentCardRead(BaseModel):
    id: int
    uuid: str
    full_name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    normalized_email: Optional[str] = None
    birth_date: Optional[date] = None
    comment: Optional[str] = None
    primary_concern: Optional[str] = None
    personal_data_consent: bool
    consent_obtained_at: Optional[datetime] = None
    consent_source: Optional[str] = None
    linked_user_id: Optional[int] = None
    created_by: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    archived_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class PaginatedUnregisteredStudentCardsResponse(BaseModel):
    items: list[UnregisteredStudentCardRead]
    total: int
    page: int
    size: int


# ── Schedule breaks (supervisor) ────────────────────────────────────────────

class ScheduleBreakCreate(BaseModel):
    """Bulk-создание повторяющихся перерывов (например обед 13:00–14:00).

    effective_from обязателен — перерыв действует с этой даты.
    effective_until необязателен (None = бессрочно).
    """
    psychologist_id: int
    days_of_week: list[int] = Field(
        min_length=1, description="Список дней 0=Mon…6=Sun"
    )
    start_time: str = Field(description="HH:MM")
    end_time: str = Field(description="HH:MM")
    title: Optional[str] = Field(default=None, max_length=255)
    effective_from: str = Field(description="YYYY-MM-DD")
    effective_until: Optional[str] = Field(
        default=None, description="YYYY-MM-DD"
    )


class ScheduleBreakRead(BaseModel):
    id: int
    psychologist_id: int
    day_of_week: int
    start_time: str
    end_time: str
    title: Optional[str] = None
    series_id: Optional[str] = None
    effective_from: str
    effective_until: Optional[str] = None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Schedule exceptions (supervisor) ────────────────────────────────────────

class ScheduleExceptionCreate(BaseModel):
    psychologist_id: int
    exception_date: str = Field(description="YYYY-MM-DD")
    exception_type: str = Field(
        description="day_off / unavailable / extra_availability"
    )
    start_time: Optional[str] = Field(default=None, description="HH:MM")
    end_time: Optional[str] = Field(default=None, description="HH:MM")
    reason: Optional[str] = Field(default=None, max_length=500)


class ScheduleExceptionRead(BaseModel):
    id: int
    psychologist_id: int
    exception_date: str
    exception_type: str
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    reason: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── MeetingType ────────────────────────────────────────────────────────────────

class MeetingTypeCreate(BaseModel):
    name: str = Field(max_length=255)
    description: Optional[str] = Field(default=None, max_length=2000)
    duration_minutes: int = Field(default=50, ge=10, le=480)
    buffer_minutes: int = Field(default=10, ge=0, le=120)
    allow_in_person: bool = True
    allow_online: bool = True
    is_group: bool = False
    is_active: bool = True
    is_bookable: bool = True
    display_order: int = 0


class MeetingTypeUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = Field(default=None, max_length=2000)
    duration_minutes: Optional[int] = Field(default=None, ge=10, le=480)
    buffer_minutes: Optional[int] = Field(default=None, ge=0, le=120)
    allow_in_person: Optional[bool] = None
    allow_online: Optional[bool] = None
    is_group: Optional[bool] = None
    is_active: Optional[bool] = None
    is_bookable: Optional[bool] = None
    display_order: Optional[int] = None


class MeetingTypeRead(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    duration_minutes: int
    buffer_minutes: int
    allow_in_person: bool
    allow_online: bool
    is_group: bool
    is_active: bool
    is_bookable: bool
    display_order: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── GroupSession ───────────────────────────────────────────────────────────────

class GroupSessionCreate(BaseModel):
    meeting_type_id: int
    psychologist_id: int
    title: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = Field(default=None, max_length=2000)
    starts_at: datetime
    ends_at: Optional[datetime] = None
    format: str = Field(description="in_person or online")
    capacity: int = Field(default=10, ge=1, le=500)
    booking_enabled: bool = True


class GroupSessionUpdate(BaseModel):
    """Частичное обновление группового занятия.

    Stage 5C-2: `status` — стабильный enum, а не свободная строка. Через generic
    PATCH допускается только явно спроектированный переход `scheduled→cancelled`;
    `completed` принадлежит system maintenance и здесь запрещён (валидация
    перехода — в сервисе).
    """
    meeting_type_id: Optional[int] = None
    psychologist_id: Optional[int] = None
    title: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = Field(default=None, max_length=2000)
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    format: Optional[str] = None
    capacity: Optional[int] = Field(default=None, ge=1, le=500)
    booking_enabled: Optional[bool] = None
    status: Optional[Literal["scheduled", "cancelled"]] = Field(
        default=None,
        description=(
            "Допустимо только 'cancelled' (переход scheduled→cancelled). "
            "'completed' выставляет только system maintenance."
        ),
    )


class GroupSessionRead(BaseModel):
    uuid: str
    meeting_type_id: int
    meeting_type_name: Optional[str] = None
    psychologist_id: int
    psychologist_name: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    starts_at: datetime
    ends_at: Optional[datetime] = None
    format: str
    capacity: int
    booking_enabled: bool
    status: str
    registered_count: int = 0
    is_registered: bool = False     # student-specific field
    created_at: datetime

    model_config = {"from_attributes": True}


class PaginatedGroupSessionsResponse(BaseModel):
    items: list[GroupSessionRead]
    total: int
    page: int
    size: int


class GroupSessionRegistrationRead(BaseModel):
    uuid: str
    group_session_id: int
    student_id: int
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Schedule series / psychologist read-only schedule ────────────────────────
# Размещено в конце файла: зависит от ScheduleRuleRead, ScheduleBreakRead и
# MeetingTypeRead — объявлены выше, поэтому forward-reference не возникает.

class ScheduleSeriesRead(BaseModel):
    """Результат создания/чтения расписания-серии.

    meeting_type_id — Optional: новые серии (schedule v3) рабочих окон не имеют
    типа встречи (None); поле сохранено для обратной совместимости с legacy.
    """
    series_id: str
    psychologist_id: int
    meeting_type_id: Optional[int] = None
    auto_extend: bool
    effective_from: str
    effective_until: Optional[str] = None
    is_active: bool
    rules: list[ScheduleRuleRead]
    breaks: list[ScheduleBreakRead]


class PsychologistScheduleRead(BaseModel):
    """Своё расписание психолога (read-only): активные окна, перерывы и типы.

    meeting_types — данные типов встреч, используемых в rules, чтобы фронт
    психолога не ходил в supervisor/admin-эндпоинты ради названий.
    """
    rules: list[ScheduleRuleRead]
    breaks: list[ScheduleBreakRead]
    meeting_types: list[MeetingTypeRead]
