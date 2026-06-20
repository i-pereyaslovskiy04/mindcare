"""
Модели: консультации и расписание.
  TherapyEngagement          — терапевтическое взаимодействие (связь клиент ↔ психолог)
  ScheduleRule               — рабочие окна психолога (только доступность; день недели,
                               start/end, meeting_type_id НЕОБЯЗАТЕЛЕН, period, series_id)
  ScheduleBreak              — повторяющиеся перерывы (например обед 13:00–14:00)
  ScheduleException          — разовые изменения: day_off / unavailable / extra_availability
  MeetingType                — справочник типов встреч (хранит duration_minutes + buffer_minutes,
                               по которым строятся слоты)
  Appointment                — запись на конкретный сеанс (с проверкой пересечений)
  GroupSession               — групповое занятие
  GroupSessionRegistration   — регистрация студента на групповое занятие
  SessionNote                — заметки после сеанса (конфиденциальные)

Модель расписания (важно):
  - длительность сессии и технический буфер принадлежат MeetingType, НЕ расписанию;
  - ScheduleRule описывает только доступность (рабочие окна);
  - слот строится от MeetingType.duration_minutes; следующий слот сдвигается на
    duration + buffer_minutes;
  - на одну дату у психолога может быть несколько разовых исключений (нет
    уникальности «одно исключение на дату»).
"""

import uuid as _uuid

from sqlalchemy import (
    Boolean, CheckConstraint, Column, Date, DateTime, ForeignKey,
    Index, Integer, String, Text, Time,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func, text as sa_text

from app.db.base import Base


class TherapyEngagement(Base):
    __tablename__ = "therapy_engagements"
    __table_args__ = (
        # Partial unique index: один клиент — не более одной активной связи.
        # Создаётся migration d2e5f8a1b4c7.
        Index(
            "ux_therapy_engagements_active_client",
            "client_id",
            unique=True,
            postgresql_where=sa_text("status = 'active' AND ended_at IS NULL"),
        ),
    )

    id              = Column(Integer, primary_key=True)
    uuid            = Column(
        UUID(as_uuid=True), unique=True, nullable=False, default=_uuid.uuid4
    )
    client_id       = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    psychologist_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    status          = Column(String(20), default="active")   # active / completed / transferred / cancelled
    primary_concern = Column(Text)
    started_at      = Column(DateTime(timezone=True), server_default=func.now())
    ended_at        = Column(DateTime(timezone=True))
    transferred_to  = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    transfer_reason = Column(Text)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    updated_at      = Column(DateTime(timezone=True), server_default=func.now())

    appointments  = relationship("Appointment", back_populates="engagement")
    session_notes = relationship("SessionNote", back_populates="engagement")


class ScheduleRule(Base):
    """
    Рабочее окно психолога (только доступность).

    Длительность слота и буфер НЕ хранятся здесь — они принадлежат MeetingType.
    meeting_type_id НЕОБЯЗАТЕЛЕН (schedule v3): рабочее окно не привязано к типу
    встречи — тип выбирается только при поиске/создании записи. Legacy-строки
    с заполненным meeting_type_id трактуются как обычные рабочие окна (значение
    игнорируется при расчёте слотов). series_id — группирует правила и перерывы,
    созданные одной операцией создания расписания (расписание = серия). period —
    метка окна
    (morning/…, опц.). auto_extend — серия участвует в ежемесячном автопродлении
    (effective_until обязателен). created_by — supervisor, создавший серию
    (для уведомления при автопродлении). Деактивация/восстановление расписания —
    через is_active на уровне серии (soft-delete не трогает Appointment).
    """
    __tablename__ = "schedule_rules"

    id              = Column(Integer, primary_key=True)
    psychologist_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    meeting_type_id = Column(
        Integer, ForeignKey("meeting_types.id", ondelete="RESTRICT"),
        nullable=True,
    )
    day_of_week     = Column(Integer, nullable=False)   # 0=Mon … 6=Sun
    start_time      = Column(Time, nullable=False)
    end_time        = Column(Time, nullable=False)
    period          = Column(String(20))               # morning/afternoon/… (опц.)
    series_id       = Column(UUID(as_uuid=True))        # группировка серии (rules+breaks)
    is_active       = Column(Boolean, default=True)
    auto_extend     = Column(Boolean, nullable=False, default=False)
    effective_from  = Column(Date, nullable=False)
    effective_until = Column(Date)
    created_by      = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at      = Column(DateTime(timezone=True), server_default=func.now())

    meeting_type = relationship("MeetingType")


class ScheduleBreak(Base):
    """
    Повторяющийся перерыв в расписании (например обед 13:00–14:00).

    Привязан к дню недели; пересекающиеся слоты исключаются при генерации.
    effective_from/effective_until ограничивают период действия перерыва, чтобы
    перерывы не жили дольше расписания, которому они принадлежат.
    series_id группирует перерывы bulk-операции.
    """
    __tablename__ = "schedule_breaks"
    __table_args__ = (
        CheckConstraint(
            "start_time < end_time", name="chk_schedule_break_times"
        ),
        Index(
            "ix_schedule_breaks_psych_day", "psychologist_id", "day_of_week"
        ),
    )

    id              = Column(Integer, primary_key=True)
    psychologist_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    day_of_week     = Column(Integer, nullable=False)   # 0=Mon … 6=Sun
    start_time      = Column(Time, nullable=False)
    end_time        = Column(Time, nullable=False)
    title           = Column(String(255))
    series_id       = Column(UUID(as_uuid=True))
    effective_from  = Column(Date, nullable=False)
    effective_until = Column(Date)
    is_active       = Column(Boolean, nullable=False, default=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())


class ScheduleException(Base):
    """
    Разовое изменение расписания на конкретную дату.

    exception_type:
      - day_off            — весь день нерабочий (нет слотов);
      - unavailable        — заблокировать диапазон start_time–end_time;
      - extra_availability — добавить доступность start_time–end_time.

    На одну дату допускается несколько исключений (нет уникальности
    «одно исключение на дату»).
    """
    __tablename__ = "schedule_exceptions"

    id              = Column(Integer, primary_key=True)
    psychologist_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    exception_date  = Column(Date, nullable=False)
    # PG enum schedule_exception_type:
    # {day_off, reduced_hours, extra_hours, unavailable, extra_availability}
    exception_type  = Column(String(20), nullable=False)
    start_time      = Column(Time)
    end_time        = Column(Time)
    reason          = Column(Text)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())


