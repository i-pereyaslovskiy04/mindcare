"""
Единый фирменный email-бренд «Психология ДонГУ» (app.services.email_brand).

Проверяет:
  * легаси Coffee-hardcode (старая кофейная палитра) отсутствует в
    отрендеренном HTML/plain-text любого email flow;
  * новый бренд (app.services.email_brand) используется централизованно —
    header/footer/код во ВСЕХ flow одинаковы по цвету и названию бренда;
  * email_brand НЕ ссылается на пользовательскую тему интерфейса
    (ui_theme_palette/ui_theme_mode/localStorage/frontend theme context) —
    структурная гарантия, а не только визуальная;
  * subject/код/временный пароль/критичные токены не потерялись при смене
    оформления;
  * plain-text fallback (используется integration-тестами через
    "Ваш код: <6 digits>") не ломается.

Без реального SMTP: send_email монкипатчится.
"""

import inspect
from unittest.mock import patch

import pytest

from app.services import email_brand, email_service

# ─── Легаси Coffee-палитра, которая НЕ должна встречаться в письмах ──────────
LEGACY_COFFEE_HEX = [
    "#FAF7F2",  # старый --warm-white (page bg)
    "#4A3728",  # старый --espresso (header bar / код)
    "#EDE4D3",  # старый --milk (текст на тёмном)
    "#C9B99A",  # старый --latte (рамка / subtitle)
    "#F5F0E8",  # старый --cream (фон code-box)
    "#2E2318",  # старый --text-main
    "#5C4D3C",  # старый --text-muted
    "#8A7260",  # старый --text-light
    "#D8CDBF",  # старый --nav-border
]


def _render_html(heading="H", description="D", code="654321", year=2026):
    return email_service._OTP_HTML.format(
        heading=heading, description=description, code=code, year=year
    )


def _render_plain(heading="H", description_plain="D", code="654321", year=2026):
    return email_service._OTP_PLAIN.format(
        heading=heading,
        description_plain=description_plain,
        code=code,
        year=year,
    )


# ─── 1. Coffee-hardcode отсутствует ───────────────────────────────────────────

class TestNoCoffeeHardcode:
    def test_html_has_no_legacy_coffee_hex(self):
        html = _render_html()
        for hexcode in LEGACY_COFFEE_HEX:
            assert hexcode not in html, f"legacy coffee color {hexcode} leaked into HTML"

    def test_plain_has_no_legacy_coffee_hex(self):
        plain = _render_plain()
        for hexcode in LEGACY_COFFEE_HEX:
            assert hexcode not in plain

    def test_email_service_source_has_no_legacy_coffee_hex(self):
        source = inspect.getsource(email_service)
        for hexcode in LEGACY_COFFEE_HEX:
            assert hexcode not in source


# ─── 2. Новый бренд применяется централизованно ──────────────────────────────

class TestBrandApplied:
    def test_brand_name_is_psihologiya_dongu(self):
        assert email_brand.BRAND_NAME == "Психология ДонГУ"

    def test_html_contains_brand_name(self):
        html = _render_html()
        assert email_brand.BRAND_NAME in html

    def test_plain_contains_brand_name(self):
        plain = _render_plain()
        assert email_brand.BRAND_NAME in plain

    def test_html_uses_brand_colors(self):
        html = _render_html()
        for token in (
            email_brand.PAGE_BG,
            email_brand.CARD_BG,
            email_brand.HEADER_BG,
            email_brand.HEADER_FG,
            email_brand.TEXT_MAIN,
            email_brand.TEXT_MUTED,
            email_brand.BORDER,
            email_brand.CODE_BG,
            email_brand.CODE_BORDER,
            email_brand.CODE_TEXT,
        ):
            assert token in html

    def test_required_brand_fields_exist(self):
        """Минимальный контракт email_brand (пункт 3 постановки задачи)."""
        for field in (
            "BRAND_NAME", "ACCENT", "PAGE_BG", "CARD_BG",
            "TEXT_MAIN", "TEXT_MUTED", "BORDER",
        ):
            assert hasattr(email_brand, field), f"email_brand missing {field}"


