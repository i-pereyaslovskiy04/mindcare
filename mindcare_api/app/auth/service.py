"""
Business logic layer — no FastAPI, no JWT, no HTTP concepts.
Depends only on storage and passlib. Safe to unit-test in isolation.
"""

import uuid
from typing import Optional

import bcrypt
from app.auth import storage
from app.auth.security import hash_token, create_refresh_token


def _hash(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _verify(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


class AuthError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code


def register_user(name: str, email: str, password: str) -> dict:
    if not name or len(name.strip()) < 2:
        raise AuthError("Name must be at least 2 characters", 422)
    if len(password) < 8:
        raise AuthError("Password must be at least 8 characters", 422)
    if storage.find_user_by_email(email):
        raise AuthError("Email already registered", 409)

    user = {
        "id": str(uuid.uuid4()),
        "name": name.strip(),
        "email": email,
        "hashed_password": _hash(password),
        "role": "student",
    }
    return storage.save_user(user)


def register_init(name: str, email: str, password: str) -> None:
    """Validate data, store hashed password + OTP in DB, send confirmation email."""
    if not name or len(name.strip()) < 2:
        raise AuthError("Name must be at least 2 characters", 422)
    if len(password) < 8:
        raise AuthError("Password must be at least 8 characters", 422)
    if storage.find_user_by_email(email):
        raise AuthError("Email already registered", 409)

    from app.auth import otp_service
    from app.services.email_service import send_registration_otp

    password_hash = _hash(password)
    try:
        code = otp_service.create_or_update_otp(email, name.strip(), password_hash)
    except ValueError as e:
        raise AuthError(str(e), 429)

    print(f"[register_init] STEP 3: sending OTP to {email}")
    try:
        send_registration_otp(email, code)
        print("[register_init] STEP 4: email sent OK")
    except Exception as e:
        import traceback
        print(f"[register_init] EMAIL ERROR: {type(e).__name__}: {e}")
        traceback.print_exc()
        raise AuthError(f"Не удалось отправить письмо: {type(e).__name__}: {e}", 500)


def register_confirm(email: str, code: str) -> dict:
    """Verify OTP against the DB record and create the user."""
    from app.auth import otp_service

    try:
        user_data = otp_service.verify_otp(email, code)
    except ValueError as e:
        raise AuthError(str(e), 400)

    user = {
        "id": str(uuid.uuid4()),
        "name": user_data["name"],
        "email": email,
        "hashed_password": user_data["password_hash"],
        "role": "student",
    }
    return storage.save_user(user)


def password_reset_init(email: str) -> None:
    """
    Send a password-reset OTP to *email*.

    Returns silently if the email is not registered (safe 200 — prevents
    email enumeration: the caller gets the same response either way).
    Reuses the existing OTP table; name/password_hash are stored as the
    user's current values and are ignored during confirm.
    """
    from app.auth import otp_service
    from app.services.email_service import send_password_reset_otp

    user = storage.find_user_by_email(email)
    if not user:
        return  # silent — don't reveal whether email is registered

    try:
        code = otp_service.create_or_update_otp(
            email=email,
            name=user["name"],
            password_hash=user["hashed_password"],
        )
    except ValueError as e:
        raise AuthError(str(e), 429)

    print(f"[password_reset] sending OTP to {email}")
    try:
        send_password_reset_otp(email, code)
    except Exception as e:
        import traceback
        print(f"[password_reset] EMAIL ERROR: {type(e).__name__}: {e}")
        traceback.print_exc()
        raise AuthError(f"Не удалось отправить письмо: {type(e).__name__}: {e}", 500)


def password_reset_confirm(email: str, code: str, new_password: str) -> None:
    """
    Verify the OTP, hash and store the new password, revoke all sessions.
    """
    if len(new_password) < 8:
        raise AuthError("Password must be at least 8 characters", 422)

    from app.auth import otp_service

    try:
        otp_service.verify_otp(email, code)  # deletes OTP record on success
    except ValueError as e:
        raise AuthError(str(e), 400)

    user = storage.find_user_by_email(email)
    if not user:
        raise AuthError("Пользователь не найден", 404)

    storage.update_user_password(user["id"], _hash(new_password))
    storage.delete_all_user_refresh_tokens(user["id"])


def authenticate_user(email: str, password: str) -> dict:
    user = storage.find_user_by_email(email)
    if not user or not _verify(password, user["hashed_password"]):
        raise AuthError("Invalid email or password", 401)
    storage.update_last_login(user["id"])
    return user


def get_user_by_id(user_id: str) -> Optional[dict]:
    return storage.find_user_by_id(user_id)


def save_refresh_token(token: str, user_id: str) -> None:
    storage.store_refresh_token(hash_token(token), user_id)


def validate_refresh_token(token: str) -> Optional[str]:
    return storage.find_refresh_token(hash_token(token))


def revoke_refresh_token(token: str) -> None:
    storage.delete_refresh_token(hash_token(token))


def rotate_refresh_token(old_token: str) -> tuple[str, str]:
    """Validate old token, atomically revoke it, issue a new one. Returns (user_id, new_token).
    Raises AuthError(401) if token is unknown or already revoked."""
    old_hash = hash_token(old_token)
    user_id = storage.find_refresh_token(old_hash)
    if not user_id:
        raise AuthError("Invalid or already-used refresh token", 401)
    storage.delete_refresh_token(old_hash)
    new_token = create_refresh_token()
    storage.store_refresh_token(hash_token(new_token), user_id)
    return user_id, new_token