class MeetingType(Base):
    """
    Справочник типов встреч/занятий.
    Управляется supervisor и admin через /api/supervisor/meeting-types/*.
    is_group=True — групповой тип (ровно один формат: in_person ИЛИ online).
    is_group=False — индивидуальный (allow_in_person и/или allow_online).
    Неактивный или is_bookable=False тип недоступен студентам для самостоятельной записи.
    """
    __tablename__ = "meeting_types"

    id               = Column(Integer, primary_key=True)
    name             = Column(String(255), nullable=False)
    description      = Column(Text)
    duration_minutes = Column(Integer, nullable=False, default=50)
    buffer_minutes   = Column(Integer, nullable=False, default=10)
    allow_in_person  = Column(Boolean, nullable=False, default=True)
    allow_online     = Column(Boolean, nullable=False, default=True)
    is_group         = Column(Boolean, nullable=False, default=False)
    is_active        = Column(Boolean, nullable=False, default=True)
    is_bookable      = Column(Boolean, nullable=False, default=True)
    display_order    = Column(Integer, nullable=False, default=0)
    created_at       = Column(DateTime(timezone=True), server_default=func.now())
    updated_at       = Column(DateTime(timezone=True), server_default=func.now())

    group_sessions = relationship("GroupSession", back_populates="meeting_type")


