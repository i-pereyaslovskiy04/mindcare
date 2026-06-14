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


_ENCRYPTION_CONFIG_ERROR = (
    "DATA_ENCRYPTION_KEY is required and must be a valid Fernet key"
)


def assert_encryption_ready() -> None:
    """Fail-fast проверка конфигурации шифрования (вызывать при старте).

    Гарантирует, что DATA_ENCRYPTION_KEY задан и валиден для Fernet, до того
    как приложение начнёт обслуживать запросы. Иначе RuntimeError/ValueError
    всплыли бы только при первом encrypted read/write (chat/session_notes).

    Безопасность:
      - сам ключ НЕ логируется и НЕ включается в текст ошибки
        (сообщение статичное; исходное исключение cryptography ключ не содержит);
      - проверка делает round-trip на статичной строке в памяти, без записи в БД;
      - формат enc:v1: и реальные данные не затрагиваются.
    """
    key = settings.DATA_ENCRYPTION_KEY
    if not key:
        raise RuntimeError(_ENCRYPTION_CONFIG_ERROR)
    try:
        fernet = Fernet(key.encode("utf-8"))
        probe = b"mindcare-encryption-healthcheck"
        if fernet.decrypt(fernet.encrypt(probe)) != probe:
            raise ValueError("encryption round-trip mismatch")
    except Exception as exc:
        raise RuntimeError(_ENCRYPTION_CONFIG_ERROR) from exc


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
