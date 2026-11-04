"""
Токен ссылки кампании (ADR-036).

Сырой токен — только в ссылке и (для повторного показа супервизору) в
test_campaigns.link_token_enc (`enc:v1:`). Поиск — по SHA-256 hex
(link_token_hash). Токен не логировать и не класть в audit metadata/context.
"""
import hashlib
import re
import secrets
from typing import Optional

# secrets.token_urlsafe(32) → 43 символа base64url без '='.
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{43}$")


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def is_well_formed(token: str) -> bool:
    return bool(token) and bool(_TOKEN_RE.fullmatch(token))


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def lookup_hash(token: str) -> Optional[str]:
    """SHA-256 для поиска; None — токен заведомо неверного формата (→ 404)."""
    return hash_token(token) if is_well_formed(token) else None
