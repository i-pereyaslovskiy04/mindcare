"""
Бизнес-логика модуля супервизора.
Все транзакционные операции открывают одну сессию и выполняются атомарно.
"""

import sys
from datetime import datetime, timezone
from typing import Optional

from app.db.session import SessionLocal
from app.db.models import AuditLog, Role, TherapyEngagement, User, UserRole


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


# ── Публичные операции ────────────────────────────────────────────────────────

def assign_psychologist(
    client_id: int,
    psychologist_id: int,
    primary_concern: Optional[str],
    actor_id: int,
    actor_role: str,
) -> dict:
    """
    Назначить психолога студенту.
    Raises SupervisorError(409) если у клиента уже есть active engagement.
    """
    with SessionLocal() as db:
        client = _get_user_with_role(client_id, "student", db)
        _get_user_with_role(psychologist_id, "psychologist", db)

        existing = _get_active_engagement(client_id, db)
        if existing:
            raise SupervisorError(
                f"У студента уже есть активная связь с психологом "
                f"(engagement id={existing.id}). Используйте переназначение.",
                status_code=409,
            )

        now = datetime.now(timezone.utc)
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

        _log_event(
            "supervisor_assign_psychologist",
            actor_id,
            actor_role,
            engagement.id,
            f"Психолог id={psychologist_id} назначен студенту id={client_id}",
            db,
        )

        # TODO: отправить уведомления студенту и психологу (NotificationService не реализован)

        db.commit()
        db.refresh(engagement)

        return {
            "id":              engagement.id,
            "status":          engagement.status,
            "client_id":       engagement.client_id,
            "psychologist_id": engagement.psychologist_id,
            "primary_concern": engagement.primary_concern,
            "started_at":      engagement.started_at,
            "ended_at":        engagement.ended_at,
            "transfer_reason": engagement.transfer_reason,
        }


def transfer_psychologist(
    engagement_id: int,
    new_psychologist_id: int,
    transfer_reason: Optional[str],
    actor_id: int,
    actor_role: str,
) -> dict:
    """
    Переназначить клиента на другого психолога.
    Закрывает старую связь (status=transferred) и создаёт новую (status=active).
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

        _get_user_with_role(new_psychologist_id, "psychologist", db)

        now = datetime.now(timezone.utc)

        # Закрыть старую связь
        old_client_id = engagement.client_id
        old_concern   = engagement.primary_concern
        engagement.status          = "transferred"
        engagement.ended_at        = now
        engagement.transferred_to  = new_psychologist_id
        engagement.transfer_reason = transfer_reason
        engagement.updated_at      = now

        # Создать новую связь
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

        _log_event(
            "supervisor_transfer_psychologist",
            actor_id,
            actor_role,
            engagement_id,
            f"Студент id={old_client_id} переназначен с психолога "
            f"id={engagement.psychologist_id} на id={new_psychologist_id}",
            db,
        )

        # TODO: отправить уведомления студенту, старому и новому психологу

        db.commit()
        db.refresh(new_engagement)

        return {
            "id":              new_engagement.id,
            "status":          new_engagement.status,
            "client_id":       new_engagement.client_id,
            "psychologist_id": new_engagement.psychologist_id,
            "primary_concern": new_engagement.primary_concern,
            "started_at":      new_engagement.started_at,
            "ended_at":        new_engagement.ended_at,
            "transfer_reason": new_engagement.transfer_reason,
        }


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

        # TODO: отправить уведомления студенту и психологу

        db.commit()
        db.refresh(engagement)

        return {
            "id":              engagement.id,
            "status":          engagement.status,
            "client_id":       engagement.client_id,
            "psychologist_id": engagement.psychologist_id,
            "primary_concern": engagement.primary_concern,
            "started_at":      engagement.started_at,
            "ended_at":        engagement.ended_at,
            "transfer_reason": engagement.transfer_reason,
        }
