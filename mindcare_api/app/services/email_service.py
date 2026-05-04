"""
Email message layer — формирует письма для конкретных событий.
Не знает про SMTP, режимы доставки или конфиг.
"""

from datetime import datetime

from app.services.email_sender import send_email

# ─── Цвета из variables.css frontend-проекта ─────────────────────────────────
#   --warm-white  #FAF7F2   страничный фон
#   --espresso    #4A3728   header bar, цвет кода
#   --milk        #EDE4D3   текст на тёмном фоне
#   --latte       #C9B99A   рамка code-box, subtitle header
#   --cream       #F5F0E8   фон code-box
#   --text-main   #2E2318   заголовок письма
#   --text-muted  #5C4D3C   основной текст тела
#   --text-light  #8A7260   дисклеймер, footer
#   --nav-border  #D8CDBF   горизонтальный разделитель

# ─── Единый HTML-шаблон OTP письма ───────────────────────────────────────────
# Table-based верстка, inline-стили, без flex/grid/JS/внешних ресурсов.
# Подстановка: {code}, {year}, {heading}, {description}.

_OTP_HTML = """\
<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
  <title>{heading}</title>
</head>
<body style="margin:0;padding:0;background-color:#FAF7F2;
             font-family:Arial,Helvetica,sans-serif;">

  <!-- outer: задаёт фон и вертикальный отступ -->
  <table width="100%" cellpadding="0" cellspacing="0" border="0"
         style="background-color:#FAF7F2;">
    <tr>
      <td align="center" style="padding:48px 16px;">

        <!-- card: белый, скруглённый -->
        <table cellpadding="0" cellspacing="0" border="0"
               style="background-color:#ffffff;border-radius:12px;
                      max-width:480px;width:100%;">

          <!-- ── header bar ─────────────────────────────────────────────── -->
          <tr>
            <td style="background-color:#4A3728;border-radius:12px 12px 0 0;
                       padding:24px 32px;">
              <p style="margin:0;font-size:20px;font-weight:bold;
                        color:#EDE4D3;letter-spacing:0.02em;">
                MindCare
              </p>
              <p style="margin:5px 0 0;font-size:12px;font-weight:normal;
                        color:#C9B99A;letter-spacing:0.03em;">
                Психологическая помощь &#183; ДонГУ
              </p>
            </td>
          </tr>

          <!-- ── body ──────────────────────────────────────────────────── -->
          <tr>
            <td style="padding:32px 32px 24px;">

              <p style="margin:0 0 8px;font-size:18px;font-weight:bold;
                        color:#2E2318;line-height:1.3;">
                {heading}
              </p>
              <p style="margin:0 0 28px;font-size:14px;color:#5C4D3C;
                        line-height:1.65;">
                {description}
              </p>

              <!-- OTP code block -->
              <table width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td align="center" style="padding:0 0 28px;">
                    <table cellpadding="0" cellspacing="0" border="0">
                      <tr>
                        <td align="center"
                            style="background-color:#F5F0E8;
                                   border:1.5px solid #C9B99A;
                                   border-radius:10px;
                                   padding:18px 44px;">
                          <span style="font-size:36px;font-weight:bold;
                                       color:#4A3728;letter-spacing:10px;
                                       font-family:Courier New,Courier,monospace;">
                            {code}
                          </span>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>

              <p style="margin:0;font-size:13px;color:#8A7260;line-height:1.6;">
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
                  <td style="border-top:1px solid #D8CDBF;
                             font-size:0;line-height:0;">&nbsp;</td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- ── footer ────────────────────────────────────────────────── -->
          <tr>
            <td style="padding:16px 32px 24px;">
              <p style="margin:0;font-size:11px;color:#8A7260;
                        text-align:center;line-height:1.5;">
                &#169; {year} MindCare &nbsp;&#183;&nbsp; ДонГУ
                &nbsp;&#183;&nbsp; Психологическая поддержка
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

_OTP_PLAIN = """\
{heading} — MindCare

Ваш код: {code}

{description_plain}
Код действителен 10 минут.

Если вы не запрашивали это действие — проигнорируйте письмо.

---
MindCare · Психологическая помощь · ДонГУ
© {year}
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
    year = datetime.utcnow().year
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
