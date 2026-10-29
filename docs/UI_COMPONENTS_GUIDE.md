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
| Выбор времени | `TimePicker` |
| Выбор даты и времени | `DateTimeInput` |

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

**Optional `id`, `aria-invalid`, `aria-describedby` (2026-10-15).** `id` получает
кнопка-контрол (цель фокуса при ошибке; без него генерируется). При `error`
контрол получает `aria-invalid="true"` и `aria-describedby` на id сообщения об
ошибке (`<id>-error`); без `error` новых атрибутов нет.

**Optional `appearance="field"` (2026-10-15).** Вид TextField: подпись
(13px/600, sentence case — без принудительного uppercase), рамка `--outline`, фон
`--surface`, фокус-кольцо, текст
ошибки 12.5px и общая коробка (`min-height` 40px вместо фиксированной высоты —
контрол растёт, а не обрезает). По умолчанию (`appearance="default"`) вид прежний;
выпадающий список не меняется.

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
- выбора времени / даты-времени → используй `TimePicker` / `DateTimeInput`
- записи на приём / выбора свободного слота → нужен feature-specific slot picker;
  DateInput не является заменой слотам расписания

---

## TimePicker

**Путь:** `src/components/UI/TimePicker/TimePicker.jsx`

**Использовать для:**
- выбора времени в формах расписания, перерывов, разовых изменений;
- любых новых `HH:MM` полей, где нужен единый дизайн.

Контракт:

| Аспект | Значение |
|---|---|
| UI `value` | `HH:MM` или `''` |
| Минуты | по умолчанию поминутно `00..59` |
| Native input | не используется (`type="text"` + popover) |

**Не использовать TimePicker для:**
- выбора доступного appointment-слота студентом или supervisor'ом — это отдельная
  feature-specific сетка слотов, потому что слоты приходят из backend-расчёта доступности.

---

## DateTimeInput

**Путь:** `src/components/UI/DateTimeInput/DateTimeInput.jsx`

Композиция `DateInput + TimePicker` для выбора даты и времени без native
`datetime-local`. Используется, например, при создании групповых занятий.

Контракт:

| Аспект | Значение |
|---|---|
| UI `value` | `YYYY-MM-DDTHH:MM` или `''` |
| Date part | через shared `DateInput` |
| Time part | через shared `TimePicker` |

---

## Tabs

Путь: `components/UI/Tabs/Tabs.jsx`. Tablist с автоактивацией (стрелки, Home/End, roving tabIndex).
Единственная реализация навигационных вкладок проекта (2026-10-28): настройки всех кабинетов, материалы, сессии психолога, журнал аудита. Свои вкладки в фичах не заводить. Props: `tabs [{id,label}]`, `active`, `onChange`, `label` (aria-label списка), `idPrefix`, `fill` (равные колонки на всю ширину колонки страницы; без него ширина по содержимому), `className` (внешняя раскладка: у компонента своих внешних отступов нет). Вид один: сегменты на подложке, выбранная — поверхность, рамка `--outline`, тень и жирное начертание (без акцентной заливки; прежний `indicator` удалён). На ≤480px вкладки всегда — равные колонки, на ≤380px — столбец. Панели рисует потребитель: `role="tabpanel"`, `id={tabPanelId(prefix,id)}`, `aria-labelledby={tabButtonId(prefix,id)}`; неактивные держать смонтированными с `hidden` (содержимое можно не монтировать, но сама панель нужна для `aria-controls`). Режим ГОСТ принудительно перекрашивает `button`, поэтому выбранная вкладка в нём инвертируется и получает внутреннюю рамку. Используется: `/student/settings`, `/psychologist|supervisor/settings`, `/psychologist/materials`, `/supervisor/materials`, `/psychologist/appointments`, журнал аудита (`AuditTabs` — обёртка с прежними id). Правило `fill` (2026-10-29): вкладки, переключающие разделы всей страницы, передают `fill` — их ширина равна ширине колонки страницы (во всех местах выше); вкладки внутри карточки или панели фильтров остаются по содержимому. Отдельных `MaterialsTabs` и подобных обёрток ради ширины не заводить.

## TableShell

Путь: `components/UI/TableShell/TableShell.jsx` (2026-10-29, пилот — `/admin/users`). Оболочка семантической таблицы: карточка-контейнер, `<table>`, `caption` (доступное имя; по умолчанию скрыт классом `visually-hidden`, `captionVisible` показывает) и базовые стили `th`/`td`. Props: `caption`, `captionVisible`, `className` (контейнер), `tableClassName`, остальные (`aria-*`, `id`) — на `<table>`; `thead`/`tbody` передаёт фича. Shell не знает о данных: колонки, состояния загрузки/пусто/ошибка, права и действия остаются в фиче. `overflow-x: auto` контейнера — только страховка. Универсального `DataTable` (конфиг колонок, приоритеты, авто-карточки) в проекте нет и пока не вводится.

**Широкая таблица + список строк фичи (пилот `/admin/users`, на визуальном согласовании).** Если таблица не помещается в колонку, фича рендерит рядом свой список (`ul/li` в одной карточке, записи разделены линией — строки данных, не карточки профиля), а не перекладывает `tr/td` в карточки через CSS. Три режима по ширине колонки контента (container query, `container-type: inline-size` на обёртке фичи): **wide** — таблица; **compact** — строка «основное (ФИО) + вторичное (email) | метки (роли, статус) | действие + ⋮», под ней детали (даты) одной строкой; **mobile** — та же разметка, вертикальнее: основное и ⋮ сверху, метки, затем детали и основное действие. Базовый вариант и fallback без container queries — mobile. Все режимы получают одни данные и один набор обработчиков страницы; диалоги монтируются один раз; смена ширины не делает запросов. Границы — по замеру Playwright (где строка ещё плотная и основная колонка читаема), не по viewport. Образец: `features/admin/users` — `UsersDataView` → `UsersTable` (на `TableShell`) / `UsersCompactList`, матрица действий — `userActions.js`.

