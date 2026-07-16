"""
Бизнес-логика модуля супервизора.
Все транзакционные операции открывают одну сессию и выполняются атомарно.
"""

import logging
import sys
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import desc

from app.chat import storage as chat_storage
from app.chat.audit import log_conversation_created
from app.chat.system_publisher import publish_system_message
from app.db.session import SessionLocal
from app.db.models import AuditLog, Role, TherapyEngagement, User, UserRole
from app.supervisor import storage

log = logging.getLogger(__name__)

# Личное согласие субъекта (как при self-registration). Mirror auth.REQUIRED_CONSENTS.
_REQUIRED_CONSENT_TYPES = ["privacy_policy", "data_processing"]

# Маппинг кодов ошибок storage.create_student → HTTP-статус.
_STUDENT_ERROR_STATUS = {
    "duplicate_email":         409,
    "psychologist_not_found":  404,
    "not_a_psychologist":      400,
    "psychologist_inactive":   422,
    "consent_policy_missing":  500,
    "student_role_missing":    500,
    "email_domain_not_allowed": 422,
}


class SupervisorError(Exception):
    """Ошибка бизнес-логики супервизора с HTTP-статусом."""

    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


# ── Внутренние хелперы ────────────────────────────────────────────────────────

def _get_user_with_role(user_id: int, expected_role: str, db) -> User:
    """
    Возвращает User если существует и имеет нужную роль.
    Raises SupervisorError 404 / 400 иначе.
    """
    user = (
        db.query(User)
        .filter(User.id == user_id, User.deleted_at.is_(None))
        .first()
    )
    if not user:
        raise SupervisorError(f"Пользователь id={user_id} не найден", status_code=404)

    has_role = (
        db.query(UserRole)
        .join(Role, Role.id == UserRole.role_id)
        .filter(UserRole.user_id == user_id, Role.name == expected_role)
        .first()
    )
    if not has_role:
        role_label = {"student": "студента", "psychologist": "психолога"}.get(
            expected_role, expected_role
        )
        raise SupervisorError(
            f"Пользователь id={user_id} не имеет роль {role_label}",
            status_code=400,
        )

    return user


def _get_active_engagement(client_id: int, db) -> Optional[TherapyEngagement]:
    return (
        db.query(TherapyEngagement)
        .filter(
            TherapyEngagement.client_id == client_id,
            TherapyEngagement.status == "active",
            TherapyEngagement.ended_at.is_(None),
        )
        .first()
    )


def _find_latest_pair_engagement(
    client_id: int, psychologist_id: int, db,
) -> Optional[TherapyEngagement]:
    """
    Последняя НЕ-активная связь пары student↔psychologist (Stage 31p).

    Используется при повторном назначении того же психолога: вместо нового
    engagement/chat реактивируется прежняя связь (тот же conversation_uuid,
    история сохраняется). Сортировка: свежайшая по started_at, затем id.
    Активные связи исключены — их обрабатывают вызывающие (no-op/409).
    """
    return (
        db.query(TherapyEngagement)
        .filter(
            TherapyEngagement.client_id == client_id,
            TherapyEngagement.psychologist_id == psychologist_id,
            (TherapyEngagement.status != "active")
            | (TherapyEngagement.ended_at.isnot(None)),
        )
        .order_by(desc(TherapyEngagement.started_at), desc(TherapyEngagement.id))
        .first()
    )


def _reactivate_engagement(engagement: TherapyEngagement, db):
    """
    Реактивирует прежнюю связь в active и переиспользует её беседу (Stage 31p).

    Внутри транзакции caller'а: status→active, ended_at/transferred_to/
    transfer_reason очищаются, conversation переиспользуется через
    ensure_engagement_conversation (новый не создаётся). Без commit.
    Возвращает (engagement, conversation, conv_created).

    ВАЖНО: вызывать только когда у клиента нет другой active-связи (иначе
    нарушится partial unique index ux_therapy_engagements_active_client) —
    в transfer текущую active закрывают и flush'ат ДО реактивации.
    """
    now = datetime.now(timezone.utc)
    engagement.status = "active"
    engagement.ended_at = None
    engagement.transferred_to = None
    engagement.transfer_reason = None
    engagement.updated_at = now
    db.flush()
    conv, conv_created = chat_storage.ensure_engagement_conversation(db, engagement.id)
    return engagement, conv, conv_created


