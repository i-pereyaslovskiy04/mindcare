"""
Email message layer — формирует письма для конкретных событий.
Не знает про SMTP, режимы доставки или конфиг.

Визуальное оформление — через app.services.email_brand (единый бренд
«Психология ДонГУ»), НЕ через пользовательскую тему интерфейса.
"""

import html
from datetime import datetime, timezone
from typing import Optional

from app.core.public_urls import LOGIN_PATH, REGISTER_CONFIRM_PATH, frontend_url
from app.services._smtp import send_email
from app.services.email_brand import (
    ACCENT,
    BORDER,
    BRAND_NAME,
    CARD_BG,
    CODE_BG,
    CODE_BORDER,
    CODE_TEXT,
    CTA_TEXT,
    HEADER_BG,
    HEADER_FG,
    HEADER_SUB,
    ORG_NAME,
    PAGE_BG,
    TAGLINE,
    TEXT_LIGHT,
    TEXT_MAIN,
    TEXT_MUTED,
)

# ─── Единый HTML-шаблон OTP/welcome письма ───────────────────────────────────
# Table-based верстка, inline-стили, без flex/grid/JS/внешних ресурсов и без
# CSS-переменных (почтовые клиенты их не поддерживают надёжно). Цвета —
# фиксированный бренд email_brand, подставленный f-строкой при импорте
# модуля (НЕ зависит от runtime/пользовательской темы).
# Подстановка на вызов: {code}, {year}, {heading}, {description}, {cta}
# ({cta} — кнопка перехода в сервис или пустая строка).

_OTP_HTML = f"""\
<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
  <title>{{heading}}</title>
</head>
<body style="margin:0;padding:0;background-color:{PAGE_BG};
             font-family:Arial,Helvetica,sans-serif;">

  <!-- outer: задаёт фон и вертикальный отступ -->
  <table width="100%" cellpadding="0" cellspacing="0" border="0"
         style="background-color:{PAGE_BG};">
    <tr>
      <td align="center" style="padding:48px 16px;">

        <!-- card: белый, скруглённый -->
        <table cellpadding="0" cellspacing="0" border="0"
               style="background-color:{CARD_BG};border-radius:12px;
                      max-width:480px;width:100%;">

          <!-- ── header bar ─────────────────────────────────────────────── -->
          <tr>
            <td style="background-color:{HEADER_BG};border-radius:12px 12px 0 0;
                       padding:24px 32px;">
              <p style="margin:0;font-size:20px;font-weight:bold;
                        color:{HEADER_FG};letter-spacing:0.02em;">
                {BRAND_NAME}
              </p>
              <p style="margin:5px 0 0;font-size:12px;font-weight:normal;
                        color:{HEADER_SUB};letter-spacing:0.03em;">
                {TAGLINE}
              </p>
            </td>
          </tr>

          <!-- ── body ──────────────────────────────────────────────────── -->
          <tr>
            <td style="padding:32px 32px 24px;">

              <p style="margin:0 0 8px;font-size:18px;font-weight:bold;
                        color:{TEXT_MAIN};line-height:1.3;">
                {{heading}}
              </p>
              <p style="margin:0 0 28px;font-size:14px;color:{TEXT_MUTED};
                        line-height:1.65;">
                {{description}}
              </p>

              <!-- OTP code block -->
              <table width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td align="center" style="padding:0 0 28px;">
                    <table cellpadding="0" cellspacing="0" border="0"
                           style="max-width:416px;">
                      <tr>
                        <td align="center"
                            style="background-color:{CODE_BG};
                                   border:1.5px solid {CODE_BORDER};
                                   border-radius:10px;
                                   padding:18px 24px;">
                          <span style="font-size:36px;font-weight:bold;
                                       color:{CODE_TEXT};letter-spacing:10px;
                                       font-family:Courier New,Courier,monospace;
                                       word-break:break-all;overflow-wrap:break-word;">
                            {{code}}
                          </span>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>

              {{cta}}

              <p style="margin:0;font-size:13px;color:{TEXT_LIGHT};line-height:1.6;">
                Если вы не запрашивали это действие&nbsp;- просто
                проигнорируйте письмо. Ваши данные в безопасности.
              </p>

            </td>
          </tr>

          <!-- ── divider ────────────────────────────────────────────────── -->
          <tr>
            <td style="padding:0 32px;">
              <table width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td style="border-top:1px solid {BORDER};
                             font-size:0;line-height:0;">&nbsp;</td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- ── footer ────────────────────────────────────────────────── -->
          <tr>
            <td style="padding:16px 32px 24px;">
              <p style="margin:0;font-size:11px;color:{TEXT_LIGHT};
                        text-align:center;line-height:1.5;">
                &#169; {{year}} {BRAND_NAME} &nbsp;&#183;&nbsp; {ORG_NAME}
              </p>
            </td>
          </tr>

        </table>
        <!-- /card -->

      </td>
    </tr>
  </table>

</body>
</html>
"""

