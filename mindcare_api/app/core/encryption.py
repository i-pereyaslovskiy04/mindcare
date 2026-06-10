from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

ENCRYPTION_PREFIX = "enc:v1:"

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet

    if _fernet is None:
        key = settings.DATA_ENCRYPTION_KEY
        if not key:
            raise RuntimeError("DATA_ENCRYPTION_KEY is not configured")

        try:
            _fernet = Fernet(key.encode("utf-8"))
        except Exception as exc:
            raise RuntimeError("DATA_ENCRYPTION_KEY is invalid") from exc

    return _fernet


def is_encrypted(value: str | None) -> bool:
    return bool(value and value.startswith(ENCRYPTION_PREFIX))


def encrypt_text(plaintext: str) -> str:
    if plaintext is None:
        raise ValueError("plaintext must not be None")

    token = _get_fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")
    return f"{ENCRYPTION_PREFIX}{token}"


def decrypt_text(ciphertext: str) -> str:
    if not ciphertext:
        raise ValueError("ciphertext must not be empty")

    if not is_encrypted(ciphertext):
        raise ValueError("value is not encrypted with expected prefix")

    token = ciphertext[len(ENCRYPTION_PREFIX):]

    try:
        return _get_fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("failed to decrypt value: invalid key or corrupted data") from exc
