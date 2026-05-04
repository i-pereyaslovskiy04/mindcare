"""
MySQL storage via SQLAlchemy ORM.

Each function manages its own session so service.py signatures stay unchanged.
Column mapping: DB full_name ↔ service "name", DB password_hash ↔ service "hashed_password".
DB id is Integer AUTO_INCREMENT; exposed to the service layer as str for JWT compatibility.
"""

from datetime import datetime, timezone
from typing import Optional

from app.db.session import SessionLocal
from app.db.models import User, RefreshToken


def _user_to_dict(user: User) -> dict:
    return {
        "id":              str(user.id),
        "name":            user.full_name,
        "email":           user.email,
        "hashed_password": user.password_hash,
        "role":            user.role,
        "is_active":       user.is_active,
    }


def find_user_by_email(email: str) -> Optional[dict]:
    with SessionLocal() as db:
        user = db.query(User).filter(User.email == email).first()
        return _user_to_dict(user) if user else None


def find_user_by_id(user_id: str) -> Optional[dict]:
    with SessionLocal() as db:
        user = db.query(User).filter(User.id == int(user_id)).first()
        return _user_to_dict(user) if user else None


def save_user(user: dict) -> dict:
    with SessionLocal() as db:
        db_user = User(
            full_name=user["name"],
            email=user["email"],
            password_hash=user["hashed_password"],
            role=user["role"],
        )
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        return _user_to_dict(db_user)


def update_last_login(user_id: str) -> None:
    with SessionLocal() as db:
        db.query(User).filter(User.id == int(user_id)).update(
            {"last_login": datetime.now(timezone.utc)},
            synchronize_session=False,
        )
        db.commit()


def store_refresh_token(token_hash: str, user_id: str) -> None:
    with SessionLocal() as db:
        db.add(RefreshToken(token_hash=token_hash, user_id=int(user_id)))
        db.commit()


def find_refresh_token(token_hash: str) -> Optional[str]:
    with SessionLocal() as db:
        row = db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()
        return str(row.user_id) if row else None


def delete_refresh_token(token_hash: str) -> None:
    with SessionLocal() as db:
        db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).delete()
        db.commit()


def update_user_password(user_id: str, password_hash: str) -> None:
    with SessionLocal() as db:
        db.query(User).filter(User.id == int(user_id)).update(
            {"password_hash": password_hash},
            synchronize_session=False,
        )
        db.commit()


def delete_all_user_refresh_tokens(user_id: str) -> None:
    with SessionLocal() as db:
        db.query(RefreshToken).filter(
            RefreshToken.user_id == int(user_id)
        ).delete(synchronize_session=False)
        db.commit()
