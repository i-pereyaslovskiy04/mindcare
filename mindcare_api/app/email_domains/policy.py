"""
Pure-функции нормализации и валидации почтового домена.

Без зависимостей на другие app-модули (кроме core.normalization). Используются
и при добавлении домена в allowlist (service/storage), и при проверке email в
in-tx helper (storage). Единый источник правил — списки доменов по модулям не
дублируются.
"""

import re

from app.core.normalization import normalize_email

# Exact-match ASCII hostname после нормализации:
#   - только a-z0-9 и дефис в метках, дефис не в начале/конце метки;
#   - минимум одна точка (есть TLD), TLD ≥ 2 букв;
#   - общая длина 1..253.
# IDN/punycode вне scope MVP — принимаем только ASCII.
_DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)([a-z0-9](-?[a-z0-9])*\.)+[a-z]{2,}$"
)


def normalize_domain(raw: str) -> str:
    """
    Каноническая форма домена: strip, lower, срезать один trailing dot.

    Возвращает пустую строку для пустого/невалидного по типу входа — вызывающий
    сам решает, ошибка это или нет (валидацию делает is_valid_domain).
    """
    if not raw:
        return ""
    d = raw.strip().lower()
    if d.endswith("."):
        d = d[:-1]
    return d


def is_valid_domain(d: str) -> bool:
    """
    True только для корректного exact-match ASCII hostname (см. _DOMAIN_RE).

    Отвергает `@`, пробелы, URL-схему (`://`), порт (`:`), путь (`/`),
    wildcard (`*`), пустые метки, метку длиннее 63, отсутствие точки и всё,
    что не проходит regex. Ожидает уже нормализованный вход.
    """
    if not d or len(d) > 253:
        return False
    # Явно отсекаем очевидно недопустимые символы до regex (быстрее и понятнее
    # в диагностике): @ пробел : / * и любые оставшиеся не-ascii.
    if any(ch in d for ch in ("@", "/", ":", "*", " ", "\t")):
        return False
    if any(len(label) > 63 for label in d.split(".")):
        return False
    return bool(_DOMAIN_RE.match(d))


def extract_domain(email: str) -> str:
    """
    Нормализованный домен из email. Пустой при отсутствии/битом local@domain.
    """
    if not email:
        return ""
    normalized = normalize_email(email)
    if "@" not in normalized:
        return ""
    return normalized.rpartition("@")[2]
