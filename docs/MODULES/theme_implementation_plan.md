# Цветовые темы — реализация и план развития

> **Статус (2026-07-12): базовая система тем РЕАЛИЗОВАНА** (этапы 1–5 промпта
> `private/prompt-claude-code-themes.md`). Ниже — фактическая архитектура,
> инструкция «как добавить тему», и первоначальный план (сохранён для истории).

## Что реализовано

**Темы:** `coffee-light` (текущий дизайн, по умолчанию), `coffee-dark`,
`nature-light`, `nature-dark` («Природное спокойствие»).
**Режимы:** Светлая / Тёмная / **Системная** (следует `prefers-color-scheme`,
живая реакция на смену темы ОС). **Палитры:** Кофейная / Природная.

Архитектура:

- `mindcare_web/src/styles/tokens/` — per-theme файлы токенов; ключ —
  `data-theme` на `<html>` (`:root` = coffee-light, дефолт без атрибута).
  Легаси-имена (`--coffee`, `--espresso`, …) сохранены как алиасы и
  переопределяются каждой темой **по роли** (espresso: текст → в dark светлый);
  ролевые токены (`--surface`, `--primary`, `--on-surface`, …) — источник
  истины для нового кода; `--*-rgb` триплеты — для `rgba(var(--x-rgb), a)`.
- `src/features/theme/ThemeContext.jsx` — провайдер (palette + mode,
  localStorage `app-theme-palette`/`app-theme-mode`, matchMedia-подписка);
  подключён в `src/app/providers.jsx`.
- `src/features/theme/ThemeToggle.jsx` — сегмент-контрол (режим + палитра)
  в Navbar (desktop + mobile drawer) и topbar CabinetLayout.
- Анти-FOUC скрипт в `public/index.html` (списки палитр/режимов синхронизировать
  с ThemeContext.jsx).
- `npm run test:contrast` (`scripts/check-contrast.js`) — WCAG-проверка пар
  токенов всех тем; исключения с порогом 3.0 задокументированы в скрипте.
- `/theme-preview` — dev-only демо-страница (не попадает в production build).

## Как добавить новую тему/палитру

1. Создать `src/styles/tokens/<palette>-light.css` и `<palette>-dark.css`
   (селектор `:root[data-theme="<palette>-light|dark"]`), заполнить все токены
   по образцу nature-*.
2. Импортировать файлы в `src/app/App.jsx`.
3. Добавить палитру в `PALETTES` (`ThemeContext.jsx`), в `PALETTE_OPTIONS`
   (`ThemeToggle.jsx`) и в список `palettes` анти-FOUC скрипта `public/index.html`.
4. Добавить тему в `THEMES` скрипта `scripts/check-contrast.js` и прогнать
   `npm run test:contrast`.
Компоненты менять не нужно.

## Не реализовано (отложено, отдельные этапы)

> Детальный план отложенных этапов (T1–T7, порядок, оценки, приёмка):
> [`theme_deferred_plan.md`](theme_deferred_plan.md)

- Высококонтрастные `*-hc` темы и режим для слабовидящих по ГОСТ Р 52872-2019
  (панель настроек: шрифт 100/150/200%, схемы Ч/Б, Б/Ч, синяя, бежевая и т.д.).
- Палитра Classic (бело-синяя) — теперь добавляется по инструкции выше.
- Синхронизация выбора темы с профилем пользователя (PATCH /api/auth/profile).
- Дочистка хардкода в pages/features (см. отчёт этапа 4: hex 222→104,
  raw rgba ~301→231; общие компоненты чистые).

---

# Первоначальный план (история)

# План реализации цветовых тем (Light, Dark, Contrast, Classic)

## Контекст
На сайте Центра психологической помощи необходимо внедрить поддержку цветовых тем:
- **Light** (по умолчанию, кофейно-кремовые оттенки)
- **Classic** (классическая бело-синяя тема, стандартный академический стиль)
- **Dark** (тёмный режим)
- **Contrast** (версия для слабовидящих, обязательно для гос. учреждений/ВУЗов)