class UnregisteredStudentCard(Base):
    """
    Карточка незарегистрированного студента (walk-in).

    Позволяет supervisor/admin записать на приём человека, который пришёл лично и
    ещё не имеет учётной записи, БЕЗ создания фейкового пользователя. Хранит
    минимальные ПДн и факт согласия на их обработку.

    Не путать с фронтовым «detail-видом карточки студента» (useStudentCard /
    PsychologistStudentCardPage) — тот показывает уже зарегистрированного User.

    Согласие: активная (не archived) карточка создаётся только при
    personal_data_consent=True (проверка на уровне сервиса). consent_obtained_at
    и consent_source фиксируют, когда и как получено согласие (например in_person).

    linked_user_id зарезервирован под будущую привязку карточки к учётной записи
    при регистрации — на этом этапе НЕ используется. Soft archive через archived_at.

    ПДн карточки (ФИО/телефон/email/комментарий/запрос) не логировать.
    """
    __tablename__ = "unregistered_student_cards"
    __table_args__ = (
        Index("ix_unreg_cards_normalized_email", "normalized_email"),
        Index("ix_unreg_cards_archived_at", "archived_at"),
        Index("ix_unreg_cards_created_by", "created_by"),
    )

    id                    = Column(Integer, primary_key=True)
    uuid                  = Column(
        UUID(as_uuid=True), unique=True, nullable=False, default=_uuid.uuid4
    )
    full_name             = Column(String(255), nullable=False)
    phone                 = Column(String(50))
    email                 = Column(String(255))
    normalized_email      = Column(String(255))
    birth_date            = Column(Date)
    comment               = Column(Text)
    primary_concern       = Column(Text)
    personal_data_consent = Column(Boolean, nullable=False, default=False)
    consent_obtained_at   = Column(DateTime(timezone=True))
    consent_source        = Column(String(30), default="in_person")
    linked_user_id        = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL")
    )
    created_by            = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at            = Column(DateTime(timezone=True), server_default=func.now())
    updated_at            = Column(DateTime(timezone=True), server_default=func.now())
    archived_at           = Column(DateTime(timezone=True))


class Appointment(Base):
    """
    Запись студента на индивидуальный приём к психологу.

    Статусы:
      pending_confirmation — ожидает подтверждения психологом (создаётся студентом)
      confirmed            — подтверждена психологом
      cancelled            — отменена (студентом или системой)
      declined             — отклонена психологом
      completed            — проведена
      no_show              — студент не явился

    Статусы pending_confirmation и confirmed занимают слот (блокируют повторные записи).
    Статусы cancelled, declined, completed, no_show не блокируют слот.
    Lazy-expire: если pending_confirmation и starts_at в прошлом — слот считается
    освободившимся; явный переход не делается (нет scheduler), проверяется при запросе слотов.

    Субъект записи — ровно один из двух (CHECK chk_appointment_subject_exactly_one):
      - client_id                    — зарегистрированный студент (есть учётная запись);
      - unregistered_student_card_id — карточка незарегистрированного студента
                                       (ручная запись супервизором, без user).
    """
    __tablename__ = "appointments"
    __table_args__ = (
        # Ровно одна ссылка на субъекта: client_id XOR unregistered_student_card_id.
        CheckConstraint(
            "num_nonnulls(client_id, unregistered_student_card_id) = 1",
            name="chk_appointment_subject_exactly_one",
        ),
    )

    id                  = Column(Integer, primary_key=True)
    uuid                = Column(
        UUID(as_uuid=True), unique=True, nullable=False, default=_uuid.uuid4
    )
    client_id           = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    unregistered_student_card_id = Column(
        Integer,
        ForeignKey("unregistered_student_cards.id", ondelete="RESTRICT"),
        nullable=True,
    )
    psychologist_id     = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    engagement_id       = Column(
        Integer, ForeignKey("therapy_engagements.id", ondelete="SET NULL")
    )
    meeting_type_id     = Column(
        Integer, ForeignKey("meeting_types.id", ondelete="SET NULL"), nullable=True
    )
    starts_at           = Column(DateTime(timezone=True), nullable=False)
    duration_minutes    = Column(Integer, nullable=False, default=50)
    ends_at             = Column(DateTime(timezone=True))
    modality            = Column(String(20), default="in_person")   # in_person / online
    topic               = Column(Text)
    status              = Column(String(30), default="pending_confirmation")
    cancellation_reason = Column(Text)
    decline_reason      = Column(Text)
    canceled_by         = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    booking_source      = Column(String(30), nullable=False, default="student_self")
    created_by          = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    created_at          = Column(DateTime(timezone=True), server_default=func.now())
    updated_at          = Column(DateTime(timezone=True), server_default=func.now())
    deleted_at          = Column(DateTime(timezone=True))

    engagement    = relationship("TherapyEngagement", back_populates="appointments")
    meeting_type  = relationship("MeetingType")
    session_notes = relationship("SessionNote", back_populates="appointment")
    unregistered_student_card = relationship("UnregisteredStudentCard")