## ActionsMenu

Путь: `components/UI/ActionsMenu/ActionsMenu.jsx`. Кнопка «⋮» с меню второстепенных действий строки; основное действие фича показывает обычной кнопкой рядом. Props: `triggerLabel` (доступное имя кнопки и меню, напр. «Другие действия: ФИО»), `items [{id, label, onSelect, tone?: 'danger'|'success', disabled?}]` — уже отфильтрованные фичей (меню о ролях, правах и API не знает), `className`. Пустой `items` — ничего не рендерится. Меню — portal в `body` с `position: fixed` (не обрезается контейнером таблицы), позиция — `shared/lib/actionsMenuPosition.js` (её же использует меню сообщения в чате). Клавиатура: Enter/Space/↓ на кнопке открывают меню с фокусом на первом доступном пункте; ↑/↓/Home/End по пунктам (недоступные пропускаются); Escape закрывает и возвращает фокус на кнопку; Tab закрывает и ведёт фокус дальше от кнопки; при выборе фокус возвращается на кнопку до вызова `onSelect` (открытый действием `Modal` после закрытия вернёт его туда же). Touch (`hover: none`): кнопка и пункты не меньше 44px.

## Контейнеры страниц кабинетов

Ширину задаёт layout, а не страница (2026-10-29). `CabinetLayout` и `AdminLayout`: `.content` — поля (28/36px, на ≤980px 20/16px), внутри `.contentInner { width:100%; max-width:var(--cabinet-content-max) /* 1180px */; margin:0 auto }`. Корень страницы — прямой ребёнок `.contentInner`.

- **Рабочая страница** (списки, таблицы, библиотека, календарь, сообщения): корень без своих `max-width`, `padding` и `margin` — занимает всю колонку. Поверх `.contentInner` контейнер не дублировать (так раньше были сдвинуты на 68px «Мои студенты», «Назначение психологов», «Подтверждение студентов»).
- **Страница-форма** (настройки всех кабинетов, `/admin/settings`, `/admin/email-domains`, мастер записи супервизора): ширину ограничивает корень — `width:100%; max-width:var(--cabinet-narrow-max) /* 760px */; margin-inline:auto`. Заголовок, описание, вкладки и панели внутри — с общим левым и правым краем. Не ставить `max-width` отдельным детям (`.tabs`, `.panel`, `.stack`) без центрирования: колонка прижимается к левому краю и визуально уезжает влево.
- **Detail-страницы публичной части** (`/materials/:id`, `/news/:id`) держат свою узкую колонку по центру `.container` — их не трогать.
- Токены — в `styles/variables.css`. Тулбары и фильтры над таблицами переносятся (`flex-wrap: wrap`), а не растягивают content-area на мобильном; в двухколоночных сетках гибкая колонка — `minmax(0, 1fr)`.
- Контракт закреплён тестом `src/styles/pageLayout.test.js` (без пиксельных проверок).

## TextField

Путь: `components/UI/TextField/TextField.jsx` (`forwardRef`). Подписанное поле: `label` связан с `input` через `htmlFor`/`id`, `hint` и `error` — через `aria-describedby`, ошибка — `role="alert"` и `aria-invalid`. Остальные props (`type`, `value`, `onChange`, `maxLength`, `readOnly`, `inputMode`…) передаются в `<input>`. Prop `appearance="field"` включает коробку, общую со `Select appearance="field"` (border-box, рамка 1px, вертикальный padding 9px, `line-height` 1.4, `min-height` 40px): контролы одинаковой высоты, при увеличенном шрифте/межстрочном интервале растут и не обрезают текст. По умолчанию вид прежний. Подпись — sentence case (13px/600, `--on-surface`), как пишется в тексте («ФИО», «Email»), без принудительного uppercase (2026-10-27, страница настроек — единственный потребитель).

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

## Chat / Messenger UI (feature-specific)

| Компонент | Путь | Назначение |
|---|---|---|
| `MessageBubble` | `src/features/chat/components/MessageBubble.jsx` | Визуальное облачко сообщения (текст + meta: время/«изменено»/✓✓). Variants: `incoming`/`outgoing`/`system`. |
| `MessageActionsMenu` | `src/features/chat/components/` | Кебаб-меню «…» для своего сообщения — «Редактировать»/«Удалить». |
| `DeleteMessageDialog` | `src/features/chat/components/` | Confirm-диалог перед удалением сообщения, построен на shared `Modal`/`Button`. |

**Governance:** эти компоненты — feature-specific Messenger-логика, **не** глобальные
shared UI controls из таблицы выше. Не переносить `MessageBubble` в `src/components/UI`,
пока не появится второй независимый потребитель за пределами чата. `MessageActionsMenu`
переиспользует существующие shared-примитивы (не дублирует Button/Modal). Перед
добавлением нового chat-контрола — проверить `src/features/chat/components/` и
`src/components/UI`.

---

## Общее правило

Перед созданием нового контрола:

1. Проверить `src/components/UI/` — есть ли подходящий компонент.
2. Если подходит — использовать его.
3. Если не подходит — зафиксировать причину в PR-описании или в `docs/UI_TECH_DEBT.md`.
4. Feature-specific элемент без причины — это tech debt.
