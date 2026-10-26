"""
Абсолютные ссылки backend → frontend (ссылки в письмах).

База — FRONTEND_PUBLIC_URL этого окружения (LOCAL http://localhost:3000,
PRODUCTION https://mindcare.donnu.ru). Не ALLOWED_ORIGINS (это CORS) и не
OAUTH_* (адреса OAuth callback).

В ссылки НЕ кладутся email, код подтверждения, пароль или токены. Ссылка
продолжения регистрации несёт только registration reference (UUIDv4 выпуска
кода) во fragment: `/register/confirm#r=<uuid>`. Fragment не уходит на сервер
при GET, не попадает в access log и Referer; сам reference без кода из письма
ничего не подтверждает.
"""

import uuid
from typing import Optional
from urllib.parse import urlsplit

from app.core.config import settings

# Маршруты frontend (mindcare_web/src/app/router.jsx). /login и
# /register/confirm открывают главную с модалкой входа на нужном шаге.
LOGIN_PATH = "/login"
REGISTER_CONFIRM_PATH = "/register/confirm"


def normalize_frontend_base(raw: Optional[str]) -> Optional[str]:
    """База без хвостового «/»; None, если это не http(s)-адрес без
    userinfo, query и fragment (тогда ссылки в письмах не добавляются)."""
    base = (raw or "").strip().rstrip("/")
    if not base:
        return None
    try:
        parts = urlsplit(base)
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    if parts.username or parts.password or parts.query or parts.fragment:
        return None
    return base


def registration_continue_path(reference: str) -> Optional[str]:
    """Путь продолжения регистрации `/register/confirm#r=<uuid>` или None,
    если reference - не UUID (тогда письмо уходит без ссылки)."""
    try:
        canonical = str(uuid.UUID(str(reference)))
    except (TypeError, ValueError, AttributeError):
        return None
    return f"{REGISTER_CONFIRM_PATH}#r={canonical}"


def frontend_url(path: str, base: Optional[str] = None) -> Optional[str]:
    """Абсолютный адрес страницы frontend: {база}/{путь} ровно с одним «/»
    между ними. base по умолчанию — settings.FRONTEND_PUBLIC_URL."""
    root = normalize_frontend_base(settings.FRONTEND_PUBLIC_URL if base is None else base)
    if root is None:
        return None
    return f"{root}/{path.lstrip('/')}"