# ─── 3. email_brand не зависит от пользовательской темы ─────────────────────

class TestBrandIndependentOfUserTheme:
    def test_brand_module_public_attributes_are_static_literals(self):
        """Каждая публичная константа бренда — обычная str-литерал, а не
        property/функция/lookup, которые могли бы читать runtime-состояние
        (пользователя, settings, localStorage, frontend theme context)."""
        public_names = [n for n in dir(email_brand) if not n.startswith("_")]
        assert "BRAND_NAME" in public_names
        for name in public_names:
            value = getattr(email_brand, name)
            assert isinstance(value, str), f"{name} is not a static str literal"

    def test_email_service_source_has_no_user_theme_references(self):
        source = inspect.getsource(email_service)
        for forbidden in ("ui_theme_palette", "ui_theme_mode", "localStorage"):
            assert forbidden not in source

    def test_brand_module_does_not_import_user_or_settings(self):
        """email_brand — чистые константы, без доступа к БД/пользователю/config.

        Структурная гарантия: даже если у пользователя выбрана Coffee-тема,
        конструктор письма физически не может прочитать это значение — у
        него нет ни объекта пользователя, ни settings, ни frontend-контекста.
        """
        source = inspect.getsource(email_brand)
        assert "import" not in source  # только литеральные константы

    def test_public_send_functions_take_no_theme_argument(self):
        for fn in (
            email_service.send_registration_otp,
            email_service.send_password_reset_otp,
            email_service.send_welcome_staff,
            email_service.send_welcome_student,
        ):
            params = set(inspect.signature(fn).parameters)
            assert not (params & {"theme", "palette", "ui_theme_mode", "ui_theme_palette"})


# ─── 4. Единое оформление во всех flow ───────────────────────────────────────

class TestConsistentAcrossFlows:
    """Разные email flow должны рендерить ОДИНАКОВЫЙ header/footer/бренд —
    единая система, а не разные шаблоны по флоу."""

    @pytest.fixture(autouse=True)
    def _capture(self, monkeypatch):
        self.sent = []

        def _fake(to, subject, body, html=None):
            self.sent.append({"to": to, "subject": subject, "body": body, "html": html})

        monkeypatch.setattr(email_service, "send_email", _fake)

    def test_registration_otp_uses_shared_brand(self):
        email_service.send_registration_otp("a@x.com", "111111")
        html = self.sent[-1]["html"]
        assert email_brand.HEADER_BG in html
        assert email_brand.BRAND_NAME in html

    def test_password_reset_otp_uses_shared_brand(self):
        email_service.send_password_reset_otp("a@x.com", "222222")
        html = self.sent[-1]["html"]
        assert email_brand.HEADER_BG in html
        assert email_brand.BRAND_NAME in html

    def test_welcome_staff_uses_shared_brand(self):
        email_service.send_welcome_staff("a@x.com", "Иван Иванов", "TmpPass123!")
        html = self.sent[-1]["html"]
        assert email_brand.HEADER_BG in html
        assert email_brand.BRAND_NAME in html

    def test_welcome_student_uses_shared_brand(self):
        email_service.send_welcome_student("a@x.com", "Пётр Петров", "TmpPass456!")
        html = self.sent[-1]["html"]
        assert email_brand.HEADER_BG in html
        assert email_brand.BRAND_NAME in html

    def test_all_four_flows_share_identical_header_block(self):
        email_service.send_registration_otp("a@x.com", "111111")
        email_service.send_password_reset_otp("a@x.com", "222222")
        email_service.send_welcome_staff("a@x.com", "N", "P1")
        email_service.send_welcome_student("a@x.com", "N", "P2")

        headers = []
        for msg in self.sent:
            html = msg["html"]
            start = html.index(f'background-color:{email_brand.HEADER_BG}')
            headers.append(html[start:start + 40])
        assert len(set(headers)) == 1, "email flows render different header styling"


# ─── 5. Критичные токены/subject не потерялись ───────────────────────────────

