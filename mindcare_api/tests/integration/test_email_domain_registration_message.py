"""
Integration: понятный текст отказа по домену при обычной регистрации (init и
confirm) и инварианты вокруг него. Запускаются только через Stage 1 isolated
runner (integration conftest fail-fast'ит вне изолированной test-БД).

Домены в проверках — синтетические `integ-…` (их убирает фикстура
reset_email_domains), а список в сообщении сверяется с тем, что реально активно
в БД: ничего не зашито ни в коде, ни в ожиданиях.

Инварианты:
  - init и confirm отвечают 422 с ОДНИМ текстом; список — активные домены;
  - отключённые домены в тексте не перечисляются; нет активных — отдельный текст;
  - сравнение домена точное: поддомен и «похожий» домен автоматически не
    разрешены; регистр домена нормализуется;
  - домен отключён между init и confirm → тот же понятный отказ, OTP цел,
    пользователь не создан, после реактивации тот же код подтверждает;
  - аудит прежний: confirm → registration_failed/domain_not_allowed, ранний
    отказ init не пишет событий; введённый email не попадает в ответ и логи.
"""

import logging
import uuid as _uuid

import pytest

from app.db.models import AllowedEmailDomain, AuthLog, OtpVerification, User
from app.db.session import SessionLocal

PASSWORD = "SecurePass42!"
INIT = "/api/auth/register/init"
CONFIRM = "/api/auth/register/confirm"

_UNAVAILABLE = (
    "Регистрация по электронной почте сейчас недоступна. Обратитесь в поддержку."
)


def _message(*domains: str) -> str:
    listed = ", ".join(f"@{d}" for d in domains)
    return (
        "Для регистрации по электронной почте используйте адрес с одним из "
        f"разрешённых доменов: {listed}."
    )


def _domain(tag: str) -> str:
    # Префикс `integ-` обязателен: по нему reset_email_domains удаляет test-строки.
    return f"integ-{tag}-{_uuid.uuid4().hex[:8]}.ru"


def _email(domain: str) -> str:
    return f"integ_{_uuid.uuid4().hex[:12]}@{domain}"


def _set_active(*active: str, inactive: tuple[str, ...] = ()) -> None:
    """Активными остаются РОВНО `active` (новые строки); все остальные домены
    отключаются. Прежнее состояние возвращает фикстура reset_email_domains."""
    with SessionLocal() as db:
        db.query(AllowedEmailDomain).update(
            {"is_active": False}, synchronize_session=False,
        )
        for name in active:
            db.add(AllowedEmailDomain(domain=name, is_active=True))
        for name in inactive:
            db.add(AllowedEmailDomain(domain=name, is_active=False))
        db.commit()


def _set_domain_active(domain: str, active: bool) -> None:
    with SessionLocal() as db:
        db.query(AllowedEmailDomain).filter(
            AllowedEmailDomain.domain == domain,
        ).update({"is_active": active}, synchronize_session=False)
        db.commit()


def _otp_exists(email: str) -> bool:
    with SessionLocal() as db:
        return db.query(OtpVerification).filter(
            OtpVerification.email == email.strip().lower(),
        ).first() is not None


def _user_exists(email: str) -> bool:
    with SessionLocal() as db:
        return db.query(User).filter(
            User.email == email.strip().lower(),
        ).first() is not None


def _auth_rows(email: str, event: str) -> list:
    with SessionLocal() as db:
        return db.query(AuthLog).filter(
            AuthLog.user_email == email.strip().lower(), AuthLog.event == event,
        ).all()


def _init(client, email: str):
    return client.post(INIT, json={
        "name": "Test User", "email": email, "password": PASSWORD,
    })


def _confirm(client, email: str, code: str):
    return client.post(CONFIRM, json={"email": email, "code": code})


def _code(capture_emails: dict, email: str) -> str:
    target = email.lower()
    for key, codes in capture_emails.items():
        if key.lower() == target and codes:
            return codes[-1]
    raise KeyError(email)


# ── init: текст и список ─────────────────────────────────────────────────────

def test_init_lists_the_single_active_domain(
    client, capture_emails, reset_email_domains,
):
    allowed = _domain("a")
    _set_active(allowed)
    email = _email(_domain("other"))

    r = _init(client, email)

    assert r.status_code == 422
    assert r.json()["detail"] == _message(allowed)
    assert capture_emails == {}                  # письмо не отправлено
    assert _otp_exists(email) is False           # OTP не создан


def test_init_lists_several_active_domains_by_name_not_by_insertion(
    client, capture_emails, reset_email_domains,
):
    a, b, c = _domain("a"), _domain("b"), _domain("c")
    _set_active(c, a, b)                         # порядок вставки ≠ алфавитный
    email = _email(_domain("other"))

    r = _init(client, email)

    assert r.status_code == 422
    assert r.json()["detail"] == _message(a, b, c)
    assert capture_emails == {} and _otp_exists(email) is False


def test_init_without_active_domains_says_email_registration_unavailable(
    client, capture_emails, reset_email_domains,
):
    _set_active()                                # активных доменов нет
    email = _email(_domain("other"))

    r = _init(client, email)

    assert r.status_code == 422
    assert r.json()["detail"] == _UNAVAILABLE
    assert "@" not in r.json()["detail"]
    assert capture_emails == {} and _otp_exists(email) is False


