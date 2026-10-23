"""
Единый фирменный стиль email MindCare — «Психология ДонГУ».

Все системные письма (OTP-коды, welcome-письма) используют ОДИН визуальный
бренд, независимый от пользовательской темы интерфейса. Email — официальная
коммуникация MindCare / ДонГУ, поэтому:

  * оформление НЕ зависит от выбранной темы кабинета (Coffee/Classic/Nature/…);
  * оформление НЕ читает ui_theme_palette / ui_theme_mode / localStorage /
    runtime frontend theme context — ничего из этого здесь не импортируется;
  * значения — СТАБИЛЬНЫЙ СНИМОК, а не живая ссылка на frontend CSS.

Источник направления — дизайн-токены темы "dongu" (светлый вариант,
mindcare_web/src/styles/tokens/dongu-light.css), зафиксированные здесь как
независимые email-константы на момент этого этапа. Header-бар использует те
же значения, что --hero-bg/--hero-fg/--hero-accent темы dongu (фирменная
тёмно-синяя подложка с светлым текстом — та же пара, что уже используется
для hero-баннера сайта независимо от светлой/тёмной темы).

Правка цветов фронтенда НЕ меняет email автоматически — это осознанно
(email должен быть стабильным независимо от будущих правок темы кабинета).
"""

BRAND_NAME = "Психология ДонГУ"

# ── Цвета (стабильный снимок dongu-light.css) ─────────────────────────────
PAGE_BG = "#F6F8FA"       # --cream       внешний фон письма
CARD_BG = "#FFFFFF"       # --warm-white  поверхность карточки письма
HEADER_BG = "#16233D"     # --espresso    header bar (= --hero-bg темы dongu)
HEADER_FG = "#EAF1FB"     # --text-on-dark заголовок в header (= --hero-fg)
HEADER_SUB = "#C3D2E6"    # --latte       подзаголовок в header (= --hero-accent)
ACCENT = "#2454A6"        # --coffee      фирменный синий ДонГУ (ссылки/CTA)
ACCENT_HOVER = "#1F4A8C"  # --mocha       hover-оттенок акцента
TEXT_MAIN = "#2E2E2E"     # --text-main   заголовок тела письма
TEXT_MUTED = "#5A616B"    # --text-muted  основной текст письма
TEXT_LIGHT = "#656C77"    # --text-light  дисклеймер / footer
BORDER = "#DCE3EC"        # --nav-border  горизонтальный разделитель
CODE_BG = "#EEF2F7"       # --milk        фон блока OTP-кода / временного пароля
CODE_BORDER = "#C3D2E6"   # --latte       рамка блока кода
CODE_TEXT = "#16233D"     # --espresso    цвет цифр кода
