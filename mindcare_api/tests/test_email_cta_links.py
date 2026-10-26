"""
Кнопки перехода в сервис в письмах и FRONTEND_PUBLIC_URL (unit, без БД и SMTP).

- Регистрация по email и паролю: «Продолжить регистрацию →» → {FRONTEND_PUBLIC_URL}
  /register/confirm#r=<reference ЭТОГО выпуска>, в HTML и в plain-text.
- Регистрация через Яндекс/VK: без этой ссылки и без reference (её
  подтверждение требует ticket из памяти вкладки).
- Письма с временным паролем: «Войти в сервис →» → {FRONTEND_PUBLIC_URL}/login.
- Ссылка компактная (текст ACCENT с подчёркиванием), не кнопка на всю ширину.
- В ссылках нет email, кода и пароля; база нормализуется без «//».
"""

import inspect
import re
from unittest.mock import patch

import pytest

from app.core import public_urls
from app.core.public_urls import (
    LOGIN_PATH,
    REGISTER_CONFIRM_PATH,
    frontend_url,
    normalize_frontend_base,
)
from app.services import email_service

EMAIL = "student.name@donnu.ru"
CODE = "482915"
PASSWORD = "Tmp-Pass-7391"
PROD = "https://mindcare.donnu.ru"


def _sent(fn, *args, base=PROD, **kwargs):
    with patch.object(public_urls.settings, "FRONTEND_PUBLIC_URL", base), \
         patch.object(email_service, "send_email") as send:
        fn(*args, **kwargs)
    kw = send.call_args.kwargs
    return kw["html"], kw["body"]


def _hrefs(html):
    return re.findall(r'href="([^"]+)"', html)


# ─── FRONTEND_PUBLIC_URL ─────────────────────────────────────────────────────

class TestFrontendUrl:
    @pytest.mark.parametrize("base", [
        "https://mindcare.donnu.ru",
        "https://mindcare.donnu.ru/",
        "https://mindcare.donnu.ru//",
        "  https://mindcare.donnu.ru/  ",
    ])
    def test_trailing_slashes_normalized(self, base):
        url = frontend_url("/register/confirm", base=base)
        assert url == "https://mindcare.donnu.ru/register/confirm"
        assert "//" not in url.split("://", 1)[1]

    def test_path_without_leading_slash(self):
        assert frontend_url("login", base=PROD) == "https://mindcare.donnu.ru/login"

    def test_base_with_subpath_kept(self):
        assert frontend_url(LOGIN_PATH, base="https://host.ru/app/") == "https://host.ru/app/login"

    def test_local_default(self):
        assert frontend_url(REGISTER_CONFIRM_PATH, base="http://localhost:3000") == (
            "http://localhost:3000/register/confirm"
        )

    @pytest.mark.parametrize("base", [
        "", "   ", "mindcare.donnu.ru", "ftp://mindcare.donnu.ru",
        "javascript:alert(1)", "https://user:pw@mindcare.donnu.ru",
        "https://mindcare.donnu.ru/?x=1", "https://mindcare.donnu.ru/#a", "https://",
    ])
    def test_invalid_base_gives_no_link(self, base):
        assert normalize_frontend_base(base) is None
        assert frontend_url(LOGIN_PATH, base=base) is None

    def test_none_base_is_not_a_url(self):
        assert normalize_frontend_base(None) is None

    def test_uses_settings_by_default(self):
        with patch.object(public_urls.settings, "FRONTEND_PUBLIC_URL", PROD + "/"):
            assert frontend_url(LOGIN_PATH) == PROD + "/login"

    def test_settings_default_is_local_frontend(self):
        from app.core.config import Settings
        assert Settings.model_fields["FRONTEND_PUBLIC_URL"].default == "http://localhost:3000"


# ─── Регистрация по email и паролю ───────────────────────────────────────────

REF = "8a62d590-71a1-4b17-90f7-4a5ff0c9d782"
CONTINUE_URL = f"{PROD}/register/confirm#r={REF}"


def _reg(**kwargs):
    kwargs.setdefault("registration_reference", REF)
    return _sent(email_service.send_registration_otp, EMAIL, CODE, **kwargs)


class TestRegistrationContinuePath:
    def test_fragment_with_canonical_uuid(self):
        assert public_urls.registration_continue_path(REF) == f"/register/confirm#r={REF}"
        assert public_urls.registration_continue_path(REF.upper()) == f"/register/confirm#r={REF}"

    @pytest.mark.parametrize("bad", ["", "not-a-uuid", "../login", None, f"{REF}&x=1"])
    def test_non_uuid_gives_no_path(self, bad):
        assert public_urls.registration_continue_path(bad) is None


