# UI Components Guide

Правила использования shared UI-компонентов в проекте MindCare Web.

Все компоненты находятся в `mindcare_web/src/components/UI/`.
Перед созданием нового контрола — всегда сверяться с этим списком.

---

## Быстрый выбор

| Нужно сделать | Компонент |
|---|---|
| Action-кнопка (сохранить, удалить, применить) | `Button` |
| Навигационная ссылка в виде кнопки (router) | `ButtonLink` |
| Чекбокс в форме | `Checkbox` |
| On/off переключатель | `Toggle` |
| Интерактивный фильтр-чип | `FilterChip` |
| Статус / роль / состояние сущности | `Badge` |
| Display-only тег контента | `Tag` |
| Выпадающий список | `Select` |
| Множественный выбор | `MultiSelect` |
| Выбор даты (только дата) | `DateInput` |

---

## Button

**Путь:** `src/components/UI/Button/Button.jsx`

**Использовать для:**
- сохранить, отменить, создать, обновить
- удалить (с подтверждением)
- загрузить ещё, назначить, переназначить
- повторить, открыть, применить, сбросить
- icon-кнопки в таблицах (edit, trash, open)

**Варианты:** `primary`, `secondary`, `ghost`, `danger`, `icon`
**Размеры:** `sm`, `md` (default)

**Не создавать** локальные `.btn`, `.btnPrimary`, `.btnSecondary`, `.btnGhost`, `.btnDanger` в feature-модулях, если задача решается через `Button`.

**Feature-specific кнопки допустимы только с явной причиной:**
- кнопка на тёмной карточке, если у `Button` нет нужного варианта (пример: `MaterialCard .btn` с `background: var(--espresso)`)
- chat send button с уникальным layout
- calendar navigation (prev/next месяц)
- close `×` внутри popover/modal, если контекстный
- специальные card controls

---

## ButtonLink

**Путь:** `src/components/UI/Button/ButtonLink.jsx`

**Использовать для:**
- React Router навигационных ссылок, которые визуально выглядят как кнопка
  (router `<Link>` со стилями `Button`: те же `variant`/`size`/`tone`)
- переходов «Открыть карточку», «Перейти в раздел» из таблиц и списков

**Не делать** `Button` + `navigate()` для обычной навигации — семантически
это ссылка (`<a>`), а не кнопка: ломает open-in-new-tab и доступность.

---

## Checkbox

**Путь:** `src/components/UI/Checkbox/Checkbox.jsx`

**Использовать для:**
- согласие с политикой конфиденциальности при регистрации
- `is_active` / `is_published` / `include_deleted` в admin-формах
- любые `<input type="checkbox">` в формах

**Не создавать** кастомные браузерные checkbox без причины.

**Не использовать Checkbox для:**
- Toggle / Switch (это другой компонент)
- task done/undone с feature-specific визуалом
- filter chips
- calendar slots

---

## Toggle

**Путь:** `src/components/UI/Toggle/Toggle.jsx`

**Использовать для:**
- on/off уведомлений
- email / push настройки
- включить / выключить настройку пользователя

Toggle — это `<button type="button" aria-pressed>`, не checkbox.
Семантика: бинарное состояние без submit.

---

## FilterChip

**Путь:** `src/components/UI/FilterChip/FilterChip.jsx`

**Использовать для:**
- фильтр по типу материала, теме, категории
- multi-select фильтры в списках
- active / inactive filter state

FilterChip должен быть `<button type="button" aria-pressed>`.

**Не использовать FilterChip для:**
- display-only тегов контента → используй `Tag`
- status badges → используй `Badge`
- emotion chips (DiaryEntryForm) — feature-specific
- calendar time slots — feature-specific
- removable tags в MultiSelect

---

## Badge

**Путь:** `src/components/UI/Badge/Badge.jsx`

**Тоны:**

| Tone | Использование |
|---|---|
| `success` | опубликовано, активен, психолог |
| `warning` | черновик, ожидает |
| `error` | заблокирован |
| `neutral` | удалён, неизвестный статус |
| `role-student` | роль студент |
| `role-psychologist` | роль психолог |
| `role-admin` | роль администратор |
| `role-supervisor` | роль супервизор |

**Использовать для:**
- статус записи в таблице (опубликовано / черновик)
- активен / скрыт / удалён
- роли пользователей в UsersTable
- статус любой сущности в admin-таблицах

Badge — это display-only `<span>`, не button.

**Мигрировано:** ArticlesTable, NewsTable, CategoriesTable, UsersTable.

**Не использовать Badge для:**
- счётчик над иконкой (count overlay)
- nav badges в CabinetLayout sidebar (feature-specific layout)
- task-card badges с уникальным визуалом (TaskItem)
- декоративный dot-индикатор

---

## Tag

**Путь:** `src/components/UI/Tag/Tag.jsx`

**Варианты:**

