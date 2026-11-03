"""
Содержательные правила заданий (ADR-033) и курсор keyset-пагинации.

Ошибки — только коды без значений (FieldError). Срок (due_date) не ограничен
диапазоном: согласованный контракт — «необязательный срок»; форму даты
проверяет pydantic (тип date или null).
"""
import base64
import binascii
import unicodedata
from datetime import datetime
from typing import Optional
from uuid import UUID

from app.assignments.errors import AssignmentValidationError, FieldError

TEXT_MAX = 4000

# Разрешённые управляющие символы в тексте задания: перевод строки и табуляция.
_ALLOWED_CONTROL = frozenset({"\n", "\t"})


def normalize_text(raw: str) -> str:
    """trim, \r\n → \n; пусто → required; > TEXT_MAX → too_long; управляющие → invalid_characters."""
    text = (raw or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise AssignmentValidationError([FieldError("text", "required")])
    if len(text) > TEXT_MAX:
        raise AssignmentValidationError([FieldError("text", "too_long")])
    for ch in text:
        if ch in _ALLOWED_CONTROL:
            continue
        if unicodedata.category(ch) in ("Cc", "Cs"):
            raise AssignmentValidationError([FieldError("text", "invalid_characters")])
    return text


# ── курсор keyset ────────────────────────────────────────────────────────────
# Непрозрачная строка base64url("<created_at ISO>|<uuid>") последнего элемента
# полученной страницы. Сервер НЕ ищет элемент-курсор: сравнивает
# (created_at, uuid) < курсора в текущей выборке, поэтому курсор действителен,
# даже если его элемент уже ушёл из выборки (выполнен/отменён/связь закрыта).

def encode_cursor(created_at: datetime, uuid_value) -> str:
    raw = f"{created_at.isoformat()}|{uuid_value}".encode("ascii")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(cursor: Optional[str]) -> Optional[tuple]:
    """None → первая страница; битый курсор → invalid_cursor (без значения)."""
    if cursor is None:
        return None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii")).decode("ascii")
        stamp, uuid_text = raw.split("|", 1)
        created_at = datetime.fromisoformat(stamp)
        if created_at.tzinfo is None:
            raise ValueError("naive")
        return created_at, UUID(uuid_text)
    except (ValueError, UnicodeError, binascii.Error):
        raise AssignmentValidationError([FieldError("before", "invalid_cursor")]) from None