class TestRegistrationContinueLink:
    def test_html_link_has_fragment_reference(self):
        html, _ = _reg()
        assert _hrefs(html) == [CONTINUE_URL]
        assert "Продолжить регистрацию \u2192" in html

    def test_plain_has_full_url(self):
        _, plain = _reg()
        assert "Продолжить регистрацию \u2192\n" + CONTINUE_URL in plain
        assert "Откройте страницу и введите код из этого письма." in plain

    def test_reference_of_this_issue_goes_to_this_letter(self):
        other = "0f8f2f44-2a8e-4c1e-9d55-0c3b1d1e2a77"
        html_a, plain_a = _reg(registration_reference=REF)
        html_b, plain_b = _reg(registration_reference=other)
        assert _hrefs(html_a) == [CONTINUE_URL]
        assert _hrefs(html_b) == [f"{PROD}/register/confirm#r={other}"]
        assert other not in html_a + plain_a and REF not in html_b + plain_b

    def test_local_base(self):
        html, plain = _reg(base="http://localhost:3000")
        assert _hrefs(html) == [f"http://localhost:3000/register/confirm#r={REF}"]
        assert f"http://localhost:3000/register/confirm#r={REF}" in plain

    def test_no_email_code_or_password_in_link(self):
        html, plain = _reg()
        for href in _hrefs(html):
            assert EMAIL not in href and CODE not in href and PASSWORD not in href
            assert "?" not in href                      # reference - только во fragment
            assert href.split("#", 1)[1] == f"r={REF}"
        url_line = next(line for line in plain.splitlines() if "http" in line)
        assert EMAIL not in url_line and CODE not in url_line
        assert "?" not in url_line

    def test_code_still_shown_in_letter(self):
        html, plain = _reg()
        assert CODE in html and f"Ваш код: {CODE}" in plain

    def test_without_reference_no_link(self):
        html, plain = _sent(email_service.send_registration_otp, EMAIL, CODE)
        assert "Продолжить регистрацию" not in html + plain
        assert _hrefs(html) == []

    def test_invalid_reference_no_link(self):
        html, plain = _reg(registration_reference="../login")
        assert _hrefs(html) == []
        assert "Продолжить регистрацию" not in html + plain
        assert CODE in html

    def test_bad_base_sends_letter_without_link(self):
        html, plain = _reg(base="")
        assert "Продолжить регистрацию" not in html + plain
        assert CODE in html

    def test_wording_uses_uchetnaya_zapis_and_no_em_dash(self):
        html, plain = _reg()
        assert "учётной записи" in html and "учётной записи" in plain
        assert "аккаунт" not in html + plain
        assert "\u2014" not in html + plain

    def test_compact_text_link_not_full_width_button(self):
        from app.services import email_brand
        html, _ = _reg()
        anchor = re.search(r"<a [^>]*>", html).group(0)
        assert f"color:{email_brand.ACCENT}" in anchor
        assert "text-decoration:underline" in anchor
        assert "font-weight:bold" in anchor
        assert "display:block" not in anchor and "background" not in anchor
        link_p = html[:html.index(anchor)].rsplit("<p ", 1)[1]
        assert "font-size:16px" in link_p
        # Старой кнопки нет: ни ячейки с фоном ACCENT, ни таблицы под неё.
        assert f'bgcolor="{email_brand.ACCENT}"' not in html
        assert not hasattr(email_brand, "CTA_TEXT")


class TestRegisterInitPassesReferenceOfThisIssue:
    def test_password_registration_sends_reference_from_issue(self):
        from app.auth import service
        from app.auth.otp_service import RegistrationOtpIssue
        issue = RegistrationOtpIssue(code=CODE, registration_reference=REF)
        with patch("app.email_domains.service.assert_email_domain_allowed"), \
             patch.object(service.storage, "email_exists_any", return_value=False), \
             patch("app.auth.otp_service.issue_registration_otp", return_value=issue), \
             patch("app.services.email_service.send_registration_otp") as send:
            service.register_init(name="Иван", email=EMAIL, password="long-password-1")
        send.assert_called_once_with(EMAIL, CODE, registration_reference=REF)

    def test_issue_repr_hides_code(self):
        from app.auth.otp_service import RegistrationOtpIssue
        assert CODE not in repr(RegistrationOtpIssue(code=CODE, registration_reference=REF))

    def test_social_registration_does_not_get_ordinary_reference(self):
        from app.oauth import service as oauth_service
        source = inspect.getsource(oauth_service)
        assert "send_registration_otp(bound_email, code)" in source
        assert "registration_reference" not in source


# ─── Письма с временным паролем ──────────────────────────────────────────────

WELCOME = [
    email_service.send_welcome_staff,
    email_service.send_welcome_student,
    email_service.send_welcome_psychologist,
]


class TestWelcomeLoginLink:
    @pytest.mark.parametrize("fn", WELCOME)
    def test_login_link_and_url(self, fn):
        html, plain = _sent(fn, EMAIL, "Иван", PASSWORD)
        assert "Войти в сервис \u2192" in html
        assert _hrefs(html) == [PROD + "/login"]
        assert "Войти в сервис \u2192\nhttps://mindcare.donnu.ru/login" in plain

    @pytest.mark.parametrize("fn", WELCOME)
    def test_login_link_is_compact(self, fn):
        from app.services import email_brand
        html, _ = _sent(fn, EMAIL, "Иван", PASSWORD)
        anchor = re.search(r"<a [^>]*>", html).group(0)
        assert f"color:{email_brand.ACCENT}" in anchor
        assert "text-decoration:underline" in anchor
        assert "display:block" not in anchor
        assert f'bgcolor="{email_brand.ACCENT}"' not in html

    @pytest.mark.parametrize("fn", WELCOME)
    def test_no_confirmation_and_no_secrets_in_link(self, fn):
        html, plain = _sent(fn, EMAIL, "Иван", PASSWORD)
        assert "/register/confirm" not in html + plain
        assert "Продолжить регистрацию" not in html + plain
        for href in _hrefs(html):
            assert PASSWORD not in href and EMAIL not in href and "?" not in href
        assert PASSWORD in html  # временный пароль по-прежнему в письме

    @pytest.mark.parametrize("fn", WELCOME)
    def test_no_em_dash(self, fn):
        html, plain = _sent(fn, EMAIL, "Иван", PASSWORD)
        assert "—" not in html + plain


def test_password_reset_letter_unchanged_without_button():
    html, plain = _sent(email_service.send_password_reset_otp, EMAIL, CODE)
    assert _hrefs(html) == []
    assert "Продолжить регистрацию" not in html + plain
    assert "Войти в сервис" not in html + plain