В данный момент все цвета жестко заданы через CSS-переменные в `:root` внутри `mindcare_web/src/styles/variables.css`.

## Связанные файлы
- `mindcare_web/src/styles/variables.css` — основной файл с палитрой.
- `mindcare_web/src/app/providers.jsx` — точка для подключения контекста.
- `mindcare_web/src/components/Navbar/Navbar.jsx` — место для переключателя и рефакторинга захардкоженных цветов SVG-иконок.

## План работ (для Claude Code)

1. **Создание провайдера темы (`ThemeContext.jsx`)**
   - Размещение: `mindcare_web/src/features/theme/ThemeContext.jsx` (или в `src/app/`)
   - Логика работы с `localStorage` (ключ `app-theme`).
   - Функция установки темы: `document.documentElement.setAttribute('data-theme', theme)`.

2. **Обновление CSS-переменных (`variables.css`)**
   - Сохранить текущие переменные для `[data-theme="light"]` (или `:root`).
   - Добавить селектор `[data-theme="classic"]` с переопределением переменных:
     - Фоны (чисто белый фон, светло-серые элементы).
     - Текст (темно-серый/черный).
     - Акценты (классический синий цвет, ассоциирующийся с доверием/медициной/образованием).
   - Добавить селектор `[data-theme="dark"]` с переопределением переменных:
     - Фоны (тёмные, приглушенные)
     - Текст (светлый)
     - Акценты
   - Добавить селектор `[data-theme="contrast"]` с высококонтрастными цветами:
     - Максимальный контраст (чёрный фон, желтый/белый текст).

3. **Подключение провайдера**
   - Обернуть приложение в `<ThemeProvider>` внутри `mindcare_web/src/app/providers.jsx`.

4. **UI Компонент (`ThemeToggle.jsx`)**
   - Размещение: `mindcare_web/src/components/Navbar/ThemeToggle.jsx`
   - Реализовать выпадающий список (Select) для переключения между четырьмя режимами.
   - Встроить компонент в правую часть `Navbar`.

5. **Устранение хардкода цветов**
   - Найти компоненты с жестко заданными цветами (например, SVG-иконки `UserIcon` и `BurgerIcon` в `Navbar.jsx`, где `stroke="rgba(139,111,71,0.65)"`).
   - Заменить на CSS-переменные (например, `stroke="var(--text-light)"`), чтобы иконки корректно отображались во всех темах.

## Промпт для реализации
При необходимости передачи задачи Claude Code, используйте следующий промпт:

```text
Задача для Claude Code:

Контекст:
Нужно добавить поддержку 4 цветовых тем на frontend:
- Light (текущая кофейная)
- Classic (академическая бело-синяя)
- Dark (темная)
- Contrast (высококонтрастная версия для слабовидящих, обязательна для ВУЗа)

Что нужно сделать:
1. Создать `mindcare_web/src/features/theme/ThemeContext.jsx`: провайдер для 4 тем (`light`, `classic`, `dark`, `contrast`), сохранение в `localStorage`, установка `document.documentElement.setAttribute('data-theme', theme)`.
2. Обновить `mindcare_web/src/styles/variables.css`: добавить `[data-theme="classic"]`, `[data-theme="dark"]` и `[data-theme="contrast"]` с переопределением цветов. Для `classic` использовать чистый белый фон, темно-серый текст и синие акценты.
3. Обернуть `{children}` в `ThemeProvider` внутри `mindcare_web/src/app/providers.jsx`.
4. Создать `ThemeToggle.jsx` (селект выбора из 4 тем) и встроить его в `Navbar.jsx`.
5. Заменить жесткие цвета (`stroke="rgba(139,111,71,0.65)"`) в SVG-иконках `Navbar.jsx` на CSS-переменные.

Ограничения:
Не использовать сторонние библиотеки для темизации (только чистый React Context + CSS Variables).
```
