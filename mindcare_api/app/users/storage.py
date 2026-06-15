"""
Работа с БД для модуля users: запросы, фильтры, пагинация.
Все SQLAlchemy-запросы изолированы здесь.
"""

import uuid as _uuid
from typing import Optional
from datetime import datetime, timezone

from sqlalchemy import or_, asc, desc, select, case as sa_case

from app.core.normalization import normalize_email
from app.db.session import SessionLocal
from app.db.models import User, UserRole, Role, UserSession, UserLegalBasisRecord

_ROLE_PRIORITY = sa_case(
    (Role.name == "admin",        1),
    (Role.name == "supervisor",   2),
    (Role.name == "psychologist", 3),
    (Role.name == "student",      4),
    else_=5,
)

ALLOWED_SORT_FIELDS = {"created_at", "email", "full_name", "last_login"}

# Служебные роли: их назначение требует документированного основания (legal basis).
STAFF_ROLES = {"psychologist", "supervisor", "admin"}


def find_users(
    page: int = 1,
    size: int = 20,
    search: Optional[str] = None,
    role: Optional[str] = None,
    is_active: Optional[bool] = None,
    sort: str = "created_at",
    order: str = "desc",
    include_deleted: bool = False,
) -> tuple[list[dict], int]:
    """
    Возвращает кортеж (items, total) для пагинированного списка юзеров.

    - items — список юзеров на текущей странице (в виде dict)
    - total — общее число юзеров с учётом фильтров (без пагинации)

    Применяет soft-delete фильтр: deleted_at IS NULL.
    Невалидные поля сортировки заменяются на 'created_at'.
    """
    if sort not in ALLOWED_SORT_FIELDS:
        sort = "created_at"

    with SessionLocal() as db:
        # ── 1. Базовый запрос с коррелированным подзапросом роли ──
        role_subq = (
            select(Role.name)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == User.id)
            .order_by(_ROLE_PRIORITY)
            .limit(1)
            .correlate(User)
            .scalar_subquery()
        )
        query = db.query(User, role_subq.label("role_name"))
        if not include_deleted:
            query = query.filter(User.deleted_at.is_(None))

        # ── 2. Фильтры ──
        if search:
            pattern = f"%{search.strip()}%"
            query = query.filter(
                or_(
                    User.email.ilike(pattern),
                    User.full_name.ilike(pattern),
                )
            )

        if role:
            role_filter_subq = (
                select(UserRole.user_id)
                .join(Role, Role.id == UserRole.role_id)
                .where(Role.name == role)
            )
            query = query.filter(User.id.in_(role_filter_subq))

        if is_active is not None:
            query = query.filter(User.is_active == is_active)

        # ── 3. Общее количество (для пагинации) ──
        total = query.count()

        # ── 4. Сортировка ──
        sort_column = getattr(User, sort, User.created_at)
        direction = desc if order == "desc" else asc
        if include_deleted:
            query = query.order_by(User.deleted_at.is_(None).desc(), direction(sort_column))
        else:
            query = query.order_by(direction(sort_column))

        # ── 5. Пагинация (LIMIT/OFFSET) ──
        offset = (page - 1) * size
        results = query.offset(offset).limit(size).all()

        # ── 6. Маппинг в dict ──
        items = []
        for user, role_name in results:
            items.append({
                "id":         user.id,
                "uuid":       str(user.uuid),
                "email":      user.email,
                "full_name":  user.full_name,
                "role":       role_name or "student",
                "is_active":  user.is_active,
                "created_at": user.created_at,
                "last_login": user.last_login,
                "deleted_at": user.deleted_at,
            })

    return items, total