_OTP_PLAIN = f"""\
{{heading}} - {BRAND_NAME}

Ваш код: {{code}}

{{description_plain}}
Код действителен 10 минут.
{{cta_plain}}
Если вы не запрашивали это действие - проигнорируйте письмо.

---
{BRAND_NAME} · {ORG_NAME}
© {{year}}
"""


# ─── Кнопка перехода в сервис (CTA) ─────────────────────────────────────────
# Bulletproof-кнопка: таблица на всю ширину карточки (на телефоне — во всю
# ширину экрана), фон — фирменный ACCENT, ссылка — блок внутри ячейки (вся
# кнопка кликабельна). Под кнопкой — подсказка, куда она ведёт.

def _cta_html(label: str, url: str, note: str) -> str:
    href = html.escape(url, quote=True)
    return f"""\
<table width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td align="center" style="padding:0 0 12px;">
                    <table width="100%" cellpadding="0" cellspacing="0" border="0"
                           style="max-width:416px;">
                      <tr>
                        <td align="center" bgcolor="{ACCENT}"
                            style="background-color:{ACCENT};border-radius:10px;">
                          <a href="{href}" target="_blank" rel="noopener noreferrer"
                             style="display:block;padding:14px 24px;font-size:15px;
                                    font-weight:bold;line-height:1.3;color:{CTA_TEXT};
                                    text-decoration:none;border-radius:10px;">{label}</a>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>
              <p style="margin:0 0 24px;font-size:13px;color:{TEXT_MUTED};
                        line-height:1.6;text-align:center;">
                {note}
              </p>"""


def _cta_plain(label: str, url: str, note: str) -> str:
    return f"\n{label}: {url}\n{note}\n"


# ─── Internal helper ─────────────────────────────────────────────────────────

def _send_otp_email(
    to_email: str,
    code: str,
    subject: str,
    heading: str,
    description_html: str,
    description_plain: str,
    cta_label: Optional[str] = None,
    cta_path: Optional[str] = None,
    cta_note: str = "",
) -> None:
    """cta_label + cta_path — кнопка перехода в сервис ({FRONTEND_PUBLIC_URL}
    + путь, без email/кода/пароля в ссылке). Если FRONTEND_PUBLIC_URL не задан
    корректно, письмо уходит без кнопки, а не со сломанной ссылкой."""
    year = datetime.now(timezone.utc).year
    cta_url = frontend_url(cta_path) if (cta_label and cta_path) else None
    cta_html = _cta_html(cta_label, cta_url, cta_note) if cta_url else ""
    cta_plain = _cta_plain(cta_label, cta_url, cta_note) if cta_url else ""
    send_email(
        to=to_email,
        subject=subject,
        body=_OTP_PLAIN.format(
            code=code,
            year=year,
            heading=heading,
            description_plain=description_plain,
            cta_plain=cta_plain,
        ),
        html=_OTP_HTML.format(
            code=code,
            year=year,
            heading=heading,
            description=description_html,
            cta=cta_html,
        ),
    )


CONTINUE_REGISTRATION_LABEL = "Продолжить регистрацию"
CONTINUE_REGISTRATION_NOTE = (
    "Откроется страница подтверждения: введите email и этот код."
)
LOGIN_LABEL = "Войти в сервис"
LOGIN_NOTE = "Войдите с этим email и временным паролем."



# ─── Public API ───────────────────────────────────────────────────────────────

