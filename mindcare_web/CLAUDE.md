# CLAUDE.md — фронтенд (`mindcare_web/`)

Этот файл загружается, когда работа идёт с файлами под `mindcare_web/`.
Общие правила проекта, ФЗ-152, бэкенд и БД — в корневом `CLAUDE.md`.
Полные правила фронта — в `mindcare_web/ARCHITECTURE.md`.

### Структура

Актуальный состав — `ls mindcare_web/src/`. Слои: `app/` (shell), `api/` (все
HTTP-вызовы), `features/` (домены), `components/UI/` (shared-примитивы),
`pages/` (только композиция, без fetch), `hooks/`, `styles/`, `data/` (только mock).

**Ключевые правила фронта:**

```
✅ Все HTTP-запросы только через api/*.api.js
✅ Pages — только композиция, никакого fetch, никакой логики
✅ Серверная фильтрация и пагинация для списков > 50 элементов
✅ Hook-контракт для списков: { items, loading, error, total, page, setPage, query, setQuery, filters, setFilters, refetch }
✅ CSS Modules — один .module.css на компонент
❌ Не добавлять fetch в components/ или pages/ напрямую
❌ Не фильтровать items на клиенте если список из БД
❌ Не использовать data/ как постоянный источник данных
```

**Терминология админки:**
- `/admin/categories` в UI называется «Типы материалов», но технически остаётся `categories`
- `/admin/tags` в UI называется «Темы», но технически остаётся `tags`
- Не переименовывать API paths, модели и файлы ради пользовательских label

**Breakpoints:** разные по слоям осознанно — Messenger 900px, CabinetLayout 600px
(+980px icon-rail). Не «выравнивать» их между собой.

---

### Frontend: темы и доступность

Система тем на дизайн-токенах. Подробности:
[`docs/MODULES/theme_implementation_plan.md`](docs/MODULES/theme_implementation_plan.md),
[`docs/MODULES/theme_gost_checklist.md`](docs/MODULES/theme_gost_checklist.md).

```
✅ Цвета — ТОЛЬКО через CSS-переменные из src/styles/tokens/ (per-theme файлы,
   ключ — data-theme на <html>). Ни одного raw hex/rgba в компонентах
✅ Палитры: coffee (по умолчанию, текущий дизайн), nature, classic, hc (AAA);
   режимы: light / dark / system (следит за prefers-color-scheme вживую).
   Итог: data-theme="{palette}-{light|dark}"
✅ Новый код пишется на ролевых токенах (--surface, --primary, --on-surface,
   --outline, --error/--success/--warning, --shadow-*); легаси-имена
   (--coffee, --espresso, --milk…) — алиасы, переопределяются темой ПО РОЛИ
✅ Полупрозрачность — rgba(var(--x-rgb), a) (есть --coffee-rgb, --espresso-rgb,
   --shadow-rgb, --error-rgb, --success-rgb, --milk-rgb, --latte-rgb, --text-*-rgb)
✅ Тема авторизованного хранится в профиле (users.ui_theme_palette/ui_theme_mode,
   PATCH /api/auth/profile — частичный, unset ≠ null); приоритет источников:
   явный выбор в сессии > профиль > localStorage > default; запись — soft-fail
✅ Новая палитра = 2 css-файла токенов + PALETTES + PALETTE_OPTIONS + список в
   анти-FOUC скрипте public/index.html + THEMES в scripts/check-contrast.js +
   ThemePalette в app/auth/schemas.py. Компоненты НЕ меняются
✅ Перед коммитом frontend-изменений с цветами: npm run test:contrast (WCAG AA;
   для hc и схем ГОСТ — AAA 7:1)
✅ Режим для слабовидящих (ГОСТ Р 52872-2019) — отдельный режим, НЕ палитра:
   src/features/a11y/ (A11yContext/A11yToggle/A11yPanel) + styles/tokens/a11y.css;
   в нём все токены сведены к паре --a11y-bg/--a11y-fg
❌ Не добавлять hex/rgba в компоненты; исключения (brand-цвета соцсетей,
   декоративные градиенты обложек, тёмный вьювер медиа) — только с комментарием
❌ Не смешивать A11yContext и ThemeContext — это разные механизмы
❌ Не удалять и не переименовывать легаси-имена токенов (миграция постепенная)
```


---

### Frontend: UI governance

Полные правила shared UI и аудитов описаны в:

- `docs/UI_COMPONENTS_GUIDE.md`
- `docs/UI_TECH_DEBT.md`
- `docs/FRONTEND_CHECKLIST.md`
- `docs/AUDIT_RULES.md`

Перед любыми изменениями frontend UI сначала проверить:

```text
src/components/UI
```

Базовые shared UI controls, которые обязательно учитывать при создании локальных контролов:

```text
src/components/UI/Button            (Button.jsx + ButtonLink.jsx)
src/components/UI/Checkbox
src/components/UI/Toggle
src/components/UI/FilterChip
src/components/UI/Badge
src/components/UI/Tag
src/components/UI/Select
src/components/UI/MultiSelect
src/components/UI/DateInput
```

В `src/components/UI` также есть более сложные shared utilities:

- `ContentPreview` — предпросмотр HTML-контента новости/материала (DOMPurify).
- `ImageUpload` — drag-drop загрузка обложки.
- `TiptapEditor` — rich-text редактор.