class TestCriticalContentPreserved:
    @pytest.fixture(autouse=True)
    def _capture(self, monkeypatch):
        self.sent = []

        def _fake(to, subject, body, html=None):
            self.sent.append({"to": to, "subject": subject, "body": body, "html": html})

        monkeypatch.setattr(email_service, "send_email", _fake)

    def test_registration_otp_code_present_in_html_and_plain(self):
        email_service.send_registration_otp("a@x.com", "734829")
        msg = self.sent[-1]
        assert "734829" in msg["html"]
        assert "734829" in msg["body"]

    def test_password_reset_subject_uses_brand_name(self):
        email_service.send_password_reset_otp("a@x.com", "111111")
        assert self.sent[-1]["subject"] == f"Восстановление пароля - {email_brand.BRAND_NAME}"

    def test_registration_subject_uses_brand_name(self):
        email_service.send_registration_otp("a@x.com", "111111")
        assert self.sent[-1]["subject"] == f"Подтверждение регистрации - {email_brand.BRAND_NAME}"

    def test_welcome_staff_password_present_in_html_and_plain(self):
        email_service.send_welcome_staff("a@x.com", "Имя", "S3cr3t!Pass")
        msg = self.sent[-1]
        assert "S3cr3t!Pass" in msg["html"]
        assert "S3cr3t!Pass" in msg["body"]

    def test_welcome_student_password_present_in_html_and_plain(self):
        email_service.send_welcome_student("a@x.com", "Имя", "AnotherPass1")
        msg = self.sent[-1]
        assert "AnotherPass1" in msg["html"]
        assert "AnotherPass1" in msg["body"]

    def test_plain_text_otp_code_line_matches_integration_fixture_regex(self):
        """tests/integration/conftest.py::capture_emails парсит plain body
        регулярным выражением r"Ваш код: (\\d{6})" — убедимся, что новая
        вёрстка его не сломала."""
        import re

        email_service.send_registration_otp("a@x.com", "456789")
        body = self.sent[-1]["body"]
        match = re.search(r"Ваш код: (\d{6})", body)
        assert match is not None
        assert match.group(1) == "456789"

    def test_send_email_still_called_for_every_flow(self):
        email_service.send_registration_otp("a@x.com", "1")
        email_service.send_password_reset_otp("a@x.com", "2")
        email_service.send_welcome_staff("a@x.com", "N", "P")
        email_service.send_welcome_student("a@x.com", "N", "P")
        assert len(self.sent) == 4
        assert all(msg["html"] for msg in self.sent)
        assert all(msg["body"] for msg in self.sent)


# ─── 6. Длинный временный пароль не ломает layout на узкой ширине ────────────
# Найдено визуальным smoke-тестом: _generate_password(length=12) в
# app/users/service.py — реальная длина temp-пароля. Код/пароль рендерится
# тем же блоком, что и 6-значный OTP (letter-spacing:10px, без пробелов),
# поэтому длинный пароль без возможности переноса форсировал ширину карточки
# далеко за пределы viewport 320–375px (подтверждено Playwright-замером).

class TestLongCodeDoesNotBreakLayout:
    def test_code_span_allows_wrapping(self):
        """word-break/overflow-wrap на span кода — иначе длинный пароль без
        пробелов не может перенестись и раздувает таблицу шире viewport."""
        html = _render_html(code="St4ffTmpPass!9")
        span_start = html.index("letter-spacing:10px")
        span_style = html[span_start:span_start + 200]
        assert "word-break" in span_style or "overflow-wrap" in span_style

    def test_code_box_table_has_max_width_constraint(self):
        """Обёртывающая таблица кода должна иметь max-width, иначе auto-layout
        таблица продолжит расти по содержимому несмотря на word-break."""
        html = _render_html(code="St4ffTmpPass!9")
        otp_block_start = html.index("OTP code block")
        otp_block = html[otp_block_start:otp_block_start + 500]
        assert "max-width" in otp_block

    def test_long_password_text_not_truncated_despite_wrapping(self):
        """Перенос строки не должен резать сам текст пароля — только CSS."""
        long_password = "St4ffTmpPass!9"
        html = _render_html(code=long_password)
        assert long_password in html


