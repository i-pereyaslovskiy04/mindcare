"""
Email message layer — формирует письма для конкретных событий.
Не знает про SMTP, режимы доставки или конфиг.

Визуальное оформление — через app.services.email_brand (единый бренд
«Психология ДонГУ»), НЕ через пользовательскую тему интерфейса.
"""

from datetime import datetime, timezone

from app.services._smtp import send_email
from app.services.email_brand import (
    BORDER,
    BRAND_NAME,
    CARD_BG,
    CODE_BG,
    CODE_BORDER,
    CODE_TEXT,
    HEADER_BG,
    HEADER_FG,
    HEADER_SUB,
    PAGE_BG,
    TEXT_LIGHT,
    TEXT_MAIN,
    TEXT_MUTED,
)

# ─── Единый HTML-шаблон OTP/welcome письма ───────────────────────────────────
# Table-based верстка, inline-стили, без flex/grid/JS/внешних ресурсов и без
# CSS-переменных (почтовые клиенты их не поддерживают надёжно). Цвета —
# фиксированный бренд email_brand, подставленный f-строкой при импорте
# модуля (НЕ зависит от runtime/пользовательской темы).
# Подстановка на вызов: {code}, {year}, {heading}, {description}.

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
                MindCare &#183; платформа психологической поддержки
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

              <p style="margin:0;font-size:13px;color:{TEXT_LIGHT};line-height:1.6;">
                Если вы не запрашивали это действие&nbsp;&#8212; просто
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
                &#169; {{year}} {BRAND_NAME} &nbsp;&#183;&nbsp; MindCare
                &nbsp;&#183;&nbsp; Донецкий государственный университет
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
{{heading}} — {BRAND_NAME} (MindCare)

Ваш код: {{code}}

{{description_plain}}
Код действителен 10 минут.

Если вы не запрашивали это действие — проигнорируйте письмо.

---
{BRAND_NAME} · MindCare · Донецкий государственный университет
© {{year}}
"""


# ─── Internal helper ─────────────────────────────────────────────────────────

def _send_otp_email(
    to_email: str,
    code: str,
    subject: str,
    heading: str,
    description_html: str,
    description_plain: str,
) -> None:
    year = datetime.now(timezone.utc).year
    send_email(
        to=to_email,
        subject=subject,
        body=_OTP_PLAIN.format(
            code=code,
            year=year,
            heading=heading,
            description_plain=description_plain,
        ),
        html=_OTP_HTML.format(
            code=code,
            year=year,
            heading=heading,
            description=description_html,
        ),
    )


# ─── Public API ───────────────────────────────────────────────────────────────

def send_registration_otp(to_email: str, code: str) -> None:
    _send_otp_email(
        to_email=to_email,
        code=code,
        subject="Подтверждение регистрации — MindCare",
        heading="Подтверждение регистрации",
        description_html=(
            "Введите код ниже, чтобы завершить создание аккаунта. "
            "Он действителен&nbsp;<strong>10&nbsp;минут</strong>."
        ),
        description_plain="Введите код ниже, чтобы завершить создание аккаунта.",
    )


def send_password_reset_otp(to_email: str, code: str) -> None:
    _send_otp_email(
        to_email=to_email,
        code=code,
        subject="Восстановление пароля — MindCare",
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
        subject="Добро пожаловать в MindCare — ваши данные для входа",
        heading="Ваш аккаунт создан",
        description_html=(
            f"Здравствуйте, <strong>{name}</strong>!<br><br>"
            "Для вас создан аккаунт психолога на платформе MindCare. "
            "Ниже — ваш временный пароль. "
            "Пожалуйста, войдите и смените его при первой возможности."
        ),
        description_plain=(
            f"Здравствуйте, {name}!\n\n"
            "Для вас создан аккаунт психолога на платформе MindCare.\n"
            "Ниже — ваш временный пароль. Смените его при первом входе."
        ),
    )


def send_welcome_staff(to_email: str, name: str, password: str) -> None:
    """Приветственное письмо staff-пользователю (psychologist/supervisor/admin,
    в т.ч. multi-role), чей аккаунт создан администратором.

    Role-neutral: без упоминания конкретной роли (не «аккаунт психолога») и без
    перечисления прав/ролей."""
    _send_otp_email(
        to_email=to_email,
        code=password,
        subject="Добро пожаловать в MindCare — ваши данные для входа",
        heading="Ваш аккаунт создан",
        description_html=(
            f"Здравствуйте, <strong>{name}</strong>!<br><br>"
            "Для вас создан аккаунт на платформе психологической службы "
            "MindCare. Ниже — ваш временный пароль. "
            "Пожалуйста, войдите и смените его при первой возможности."
        ),
        description_plain=(
            f"Здравствуйте, {name}!\n\n"
            "Для вас создан аккаунт на платформе психологической службы "
            "MindCare.\nНиже — ваш временный пароль. Смените его при первом входе."
        ),
    )


def send_welcome_student(to_email: str, name: str, password: str) -> None:
    """Приветственное письмо студенту, чей аккаунт создан admin/supervisor.

    Без staff-специфичного текста (не «аккаунт психолога»)."""
    _send_otp_email(
        to_email=to_email,
        code=password,
        subject="Добро пожаловать в MindCare — ваши данные для входа",
        heading="Ваш аккаунт создан",
        description_html=(
            f"Здравствуйте, <strong>{name}</strong>!<br><br>"
            "Для вас создан аккаунт на платформе психологической службы "
            "MindCare. Ниже — ваш временный пароль. "
            "Пожалуйста, войдите и смените его при первом входе."
        ),
        description_plain=(
            f"Здравствуйте, {name}!\n\n"
            "Для вас создан аккаунт на платформе психологической службы "
            "MindCare.\nНиже — ваш временный пароль. Смените его при первом входе."
        ),
    )