def _log_event(
    event_type: str,
    actor_id: int,
    actor_role: str,
    entity_id: int,
    description: str,
    db,
) -> None:
    """Записывает событие в audit_log. Не прерывает flow при ошибке."""
    try:
        db.add(AuditLog(
            user_id=actor_id,
            user_role=actor_role,
            event_type=event_type,
            entity_type="therapy_engagement",
            entity_id=entity_id,
            description=description,
        ))
    except Exception as exc:
        print(
            f"[AUDIT FAIL] {event_type}: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )


# ── System-уведомления Messenger (Stage 31r) ──────────────────────────────────
#
# Тексты: только «Чат с психологом/пациентом <ФИО> создан/закрыт.» — без «снова»,
# без «консультационной связи». Первое назначение и реактивация дают ОДИН текст
# «создан». Уведомления получают ОБА участника (студент и психолог).

def _student_chat_created_text(psychologist_name: str) -> str:
    return f"Чат с психологом {psychologist_name} создан."


def _student_chat_closed_text(psychologist_name: str) -> str:
    return f"Чат с психологом {psychologist_name} закрыт."


def _psychologist_chat_created_text(patient_name: str) -> str:
    return f"Чат с пациентом {patient_name} создан."


def _psychologist_chat_closed_text(patient_name: str) -> str:
    return f"Чат с пациентом {patient_name} закрыт."


def _user_display_name(user: Optional[User]) -> str:
    """ФИО, иначе email, иначе нейтральная заглушка."""
    if user is None:
        return "—"
    return user.full_name or user.email or "—"


def _occurrence_marker(now: datetime) -> str:
    """
    Маркер конкретной операции (Stage 31r). Включается в event_key, чтобы тот
    был уникален per-occurrence, а не только per-engagement: после Stage 31p
    engagement.id переиспользуется при реактивации, и без маркера повторный
    close→reactivate→close давал бы тот же ключ → idempotency-коллизия →
    тихая потеря уведомления. Микросекунды дают уникальность между операциями;
    единый marker на одну операцию сохраняет идемпотентность при ретрае.
    """
    return now.strftime("%Y%m%d%H%M%S%f")


def _publish_chat_event(
    *, engagement_id: int, occurrence: str, recipient_id: int, kind: str, text: str,
) -> None:
    """
    Публикует одно system-уведомление chat-lifecycle (soft-fail внутри publisher).
    kind ∈ {"created", "closed"}. event_key уникален per-occurrence и per-recipient.
    """
    event_key = (
        f"chat_{kind}:engagement:{engagement_id}"
        f":{occurrence}:recipient:{recipient_id}"
    )
    publish_system_message(recipient_id=recipient_id, event_key=event_key, text=text)


# ── Публичные операции ────────────────────────────────────────────────────────

def create_student(
    full_name: str,
    email: str,
    phone: Optional[str],
    psychologist_id: Optional[int],
    primary_concern: Optional[str],
    actor_id,
    actor_role: str,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    """
    Создать полноценный аккаунт студента (admin/supervisor) с временным паролем.

    Core-запись атомарна (storage.create_student): User + UserRole(student) +
    ConsentRecord[] + (опц.) активный TherapyEngagement + AuditLog — один commit.
    Хеш пароля считается ДО транзакции (bcrypt медленный). После commit — soft-fail
    шаги (привязка карточек, welcome-письмо, system-сообщения), их сбой НЕ
    откатывает аккаунт. ПДн/пароль не логируются.

    Raises SupervisorError (маппинг кодов storage → HTTP-статус).
    """
    # Локальные импорты — переиспользуем существующие механизмы, избегаем циклов.
    from app.auth.service import _hash
    from app.users.service import _generate_password

    password = _generate_password()
    password_hash = _hash(password)

    try:
        result = storage.create_student(
            email=email,
            full_name=full_name,
            password_hash=password_hash,
            phone=phone,
            psychologist_id=psychologist_id,
            primary_concern=primary_concern,
            actor_id=int(actor_id),
            actor_role=actor_role,
            ip=ip,
            user_agent=user_agent,
            required_consent_types=_REQUIRED_CONSENT_TYPES,
        )
    except storage.StudentCreateError as exc:
        raise SupervisorError(
            exc.message, _STUDENT_ERROR_STATUS.get(exc.code, 400)
        )

    new_id = int(result["id"])
    new_email = result["email"]

    # ── Post-commit soft-fail (аккаунт уже зафиксирован) ─────────────────────
    # Привязка карточек незарегистрированного студента (этап 2): идемпотентна,
    # привязывает только незанятые карточки с совпавшим normalized_email.
    linked = 0
    try:
        from app.appointments.service import link_unregistered_cards_to_user
        linked = link_unregistered_cards_to_user(new_id, new_email)
    except Exception:
        log.exception(
            "[create_student] card linking failed for user_id=%s", new_id
        )

    # Welcome-письмо с временным паролем (soft-fail; ПДн/пароль не логируем).
    try:
        from app.services.email_service import send_welcome_student
        send_welcome_student(
            to_email=new_email,
            name=result["full_name"],
            password=password,
        )
    except Exception as exc:
        log.warning(
            "[create_student] welcome email failed for user_id=%s: %s",
            new_id, type(exc).__name__,
        )

    # System-уведомления в раздел «Сообщения» (soft-fail, content не логируется).
    publish_system_message(
        recipient_id=new_id,
        event_key=f"welcome:user:{new_id}",
        text="Ваша учётная запись MindCare создана.",
    )
    engagement = result.get("engagement")
    if engagement:
        psych_name = result.get("psychologist_name")
        publish_system_message(
            recipient_id=new_id,
            event_key=f"engagement_assigned:engagement:{engagement['id']}",
            text=(
                f"Вам назначен психолог: {psych_name}." if psych_name
                else "Вам назначен психолог."
            ),
        )

    result["temporary_password"] = password
    result["linked_cards_count"] = linked
    return result


def assign_psychologist(
    client_id: int,
    psychologist_id: int,
    primary_concern: Optional[str],
    actor_id: int,
    actor_role: str,
) -> dict:
    """
    Назначить психолога студенту (Stage 31p lifecycle).

    - тот же психолог уже active у студента → 409 (no-op, ничего не меняется);
    - другой active уже есть → 409 (нужно переназначение);
    - есть прежняя (закрытая/transferred) связь именно с этим психологом →
      реактивируем её и переиспользуем старую беседу (тот же conversation_uuid);
    - иначе → создаём новую связь и беседу (поведение Stage 31o).
    """
    with SessionLocal() as db:
        client = _get_user_with_role(client_id, "student", db)
        psychologist = _get_user_with_role(psychologist_id, "psychologist", db)
        # Имена фиксируем до commit (после — атрибуты expire вне сессии).
        psych_name = _user_display_name(psychologist)
        patient_name = _user_display_name(client)

        existing = _get_active_engagement(client_id, db)
        if existing:
            if existing.psychologist_id == psychologist_id:
                raise SupervisorError(
                    "Этот психолог уже назначен пациенту", status_code=409
                )
            raise SupervisorError(
                f"У студента уже есть активная связь с психологом "
                f"(engagement id={existing.id}). Используйте переназначение.",
                status_code=409,
            )

        now = datetime.now(timezone.utc)
        occurrence = _occurrence_marker(now)
        prior = _find_latest_pair_engagement(client_id, psychologist_id, db)
        if prior is not None:
            # Реактивация прежней связи этой пары — старый чат снова активен.
            engagement, conv, conv_created = _reactivate_engagement(prior, db)
            reactivated = True
            audit_event = "supervisor_reactivate_psychologist"
            audit_desc = (
                f"Психолог id={psychologist_id} повторно назначен "
                f"(реактивация связи id={engagement.id}) студенту id={client_id}"
            )
        else:
            engagement = TherapyEngagement(
                client_id=client_id,
                psychologist_id=psychologist_id,
                status="active",
                primary_concern=primary_concern,
                started_at=now,
                ended_at=None,
            )
            db.add(engagement)
            db.flush()
            # Беседа создаётся в ТОЙ ЖЕ транзакции (Stage 31o).
            conv, conv_created = chat_storage.ensure_engagement_conversation(
                db, engagement.id
            )
            reactivated = False
            audit_event = "supervisor_assign_psychologist"
            audit_desc = (
                f"Психолог id={psychologist_id} назначен студенту id={client_id}"
            )

        conv_id = conv.id
        conv_uuid = str(conv.uuid)

        _log_event(audit_event, actor_id, actor_role, engagement.id, audit_desc, db)

        db.commit()
        db.refresh(engagement)

        result = {
            "id":              engagement.id,
            "status":          engagement.status,
            "client_id":       engagement.client_id,
            "psychologist_id": engagement.psychologist_id,
            "primary_concern": engagement.primary_concern,
            "started_at":      engagement.started_at,
            "ended_at":        engagement.ended_at,
            "transfer_reason": engagement.transfer_reason,
        }
        eng_id = engagement.id

    # chat_conversation_created audit — post-commit soft-fail, как в lazy-пути
    # (app/chat/service.py). Одно событие на беседу: только при реальном создании
    # (реактивация переиспользует старую беседу → conv_created=False).
    if conv_created:
        log_conversation_created(
            actor_id=actor_id,
            actor_role=actor_role,
            conversation_id=conv_id,
            conversation_uuid=conv_uuid,
            engagement_id=eng_id,
        )

    # System-уведомления — после успешного commit (soft-fail). Один текст
    # «создан» и для нового назначения, и для реактивации (без «снова»).
    # Оба участника получают уведомление в свою system-беседу.
    _publish_chat_event(
        engagement_id=eng_id, occurrence=occurrence, recipient_id=client_id,
        kind="created", text=_student_chat_created_text(psych_name),
    )
    _publish_chat_event(
        engagement_id=eng_id, occurrence=occurrence, recipient_id=psychologist_id,
        kind="created", text=_psychologist_chat_created_text(patient_name),
    )
    return result


def transfer_psychologist(
    engagement_id: int,
    new_psychologist_id: int,
    transfer_reason: Optional[str],
    actor_id: int,
    actor_role: str,
) -> dict:
    """
    Переназначить клиента на другого психолога (Stage 31p lifecycle).

    Закрывает текущую active-связь (status=transferred). Для нового психолога:
    - если этот психолог уже active у клиента → 409 (no-op);
    - если была прежняя связь именно с ним → реактивируем её, переиспользуя
      старую беседу (тот же conversation_uuid, история сохраняется);
    - иначе → создаём новую active-связь и беседу (поведение Stage 31o).
    """
    with SessionLocal() as db:
        engagement = (
            db.query(TherapyEngagement)
            .filter(TherapyEngagement.id == engagement_id)
            .first()
        )
        if not engagement:
            raise SupervisorError(
                f"Связь id={engagement_id} не найдена", status_code=404
            )
        if engagement.status != "active":
            raise SupervisorError(
                f"Можно переназначить только активную связь "
                f"(текущий статус: {engagement.status})",
                status_code=400,
            )
        if engagement.psychologist_id == new_psychologist_id:
            raise SupervisorError(
                "Этот психолог уже назначен пациенту", status_code=409
            )

        new_psychologist = _get_user_with_role(new_psychologist_id, "psychologist", db)
        new_psych_name = _user_display_name(new_psychologist)

        now = datetime.now(timezone.utc)
        occurrence = _occurrence_marker(now)

        # Закрыть текущую active-связь. flush ДО активации новой, чтобы
        # partial unique index ux_therapy_engagements_active_client видел только
        # одну active-строку клиента в момент реактивации/создания.
        old_client_id        = engagement.client_id
        old_concern          = engagement.primary_concern
        old_psychologist_id  = engagement.psychologist_id
        # Имена фиксируем до commit (после — атрибуты expire вне сессии).
        old_psych_name = _user_display_name(
            db.query(User).filter(User.id == old_psychologist_id).first()
        )
        patient_name = _user_display_name(
            db.query(User).filter(User.id == old_client_id).first()
        )
        engagement.status          = "transferred"
        engagement.ended_at        = now
        engagement.transferred_to  = new_psychologist_id
        engagement.transfer_reason = transfer_reason
        engagement.updated_at      = now
        db.flush()

        prior = _find_latest_pair_engagement(old_client_id, new_psychologist_id, db)
        if prior is not None:
            # Возврат к прежнему психологу — реактивируем старую связь и чат.
            new_engagement, conv, conv_created = _reactivate_engagement(prior, db)
            reactivated = True
        else:
            new_engagement = TherapyEngagement(
                client_id=old_client_id,
                psychologist_id=new_psychologist_id,
                status="active",
                primary_concern=old_concern,
                started_at=now,
                ended_at=None,
            )
            db.add(new_engagement)
            db.flush()
            # Беседа для НОВОЙ active-связи — в той же транзакции (Stage 31o).
            conv, conv_created = chat_storage.ensure_engagement_conversation(
                db, new_engagement.id
            )
            reactivated = False

        conv_id = conv.id
        conv_uuid = str(conv.uuid)

        _log_event(
            "supervisor_transfer_psychologist",
            actor_id,
            actor_role,
            engagement_id,
            f"Студент id={old_client_id} переназначен с психолога "
            f"id={old_psychologist_id} на id={new_psychologist_id}"
            + (" (реактивация прежней связи)" if reactivated else ""),
            db,
        )

        db.commit()
        db.refresh(new_engagement)

        result = {
            "id":              new_engagement.id,
            "status":          new_engagement.status,
            "client_id":       new_engagement.client_id,
            "psychologist_id": new_engagement.psychologist_id,
            "primary_concern": new_engagement.primary_concern,
            "started_at":      new_engagement.started_at,
            "ended_at":        new_engagement.ended_at,
            "transfer_reason": new_engagement.transfer_reason,
        }
        new_eng_id = new_engagement.id

    # chat_conversation_created audit для новой беседы — post-commit soft-fail.
    if conv_created:
        log_conversation_created(
            actor_id=actor_id,
            actor_role=actor_role,
            conversation_id=conv_id,
            conversation_uuid=conv_uuid,
            engagement_id=new_eng_id,
        )

    # System-уведомления — после успешного commit (soft-fail). Transfer = два
    # события: старая связь закрыта + новая создана. Получают все участники.
    old_eng_id = engagement_id
    # пациенту: старый чат закрыт + новый создан
    _publish_chat_event(
        engagement_id=old_eng_id, occurrence=occurrence, recipient_id=old_client_id,
        kind="closed", text=_student_chat_closed_text(old_psych_name),
    )
    _publish_chat_event(
        engagement_id=new_eng_id, occurrence=occurrence, recipient_id=old_client_id,
        kind="created", text=_student_chat_created_text(new_psych_name),
    )
    # старому психологу: чат с пациентом закрыт
    _publish_chat_event(
        engagement_id=old_eng_id, occurrence=occurrence,
        recipient_id=old_psychologist_id,
        kind="closed", text=_psychologist_chat_closed_text(patient_name),
    )
    # новому психологу: чат с пациентом создан
    _publish_chat_event(
        engagement_id=new_eng_id, occurrence=occurrence,
        recipient_id=new_psychologist_id,
        kind="created", text=_psychologist_chat_created_text(patient_name),
    )
    return result


def close_engagement(
    engagement_id: int,
    reason: Optional[str],
    actor_id: int,
    actor_role: str,
) -> dict:
    """
    Закрыть активную связь клиента с психологом (status=completed).
    """
    with SessionLocal() as db:
        engagement = (
            db.query(TherapyEngagement)
            .filter(TherapyEngagement.id == engagement_id)
            .first()
        )
        if not engagement:
            raise SupervisorError(
                f"Связь id={engagement_id} не найдена", status_code=404
            )
        if engagement.status != "active":
            raise SupervisorError(
                f"Можно закрыть только активную связь "
                f"(текущий статус: {engagement.status})",
                status_code=400,
            )

        now = datetime.now(timezone.utc)
        occurrence = _occurrence_marker(now)
        client_id = engagement.client_id
        psychologist_id = engagement.psychologist_id
        # Имена фиксируем до commit (после — атрибуты expire вне сессии).
        psych_name = _user_display_name(
            db.query(User).filter(User.id == psychologist_id).first()
        )
        patient_name = _user_display_name(
            db.query(User).filter(User.id == client_id).first()
        )
        engagement.status          = "completed"
        engagement.ended_at        = now
        engagement.transfer_reason = reason
        engagement.updated_at      = now

        _log_event(
            "supervisor_close_engagement",
            actor_id,
            actor_role,
            engagement_id,
            f"Связь id={engagement_id} закрыта супервизором id={actor_id}"
            + (f" — причина: {reason}" if reason else ""),
            db,
        )

        db.commit()
        db.refresh(engagement)

        result = {
            "id":              engagement.id,
            "status":          engagement.status,
            "client_id":       engagement.client_id,
            "psychologist_id": engagement.psychologist_id,
            "primary_concern": engagement.primary_concern,
            "started_at":      engagement.started_at,
            "ended_at":        engagement.ended_at,
            "transfer_reason": engagement.transfer_reason,
        }

    # System-уведомления — после успешного commit (soft-fail). Закрытие чата
    # получают оба участника. reason в тексте не раскрывается (MVP).
    _publish_chat_event(
        engagement_id=engagement_id, occurrence=occurrence, recipient_id=client_id,
        kind="closed", text=_student_chat_closed_text(psych_name),
    )
    _publish_chat_event(
        engagement_id=engagement_id, occurrence=occurrence,
        recipient_id=psychologist_id,
        kind="closed", text=_psychologist_chat_closed_text(patient_name),
    )
    return result