# ─── 7. Legacy "MindCare" отсутствует в пользовательских email-текстах ───────
# Официальное пользовательское название — «Психология ДонГУ» (email_brand.
# BRAND_NAME). "MindCare" остаётся техническим именем проекта/репозитория,
# но получатель письма больше не должен его видеть ни в subject, ни в теле,
# ни в plain-text fallback — ни для одного из пяти email flow.

class TestNoLegacyMindCareBrandInEmail:
    @pytest.fixture(autouse=True)
    def _capture(self, monkeypatch):
        self.sent = []

        def _fake(to, subject, body, html=None):
            self.sent.append({"to": to, "subject": subject, "body": body, "html": html})

        monkeypatch.setattr(email_service, "send_email", _fake)

    def _assert_no_mindcare(self, msg):
        assert "MindCare" not in msg["subject"]
        assert "MindCare" not in msg["html"]
        assert "MindCare" not in msg["body"]

    def test_registration_otp_has_no_mindcare(self):
        email_service.send_registration_otp("a@x.com", "111111")
        self._assert_no_mindcare(self.sent[-1])

    def test_password_reset_otp_has_no_mindcare(self):
        email_service.send_password_reset_otp("a@x.com", "222222")
        self._assert_no_mindcare(self.sent[-1])

    def test_welcome_psychologist_has_no_mindcare(self):
        email_service.send_welcome_psychologist("a@x.com", "Имя", "Pass123!")
        self._assert_no_mindcare(self.sent[-1])

    def test_welcome_staff_has_no_mindcare(self):
        email_service.send_welcome_staff("a@x.com", "Имя", "Pass123!")
        self._assert_no_mindcare(self.sent[-1])

    def test_welcome_student_has_no_mindcare(self):
        email_service.send_welcome_student("a@x.com", "Имя", "Pass123!")
        self._assert_no_mindcare(self.sent[-1])

    def test_email_brand_tagline_and_org_name_defined(self):
        """TAGLINE/ORG_NAME — централизованные константы (не per-template
        hardcode), используемые header-subtitle и footer."""
        assert email_brand.TAGLINE
        assert email_brand.ORG_NAME == "Донецкий государственный университет"
        html = _render_html()
        assert email_brand.TAGLINE in html
        assert email_brand.ORG_NAME in html


# ─── 8. Пунктуация пользовательского текста: без длинного тире ───────────────
# Редакционное правило этапа polish: пользовательские email-тексты используют
# обычный дефис с пробелами (" - "), не длинное тире (—/&#8212;). Правило не
# затрагивает docstring/комментарии модуля (не рендерятся пользователю).

class TestNoEmDashInUserFacingText:
    def test_html_has_no_em_dash(self):
        html = _render_html()
        assert "—" not in html
        assert "&#8212;" not in html

    def test_plain_has_no_em_dash(self):
        plain = _render_plain()
        assert "—" not in plain

    def test_subjects_have_no_em_dash(self, monkeypatch):
        sent = []
        monkeypatch.setattr(
            email_service, "send_email",
            lambda to, subject, body, html=None: sent.append(subject),
        )
        email_service.send_registration_otp("a@x.com", "111111")
        email_service.send_password_reset_otp("a@x.com", "222222")
        email_service.send_welcome_staff("a@x.com", "Имя", "Pass123!")
        email_service.send_welcome_student("a@x.com", "Имя", "Pass123!")
        for subject in sent:
            assert "—" not in subject, subject

    def test_welcome_texts_use_service_wording_not_platform(self, monkeypatch):
        """Пункт 2 polish-этапа: «учётная запись в сервисе», не «аккаунт на
        платформе»."""
        sent = []
        monkeypatch.setattr(
            email_service, "send_email",
            lambda to, subject, body, html=None: sent.append(html),
        )
        email_service.send_welcome_staff("a@x.com", "Имя", "Pass123!")
        email_service.send_welcome_student("a@x.com", "Имя", "Pass123!")
        email_service.send_welcome_psychologist("a@x.com", "Имя", "Pass123!")
        for html in sent:
            assert "на платформе" not in html
            assert "учётная запись" in html
            assert "в сервисе «Психология ДонГУ»" in html
