"""
ADR-032 — валидаторы контактов (чистые функции, без БД).

Ошибки — только коды (index/field/code); ни одно значение контакта не попадает
в ошибки. Каталог содержит все прежние сервисы старой формы настроек.
"""
import uuid

import pytest

from app.user_contacts import catalog, validators
from app.user_contacts.errors import ContactsValidationError


def _item(**overrides):
    base = {"id": str(uuid.uuid4()), "type": "phone", "service": None,
            "value": "+79491234567", "label": None}
    base.update(overrides)
    return base


def _errors(items):
    with pytest.raises(ContactsValidationError) as info:
        validators.normalize_items(items)
    return [e.as_dict() for e in info.value.errors]


def _one(**overrides):
    return validators.normalize_items([_item(**overrides)])[0]


# ── каталог ───────────────────────────────────────────────────────────────────

def test_catalog_keeps_every_legacy_service_and_adds_other_variants():
    # Прежний список: Telegram, Instagram, LinkedIn, VK, Facebook, X (Twitter), «Сайт».
    assert "telegram" in catalog.SERVICE_CODES["messenger"]
    for code in ("instagram", "linkedin", "vk", "facebook", "x"):
        assert code in catalog.SERVICE_CODES["social"]
    assert "website" in catalog.TYPE_CODES
    labels = {c["label"] for c in catalog.catalog_dto()["services"]["social"]}
    assert {"VK", "Instagram", "Facebook", "LinkedIn", "X (Twitter)"} <= labels
    # «Другой сервис» и тип «Другое» сохраняются.
    for kind in ("messenger", "social"):
        assert catalog.OTHER_SERVICE in catalog.SERVICE_CODES[kind]
    assert "other" in catalog.TYPE_CODES
    assert (catalog.MAX_ITEMS, catalog.LABEL_MAX, catalog.VALUE_MAX) == (10, 80, 500)


# ── id ────────────────────────────────────────────────────────────────────────

def test_id_is_required_and_never_generated():
    item = _item()
    del item["id"]
    assert _errors([item]) == [{"index": 0, "field": "id", "code": "required"}]
    assert _errors([_item(id="  ")])[0]["code"] == "required"


@pytest.mark.parametrize("bad", ["not-a-uuid", "123", "00000000-0000-0000-0000-000000000000", 7])
def test_invalid_ids(bad):
    assert _errors([_item(id=bad)]) == [{"index": 0, "field": "id", "code": "invalid_id"}]


def test_id_is_canonicalized_and_duplicates_rejected():
    raw = str(uuid.uuid4())
    assert _one(id=raw.upper())["id"] == raw
    errors = _errors([_item(id=raw), _item(id=raw.upper(), value="+79490000000")])
    assert errors == [{"index": 1, "field": "id", "code": "duplicate_id"}]


# ── телефон ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("+7 (949) 123-45-67", "+79491234567"),
    ("8 949 123 45 67", "+79491234567"),
    ("79491234567", "+79491234567"),
    ("949-123-45-67", "+79491234567"),
    ("+380 50 123 45 67", "+380501234567"),
    ("+1234567", "+1234567"),
    ("380501234567", "+380501234567"),
])
def test_phone_is_normalized(raw, expected):
    assert _one(value=raw)["value"] == expected


@pytest.mark.parametrize("raw", ["12", "1234567", "+12", "abc", "+7 (949) 12", "+1234567890123456", "7-9-4"])
def test_invalid_phones(raw):
    assert _errors([_item(value=raw)]) == [{"index": 0, "field": "value", "code": "invalid_phone"}]


# ── email ─────────────────────────────────────────────────────────────────────

def test_email_is_contact_only_without_domain_allowlist():
    item = _one(type="email", value="  Person@Some-Domain.RU ")
    assert item["value"] == "person@some-domain.ru"        # любой домен, нижний регистр
    assert _one(type="email", value="a@example.org")["value"] == "a@example.org"


@pytest.mark.parametrize("raw", ["no-at", "a@", "@b.ru", "a b@c.ru", "a@@b.ru", "x" * 260 + "@b.ru"])
def test_invalid_emails(raw):
    assert _errors([_item(type="email", value=raw)])[0]["code"] == "invalid_email"


# ── сайты и ссылки ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("https://Example.com/Path?x=1#f", "https://example.com/Path?x=1#f"),
    ("example.com", "https://example.com"),
    ("http://sub.example.ru:8080/a", "http://sub.example.ru:8080/a"),
    ("www.example.com/x", "https://www.example.com/x"),
])
def test_website_is_http_only_and_normalized(raw, expected):
    assert _one(type="website", value=raw)["value"] == expected


@pytest.mark.parametrize("raw,code", [
    ("javascript:alert(1)", "unsafe_url"),
    ("JaVaScRiPt:alert(1)", "unsafe_url"),
    ("data:text/html;base64,AAAA", "unsafe_url"),
    ("file:///etc/passwd", "unsafe_url"),
    ("ftp://example.com", "unsafe_url"),
    ("mailto:a@b.ru", "unsafe_url"),
    ("tel:+79491234567", "unsafe_url"),
    ("https://user:pass@example.com", "unsafe_url"),
    ("https://user@example.com", "unsafe_url"),
    ("//example.com", "invalid_url"),
    ("http://", "invalid_url"),
    ("https://localhost", "invalid_url"),
    ("https://192.168.0.1", "invalid_url"),
    ("https://exa mple.com", "invalid_url"),
    ("not a url", "invalid_url"),
    ("https://example.com:99999", "invalid_url"),
])
def test_unsafe_or_invalid_urls(raw, code):
    assert _errors([_item(type="website", value=raw)]) == [
        {"index": 0, "field": "value", "code": code}
    ]