def test_disabled_domains_are_not_listed(client, reset_email_domains):
    active, disabled = _domain("a"), _domain("off")
    _set_active(active, inactive=(disabled,))

    r = _init(client, _email(_domain("other")))

    assert r.json()["detail"] == _message(active)
    assert disabled not in r.text


# ── точное сравнение домена ──────────────────────────────────────────────────

@pytest.mark.parametrize("variant", [
    lambda d: f"mail.{d}",                       # поддомен разрешённого
    lambda d: f"x{d}",                           # «надстроенный» домен
    lambda d: d[: -len(".ru")] + ".com",         # тот же корень, другая зона
    lambda d: f"{d}.evil.example",               # разрешённый как префикс чужого
])
def test_subdomain_and_lookalikes_are_not_allowed_automatically(
    client, capture_emails, reset_email_domains, variant,
):
    allowed = _domain("a")
    _set_active(allowed)
    email = _email(variant(allowed))

    r = _init(client, email)

    assert r.status_code == 422, r.text
    assert r.json()["detail"] == _message(allowed)
    assert capture_emails == {} and _otp_exists(email) is False


def test_exact_domain_passes_and_case_is_normalized(
    client, capture_emails, reset_email_domains,
):
    allowed = _domain("a")
    _set_active(allowed)

    exact = _email(allowed)
    assert _init(client, exact).status_code == 200
    assert _otp_exists(exact) is True

    shouting = f"Integ_{_uuid.uuid4().hex[:12]}@{allowed.upper()}"
    assert _init(client, shouting).status_code == 200
    assert _otp_exists(shouting) is True


# ── confirm: домен отключили между init и confirm ────────────────────────────

def test_confirm_after_domain_disabled_gives_same_text_and_keeps_otp(
    client, capture_emails, reset_email_domains,
):
    a, b = _domain("a"), _domain("b")
    _set_active(a, b)
    email = _email(a)
    assert _init(client, email).status_code == 200
    code = _code(capture_emails, email)

    _set_domain_active(a, False)                 # админ отключил домен

    refusal = _confirm(client, email, code)
    assert refusal.status_code == 422, refusal.text
    assert refusal.json()["detail"] == _message(b)
    assert _otp_exists(email) is True            # OTP НЕ потреблён
    assert _user_exists(email) is False          # пользователь не создан

    # init на тот же адрес — тот же статус и тот же текст.
    again = _init(client, email)
    assert again.status_code == 422
    assert again.json()["detail"] == refusal.json()["detail"]
    assert _otp_exists(email) is True

    _set_domain_active(a, True)                  # домен вернули — тот же код годится
    ok = _confirm(client, email, code)
    assert ok.status_code == 201, ok.text
    assert _user_exists(email) is True


def test_confirm_with_no_active_domains_says_unavailable_and_keeps_otp(
    client, capture_emails, reset_email_domains,
):
    only = _domain("a")
    _set_active(only)
    email = _email(only)
    assert _init(client, email).status_code == 200
    code = _code(capture_emails, email)

    _set_active()                                # теперь активных нет вовсе

    refusal = _confirm(client, email, code)
    assert refusal.status_code == 422
    assert refusal.json()["detail"] == _UNAVAILABLE
    assert _otp_exists(email) is True and _user_exists(email) is False

    _set_domain_active(only, True)
    assert _confirm(client, email, code).status_code == 201


def test_wrong_code_is_reported_as_code_error_not_domain_error(
    client, capture_emails, reset_email_domains,
):
    a = _domain("a")
    _set_active(a)
    email = _email(a)
    assert _init(client, email).status_code == 200
    _set_domain_active(a, False)

    r = _confirm(client, email, "000000")

    # Код проверяется раньше домена: неверный код домен не раскрывает.
    assert r.status_code == 400
    assert "доменов" not in r.json()["detail"]


# ── аудит и приватность ──────────────────────────────────────────────────────

def test_audit_keeps_stable_code_and_init_refusal_is_not_audited(
    client, capture_emails, reset_email_domains,
):
    a, b = _domain("a"), _domain("b")
    _set_active(a, b)
    email = _email(a)
    assert _init(client, email).status_code == 200
    code = _code(capture_emails, email)
    _set_domain_active(a, False)

    assert _init(client, email).status_code == 422
    assert _auth_rows(email, "registration_failed") == []     # ранний отказ — без события

    assert _confirm(client, email, code).status_code == 422
    rows = _auth_rows(email, "registration_failed")
    assert len(rows) == 1
    assert rows[0].success is False
    assert rows[0].failure_reason == "domain_not_allowed"      # код, а не текст/домены
    assert a not in rows[0].failure_reason and b not in rows[0].failure_reason


def test_refusal_does_not_echo_or_log_the_entered_email(
    client, capture_emails, reset_email_domains, caplog,
):
    a, b = _domain("a"), _domain("b")
    _set_active(a, b)
    email = _email(a)
    local = email.split("@", 1)[0]
    assert _init(client, email).status_code == 200
    code = _code(capture_emails, email)
    _set_domain_active(a, False)

    caplog.set_level(logging.DEBUG, logger="app")
    responses = [_init(client, email), _confirm(client, email, code)]

    for r in responses:
        assert r.status_code == 422
        assert local not in r.text and email not in r.text
    app_records = [rec for rec in caplog.records if rec.name.startswith("app")]
    for rec in app_records:
        assert local not in rec.getMessage()
