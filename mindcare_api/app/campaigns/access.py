"""
Сроки и кодовое слово ссылки кампании (ТЗ редактора методик, этап 2, §6).

Кодовое слово:
  - нормализация — пробелы схлопываются, регистр не важен (casefold): его
    диктуют в аудитории, «Весна 2026» и «весна  2026» — одно слово;
  - длина после нормализации 4–64, без управляющих символов;
  - хранится только bcrypt (как пароли); открытый текст не хранится, не
    логируется и не попадает в аудит. Проверка — bcrypt.checkpw (постоянное
    время сравнения внутри bcrypt);
  - в bcrypt подаётся SHA-256 hex нормализованного слова (64 ASCII-байта):
    bcrypt принимает не больше 72 байт, а 64 кириллических символа — 128
    байт (bcrypt 5 бросает ValueError, 4.x молча обрезал бы хвост).

Сроки: время сервера (UTC в БД). До opens_at анкета не открывается, начиная с
closes_at ссылка ведёт себя как закрытая кампания.
"""
import hashlib
import re
from datetime import datetime, timezone
from typing import Optional

import bcrypt

CODE_MIN = 4
CODE_MAX = 64
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


class AccessCodeInvalid(ValueError):
    """Кодовое слово не прошло правила (длина, символы) → 422."""


def normalize_code(code: str) -> str:
    if not isinstance(code, str) or _CONTROL_RE.search(code):
        raise AccessCodeInvalid("недопустимые символы")
    cleaned = " ".join(code.split()).casefold()
    if not CODE_MIN <= len(cleaned) <= CODE_MAX:
        raise AccessCodeInvalid(f"от {CODE_MIN} до {CODE_MAX} символов")
    return cleaned


def _prehash(normalized: str) -> bytes:
    return hashlib.sha256(normalized.encode()).hexdigest().encode()


def hash_code(code: str) -> str:
    """Хеш нормализованного слова. Вызывать ВНЕ транзакции (bcrypt медленный)."""
    return bcrypt.hashpw(_prehash(normalize_code(code)), bcrypt.gensalt()).decode()


def code_matches(code: Optional[str], hashed: str) -> bool:
    try:
        normalized = normalize_code(code or "")
    except AccessCodeInvalid:
        return False
    return bcrypt.checkpw(_prehash(normalized), hashed.encode())


def now() -> datetime:
    return datetime.now(timezone.utc)


def not_started(opens_at: Optional[datetime], at: Optional[datetime] = None) -> bool:
    return opens_at is not None and (at or now()) < opens_at


def expired(closes_at: Optional[datetime], at: Optional[datetime] = None) -> bool:
    return closes_at is not None and (at or now()) >= closes_at


def state(status: str, opens_at: Optional[datetime], closes_at: Optional[datetime],
          at: Optional[datetime] = None) -> str:
    """Что видит участник по ссылке: closed | scheduled | expired | open."""
    if status != "open":
        return "closed"
    if not_started(opens_at, at):
        return "scheduled"
    if expired(closes_at, at):
        return "expired"
    return "open"
