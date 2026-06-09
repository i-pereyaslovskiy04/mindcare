"""
SQLAlchemy-запросы для модуля супервизора.
Только чтение (SELECT). Транзакционные операции — в service.py.
"""

from typing import Optional

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import aliased

from app.db.session import SessionLocal
from app.db.models import (
    PsychologistProfile,
    Role,
    TherapyEngagement,
    User,
    UserRole,
)


def get_students(
    search: Optional[str] = None,
    page: int = 1,
    size: int = 20,
) -> tuple[list[dict], int]:
    """
    Возвращает (items, total) — студентов с их текущим активным engagement.
    """
    with SessionLocal() as db:
        PsychUser = aliased(User)

        base_filter = [
            Role.name == "student",
            User.is_active.is_(True),
            User.deleted_at.is_(None),
        ]
        if search:
            pattern = f"%{search.strip()}%"
            base_filter.append(
                or_(User.email.ilike(pattern), User.full_name.ilike(pattern))
            )

        # Отдельный count (без лишних outer join — быстрее)
        total = (
            db.query(func.count(User.id))
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .filter(*base_filter)
            .scalar()
        ) or 0

        results = (
            db.query(User, TherapyEngagement, PsychUser)
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .filter(*base_filter)
            .outerjoin(
                TherapyEngagement,
                and_(
                    TherapyEngagement.client_id == User.id,
                    TherapyEngagement.status == "active",
                    TherapyEngagement.ended_at.is_(None),
                ),
            )
            .outerjoin(PsychUser, PsychUser.id == TherapyEngagement.psychologist_id)
            .order_by(User.full_name)
            .offset((page - 1) * size)
            .limit(size)
            .all()
        )

        items = []
        for student, engagement, psy in results:
            current_engagement = None
            if engagement:
                current_engagement = {
                    "id":     engagement.id,
                    "status": engagement.status,
                    "psychologist": {
                        "id":        psy.id,
                        "uuid":      str(psy.uuid),
                        "full_name": psy.full_name,
                        "email":     psy.email,
                    } if psy else None,
                }
            items.append({
                "id":                 student.id,
                "uuid":               str(student.uuid),
                "full_name":          student.full_name,
                "email":              student.email,
                "current_engagement": current_engagement,
            })

        return items, total


def get_psychologists(
    search: Optional[str] = None,
    page: int = 1,
    size: int = 100,
) -> tuple[list[dict], int]:
    """
    Возвращает (items, total) — психологов с полем is_accepting из profiles.
    """
    with SessionLocal() as db:
        base_filter = [
            Role.name == "psychologist",
            User.is_active.is_(True),
            User.deleted_at.is_(None),
        ]
        if search:
            pattern = f"%{search.strip()}%"
            base_filter.append(
                or_(User.email.ilike(pattern), User.full_name.ilike(pattern))
            )

        total = (
            db.query(func.count(User.id))
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .filter(*base_filter)
            .scalar()
        ) or 0

        results = (
            db.query(User, PsychologistProfile)
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .filter(*base_filter)
            .outerjoin(PsychologistProfile, PsychologistProfile.user_id == User.id)
            .order_by(User.full_name)
            .offset((page - 1) * size)
            .limit(size)
            .all()
        )

        items = []
        for user, profile in results:
            items.append({
                "id":           user.id,
                "uuid":         str(user.uuid),
                "full_name":    user.full_name,
                "email":        user.email,
                "is_accepting": profile.is_accepting if profile else None,
            })

        return items, total


def get_engagements(
    status: Optional[str] = None,
    student_search: Optional[str] = None,
    psychologist_search: Optional[str] = None,
    page: int = 1,
    size: int = 20,
) -> tuple[list[dict], int]:
    """
    Возвращает (items, total) — список всех связок с фильтрами.
    """
    with SessionLocal() as db:
        ClientUser = aliased(User, name="client_user")
        PsychUser  = aliased(User, name="psy_user")

        q = (
            db.query(TherapyEngagement, ClientUser, PsychUser)
            .join(ClientUser, ClientUser.id == TherapyEngagement.client_id)
            .join(PsychUser,  PsychUser.id  == TherapyEngagement.psychologist_id)
            .filter(
                ClientUser.deleted_at.is_(None),
                PsychUser.deleted_at.is_(None),
            )
        )

        if status:
            q = q.filter(TherapyEngagement.status == status)
        if student_search:
            pattern = f"%{student_search.strip()}%"
            q = q.filter(
                or_(ClientUser.email.ilike(pattern), ClientUser.full_name.ilike(pattern))
            )
        if psychologist_search:
            pattern = f"%{psychologist_search.strip()}%"
            q = q.filter(
                or_(PsychUser.email.ilike(pattern), PsychUser.full_name.ilike(pattern))
            )

        total = q.with_entities(func.count(TherapyEngagement.id)).scalar() or 0

        results = (
            q.order_by(TherapyEngagement.started_at.desc())
            .offset((page - 1) * size)
            .limit(size)
            .all()
        )

        items = []
        for eng, client, psy in results:
            items.append({
                "id":              eng.id,
                "status":          eng.status,
                "primary_concern": eng.primary_concern,
                "started_at":      eng.started_at,
                "ended_at":        eng.ended_at,
                "transfer_reason": eng.transfer_reason,
                "client": {
                    "id":        client.id,
                    "uuid":      str(client.uuid),
                    "full_name": client.full_name,
                    "email":     client.email,
                },
                "psychologist": {
                    "id":        psy.id,
                    "uuid":      str(psy.uuid),
                    "full_name": psy.full_name,
                    "email":     psy.email,
                },
            })

        return items, total