class GroupSession(Base):
    """
    Групповое занятие, создаваемое supervisor.
    Студент может записаться если booking_enabled=True, есть места и занятие не началось.
    Подтверждение психологом не требуется.
    """
    __tablename__ = "group_sessions"

    id              = Column(Integer, primary_key=True)
    uuid            = Column(
        UUID(as_uuid=True), unique=True, nullable=False, default=_uuid.uuid4
    )
    meeting_type_id = Column(
        Integer, ForeignKey("meeting_types.id", ondelete="RESTRICT"), nullable=False
    )
    psychologist_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_by      = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    title           = Column(String(255))
    description     = Column(Text)
    starts_at       = Column(DateTime(timezone=True), nullable=False)
    ends_at         = Column(DateTime(timezone=True))
    format          = Column(String(20), nullable=False)   # in_person / online
    capacity        = Column(Integer, nullable=False, default=10)
    booking_enabled = Column(Boolean, nullable=False, default=True)
    status          = Column(String(20), nullable=False, default="scheduled")  # scheduled / cancelled / completed
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    updated_at      = Column(DateTime(timezone=True), server_default=func.now())

    meeting_type  = relationship("MeetingType", back_populates="group_sessions")
    registrations = relationship("GroupSessionRegistration", back_populates="group_session")


class GroupSessionRegistration(Base):
    """
    Регистрация студента на групповое занятие.
    Partial unique index: только одна активная (registered) регистрация
    на пару (group_session_id, student_id). Cancelled-строки игнорируются,
    что позволяет студенту отменить запись и зарегистрироваться повторно.
    """
    __tablename__ = "group_session_registrations"
    __table_args__ = (
        Index(
            "ux_gsr_active",
            "group_session_id",
            "student_id",
            unique=True,
            postgresql_where=sa_text("status = 'registered'"),
        ),
    )

    id               = Column(Integer, primary_key=True)
    uuid             = Column(
        UUID(as_uuid=True), unique=True, nullable=False, default=_uuid.uuid4
    )
    group_session_id = Column(
        Integer, ForeignKey("group_sessions.id", ondelete="CASCADE"), nullable=False
    )
    student_id       = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    status           = Column(String(20), nullable=False, default="registered")  # registered / cancelled
    created_at       = Column(DateTime(timezone=True), server_default=func.now())
    updated_at       = Column(DateTime(timezone=True), server_default=func.now())

    group_session = relationship("GroupSession", back_populates="registrations")


class SessionNote(Base):
    """
    Заметки после сеанса.

    SECURITY NOTE: поле content физически остаётся TEXT-колонкой, но application
    layer хранит в нём только Fernet ciphertext с префиксом "enc:v1:".

    Шифрование/расшифровка реализованы в app/core/encryption.py и подключены
    через app/session_notes/storage.py:
    - encrypt_text(plaintext) вызывается перед записью в БД;
    - decrypt_text(ciphertext) вызывается при чтении для API response.

    ORM-объект SessionNote.content всегда содержит ciphertext и никогда не
    мутируется plaintext-значением (SQLAlchemy не делает flush plaintext).

    Ограничения и ответственность:
    - Не записывать plaintext напрямую в SessionNote.content.
    - Не логировать content в audit/data_change_log/stdout.
    - Plaintext fallback намеренно отсутствует — decrypt упадёт если значение
      не начинается с "enc:v1:".
    - Безопасность данных зависит от корректного хранения DATA_ENCRYPTION_KEY
      (см. .env.example, раздел ENCRYPTION). Потеря ключа = потеря всех заметок.

    ФЗ-152: данный подход устраняет риск хранения психологических данных
    (специальная категория ПДн) в открытом виде на уровне БД.
    """
    __tablename__ = "session_notes"

    id                    = Column(Integer, primary_key=True)
    uuid                  = Column(
        UUID(as_uuid=True), unique=True, nullable=False, default=_uuid.uuid4
    )
    appointment_id        = Column(
        Integer, ForeignKey("appointments.id", ondelete="SET NULL")
    )
    engagement_id         = Column(
        Integer, ForeignKey("therapy_engagements.id", ondelete="SET NULL")
    )
    author_id             = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    note_type             = Column(String(20), default="general")   # general / diagnosis / plan / followup
    content               = Column(Text, nullable=False)
    is_shared_with_client = Column(Boolean, default=False)
    version               = Column(Integer, default=1)
    created_at            = Column(DateTime(timezone=True), server_default=func.now())
    updated_at            = Column(DateTime(timezone=True), server_default=func.now())

    appointment = relationship("Appointment", back_populates="session_notes")
    engagement  = relationship("TherapyEngagement", back_populates="session_notes")
