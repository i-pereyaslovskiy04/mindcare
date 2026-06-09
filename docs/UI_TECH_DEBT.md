# UI Tech Debt

Реестр осознанных исключений в MindCare Web.

Каждый элемент похож на существующий shared UI-компонент, но намеренно не мигрирован.
Это не баги — это задокументированные решения с обоснованием.

Перед миграцией любого из них — отдельный промпт, отдельная задача.

---

## TaskItem badges

- **Где:** `pages/student/Tasks/components/TaskItem.jsx`
- **Похоже на:** `Badge`
- **Почему оставлено:** task-card badge имеет уникальный визуал, привязанный к task-specific layout (цвет фона таска, приоритет). Мигрировать без аудита TaskItem нельзя.
- **Что делать дальше:** сначала аудит TaskItem, определить нужные тоны, потом отдельная миграция.
- **Можно мигрировать позже:** да
- **Риск:** средний

---

## Calendar time slots

- **Где:** `pages/student/Calendar/CalendarPage.jsx`
- **Похоже на:** `FilterChip` / ChoiceChip
- **Почему оставлено:** time slot — это picker с семантикой выбора времени записи, не фильтр. Визуально похоже, но поведение другое.
- **Что делать дальше:** не мигрировать в FilterChip. Если нужен TimePicker компонент — отдельный аудит.
- **Можно мигрировать позже:** нет без специального TimePicker компонента
- **Риск:** высокий

---

## Calendar format chips

- **Где:** `pages/student/Calendar/CalendarPage.jsx`
- **Похоже на:** `FilterChip`
- **Почему оставлено:** формат консультации (очно / онлайн) — возможно FilterChip, но нужен аудит контекста записи.
- **Что делать дальше:** включить в аудит Calendar при будущей задаче.
- **Можно мигрировать позже:** возможно
- **Риск:** низкий

---

## CabinetLayout nav badges

- **Где:** `components/CabinetLayout/CabinetLayout.jsx`, `CabinetLayout.module.css`
- **Похоже на:** `Badge`
- **Почему оставлено:** nav badge привязан к sidebar layout, имеет абсолютное позиционирование относительно nav-item. Не является отдельным display-only статусом — это layout элемент.
- **Что делать дальше:** при рефакторинге CabinetLayout решить отдельно.
- **Можно мигрировать позже:** да, если badge станет самостоятельным
- **Риск:** низкий

---

## CabinetLayout navBadgeSoon

- **Где:** `components/CabinetLayout/CabinetLayout.module.css`
- **Похоже на:** `Badge` (tone: warning)
- **Почему оставлено:** это "скоро" label-плашка на nav-item, семантически ближе к feature flag чем к статусу. Уникальный визуал.
- **Что делать дальше:** при добавлении реальных фич — убрать или стандартизировать.
- **Можно мигрировать позже:** да
- **Риск:** низкий

---

## CabinetLayout notification dot

- **Где:** `components/CabinetLayout/CabinetLayout.jsx`
- **Похоже на:** count overlay badge
- **Почему оставлено:** декоративный dot-индикатор, не статус сущности. Отсутствует `aria-hidden="true"` — это accessibility debt.
- **Что делать дальше:** добавить `aria-hidden="true"` при задаче на CabinetLayout. Не мигрировать в Badge.
- **Можно мигрировать позже:** нет, не Badge
- **Риск:** низкий (визуал), средний (accessibility)

---

## SearchBar count badge

- **Где:** `pages/materials/components/SearchBar.jsx`
- **Похоже на:** `Badge` (neutral)
- **Почему оставлено:** count badge внутри поисковой строки — inline layout контрол, не статус сущности.
- **Что делать дальше:** не мигрировать в Badge. Если нужен общий компонент — CountBadge отдельно.
- **Можно мигрировать позже:** нет без отдельного CountBadge
- **Риск:** низкий

---

## SearchBar removable chips

- **Где:** `pages/materials/components/SearchBar.jsx`
- **Похоже на:** `Tag` / `FilterChip`
- **Почему оставлено:** removable chip — интерактивный элемент с × для удаления. Ни Tag (display-only), ни FilterChip (toggle-фильтр) не покрывают эту семантику.
- **Что делать дальше:** при задаче на SearchBar — оценить создание RemovableChip компонента.
- **Можно мигрировать позже:** нет без RemovableChip
- **Риск:** средний

---

## FeaturedNews newsTagOverlay

