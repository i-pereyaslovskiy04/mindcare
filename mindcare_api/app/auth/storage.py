"""
PostgreSQL storage via SQLAlchemy ORM.

Сессии хранятся в user_sessions (таблица из SQL-схемы).
Роль пользователя берётся через JOIN user_roles → roles.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from app.db.session import SessionLocal
from app.db.models import User, UserRole, Role, UserSession
from app.auth.security import generate_session_token
from app.core.config import SESSION_EXPIRE_DAYS


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def _get_primary_role(db, user_id: int) -> str:
    """Первая активная роль пользователя, по умолчанию — 'student'."""
    ur = (
        db.query(UserRole)
        .join(Role, UserRole.role_id == Role.id)
        .filter(UserRole.user_id == user_id)
        .filter(
            (UserRole.expires_at == None) | (UserRole.expires_at > datetime.now(timezone.utc))
        )
        .first()
    )
    return ur.role.name if ur else "student"


def _user_to_dict(user: User, db) -> dict:
    return {
        "id":              str(user.id),
        "name":            user.full_name,
        "email":           user.email,
        "hashed_password": user.password_hash,
        "role":            _get_primary_role(db, user.id),
        "is_active":       user.is_active,
    }


def _assign_role(db, user_id: int, role_name: str = "student") -> None:
    """Назначает роль пользователю. Если роль не найдена в БД — пропускает."""
    role = db.query(Role).filter(Role.name == role_name).first()
    if role:
        db.add(UserRole(user_id=user_id, role_id=role.id))


# ---------------------------------------------------------------------------
# Пользователи
# ---------------------------------------------------------------------------

def find_user_by_email(email: str) -> Optional[dict]:
    with SessionLocal() as db:
        user = (
            db.query(User)
            .filter(User.email == email, User.deleted_at == None)
            .first()
        )
        return _user_to_dict(user, db) if user else None


def find_user_by_id(user_id: str) -> Optional[dict]:
    with SessionLocal() as db:
        user = (
            db.query(User)
            .filter(User.id == int(user_id), User.deleted_at == None)
            .first()
        )
        return _user_to_dict(user, db) if user else None


def save_user(user: dict) -> dict:
    with SessionLocal() as db:
        db_user = User(
            full_name=user["name"],
            email=user["email"],
            password_hash=user["hashed_password"],
        )
        db.add(db_user)
        db.flush()  # получаем id до commit, чтобы создать user_roles в той же транзакции
        _assign_role(db, db_user.id, user.get("role", "student"))
        db.commit()
        db.refresh(db_user)
        return _user_to_dict(db_user, db)


def update_last_login(user_id: str) -> None:
    with SessionLocal() as db:
        db.query(User).filter(User.id == int(user_id)).update(
            {"last_login": datetime.now(timezone.utc)},
            synchronize_session=False,
        )
        db.commit()


def update_user_password(user_id: str, password_hash: str) -> None:
    with SessionLocal() as db:
        db.query(User).filter(User.id == int(user_id)).update(
            {"password_hash": password_hash},
            synchronize_session=False,
        )
        db.commit()


# ---------------------------------------------------------------------------
# Сессии (заменяют JWT refresh-токены)
# ---------------------------------------------------------------------------

def create_session(
    user_id: str,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
    expire_days: int = SESSION_EXPIRE_DAYS,
) -> tuple[str, datetime]:
    """Создаёт сессию в БД. Возвращает (session_token, expires_at)."""
    token = generate_session_token()
    expires_at = datetime.now(timezone.utc) + timedelta(days=expire_days)

    with SessionLocal() as db:
        db.add(UserSession(
            id=token,
            user_id=int(user_id),
            ip_address=ip,
            user_agent=user_agent,
            expires_at=expires_at,
        ))
        db.commit()

    return token, expires_at


def find_session(token: str) -> Optional[dict]:
    """Ищет активную (не отозванную, не просроченную) сессию.
    Возвращает {'user_id': str, 'expires_at': datetime} или None."""
    with SessionLocal() as db:
        session = (
            db.query(UserSession)
            .filter(
                UserSession.id == token,
                UserSession.is_revoked == False,
                UserSession.expires_at > datetime.now(timezone.utc),
            )
            .first()
        )
        if not session:
            return None
        return {"user_id": str(session.user_id), "expires_at": session.expires_at}


def revoke_session(token: str) -> None:
    """Отзывает одну сессию (logout)."""
    with SessionLocal() as db:
        db.query(UserSession).filter(UserSession.id == token).update(
            {"is_revoked": True}, synchronize_session=False
        )
        db.commit()


def revoke_all_user_sessions(user_id: str) -> None:
    """Отзывает все сессии пользователя (например, после смены пароля)."""
    with SessionLocal() as db:
        db.query(UserSession).filter(
            UserSession.user_id == int(user_id)
        ).update({"is_revoked": True}, synchronize_session=False)
        db.commit()


def touch_session(token: str) -> None:
    """Обновляет last_active для сессии."""
    with SessionLocal() as db:
        db.query(UserSession).filter(UserSession.id == token).update(
            {"last_active": datetime.now(timezone.utc)},
            synchronize_session=False,
        )
        db.commit()