| Variant | Использование |
|---|---|
| `public` | тег на публичной странице материала / новости (11px, uppercase) |
| `admin` | тег в admin-таблице (12px, pill shape) |
| `category` | категория в admin-таблице (12px, pill, sand bg) |
| `card` | тег на карточке MaterialCard (clamp 12–13px, uppercase) |

**Использовать для:**
- тема материала (MaterialCard, MaterialsItemPage)
- тег новости (NewsItemPage, NewsTable)
- категория статьи (ArticlesTable)
- словарный тег в TagsTable

Tag — это display-only `<span>`, не button.

**Мигрировано:** MaterialsItemPage, NewsItemPage, ArticlesTable, NewsTable, TagsTable, MaterialCard.

**Не использовать Tag для:**
- фильтр → используй `FilterChip`
- статус / роль → используй `Badge`
- removable chip → feature-specific
- overlay тег внутри кликабельной hero-карточки (FeaturedNews.newsTagOverlay)

---

## Select

**Путь:** `src/components/UI/Select/Select.jsx`

**Использовать для:**
- выпадающие списки в формах admin
- select с поиском, если поддерживается

Не создавать локальные `<select>` без проверки этого компонента.

**Optional `displayLabel` (Stage 31n-hotfix).** Показывает текущее значение,
которого намеренно нет в `options` (значение отображается как выбранное, но в
выпадающем списке не предлагается). Use-case: текущая роль `student` у
редактируемого пользователя — она отображается, но `options` admin edit содержат
только staff/admin (`psychologist`/`supervisor`/`admin`), поэтому вернуться к
`student` через dropdown нельзя. **Backward compatible:** без `displayLabel`
`Select` работает как раньше (если `value` нет в `options` — показывается
`placeholder`).

---

## MultiSelect

**Путь:** `src/components/UI/MultiSelect/MultiSelect.jsx`

**Использовать для:**
- множественный выбор тегов при создании/редактировании новостей и статей
- любой multi-select в admin-формах

Выбранные теги внутри MultiSelect — feature-specific removable chips,
не мигрировать в `Tag` (разная семантика: интерактивные, не display-only).

---

## DateInput

**Путь:** `src/components/UI/DateInput/DateInput.jsx`

**Использовать для:**
- выбор **только даты** в admin-формах (сейчас: «Дата публикации» в news/articles)
- любые date-only поля в новых формах

Кастомный popover-календарь через portal — **не** нативный `<input type="datetime-local">`
или `type="date"` (нативный popup выбивается из дизайна). В новых формах нативные
date/datetime инпуты не использовать без явной причины.

**Контракт (date-only):**

| Аспект | Значение |
|---|---|
| UI `value` | `YYYY-MM-DD` или `''` (controlled) |
| Отображение в поле | `дд.мм.гггг` |
| Хелперы | `isoToDateOnly(iso)` → `YYYY-MM-DD`; `dateOnlyToPublishedAtIso(date)` → ISO datetime |
| API (news/articles) | `published_at` остаётся ISO datetime string / `null`; дата конвертируется в полдень UTC (`T12:00:00.000Z`), чтобы не было сдвига дня по таймзоне |
| Время | в UI не выбирается |
| Scheduling | **нет** — будущая дата не откладывает публикацию |

Popover сам выбирает направление (вниз/вверх) и зажимается в пределах viewport
(`popoverPosition.js` → `computePopoverPosition`); закрывается по Escape и клику вне.

**Не использовать DateInput для:**
- выбора времени / даты-времени → нужен будущий `DateTimePicker` / `TimeInput` (не реализованы)
- записи на приём / выбора слота → нужен будущий `SlotPicker` (не реализован);
  DateInput не является заменой слотам расписания

---

## Shared content utilities

В `src/components/UI` есть компоненты, которые не являются governance controls, но переиспользуются в нескольких местах:

| Компонент | Путь | Назначение |
|---|---|---|
| `ContentPreview` | `src/components/UI/ContentPreview/` | Предпросмотр HTML-контента новости или материала. Использует DOMPurify. |
| `ImageUpload` | `src/components/UI/ImageUpload/` | Drag-drop загрузка изображения обложки. |
| `TiptapEditor` | `src/components/UI/TiptapEditor/` | Rich-text редактор (StarterKit, Image, TextAlign). |

Эти компоненты **не являются** заменой Button / Checkbox / Toggle / FilterChip / Badge / Tag.

Правила при работе с ними:
- Не заменять их на Button/Tag/Badge.
- Не считать их нарушением governance.
- Перед созданием своей логики preview/upload/editor — проверить эти компоненты на переиспользование.
- Изменять только после отдельного анализа задачи.
- Не создавать дубль без явного обоснования.

---

## Общее правило

Перед созданием нового контрола:

1. Проверить `src/components/UI/` — есть ли подходящий компонент.
2. Если подходит — использовать его.
3. Если не подходит — зафиксировать причину в PR-описании или в `docs/UI_TECH_DEBT.md`.
4. Feature-specific элемент без причины — это tech debt.