def send_registration_otp(
    to_email: str, code: str, *, with_continue_link: bool = False,
) -> None:
    """with_continue_link=True — регистрация по email и паролю: кнопка
    «Продолжить регистрацию» ведёт на /register/confirm (ввод email и кода
    без исходной вкладки). Регистрация через Яндекс/VK зовёт без кнопки: её
    подтверждение требует ticket из памяти вкладки, /register/confirm его
    не продолжит."""
    _send_otp_email(
        to_email=to_email,
        code=code,
        subject=f"Подтверждение регистрации - {BRAND_NAME}",
        heading="Подтверждение регистрации",
        description_html=(
            "Введите код ниже, чтобы завершить создание учётной записи. "
            "Он действителен&nbsp;<strong>10&nbsp;минут</strong>."
        ),
        description_plain="Введите код ниже, чтобы завершить создание учётной записи.",
        cta_label=CONTINUE_REGISTRATION_LABEL if with_continue_link else None,
        cta_path=REGISTER_CONFIRM_PATH if with_continue_link else None,
        cta_note=CONTINUE_REGISTRATION_NOTE,
    )


def send_password_reset_otp(to_email: str, code: str) -> None:
    _send_otp_email(
        to_email=to_email,
        code=code,
        subject=f"Восстановление пароля - {BRAND_NAME}",
        heading="Восстановление пароля",
        description_html=(
            "Введите код, чтобы сбросить пароль. "
            "Он действителен&nbsp;<strong>10&nbsp;минут</strong>."
        ),
        description_plain="Введите код, чтобы сбросить пароль.",
    )


def send_welcome_psychologist(to_email: str, name: str, password: str) -> None:
    _send_otp_email(
        to_email=to_email,
        code=password,
        subject=f"Добро пожаловать в «{BRAND_NAME}» - ваши данные для входа",
        heading="Ваша учётная запись создана",
        description_html=(
            f"Здравствуйте, <strong>{name}</strong>!<br><br>"
            f"Для вас создана учётная запись психолога в сервисе «{BRAND_NAME}». "
            "Ниже - ваш временный пароль. "
            "Пожалуйста, войдите и смените его при первой возможности."
        ),
        description_plain=(
            f"Здравствуйте, {name}!\n\n"
            f"Для вас создана учётная запись психолога в сервисе «{BRAND_NAME}».\n"
            "Ниже - ваш временный пароль. Смените его при первом входе."
        ),
        cta_label=LOGIN_LABEL,
        cta_path=LOGIN_PATH,
        cta_note=LOGIN_NOTE,
    )


def send_welcome_staff(to_email: str, name: str, password: str) -> None:
    """Приветственное письмо staff-пользователю (psychologist/supervisor/admin,
    в т.ч. multi-role), чья учётная запись создана администратором.

    Role-neutral: без упоминания конкретной роли (не «учётная запись психолога») и без
    перечисления прав/ролей."""
    _send_otp_email(
        to_email=to_email,
        code=password,
        subject=f"Добро пожаловать в «{BRAND_NAME}» - ваши данные для входа",
        heading="Ваша учётная запись создана",
        description_html=(
            f"Здравствуйте, <strong>{name}</strong>!<br><br>"
            f"Для вас создана учётная запись в сервисе «{BRAND_NAME}». "
            "Ниже - ваш временный пароль. "
            "Пожалуйста, войдите и смените его при первой возможности."
        ),
        description_plain=(
            f"Здравствуйте, {name}!\n\n"
            f"Для вас создана учётная запись в сервисе «{BRAND_NAME}».\n"
            "Ниже - ваш временный пароль. Смените его при первом входе."
        ),
        cta_label=LOGIN_LABEL,
        cta_path=LOGIN_PATH,
        cta_note=LOGIN_NOTE,
    )


def send_welcome_student(to_email: str, name: str, password: str) -> None:
    """Приветственное письмо студенту, чья учётная запись создана admin/supervisor.

    Без staff-специфичного текста (не «учётная запись психолога»)."""
    _send_otp_email(
        to_email=to_email,
        code=password,
        subject=f"Добро пожаловать в «{BRAND_NAME}» - ваши данные для входа",
        heading="Ваша учётная запись создана",
        description_html=(
            f"Здравствуйте, <strong>{name}</strong>!<br><br>"
            f"Для вас создана учётная запись в сервисе «{BRAND_NAME}». "
            "Ниже - ваш временный пароль. "
            "Пожалуйста, войдите и смените его при первом входе."
        ),
        description_plain=(
            f"Здравствуйте, {name}!\n\n"
            f"Для вас создана учётная запись в сервисе «{BRAND_NAME}».\n"
            "Ниже - ваш временный пароль. Смените его при первом входе."
        ),
        cta_label=LOGIN_LABEL,
        cta_path=LOGIN_PATH,
        cta_note=LOGIN_NOTE,
    )