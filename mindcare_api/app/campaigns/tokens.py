"""
Токен ссылки кампании (ADR-036, ЧПУ — дополнение 2026-11-05).

Токен — человекопонятный slug из названия кампании + случайный хвост:
«ИТО Экономфак 2026» → `ito-ekonomfak-2026-k7m2xq`. Читаемая часть —
только для людей; неугадываемость даёт хвост (6 символов из 31 → ~9·10⁸).
Ссылки старого формата (43 символа base64url) продолжают работать.

Сырой токен — только в ссылке и (для повторного показа супервизору) в
test_campaigns.link_token_enc (`enc:v1:`). Поиск — по SHA-256 hex
(link_token_hash). Токен не логировать и не класть в audit metadata/context.
"""
import hashlib
import re
import secrets
from typing import Optional

# Прежний формат: secrets.token_urlsafe(32) → 43 символа base64url без '='.
_LEGACY_RE = re.compile(r"^[A-Za-z0-9_-]{43}$")

SUFFIX_LEN = 6
SLUG_MAX = 48
FALLBACK_SLUG = "opros"
# Без 0/o и 1/l/i — хвост легко продиктовать и перепечатать.
_SUFFIX_ALPHABET = "23456789abcdefghjkmnpqrstuvwxyz"
_SLUG_RE = re.compile(
    rf"^[a-z0-9]+(?:-[a-z0-9]+)*-[{_SUFFIX_ALPHABET}]{{{SUFFIX_LEN}}}$")
_TOKEN_MAX = SLUG_MAX + 1 + SUFFIX_LEN

# Транслитерация — упрощённая ГОСТ Р 7.0.34-2014 (+ украинские буквы).
_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "i", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "iu", "я": "ia",
    "і": "i", "ї": "i", "є": "e", "ґ": "g",
}


def slugify(title: str) -> str:
    """Латинский slug из названия: a-z0-9 и одиночные дефисы, ≤ SLUG_MAX."""
    out = []
    for ch in (title or "").lower():
        if ch in _TRANSLIT:
            out.append(_TRANSLIT[ch])
        elif "a" <= ch <= "z" or "0" <= ch <= "9":
            out.append(ch)
        else:
            out.append("-")
    slug = re.sub(r"-+", "-", "".join(out)).strip("-")
    if len(slug) > SLUG_MAX:
        cut = slug[:SLUG_MAX]
        # Обрезать по границе слова, если она не слишком близко к началу.
        if "-" in cut and slug[SLUG_MAX] != "-":
            head = cut.rsplit("-", 1)[0]
            cut = head if len(head) >= SLUG_MAX // 2 else cut
        slug = cut.strip("-")
    return slug or FALLBACK_SLUG


def generate_token(title: str) -> str:
    suffix = "".join(secrets.choice(_SUFFIX_ALPHABET) for _ in range(SUFFIX_LEN))
    return f"{slugify(title)}-{suffix}"


def is_well_formed(token: str) -> bool:
    if not token or len(token) > _TOKEN_MAX:
        return False
    return bool(_SLUG_RE.fullmatch(token) or _LEGACY_RE.fullmatch(token))


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def lookup_hash(token: str) -> Optional[str]:
    """SHA-256 для поиска; None — токен заведомо неверного формата (→ 404)."""
    return hash_token(token) if is_well_formed(token) else None
