"""Кодовое слово кампании (app/campaigns/access.py) — без БД."""
from datetime import datetime, timedelta, timezone

import pytest

from app.campaigns import access


def test_normalization_and_match():
    h = access.hash_code("  Весна   2026 ")
    assert h.startswith("$2")
    assert access.code_matches("весна 2026", h)
    assert access.code_matches("ВЕСНА 2026", h)
    assert not access.code_matches("весна 2025", h)
    assert not access.code_matches(None, h)
    assert not access.code_matches("ab", h)


def test_long_cyrillic_beyond_72_bytes():
    word = "ж" * 64                         # 128 байт UTF-8
    h = access.hash_code(word)
    assert access.code_matches(word, h)
    assert not access.code_matches("ж" * 63 + "з", h)   # отличие в конце


@pytest.mark.parametrize("code", ["abc", "x" * 65, "a\x01bcd"])
def test_invalid(code):
    with pytest.raises(access.AccessCodeInvalid):
        access.hash_code(code)


def test_state():
    now = datetime(2026, 11, 7, tzinfo=timezone.utc)
    day = timedelta(days=1)
    assert access.state("closed", None, None, now) == "closed"
    assert access.state("open", now + day, None, now) == "scheduled"
    assert access.state("open", None, now, now) == "expired"
    assert access.state("open", now - day, now + day, now) == "open"
