import hashlib
import secrets


def generate_session_token() -> str:
    """Генерирует криптографически стойкий токен сессии (43 символа, URL-safe)."""
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    """
    SHA-256 hex (64 символа) от session token — для хранения в user_sessions.id
    и auth_log.session_id вместо raw token.

    SHA-256 без соли достаточен: токен — не пароль, а opaque random value
    с 256 битами энтропии (secrets.token_urlsafe(32)), перебор прообраза
    и rainbow-таблицы неприменимы. Цель — чтобы значение из дампа БД
    нельзя было использовать как Bearer credential.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