Они не являются заменой Button/Checkbox/Toggle/FilterChip/Badge/Tag, но перед созданием preview/upload/editor-логики нужно проверить их повторное использование.

Правила использования:

```text
✅ Button — обычные action-кнопки: сохранить, отменить, удалить, загрузить ещё, назначить, повторить, применить.
✅ ButtonLink — React Router навигационные ссылки, выглядящие как кнопки (router <Link> со стилями Button). Не делать Button + navigate() для обычной навигации.
✅ Checkbox — настоящие form-checkbox: согласие, active/inactive, published/unpublished, include deleted.
✅ Toggle — on/off переключатели: уведомления, настройки, включить/выключить.
✅ FilterChip — интерактивные фильтр-чипы с active/inactive состоянием.
✅ Badge — display-only статусы, роли и состояния: опубликовано, черновик, активен, заблокирован, роль пользователя.
✅ Tag — display-only теги контента: тема материала, тег новости, категория статьи.
✅ Select / MultiSelect — выбор одного или нескольких значений.
✅ DateInput — выбор ТОЛЬКО даты (value YYYY-MM-DD, кастомный popover). Перед созданием локального календаря/date-поля проверить src/components/UI/DateInput. Не использовать нативный datetime-local/date в новых формах без причины.
✅ TimePicker — shared выбор времени (`HH:MM`, поминутно 00..59), без native `type=time`.
✅ DateTimeInput — shared дата+время на базе DateInput+TimePicker, без native `datetime-local`.
   Используется для групповых занятий и похожих форм. Для выбора свободного слота записи
   всё ещё использовать feature-specific slot UI, а не DateInput как замену слотам.
```

Запрещено без отдельного обоснования:

```text
❌ Создавать локальные .btn*, .checkbox*, .toggle*, .chip*, .badge*, .tag*, если уже есть подходящий shared-компонент.
❌ Писать локальный UI-контрол, не проверив src/components/UI.
❌ Дублировать стили Button / Checkbox / Toggle / FilterChip / Badge / Tag в CSS Modules.
❌ Использовать button там, где элемент display-only и должен быть span.
❌ Использовать span/div там, где элемент интерактивный и должен быть button/input.
```

Feature-specific UI разрешён только с обоснованием в финальном отчёте.

Осознанные исключения (не мигрировать без отдельного решения):

```text
- Calendar time slots / time picker
- Calendar format chips
- CabinetLayout nav badges
- CabinetLayout navBadgeSoon
- CabinetLayout notification dot
- SearchBar count overlay
- SearchBar removable chips
- TaskItem badges
- Chat controls
- DiaryEntryForm emotion chips
- FeaturedNews newsTagOverlay
- ContentPreview category/tag
- Student MaterialsPage articleTopic
- StudentHome period chips
- StudentHome dark-card buttons
- MultiSelect selected tags внутри shared MultiSelect
```

Если задача затрагивает похожий UI-элемент, сначала свериться с `docs/UI_TECH_DEBT.md`.
Если элемент там числится как feature-specific — не мигрировать без отдельного решения.

---

### Frontend task checklist

Перед завершением любой frontend-задачи проверить:

```text
- Использованы shared UI-компоненты там, где они подходят.
- Не добавлены новые локальные .btn*, .badge*, .tag*, .chip*, .toggle*, .checkbox* без причины.
- Feature-specific элементы явно обоснованы.
- Интерактивные button имеют type="button", если это не submit.
- Toggle / FilterChip / choice-like controls имеют aria-pressed или корректную семантику.
- Декоративные элементы имеют aria-hidden="true".
- Display-only элементы не рендерятся как button.
- Цвета берутся из CSS variables проекта, а не из случайных hex.
- Проверен responsive для затронутых страниц.
- Запущен build.
```

В финальном отчёте по frontend-задаче обязательно указать:

```text
1. Какие файлы изменены.
2. Какие shared UI-компоненты использованы.
3. Какие feature-specific элементы намеренно оставлены.
4. Какие CSS-классы удалены.
5. Прошёл ли build.
6. Есть ли visual/accessibility risks.
```

---

### Соглашения по коду: Frontend

> Полные правила — в `mindcare_web/ARCHITECTURE.md`. Здесь только самое важное для быстрой работы.

**Именование:**
```
React компонент  → PascalCase       → UserCard.jsx
Hook             → camelCase + use  → useAdminUsers.js
API модуль       → camelCase + .api → users.api.js
CSS Module       → совпадает с компонентом → UserCard.module.css
```

**Структура нового feature-модуля:**
```
features/<domain>/
├── ui/                    — React-компоненты домена
├── hooks/                 — hooks специфичные для домена
└── components/            — вспомогательные компоненты
```

**Hook-контракты (строго):**
```js
// Список с серверной пагинацией (для всех admin-списков)
return { items, loading, error, total, page, setPage, query, setQuery, filters, setFilters, refetch }

// Один объект или короткий список
return { data, loading, error, refetch }

// Форма
return { values, errors, handleChange, handleSubmit }
```

**API-вызовы:**
```js
// Все вызовы через api/client.js — никогда fetch() напрямую в компонентах
// client.js автоматически добавляет Authorization: Bearer <token>
// и обрабатывает 401 (logout + redirect)
```

**CSS:**
```css
/* Классы в camelCase */
.cardTitle { }
.btnPrimary { }

/* Один .module.css на компонент — не шарить между компонентами */
/* Никаких глобальных селекторов внутри модуля */
```
