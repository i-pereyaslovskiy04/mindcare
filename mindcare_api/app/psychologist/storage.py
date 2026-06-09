"""
SQLAlchemy-запросы для модуля психолога.
"""

from typing import Optional

from sqlalchemy import and_, func, or_

from app.db.session import SessionLocal
from app.db.models import TherapyEngagement, User


def get_my_student_detail(psychologist_id: int, student_id: int) -> Optional[dict]:
    """
    Возвращает детальную карточку студента, если он назначен данному психологу активным engagement.
    Возвращает None, если студент не найден или не назначен — 404 на уровне роута.
    """
    with SessionLocal() as db:
        row = (
            db.query(TherapyEngagement, User)
            .join(User, User.id == TherapyEngagement.client_id)
            .filter(
                TherapyEngagement.psychologist_id == psychologist_id,
                TherapyEngagement.client_id == student_id,
                TherapyEngagement.status == "active",
                TherapyEngagement.ended_at.is_(None),
                User.is_active.is_(True),
                User.deleted_at.is_(None),
            )
            .first()
        )
        if not row:
            return None
        eng, student = row
        return {
            "engagement_id": eng.id,
            "student_id":    student.id,
            "student_uuid":  str(student.uuid),
            "full_name":     student.full_name,
            "email":         student.email,
            "assigned_at":   eng.started_at,
            "registered_at": student.created_at,
            "status":        eng.status,
        }


def get_my_students(
    psychologist_id: int,
    search: Optional[str] = None,
    page: int = 1,
    size: int = 20,
) -> tuple[list[dict], int]:
    """
    Возвращает (items, total) — студентов с активной связью для данного психолога.
    """
    with SessionLocal() as db:
        base_filter = [
            TherapyEngagement.psychologist_id == psychologist_id,
            TherapyEngagement.status == "active",
            TherapyEngagement.ended_at.is_(None),
            User.is_active.is_(True),
            User.deleted_at.is_(None),
        ]
        if search:
            pattern = f"%{search.strip()}%"
            base_filter.append(
                or_(User.email.ilike(pattern), User.full_name.ilike(pattern))
            )

        total = (
            db.query(func.count(TherapyEngagement.id))
            .join(User, User.id == TherapyEngagement.client_id)
            .filter(*base_filter)
            .scalar()
        ) or 0

        results = (
            db.query(TherapyEngagement, User)
            .join(User, User.id == TherapyEngagement.client_id)
            .filter(*base_filter)
            .order_by(User.full_name)
            .offset((page - 1) * size)
            .limit(size)
            .all()
        )

        items = []
        for eng, student in results:
            items.append({
                "engagement_id": eng.id,
                "student_id":    student.id,
                "student_uuid":  str(student.uuid),
                "full_name":     student.full_name,
                "email":         student.email,
                "assigned_at":   eng.started_at,
                "status":        eng.status,
            })

        return items, total
