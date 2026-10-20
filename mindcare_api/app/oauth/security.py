"""
Криптографические примитивы social login (Stage Social Auth 2B).

state / ticket — 256 бит из secrets, в БД только SHA-256 hex. PKCE verifier —
86 символов (диапазон RFC 7636: 43–128), challenge — только S256. Raw значения
не логируются и не хранятся (verifier — только `enc:v1:`, см. service).
"""
import base64
import hashlib
import hmac
import secrets

STATE_BYTES = 32
TICKET_BYTES = 32
VERIFIER_BYTES = 64   # token_urlsafe(64) → 86 символов [A-Za-z0-9_-]


def generate_state() -> str:
    """43 символа [A-Za-z0-9_-] (VK требует ≥32 таких символов)."""
    return secrets.token_urlsafe(STATE_BYTES)


def generate_ticket() -> str:
    return secrets.token_urlsafe(TICKET_BYTES)


def generate_code_verifier() -> str:
    return secrets.token_urlsafe(VERIFIER_BYTES)


def code_challenge_s256(verifier: str) -> str:
    """BASE64URL(SHA256(ASCII(verifier))) без '=' (RFC 7636 §4.2)."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))