def get_user_by_uuid(uuid: str) -> Optional[dict]:
    """
    Возвращает dict с данными юзера (включая роль) или None если не найден.
    Применяет soft-delete фильтр: deleted_at IS NULL.
    """
    try:
        uuid_obj = _uuid.UUID(uuid)
    except ValueError:
        return None

    with SessionLocal() as db:
        role_subq = (
            select(Role.name)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == User.id)
            .order_by(_ROLE_PRIORITY)
            .limit(1)
            .correlate(User)
            .scalar_subquery()
        )
        row = (
            db.query(User, role_subq.label("role_name"))
            .filter(User.uuid == uuid_obj)
            .filter(User.deleted_at.is_(None))
            .first()
        )
        if not row:
            return None
        user, role_name = row
        return {
            "id":         user.id,
            "uuid":       str(user.uuid),
            "email":      user.email,
            "full_name":  user.full_name,
            "phone":      user.phone,
            "role":       role_name or "student",
            "is_active":  user.is_active,
            "created_at": user.created_at,
            "last_login": user.last_login,
        }


def update_user(
    uuid: str,
    full_name: Optional[str] = None,
    phone: Optional[str] = None,
    is_active: Optional[bool] = None,
    role: Optional[str] = None,
    *,
    legal_basis_confirmed: Optional[bool] = None,
    basis_type: Optional[str] = None,
    basis_reference: Optional[str] = None,
    legal_basis_comment: Optional[str] = None,
    confirmed_by_user_id: Optional[int] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    """
    Обновляет поля юзера и/или его роль.
    Роль меняется атомарно: удаляем старую запись user_roles, вставляем новую.

    Назначение служебной роли (psychologist/supervisor/admin), отличной от
    текущей, требует документированного основания: в ТОЙ ЖЕ транзакции
    создаётся UserLegalBasisRecord (НЕ consent_records). Если основание не
    подтверждено / не указан basis_type или basis_reference — ValueError,
    роль не меняется, частичных записей нет (commit не выполняется).
    Переход staff → student основания не требует и старые записи не удаляет.

    Raises ValueError если юзер не найден, роль не существует в БД, либо
    отсутствует обязательное основание при смене роли на служебную.
    """
    try:
        uuid_obj = _uuid.UUID(uuid)
    except ValueError:
        raise ValueError(f"Некорректный UUID: {uuid}")

    with SessionLocal() as db:
        user = (
            db.query(User)
            .filter(User.uuid == uuid_obj)
            .filter(User.deleted_at.is_(None))
            .first()
        )
        if not user:
            raise ValueError(f"Пользователь {uuid} не найден")

        # Текущая (primary) роль — нужна для policy и для metadata записи основания.
        cur_role_row = (
            db.query(Role.name)
            .join(UserRole, UserRole.role_id == Role.id)
            .filter(UserRole.user_id == user.id)
            .order_by(_ROLE_PRIORITY)
            .first()
        )
        old_role = cur_role_row[0] if cur_role_row else "student"

        # Требуется ли legal basis: смена на служебную роль, отличную от текущей.
        requires_basis = (
            role is not None and role != old_role and role in STAFF_ROLES
        )
        if requires_basis:
            # Проверки ДО любых мутаций — чтобы не было частичных изменений.
            if legal_basis_confirmed is not True:
                raise ValueError(
                    "Для назначения служебной роли необходимо подтвердить "
                    "документированное основание (legal_basis_confirmed)"
                )
            if not basis_type:
                raise ValueError(
                    "Необходимо указать basis_type для смены роли на служебную"
                )
            if not (basis_reference and basis_reference.strip()):
                raise ValueError(
                    "Необходимо указать basis_reference (документ-основание) "
                    "для смены роли на служебную"
                )

        if full_name is not None:
            stripped = full_name.strip()
            if len(stripped) < 2:
                raise ValueError("ФИО должно содержать минимум 2 символа")
            user.full_name = stripped
        if phone is not None:
            user.phone = phone.strip() or None
        if is_active is not None:
            user.is_active = is_active

        if role is not None:
            role_obj = db.query(Role).filter(Role.name == role).first()
            if not role_obj:
                raise ValueError(f"Роль '{role}' не найдена в БД")
            db.query(UserRole).filter(UserRole.user_id == user.id).delete()
            db.add(UserRole(user_id=user.id, role_id=role_obj.id))
            current_role = role

            if requires_basis:
                db.add(UserLegalBasisRecord(
                    user_id=user.id,
                    basis_type=basis_type,
                    basis_source="admin_ui",
                    basis_reference=basis_reference.strip(),
                    confirmed_by_user_id=confirmed_by_user_id,
                    ip_address=ip,
                    user_agent=user_agent,
                    comment=legal_basis_comment,
                    record_metadata={
                        "action":   "role_change",
                        "old_role": old_role,
                        "new_role": role,
                    },
                ))
        else:
            current_role = old_role

        db.commit()
        db.refresh(user)

        return {
            "id":         user.id,
            "uuid":       str(user.uuid),
            "email":      user.email,
            "full_name":  user.full_name,
            "phone":      user.phone,
            "role":       current_role,
            "is_active":  user.is_active,
            "created_at": user.created_at,
            "last_login": user.last_login,
        }


def soft_delete_user(uuid: str) -> bool:
    """
    Мягкое удаление юзера — выставляет deleted_at, не удаляет физически.
    Возвращает True если юзер найден и помечен удалённым, False если не найден.
    Также отзывает все активные сессии юзера.
    """
    try:
        uuid_obj = _uuid.UUID(uuid)
    except ValueError:
        return False

    with SessionLocal() as db:
        user = (
            db.query(User)
            .filter(User.uuid == uuid_obj)
            .filter(User.deleted_at.is_(None))
            .first()
        )
        if not user:
            return False

        now = datetime.now(timezone.utc)
        user.deleted_at = now
        user.is_active = False

        db.query(UserSession).filter(
            UserSession.user_id == user.id,
            ~UserSession.is_revoked,
        ).update({"is_revoked": True}, synchronize_session=False)

        db.commit()
        return True


def create_user(
    email: str,
    full_name: str,
    password_hash: str,
    role: str,
    phone: Optional[str] = None,
    *,
    basis_type: str = "service_duty",
    basis_reference: Optional[str] = None,
    legal_basis_comment: Optional[str] = None,
    confirmed_by_user_id: Optional[int] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    """
    Создаёт нового пользователя с указанной ролью.

    Используется только из админских эндпоинтов.
    Публичная регистрация — через auth/storage.save_user.

    В той же транзакции создаёт UserLegalBasisRecord — документированное
    основание организации для создания учётной записи (НЕ consent_records:
    это не «согласие за пользователя», см. app/db/models/legal_basis.py).
    Если запись основания не создаётся — пользователь не создаётся (rollback).

    Возвращает dict с данными созданного юзера.
    """
    with SessionLocal() as db:
        existing = (
            db.query(User)
            .filter(User.email == normalize_email(email))
            .filter(User.deleted_at.is_(None))
            .first()
        )
        if existing:
            raise ValueError(f"Пользователь с email {email} уже существует")

        new_user = User(
            email=normalize_email(email),
            full_name=full_name.strip(),
            password_hash=password_hash,
            phone=phone.strip() or None if phone else None,
            is_active=True,
        )
        db.add(new_user)
        db.flush()  # получаем id до commit — нужен для user_roles и legal basis

        role_obj = db.query(Role).filter(Role.name == role).first()
        if not role_obj:
            raise ValueError(f"Роль '{role}' не найдена в БД")

        db.add(UserRole(user_id=new_user.id, role_id=role_obj.id))
        db.add(UserLegalBasisRecord(
            user_id=new_user.id,
            basis_type=basis_type,
            basis_source="admin_ui",
            basis_reference=basis_reference,
            confirmed_by_user_id=confirmed_by_user_id,
            ip_address=ip,
            user_agent=user_agent,
            comment=legal_basis_comment,
        ))
        db.commit()
        db.refresh(new_user)

        return {
            "id":         new_user.id,
            "uuid":       str(new_user.uuid),
            "email":      new_user.email,
            "full_name":  new_user.full_name,
            "role":       role,
            "is_active":  new_user.is_active,
            "created_at": new_user.created_at,
        }
