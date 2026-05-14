"""
Работа с БД для модуля users: запросы, фильтры, пагинация.
Все SQLAlchemy-запросы изолированы здесь.
"""

from typing import Optional
from datetime import datetime, timezone

from sqlalchemy import or_, asc, desc
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.db.models import User, UserRole, Role

ALLOWED_SORT_FIELDS = {"created_at", "email", "full_name", "last_login"}


def find_users(
    page: int = 1,
    size: int = 20,
    search: Optional[str] = None,
    role: Optional[str] = None,
    is_active: Optional[bool] = None,
    sort: str = "created_at",
    order: str = "desc",
) -> tuple[list[dict], int]:
    """
    Возвращает кортеж (items, total) для пагинированного списка юзеров.
    
    - items — список юзеров на текущей странице (в виде dict)
    - total — общее число юзеров с учётом фильтров (без пагинации)
    
    Применяет soft-delete фильтр: deleted_at IS NULL.
    Невалидные поля сортировки заменяются на 'created_at'.
    """
    # Защита от невалидного sort (whitelist)
    if sort not in ALLOWED_SORT_FIELDS:
        sort = "created_at"
    
    with SessionLocal() as db:
        # ... тут будет основная логика
        # ── 1. Базовый запрос с JOIN к ролям ──
        query = (
            db.query(User, Role.name.label("role_name"))
            .outerjoin(UserRole, UserRole.user_id == User.id)
            .outerjoin(Role, Role.id == UserRole.role_id)
            .filter(User.deleted_at.is_(None))
        )

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
            query = query.filter(Role.name == role)

        if is_active is not None:
            query = query.filter(User.is_active == is_active)

        # ── 3. Общее количество (для пагинации) ──
        total = query.count()

        # ── 4. Сортировка ──
        sort_column = getattr(User, sort, User.created_at)
        direction = desc if order == "desc" else asc
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
            })

    return items, total


def get_user_by_uuid(uuid: str) -> Optional[dict]:
    """
    Возвращает dict с данными юзера (включая роль) или None если не найден.
    Применяет soft-delete фильтр: deleted_at IS NULL.
    """
    with SessionLocal() as db:
        row = (
            db.query(User, Role.name.label("role_name"))
            .outerjoin(UserRole, UserRole.user_id == User.id)
            .outerjoin(Role, Role.id == UserRole.role_id)
            .filter(User.uuid == uuid)
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
) -> dict:
    """
    Обновляет поля юзера и/или его роль.
    Роль меняется атомарно: удаляем старую запись user_roles, вставляем новую.
    Raises ValueError если юзер не найден или роль не существует в БД.
    """
    with SessionLocal() as db:
        user = (
            db.query(User)
            .filter(User.uuid == uuid)
            .filter(User.deleted_at.is_(None))
            .first()
        )
        if not user:
            raise ValueError(f"Пользователь {uuid} не найден")

        if full_name is not None:
            user.full_name = full_name.strip()
        if phone is not None:
            user.phone = phone
        if is_active is not None:
            user.is_active = is_active

        if role is not None:
            role_obj = db.query(Role).filter(Role.name == role).first()
            if not role_obj:
                raise ValueError(f"Роль '{role}' не найдена в БД")
            db.query(UserRole).filter(UserRole.user_id == user.id).delete()
            db.add(UserRole(user_id=user.id, role_id=role_obj.id))
            current_role = role
        else:
            user_role = (
                db.query(UserRole, Role.name)
                .join(Role, Role.id == UserRole.role_id)
                .filter(UserRole.user_id == user.id)
                .first()
            )
            current_role = user_role[1] if user_role else "student"

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


def create_user(
    email: str,
    full_name: str,
    password_hash: str,
    role: str,
    phone: Optional[str] = None,
) -> dict:
    """
    Создаёт нового пользователя с указанной ролью.
    
    Используется только из админских эндпоинтов.
    Публичная регистрация — через auth/storage.save_user.
    
    Возвращает dict с данными созданного юзера.
    Не создаёт consent_records — для adminski-созданных юзеров
    согласие фиксируется отдельно при первом логине (TODO: Этап 2).
    """
    with SessionLocal() as db:
        # Проверка дубликата email — до создания юзера
        existing = (
            db.query(User)
            .filter(User.email == email.lower().strip())
            .filter(User.deleted_at.is_(None))
            .first()
        )
        if existing:
            raise ValueError(f"Пользователь с email {email} уже существует")

        # Создаём юзера
        new_user = User(
            email=email.lower().strip(),
            full_name=full_name.strip(),
            password_hash=password_hash,
            phone=phone,
            is_active=True,
        )
        db.add(new_user)
        db.flush()  # получаем id до commit — нужен для user_roles

        # Назначаем роль
        role_obj = db.query(Role).filter(Role.name == role).first()
        if not role_obj:
            raise ValueError(f"Роль '{role}' не найдена в БД")

        db.add(UserRole(user_id=new_user.id, role_id=role_obj.id))
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