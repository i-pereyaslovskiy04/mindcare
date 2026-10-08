"""
Текст отказа по домену при ОБЫЧНОЙ регистрации (init и confirm) — без БД.

Домены в тексте берутся только из списка активных доменов на момент отказа
(`EmailDomainNotAllowedError.allowed_domains`), в коде их нет; init и confirm
строят текст одной функцией, поэтому не расходятся. Текст говорит про
регистрацию «по электронной почте»: вход через Яндекс allowlist не применяет
(ADR-027 п. 5), поэтому «любая регистрация» не утверждается.
"""

import pytest

from app.auth import service, storage
from app.email_domains import service as domain_service
from app.email_domains.errors import EmailDomainNotAllowedError

# Синтетические домены: реальные имена в проверках не используются.
DOMAIN_LISTS = [
    (),                                          # активных доменов нет
    ("a.example",),                              # один
    ("a.example", "b.example", "c.example"),     # несколько
]


# ── registration_domain_message ───────────────────────────────────────────────

def test_message_for_one_domain():
    assert domain_service.registration_domain_message(["a.example"]) == (
        "Для регистрации по электронной почте используйте адрес с одним из "
        "разрешённых доменов: @a.example."
    )


def test_message_for_several_domains_keeps_given_order():
    message = domain_service.registration_domain_message(
        ("b.example", "a.example", "c.example")
    )
    assert message == (
        "Для регистрации по электронной почте используйте адрес с одним из "
        "разрешённых доменов: @b.example, @a.example, @c.example."
    )


def test_message_when_no_active_domains():
    message = domain_service.registration_domain_message(())
    assert message == (
        "Регистрация по электронной почте сейчас недоступна. "
        "Обратитесь в поддержку."
    )
    assert "@" not in message           # нечего перечислять


@pytest.mark.parametrize("domains", DOMAIN_LISTS)
def test_message_speaks_about_email_registration_only(domains):
    message = domain_service.registration_domain_message(domains)
    assert "по электронной почте" in message
    # Яндекс allowlist не применяет: нельзя утверждать, что правило для любой
    # регистрации.
    assert "Регистрация доступна только" not in message


@pytest.mark.parametrize("hostile", ["{0}.test", "%s.test", "{domains}.test"])
def test_domains_are_data_not_template(hostile):
    message = domain_service.registration_domain_message([hostile])
    assert message.endswith(f"@{hostile}.")


# ── EmailDomainNotAllowedError ────────────────────────────────────────────────

def test_exception_payload_defaults_and_compatibility():
    bare = EmailDomainNotAllowedError("x")
    assert bare.allowed_domains == ()
    assert str(bare) == "x"

    exc = EmailDomainNotAllowedError("x", allowed_domains=["a.example", "b.example"])
    assert exc.allowed_domains == ("a.example", "b.example")      # неизменяемый кортеж
    assert str(exc) == "x"
    # Не ValueError: creation-пути с `except ValueError` его не перехватывают.
    assert not isinstance(exc, ValueError)


# ── ранняя проверка: точное сравнение и список в исключении ───────────────────

def test_early_check_compares_exact_normalized_domain(monkeypatch):
    seen = []
    monkeypatch.setattr(
        domain_service.storage, "is_domain_active",
        lambda domain: seen.append(domain) or domain == "a.example",
    )
    monkeypatch.setattr(
        domain_service.storage, "list_active_domain_names", lambda: ["a.example"],
    )

    domain_service.assert_email_domain_allowed("User@A.Example")   # нормализация
    with pytest.raises(EmailDomainNotAllowedError):
        domain_service.assert_email_domain_allowed("u@mail.a.example")  # поддомен
    assert seen == ["a.example", "mail.a.example"]    # сравнивается весь домен


def test_early_refusal_carries_active_domains_and_allowed_path_does_not_query_them(
    monkeypatch,
):
    queried = []
    monkeypatch.setattr(
        domain_service.storage, "is_domain_active", lambda domain: domain == "ok.example",
    )
    monkeypatch.setattr(
        domain_service.storage, "list_active_domain_names",
        lambda: queried.append(True) or ["b.example", "ok.example"],
    )

    domain_service.assert_email_domain_allowed("u@ok.example")
    assert queried == []                               # разрешён — список не читаем

    with pytest.raises(EmailDomainNotAllowedError) as refusal:
        domain_service.assert_email_domain_allowed("u@other.example")
    assert refusal.value.allowed_domains == ("b.example", "ok.example")
    assert queried == [True]


@pytest.mark.parametrize("email", ["", "no-at-symbol", "user@"])
def test_email_without_domain_is_refused_with_list(monkeypatch, email):
    monkeypatch.setattr(
        domain_service.storage, "is_domain_active",
        lambda domain: pytest.fail("is_domain_active не должен вызываться без домена"),
    )
    monkeypatch.setattr(
        domain_service.storage, "list_active_domain_names", lambda: ["a.example"],
    )
    with pytest.raises(EmailDomainNotAllowedError) as refusal:
        domain_service.assert_email_domain_allowed(email)
    assert refusal.value.allowed_domains == ("a.example",)


def test_public_list_delegates_to_storage_names_only(monkeypatch):
    monkeypatch.setattr(
        domain_service.storage, "list_active_domain_names",
        lambda: ["a.example", "b.example"],
    )
    assert domain_service.list_public_domains() == ["a.example", "b.example"]


# ── init и confirm: один статус, один текст ───────────────────────────────────

@pytest.fixture
def nothing_after_domain_refusal(monkeypatch):
    """Шаги ПОСЛЕ отказа по домену выполняться не должны: ни проверка email,
    ни OTP, ни письмо, ни post-registration действия."""
    def _boom(*args, **kwargs):
        raise AssertionError("шаг после отказа по домену выполнен")

    monkeypatch.setattr(storage, "email_exists_any", _boom)
    monkeypatch.setattr("app.auth.otp_service.create_or_update_otp", _boom)
    monkeypatch.setattr("app.services.email_service.send_registration_otp", _boom)
    monkeypatch.setattr(service, "run_post_registration_actions", _boom)


@pytest.mark.parametrize("domains", DOMAIN_LISTS)
def test_init_and_confirm_refuse_with_identical_text(
    monkeypatch, nothing_after_domain_refusal, domains,
):
    exc = EmailDomainNotAllowedError("внутренний текст", allowed_domains=domains)

    def _refuse_early(_email):
        raise exc

    def _refuse_in_tx(**_kwargs):
        raise exc

    monkeypatch.setattr(
        "app.email_domains.service.assert_email_domain_allowed", _refuse_early,
    )
    monkeypatch.setattr(storage, "register_confirm_atomic", _refuse_in_tx)

    with pytest.raises(service.AuthError) as init_refusal:
        service.register_init(
            name="Тест Тест", email="user@x.test", password="password123",
        )
    with pytest.raises(service.AuthError) as confirm_refusal:
        service.register_confirm(email="user@x.test", code="123456")

    expected = domain_service.registration_domain_message(domains)
    assert init_refusal.value.message == expected
    assert confirm_refusal.value.message == expected
    assert init_refusal.value.status_code == confirm_refusal.value.status_code == 422
    # Аудит как прежде: ранний отказ init не аудируется, confirm → registration_failed.
    assert init_refusal.value.audit_code is None
    assert confirm_refusal.value.audit_code == "domain_not_allowed"
    # Внутренний текст исключения и введённый email клиенту не уходят.
    for refusal in (init_refusal.value, confirm_refusal.value):
        assert "внутренний текст" not in refusal.message
        assert "user@x.test" not in refusal.message
        assert "user" not in refusal.message       # локальная часть введённого email