- **Где:** `features/news/FeaturedNews.jsx`, `.newsTagOverlay` в CSS модуле
- **Похоже на:** `Tag` (variant: public)
- **Почему оставлено:** overlay тег поверх hero-изображения внутри кликабельной карточки. Имеет абсолютное позиционирование, backdrop-filter или полупрозрачный фон — визуально отличается от `Tag`. Менять внутри кликабельного элемента небезопасно без аудита.
- **Что делать дальше:** при редизайне FeaturedNews — отдельный аудит overlay tags.
- **Можно мигрировать позже:** возможно, с созданием `variant="overlay"` для Tag
- **Риск:** средний

---

## ContentPreview category/tag

- **Где:** `components/UI/ContentPreview/ContentPreview.jsx`
- **Похоже на:** `Tag` (variant: public / admin)
- **Почему оставлено:** ContentPreview рендерит preview-стиль новости/материала и использует hardcoded цвета внутри preview-контейнера. Мигрировать можно, но нужен отдельный аудит стилей preview.
- **Что делать дальше:** при задаче на ContentPreview — отдельная миграция.
- **Можно мигрировать позже:** да
- **Риск:** низкий

---

## Student MaterialsPage articleTopic

- **Где:** `pages/student/Materials/MaterialsPage.jsx`
- **Похоже на:** `Tag` (variant: public)
- **Почему оставлено:** стиль `.articleTopic` на студенческой странице материалов — отдельный контекст. Не мигрирован в ходе текущего этапа (аудит scope не включал Student pages).
- **Что делать дальше:** при задаче на Student Materials — включить в миграцию.
- **Можно мигрировать позже:** да
- **Риск:** низкий

---

## DiaryEntryForm emotion chips

- **Где:** `pages/student/components/Diary/DiaryEntryForm.jsx`
- **Похоже на:** `FilterChip` / ChoiceChip
- **Почему оставлено:** emotion chip — интерактивный выбор эмоции с emoji, иконкой или иллюстрацией. Это domain-specific контрол для дневника настроения, семантически отличается от фильтра.
- **Что делать дальше:** не мигрировать в FilterChip. Если нужна унификация — отдельный EmotionChip или ChoiceChip компонент.
- **Можно мигрировать позже:** нет без ChoiceChip
- **Риск:** высокий

---

## StudentHome period chips

- **Где:** `pages/student/StudentHome.jsx` (или аналог)
- **Похоже на:** `FilterChip`
- **Почему оставлено:** period chips (сегодня / неделя / месяц) — возможно FilterChip, нужен аудит.
- **Что делать дальше:** при задаче на StudentHome — проверить семантику.
- **Можно мигрировать позже:** возможно
- **Риск:** низкий

---

## StudentHome dark-card buttons

- **Где:** `pages/student/StudentHome.jsx`
- **Похоже на:** `Button` (variant: primary)
- **Почему оставлено:** кнопки на тёмных hero-карточках имеют светлый цвет на тёмном фоне. У `Button` нет варианта для тёмного фона. Feature-specific обоснование.
- **Что делать дальше:** при задаче на Button — добавить `variant="on-dark"` или `tone="light"`.
- **Можно мигрировать позже:** да, после расширения Button
- **Риск:** средний

---

## Chat controls

- **Где:** chat/messaging feature (если реализована)
- **Похоже на:** `Button` (icon variant), `Toggle`
- **Почему оставлено:** chat send button, attach button, emoji toggle — контекстные контролы с уникальным layout внутри chat-input.
- **Что делать дальше:** при задаче на chat — оценить отдельно.
- **Можно мигрировать позже:** частично (send = Button icon)
- **Риск:** низкий

---

## MultiSelect selected tags

- **Где:** `components/UI/MultiSelect/MultiSelect.jsx`
- **Похоже на:** `Tag` (removable)
- **Почему оставлено:** выбранные теги внутри MultiSelect — интерактивные removable chips с × для удаления. Семантика отличается от display-only `Tag`. Внутренний контрол MultiSelect.
- **Что делать дальше:** не мигрировать в `Tag`. При создании RemovableChip — можно переиспользовать.
- **Можно мигрировать позже:** нет без RemovableChip
- **Риск:** низкий

---

## Что добавлять в этот файл

Любой элемент, который:
1. Визуально или функционально похож на shared UI-компонент.
2. Намеренно не мигрирован — с причиной.
3. Требует отдельного решения в будущем.

Не добавлять элементы, которые уже мигрированы.
