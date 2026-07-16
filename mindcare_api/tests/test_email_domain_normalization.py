"""
Unit-тесты pure-функций нормализации/валидации домена
(app.email_domains.policy). Без БД.
"""

import pytest

from app.email_domains.policy import (
    extract_domain, is_valid_domain, normalize_domain,
)


# ─── normalize_domain ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("donnu.ru", "donnu.ru"),
    ("  DonNU.ru  ", "donnu.ru"),
    ("MAIL.RU", "mail.ru"),
    ("ya.ru.", "ya.ru"),            # trailing dot срезается (один)
    ("  Ya.RU. ", "ya.ru"),
    ("", ""),
    (None, ""),
])
def test_normalize_domain(raw, expected):
    assert normalize_domain(raw) == expected


# ─── is_valid_domain (ожидает уже нормализованный вход) ───────────────────────

@pytest.mark.parametrize("domain", [
    "donnu.ru",
    "ya.ru",
    "vk.com",
    "sub.example.co.uk",
    "a-b.example.ru",
    "x1.y2.zz",
])
def test_is_valid_domain_true(domain):
    assert is_valid_domain(domain) is True


@pytest.mark.parametrize("domain", [
    "",
    "localhost",              # нет точки / TLD
    "user@donnu.ru",          # @
    "http://donnu.ru",        # схема (://, /)
    "donnu.ru/path",          # путь
    "donnu.ru:8080",          # порт
    "*.donnu.ru",             # wildcard
    "-bad.ru",                # метка начинается с дефиса
    "bad-.ru",                # метка заканчивается дефисом
    "x..ru",                  # пустая метка
    "x.r",                    # TLD < 2
    "тест.рф",                # не-ascii (IDN вне scope)
    "space domain.ru",        # пробел
    "a." + "b" * 64 + ".ru",  # метка > 63
])
def test_is_valid_domain_false(domain):
    assert is_valid_domain(domain) is False


def test_is_valid_domain_rejects_over_253():
    long_domain = ".".join(["abc"] * 80) + ".ru"  # > 253 символов
    assert len(long_domain) > 253
    assert is_valid_domain(long_domain) is False


# ─── extract_domain ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("email,expected", [
    ("user@donnu.ru", "donnu.ru"),
    ("  User@Ya.RU ", "ya.ru"),          # trim + lower через normalize_email
    ("MiXeD@Mail.Ru", "mail.ru"),
    ("", ""),
    ("no-at-symbol", ""),                # нет @ → пусто
    ("user@", ""),                       # пустой домен
])
def test_extract_domain(email, expected):
    assert extract_domain(email) == expected


def test_normalize_then_validate_mixed_case_domain():
    """mixed-case домен нормализуется и проходит валидацию."""
    assert is_valid_domain(normalize_domain("YaNdEx.RU")) is True
