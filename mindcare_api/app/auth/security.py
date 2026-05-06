import secrets


def generate_session_token() -> str:
    """Генерирует криптографически стойкий токен сессии (43 символа, URL-safe)."""
    return secrets.token_urlsafe(32)
