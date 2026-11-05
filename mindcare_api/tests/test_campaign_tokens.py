"""Unit: ЧПУ-токен ссылки кампании (ADR-036, дополнение 2026-11-05)."""
import secrets

import pytest

from app.campaigns import tokens


@pytest.mark.parametrize("title, slug", [
    ("ИТО Экономфак 2026", "ito-ekonomfak-2026"),
    ("  ИТО — 1 курс, «Физтех»!  ", "ito-1-kurs-fiztekh"),
    ("Щука Жёлтая Юла Ящик", "shchuka-zheltaia-iula-iashchik"),
    ("Їжак Ґанок Єнот Ірис", "izhak-ganok-enot-iris"),
    ("ITO Test_Group", "ito-test-group"),
    ("!!! ???", tokens.FALLBACK_SLUG),
])
def test_slugify(title, slug):
    assert tokens.slugify(title) == slug


def test_slugify_long_title_cut_on_word_boundary():
    slug = tokens.slugify("Индивидуально типологический опросник для студентов "
                          "первого курса экономического факультета")
    assert len(slug) <= tokens.SLUG_MAX
    assert not slug.endswith("-")
    assert slug == "individualno-tipologicheskii-oprosnik-dlia"


def test_generate_token_format_and_randomness():
    a = tokens.generate_token("ИТО Экономфак 2026")
    b = tokens.generate_token("ИТО Экономфак 2026")
    assert a.startswith("ito-ekonomfak-2026-")
    assert len(a.rsplit("-", 1)[1]) == tokens.SUFFIX_LEN
    assert a != b
    assert tokens.is_well_formed(a)
    assert tokens.lookup_hash(a) == tokens.hash_token(a)


@pytest.mark.parametrize("title", ["x" * 300, "А" * 300, "!!!", "ИТО"])
def test_generated_token_always_well_formed(title):
    assert tokens.is_well_formed(tokens.generate_token(title))


def test_legacy_token_accepted():
    assert tokens.is_well_formed(secrets.token_urlsafe(32))


@pytest.mark.parametrize("token", [
    "", "ito", "ito-2026", "ito-2026-k7m2x",          # нет хвоста / короткий
    "ito-2026-k7m2x0",                                 # 0 нет в алфавите хвоста
    "Ito-2026-k7m2xq", "ito--2026-k7m2xq", "-ito-k7m2xq",
    "ито-k7m2xq", "ito-2026-k7m2xq/", "a" * 60 + "-k7m2xq",
])
def test_malformed_rejected(token):
    assert tokens.lookup_hash(token) is None
