"""
Email message layer — формирует письма для конкретных событий.
Не знает про SMTP, режимы доставки или конфиг.

Визуальное оформление — через app.services.email_brand (единый бренд
«Психология ДонГУ»), НЕ через пользовательскую тему интерфейса.
"""

import html
from datetime import datetime, timezone
from typing import Optional

from app.core.public_urls import (
    LOGIN_PATH, SOCIAL_REGISTRATION_PATH, frontend_url, registration_continue_path,
)
from app.services._smtp import send_email
from app.services.email_brand import (
    ACCENT,
    BORDER,
    BRAND_NAME,
    CARD_BG,
    CODE_BG,
    CODE_BORDER,
    CODE_TEXT,
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
# ({cta} — ссылка перехода в сервис или пустая строка).

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


# ─── Ссылка перехода в сервис (CTA) ─────────────────────────────────────────
# Компактная текстовая ссылка под кодом: подсказка, куда она ведёт, и обычный
# <a> фирменного цвета ACCENT с подчёркиванием. Без фона, кнопки на всю
# ширину и display:block — простые inline-стили, понятные почтовым клиентам.
# В plain-text — полный адрес отдельной строкой.

CTA_ARROW = "\u2192"   # «→» после текста ссылки


def _cta_html(label: str, url: str, note: str) -> str:
    href = html.escape(url, quote=True)
    text = html.escape(f"{label} {CTA_ARROW}")
    return f"""\
<p style="margin:0 0 6px;font-size:14px;color:{TEXT_MUTED};line-height:1.6;">
                {note}
              </p>
              <p style="margin:0 0 24px;font-size:16px;line-height:1.5;">
                <a href="{href}" target="_blank" rel="noopener noreferrer"
                   style="color:{ACCENT};font-weight:bold;text-decoration:underline;">{text}</a>
              </p>"""


def _cta_plain(label: str, url: str, note: str) -> str:
    return f"\n{note}\n{label} {CTA_ARROW}\n{url}\n"


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
    """cta_label + cta_path — ссылка перехода в сервис ({FRONTEND_PUBLIC_URL}
    + путь, без email/кода/пароля в ссылке). Если FRONTEND_PUBLIC_URL не задан
    корректно, письмо уходит без ссылки, а не со сломанной."""
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
CONTINUE_REGISTRATION_NOTE = "Откройте страницу и введите код из этого письма."
LOGIN_LABEL = "Войти в сервис"
LOGIN_NOTE = "Войдите с этим email и временным паролем."



# ─── Public API ───────────────────────────────────────────────────────────────

def send_registration_otp(
    to_email: str, code: str, *, registration_reference: Optional[str] = None,
    social_continuation: bool = False,
) -> None:
    """Ссылка «Продолжить регистрацию →» (одна из двух, не обе):

      * registration_reference — регистрация по email и паролю:
        /register/confirm#r=<reference> ЭТОГО выпуска кода (вводится только код);
      * social_continuation — регистрация через Яндекс/VK: /register/social без
        секретов (ticket в HttpOnly cookie браузера, прошедшего вход через
        провайдера; в другом браузере продолжить нельзя).

    Без обоих — письмо без ссылки."""
    if registration_reference is not None and social_continuation:
        raise ValueError("registration_reference and social_continuation are exclusive")
    if registration_reference is not None:
        continue_path = registration_continue_path(registration_reference)
    elif social_continuation:
        continue_path = SOCIAL_REGISTRATION_PATH
    else:
        continue_path = None
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
        cta_label=CONTINUE_REGISTRATION_LABEL if continue_path else None,
        cta_path=continue_path,
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