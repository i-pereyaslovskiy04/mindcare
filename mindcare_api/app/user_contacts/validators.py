"""
Чистая нормализация и валидация дополнительных контактов (ADR-032).

Без БД и HTTP. Ошибки — только коды (FieldError); значения контактов в ошибки,
сообщения и исключения не попадают никогда. Итог — канонические элементы
{id, type, service, value, label} с ровно этим набором ключей (по ним
сравнивается «ничего не изменилось»).

Ссылки: допустимы только http/https; произвольный текст в ссылку не
превращается (поле `other` и хэндлы остаются текстом, href на клиенте строится
только для проверенных значений). Сервер ссылки не загружает.
"""
import re
import unicodedata
import uuid as _uuid
from typing import Optional
from urllib.parse import urlsplit, urlunsplit

from app.core.normalization import normalize_email
from app.user_contacts import catalog
from app.user_contacts.errors import ContactsValidationError, FieldError

_PHONE_CHARS = re.compile(r"^\+?[\d\s().\-]+$")
_HANDLE = re.compile(r"^@?[\w.\-]{2,100}$")
_SCHEME = re.compile(r"^([a-zA-Z][a-zA-Z0-9+.\-]*)://")
_DANGEROUS = re.compile(
    r"^(javascript|data|vbscript|file|mailto|tel|sms|blob|about|ftp|ws|wss)\s*:",
    re.IGNORECASE,
)
_ANY_SCHEME_NOT_PORT = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:(?!\d+(/|$))")
_HOST = re.compile(
    r"^(?=.{1,253}$)([a-z0-9]([a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z0-9\-]{2,63}$"
)
_BIDI = frozenset(
    "\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069\u200e\u200f\u061c"
)


