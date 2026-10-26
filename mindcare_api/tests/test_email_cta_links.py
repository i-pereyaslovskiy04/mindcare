"""
Кнопки перехода в сервис в письмах и FRONTEND_PUBLIC_URL (unit, без БД и SMTP).

- Регистрация по email и паролю: «Продолжить регистрацию» → {FRONTEND_PUBLIC_URL}
  /register/confirm, в HTML и в plain-text.
- Регистрация через Яндекс/VK: без этой кнопки (её подтверждение требует
  ticket из памяти вкладки).
- Письма с временным паролем: «Войти в сервис» → {FRONTEND_PUBLIC_URL}/login.
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

class TestRegistrationContinueLink:
    def test_html_has_button_and_confirm_url(self):
        html, _ = _sent(email_service.send_registration_otp, EMAIL, CODE,
                        with_continue_link=True)
        assert "Продолжить регистрацию" in html
        assert _hrefs(html) == [PROD + "/register/confirm"]

    def test_plain_has_full_url(self):
        _, plain = _sent(email_service.send_registration_otp, EMAIL, CODE,
                         with_continue_link=True)
        assert "Продолжить регистрацию: https://mindcare.donnu.ru/register/confirm" in plain
        assert "введите email и этот код" in plain

    def test_local_base(self):
        html, plain = _sent(email_service.send_registration_otp, EMAIL, CODE,
                            base="http://localhost:3000", with_continue_link=True)
        assert _hrefs(html) == ["http://localhost:3000/register/confirm"]
        assert "http://localhost:3000/register/confirm" in plain

    def test_no_email_code_or_token_in_link(self):
        html, plain = _sent(email_service.send_registration_otp, EMAIL, CODE,
                            with_continue_link=True)
        for href in _hrefs(html):
            assert EMAIL not in href and CODE not in href
            assert "?" not in href and "#" not in href
        url_line = next(line for line in plain.splitlines() if "http" in line)
        assert EMAIL not in url_line and CODE not in url_line

    def test_code_still_shown_in_letter(self):
        html, plain = _sent(email_service.send_registration_otp, EMAIL, CODE,
                            with_continue_link=True)
        assert CODE in html and f"Ваш код: {CODE}" in plain

    def test_without_flag_no_button(self):
        html, plain = _sent(email_service.send_registration_otp, EMAIL, CODE)
        assert "Продолжить регистрацию" not in html + plain
        assert _hrefs(html) == []

    def test_bad_base_sends_letter_without_button(self):
        html, plain = _sent(email_service.send_registration_otp, EMAIL, CODE,
                            base="", with_continue_link=True)
        assert "Продолжить регистрацию" not in html + plain
        assert CODE in html

    def test_wording_uses_uchetnaya_zapis_and_no_em_dash(self):
        html, plain = _sent(email_service.send_registration_otp, EMAIL, CODE,
                            with_continue_link=True)
        assert "учётной записи" in html and "учётной записи" in plain
        assert "аккаунт" not in html + plain
        assert "—" not in html + plain

    def test_button_uses_brand_accent(self):
        from app.services import email_brand
        html, _ = _sent(email_service.send_registration_otp, EMAIL, CODE,
                        with_continue_link=True)
        assert f'bgcolor="{email_brand.ACCENT}"' in html
        assert f"color:{email_brand.CTA_TEXT}" in html
        # Кнопка на всю ширину карточки — удобна на узком экране.
        assert 'width="100%" cellpadding="0" cellspacing="0" border="0"\n' in html


class TestRegisterInitPassesContinueFlag:
    def test_password_registration_sends_continue_link(self):
        from app.auth import service
        with patch("app.email_domains.service.assert_email_domain_allowed"), \
             patch.object(service.storage, "email_exists_any", return_value=False), \
             patch("app.auth.otp_service.create_or_update_otp", return_value=CODE), \
             patch("app.services.email_service.send_registration_otp") as send:
            service.register_init(name="Иван", email=EMAIL, password="long-password-1")
        send.assert_called_once_with(EMAIL, CODE, with_continue_link=True)

    def test_social_registration_does_not_request_continue_link(self):
        from app.oauth import service as oauth_service
        source = inspect.getsource(oauth_service)
        assert "send_registration_otp(bound_email, code)" in source
        assert "with_continue_link" not in source


# ─── Письма с временным паролем ──────────────────────────────────────────────

WELCOME = [
    email_service.send_welcome_staff,
    email_service.send_welcome_student,
    email_service.send_welcome_psychologist,
]


class TestWelcomeLoginLink:
    @pytest.mark.parametrize("fn", WELCOME)
    def test_login_button_and_url(self, fn):
        html, plain = _sent(fn, EMAIL, "Иван", PASSWORD)
        assert "Войти в сервис" in html
        assert _hrefs(html) == [PROD + "/login"]
        assert "Войти в сервис: https://mindcare.donnu.ru/login" in plain

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