def test_url_length_limit():
    assert _errors([_item(type="website", value="https://e.com/" + "a" * 500)])[0]["code"] == "too_long"


# ── мессенджеры и соцсети ─────────────────────────────────────────────────────

def test_messenger_accepts_handle_phone_or_link():
    assert _one(type="messenger", service="telegram", value="@name_1")["value"] == "@name_1"
    assert _one(type="messenger", service="whatsapp", value="8 949 123 45 67")["value"] == "+79491234567"
    assert _one(type="messenger", service="telegram", value="t.me/name")["value"] == "https://t.me/name"


def test_social_accepts_handle_or_link_but_not_phone():
    assert _one(type="social", service="vk", value="ivan.petrov")["value"] == "ivan.petrov"
    assert _one(type="social", service="vk", value="https://vk.com/id1")["value"] == "https://vk.com/id1"
    assert _errors([_item(type="social", service="vk", value="+7 949 123 45 67")])[0]["code"] == "invalid_value"


def test_handle_must_be_valid():
    for bad in ("a", "has space", "@", "bad!char"):
        assert _errors([_item(type="messenger", service="telegram", value=bad)])[0]["code"] in (
            "invalid_value", "invalid_url")


def test_service_is_required_for_messenger_and_social_and_forbidden_elsewhere():
    assert _errors([_item(type="messenger", service=None, value="@name")]) == [
        {"index": 0, "field": "service", "code": "service_required"}]
    assert _errors([_item(type="social", service="telegram", value="@name")]) == [
        {"index": 0, "field": "service", "code": "invalid_service"}]
    assert _errors([_item(type="phone", service="telegram")]) == [
        {"index": 0, "field": "service", "code": "service_not_allowed"}]


def test_other_service_and_other_type_require_a_name():
    assert _errors([_item(type="messenger", service="other", value="любой ник")]) == [
        {"index": 0, "field": "label", "code": "label_required"}]
    assert _one(type="messenger", service="other", value="любой ник", label="Сигнал-чат")["label"] == "Сигнал-чат"
    assert _errors([_item(type="other", value="любое значение")]) == [
        {"index": 0, "field": "label", "code": "label_required"}]
    assert _errors([_item(type="other", value="x", label="   ")])[0]["code"] == "label_required"


def test_other_type_is_plain_text_never_normalized_to_a_link():
    item = _one(type="other", value="javascript:alert(1)", label="Странный способ")
    assert item["value"] == "javascript:alert(1)"           # текст; href на клиенте не строится


# ── общие правила ─────────────────────────────────────────────────────────────

def test_empty_and_whitespace_values_are_rejected():
    for value in ("", "   ", "\t"):
        assert _errors([_item(value=value)]) == [{"index": 0, "field": "value", "code": "required"}]


def test_limits_and_characters():
    assert _errors([_item(type="other", value="x" * 501, label="n")])[0]["code"] == "too_long"
    assert _errors([_item(type="other", value="x", label="y" * 81)]) == [
        {"index": 0, "field": "label", "code": "too_long"}]
    assert _one(type="other", value="x" * 500, label="y" * 80)
    for bad in ("a\x00b", "a\nb", "a‮b"):
        assert _errors([_item(type="other", value=bad, label="n")])[0]["code"] == "invalid_characters"


def test_at_most_ten_items():
    items = [_item(value=f"+7949000{i:04d}") for i in range(11)]
    assert _errors(items) == [{"index": None, "field": "items", "code": "too_many"}]
    assert len(validators.normalize_items(items[:10])) == 10


def test_duplicates_by_normalized_value():
    a = _item(value="+7 (949) 123-45-67")
    b = _item(value="89491234567")
    assert _errors([a, b]) == [{"index": 1, "field": "value", "code": "duplicate"}]
    handles = [_item(type="messenger", service="telegram", value="@Name"),
               _item(type="messenger", service="telegram", value="name")]
    assert _errors(handles) == [{"index": 1, "field": "value", "code": "duplicate"}]
    # тот же ник в разных сервисах — разные контакты
    ok = [_item(type="messenger", service="telegram", value="name"),
          _item(type="messenger", service="viber", value="name")]
    assert len(validators.normalize_items(ok)) == 2


def test_all_errors_are_collected_and_contain_no_values():
    secret = "secret.person@private-mail.example"
    items = [
        _item(type="website", value="javascript:" + secret),
        _item(type="phone", value="12"),
        _item(type="bogus", value=secret),
        _item(type="email", value=secret + "!"),
    ]
    with pytest.raises(ContactsValidationError) as info:
        validators.normalize_items(items)
    dumped = repr([e.as_dict() for e in info.value.errors]) + str(info.value) + repr(info.value.args)
    assert secret not in dumped and "private-mail" not in dumped
    assert len(info.value.errors) == 4


def test_label_is_trimmed_and_nfc_normalized():
    item = _one(label="  Рабочий  ")
    assert item["label"] == "Рабочий"
    assert _one(label="")["label"] is None


def test_canonical_item_has_exactly_the_five_keys():
    assert set(_one()) == {"id", "type", "service", "value", "label"}