class _Bad(Exception):
    """Внутренний сигнал: у значения есть код ошибки (без самого значения)."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


# ── текст ─────────────────────────────────────────────────────────────────────

def _clean(raw, max_len: int) -> str:
    """trim + NFC; запрещены управляющие и bidi-символы; длина после trim."""
    if not isinstance(raw, str):
        raise _Bad("invalid_value")
    text = unicodedata.normalize("NFC", raw.strip())
    for ch in text:
        if ch in _BIDI or unicodedata.category(ch) in ("Cc", "Zl", "Zp"):
            raise _Bad("invalid_characters")
    if len(text) > max_len:
        raise _Bad("too_long")
    return text


# ── id ────────────────────────────────────────────────────────────────────────

def normalize_id(raw) -> str:
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        raise _Bad("required")
    try:
        parsed = _uuid.UUID(str(raw).strip())
    except (ValueError, AttributeError):
        raise _Bad("invalid_id") from None
    if parsed.int == 0:
        raise _Bad("invalid_id")
    return str(parsed)


# ── телефон ───────────────────────────────────────────────────────────────────

def normalize_phone(text: str) -> str:
    """Канон «+цифры». 8/7/10-значные RU-номера → +7…; без «+» нужно ≥ 10 цифр."""
    if not _PHONE_CHARS.match(text):
        raise _Bad("invalid_phone")
    digits = re.sub(r"\D", "", text)
    if text.startswith("+"):
        if 7 <= len(digits) <= 15:
            return "+" + digits
        raise _Bad("invalid_phone")
    if len(digits) == 11 and digits[0] in "78":
        return "+7" + digits[1:]
    if len(digits) == 10:
        return "+7" + digits
    if 10 <= len(digits) <= 15:
        return "+" + digits
    raise _Bad("invalid_phone")


def _looks_like_phone(text: str) -> bool:
    return bool(_PHONE_CHARS.match(text))


# ── email ─────────────────────────────────────────────────────────────────────

def normalize_email_contact(text: str) -> str:
    """Только способ связи: allowlist доменов и уникальность НЕ применяются."""
    from email_validator import validate_email

    if len(text) > 254 or any(c.isspace() for c in text):
        raise _Bad("invalid_email")
    try:
        result = validate_email(text, check_deliverability=False)
    except ValueError:
        raise _Bad("invalid_email") from None
    return normalize_email(result.normalized)


# ── ссылки ────────────────────────────────────────────────────────────────────

def normalize_http_url(text: str) -> str:
    if any(c.isspace() for c in text):
        raise _Bad("invalid_url")
    match = _SCHEME.match(text)
    if match:
        if match.group(1).lower() not in ("http", "https"):
            raise _Bad("unsafe_url")
        candidate = text
    elif _DANGEROUS.match(text) or _ANY_SCHEME_NOT_PORT.match(text):
        raise _Bad("unsafe_url")
    elif text.startswith("//"):
        raise _Bad("invalid_url")
    else:
        candidate = "https://" + text
    try:
        parts = urlsplit(candidate)
        port = parts.port
    except ValueError:
        raise _Bad("invalid_url") from None
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        raise _Bad("unsafe_url")
    host = (parts.hostname or "").lower()
    if not host:
        raise _Bad("invalid_url")
    try:
        ascii_host = host.encode("idna").decode("ascii")
    except UnicodeError:
        raise _Bad("invalid_url") from None
    if not _HOST.match(ascii_host) or ascii_host.rsplit(".", 1)[-1].isdigit():
        raise _Bad("invalid_url")
    netloc = host + (f":{port}" if port else "")
    normalized = urlunsplit(
        (parts.scheme.lower(), netloc, parts.path, parts.query, parts.fragment)
    )
    if len(normalized) > catalog.VALUE_MAX:
        raise _Bad("too_long")
    return normalized


def _is_url_like(text: str) -> bool:
    return "/" in text or text.lower().startswith("www.") or bool(_SCHEME.match(text))


def validate_handle(text: str) -> str:
    if not _HANDLE.match(text):
        raise _Bad("invalid_value")
    return text


# ── значение по типу ──────────────────────────────────────────────────────────

def _normalize_value(item_type: str, service: Optional[str], raw) -> str:
    text = _clean(raw, catalog.VALUE_MAX)
    if not text:
        raise _Bad("required")
    if item_type == "phone":
        return normalize_phone(text)
    if item_type == "email":
        return normalize_email_contact(text)
    if item_type == "website":
        return normalize_http_url(text)
    if item_type in ("messenger", "social"):
        if service == catalog.OTHER_SERVICE:
            # Свободное название/идентификатор; явная схема — только http(s).
            return normalize_http_url(text) if _SCHEME.match(text) else text
        if item_type == "messenger" and _looks_like_phone(text):
            return normalize_phone(text)
        if _is_url_like(text):
            return normalize_http_url(text)
        return validate_handle(text)
    return text  # other: простой текст, никогда не ссылка


def _dup_key(item: dict) -> tuple:
    value = item["value"].casefold()
    if item["type"] in ("messenger", "social"):
        value = value.lstrip("@")
    return (item["type"], item["service"], value)


# ── список ────────────────────────────────────────────────────────────────────

def normalize_items(raw_items) -> list:
    """
    Нормализует список; при любых нарушениях бросает ContactsValidationError со
    ВСЕМИ ошибками (index/field/code). Порядок элементов сохраняется.
    """
    if not isinstance(raw_items, (list, tuple)):
        raise ContactsValidationError([FieldError(None, "items", "invalid_type")])
    if len(raw_items) > catalog.MAX_ITEMS:
        raise ContactsValidationError([FieldError(None, "items", "too_many")])

    errors: list = []
    result: list = []
    seen_ids: set = set()
    seen_keys: set = set()

    for index, raw in enumerate(raw_items):
        if not isinstance(raw, dict):
            errors.append(FieldError(index, None, "invalid_type"))
            continue
        before = len(errors)

        def bad(field: str, code: str, _index: int = index) -> None:
            errors.append(FieldError(_index, field, code))

        try:
            item_id = normalize_id(raw.get("id"))
            if item_id in seen_ids:
                bad("id", "duplicate_id")
            seen_ids.add(item_id)
        except _Bad as exc:
            item_id = None
            bad("id", exc.code)

        item_type = raw.get("type")
        if not isinstance(item_type, str) or item_type not in catalog.TYPE_CODES:
            bad("type", "invalid_type")
            continue

        service = raw.get("service")
        if isinstance(service, str):
            service = service.strip() or None
        kind = catalog.SERVICE_KIND.get(item_type)
        if kind:
            if service is None:
                bad("service", "service_required")
            elif service not in catalog.SERVICE_CODES[kind]:
                bad("service", "invalid_service")
        elif service is not None:
            bad("service", "service_not_allowed")
            service = None

        label = None
        try:
            label_text = raw.get("label")
            label = _clean(label_text, catalog.LABEL_MAX) if label_text is not None else ""
            label = label or None
        except _Bad as exc:
            bad("label", exc.code)
        else:
            needs_name = item_type == "other" or service == catalog.OTHER_SERVICE
            if needs_name and label is None:
                bad("label", "label_required")

        value = None
        try:
            value = _normalize_value(item_type, service, raw.get("value"))
        except _Bad as exc:
            bad("value", exc.code)

        if len(errors) == before and item_id is not None and value is not None:
            normalized = {
                "id": item_id, "type": item_type, "service": service,
                "value": value, "label": label,
            }
            key = _dup_key(normalized)
            if key in seen_keys:
                bad("value", "duplicate")
            else:
                seen_keys.add(key)
                result.append(normalized)

    if errors:
        raise ContactsValidationError(errors)
    return result
