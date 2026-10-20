# Handoff: Admin Content CRUD + публичные страницы — 2026-06-04

## Состояние проекта

**Проект:** MindCare — платформа психологической службы ДонГУ
**Этап:** MVP (Этап 1)
**Стек:** FastAPI + SQLAlchemy (sync, psycopg2) + PostgreSQL 15+ / React 19 + CRA + CSS Modules

---

## Что полностью готово в этой сессии

### 1. Media upload (бэкенд)

- `app/media/` — новый модуль
- `POST /api/media/upload` — загрузка изображений (auth)
- Валидация через Pillow по содержимому (не только MIME)
- Сохранение в `media/uploads/YYYY/MM/`, запись в таблицу `media_files`
- StaticFiles смонтированы на `/media` в `main.py`

### 2. News CRUD (бэкенд + фронтенд)

**Бэкенд `app/news/`:**
- `routes_admin.py` — `GET/POST/GET/{uuid}/PATCH/DELETE /api/admin/news/*`
- `routes_public.py` — `GET /api/news`, `GET /api/news/{uuid}`
- `storage.py` — `_news_to_dict`, exclude_unset семантика через dict (не Pydantic)
- `schemas.py` — `NewsRead` содержит `cover_image_uuid` (нужен фронту при редактировании)

**Фронтенд `features/admin/news/`:**
- `useAdminNews` — hook с `requestId` race-condition защитой
- `NewsTable` — дизайн как UsersTable: скелетон, иконки, `editLoadingId`
- `NewsFormModal` — TipTap редактор, ImageUpload, ContentPreview, `formReady` флаг
- `NewsPage` — `handleEdit` с `getAdminNewsItem(uuid)` + catch + `editLoadingId`

### 3. Articles CRUD (бэкенд + фронтенд)

Аналогичная структура как News, плюс:
- Категории (`categories[]`) вместо простого тега
- `excerpt` (краткое описание)
- `GET /api/articles/categories` и `GET /api/admin/articles/categories`

### 4. TipTap rich-text редактор (компонент)

- `components/UI/TiptapEditor/TiptapEditor.jsx`
- Расширения: StarterKit, Image, TextAlign (paragraph + heading)
- Toolbar: Bold, Italic, H1/H2/H3, Lists, Quote, HR, Align (L/C/R/J)
- Вставка изображений: кнопка в toolbar + paste + drag-drop
- `insertImageRef` паттерн для стабильного closure в `editorProps`
- `formReady` флаг — TipTap рендерится только когда форма заполнена данными

### 5. Компоненты

- `Modal` — пропы `wide` (max-width 780px), `zIndex`. Sticky header + scrollable body
- `ImageUpload` — drag-drop, preview, remove
- `ContentPreview` — предпросмотр через DOMPurify + Modal (zIndex 2100)

### 6. Публичные страницы новостей

- `news.api.js` — `normalizeNewsItem()` экспортируется, используется и в `useNews.js` и в `NewsSection.jsx`
- `NewsSection.jsx` — исправлен вызов `getNews({ page:1, size:6 })`, применяется нормализация
- `FeaturedNews.jsx` — показывает обложку (`news.image`) если есть
- `NewsItemPage.jsx` — rich HTML через `DOMPurify.sanitize(news.content)`

### 7. Миграция MaterialsPage на реальный API

- `useMaterials.js` — полный рерайт: `getArticles()` + `getPublicCategories()`
  - "Загрузить ещё" — накапливает страницы
  - `categoryMetaRef` — ref вместо state, исключает двойной fetch при маунте
  - `setSelectedTags` — single-select (API принимает один `category_id`)
  - `reqId` — защита от race conditions
- `materials.api.js` — реэкспорт из `articles.api.js`, mock убран
- `MaterialsPage.jsx` — динамические `tagOptions`/`topicOptions` из хука
- `MaterialsItemPage.jsx` — реальные поля API + DOMPurify для `content`
- `MaterialsGrid.jsx` — принимает `loading`, показывает shimmer-скелетон
- `fix_category_encoding.py` — скрипт исправления CP1251/UTF-8 mismatch в БД

---

## Архитектурные решения

**`formReady` флаг для TipTap:**
TipTap инициализируется один раз при маунте. При редактировании данные грузятся асинхронно. Решение: рендерить `<TiptapEditor>` только после `setForm + setFormReady(true)` — React 18 батчит эти два setState в одном рендере.

**`insertImageRef` паттерн:**
`handlePaste`/`handleDrop` создаются один раз при инициализации TipTap. Ref обновляется каждый рендер, поэтому handler всегда вызывает актуальную функцию загрузки.

**exclude_unset семантика через dict:**
PATCH-эндпоинты передают `body.model_dump(exclude_unset=True)` в storage. Storage проверяет `"key" in data` — это позволяет отличить "поле не передано" от "поле передано как null" (например, удаление обложки).

**`normalizeNewsItem` в `news.api.js`:**
Функция нормализации перенесена из hook в api-модуль — единый источник правды для `useNews.js`, `NewsSection.jsx` и других компонентов.

---

## Роутер (актуальный)

```
/                    → Home (public)
/news                → NewsPage (public)
/news/:id            → NewsItemPage (public)
/materials           → MaterialsPage (public)
/materials/:id       → MaterialsItemPage (public)
/admin/users         → UsersPage
/admin/tags          → TagsPage
/admin/news          → AdminNewsPage
/admin/articles      → AdminArticlesPage
```

---

## Известные ограничения

- **Фильтр тем в материалах** (`topicOptions`) — всегда пустой, публичный API не поддерживает фильтр по тегам
- **Сортировка в материалах** — клиентская (`.reverse()`), не серверная
- **`student/Materials`** — stub на mock-данных, не мигрирован на реальный API
- **Кодировка категорий** — при первом запуске нужно выполнить `python scripts/fix_category_encoding.py` если категории были созданы до исправления

---

## Следующий приоритет

**Admin Categories CRUD** — категории в БД есть, но управлять ими нельзя через UI.
Нужно: `GET/POST/PATCH/DELETE /api/admin/categories`, страница `/admin/categories`.

---

## Промпт для следующего чата

```
Прочитай CLAUDE.md и docs/HANDOFFS/2026-06-04-content-crud-complete.md.

Проект: MindCare — платформа психологической службы ДонГУ.
Admin Content (новости, материалы, TipTap, ImageUpload) полностью реализован.
Публичные страницы новостей и материалов работают на реальном API.

Следующий приоритет: Admin Categories CRUD.
Таблица `categories` в БД уже есть (модель `Category` в app/db/models/content.py).
Категории используются в articles (M:N через article_categories).
Нужен полноценный CRUD: бэкенд /api/admin/categories + фронтенд страница.

Прочитай также:
- mindcare_web/ARCHITECTURE.md
- docs/BACKLOG.md
- docs/DECISIONS.md

После прочтения — предложи план реализации. Не начинай писать код без моего согласия.
```
