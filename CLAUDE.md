# CLAUDE.md

Этот файл описывает проект для Claude Code. Прочитай его целиком перед любой задачей.

## О проекте

**MindCare** — веб-платформа психологической службы Донецкого государственного университета.

Функциональность:
- Запись студентов на консультации к штатным психологам
- Онлайн-психодиагностика (тесты с автоподсчётом результатов)
- Блог, новости, справочник ресурсов помощи
- Модуль вопросов и ответов (Q&A)
- Личные кабинеты по ролям (студент, психолог, супервизор, админ)
- Административная панель

**Критически важно:** платформа работает с психологическими и медицинскими данными.
Она попадает под **ФЗ-152 РФ** (защита персональных данных). Это влияет на:
- Все данные пользователей хранятся на серверах в РФ
- Согласие на обработку ПДн фиксируется в `consent_records` при регистрации
- Перед каждым тестом и записью на консультацию проверяется актуальность согласия
- Заметки сессий (`session_notes`) шифруются на уровне приложения: Fernet, `enc:v1:` prefix, `app/core/encryption.py`; не писать plaintext в `SessionNote.content`, не логировать `content`
- IP-адреса анонимизируются через 90 дней (`anonymize_old_ips()` в БД)

**Монорепо с двумя проектами:**
- `mindcare_api/` — Python FastAPI бэкенд, порт 8000
- `mindcare_web/` — React 19 фронтенд (CRA), порт 3000

## Команды

### Backend (`mindcare_api/`)

```powershell
# Активация виртуального окружения (Windows, обязательно перед всем остальным)
.venv\Scripts\Activate.ps1

# Если PowerShell блокирует скрипты:
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

```bash
# Установка зависимостей (после активации venv)
pip install -r requirements.txt

# Запуск dev-сервера (из папки mindcare_api/)
uvicorn app.main:app --reload

# Создание первого администратора (интерактивный скрипт)
python scripts/create_admin.py

# Диагностика SMTP
python scripts/test_smtp.py

# Создание будущих партиций audit-таблиц (запускать отдельно, не из FastAPI)
# Рекомендуется запускать раз в год с запасом 24+ месяца
python scripts/ensure_audit_partitions.py --months-ahead 24
python scripts/ensure_audit_partitions.py --months-ahead 24 --dry-run  # проверка без DDL
```

### База данных

```bash
# ══════════════════════════════════════════════════════════
# ПОРЯДОК ЗАПУСКА (ОБЯЗАТЕЛЬНО перед стартом приложения):
# ══════════════════════════════════════════════════════════

# 1. Применить все Alembic-миграции (создаёт/обновляет схему)
cd mindcare_api/
alembic upgrade head

# 2. Запустить приложение (seed выполнится автоматически в lifespan)
uvicorn app.main:app --reload

# ══════════════════════════════════════════════════════════

# Подключение к БД для ручных запросов
psql -U MindcareUser -d mindcare

# Проверить текущую версию схемы
cd mindcare_api/ && alembic current

# Создать новую миграцию после изменения ORM-моделей
cd mindcare_api/ && alembic revision --autogenerate -m "describe_change"

# История миграций
cd mindcare_api/ && alembic history
```

> **Важно:** схема БД управляется **только** через Alembic.
> `Base.metadata.create_all()` **удалён** — не использовать.
> Все 48 таблиц создаются через `alembic upgrade head`.
> Audit-таблицы (`auth_log`, `audit_log`, `data_change_log`) включены в Alembic
> начиная с migration `3a7c5e2b8f1d`.
>
> FastAPI при старте **НЕ** применяет миграции — только проверяет revision
> и выдаёт WARNING если DB отстаёт от head.

### Frontend (`mindcare_web/`)

```bash
# Установка зависимостей
npm install

# Dev-сервер (порт 3000, проксирует /api/* на порт 8000)
npm start

# Продакшен-сборка
npm run build

# Запуск всех тестов
npm test

# Запуск одного файла
npm test -- --testPathPattern=App.test.js
```

> **Важно:** для full-stack разработки нужно запустить **оба** сервера одновременно.
> Фронт проксирует `/api/*` запросы на `http://localhost:8000` через настройку в `package.json`.

## Тестирование

### Правила для Claude Code

При изменении backend/security/auth:

```
✅ Проверить, есть ли релевантные тесты в mindcare_api/tests/
✅ Добавить или обновить тесты для изменённой логики
✅ Запустить релевантный pytest перед завершением задачи
✅ Если тесты не добавлены — объяснить причину в финальном отчёте
❌ Не утверждать "покрыто тестами", если покрыта только конкретная зона
```

### Команды

**Backend:**
```bash
cd mindcare_api
.venv\Scripts\python.exe -m compileall app -q
.venv\Scripts\python.exe -m pytest tests/test_change_password.py -v
.venv\Scripts\python.exe -m pytest tests/ -v
```

**Frontend:**
```bash
cd mindcare_web
npm run lint
npm run build
```

**Через скрипты в корне проекта:**
```powershell
.\test.ps1    # compileall + все backend-тесты (без запуска проекта)
.\start.ps1   # backend-тесты, затем запуск проекта
```

### Уровни тестов

| Уровень | Что покрывает | Когда добавлять |
|---------|---------------|-----------------|
| Unit | Service/helper logic, без реальной БД | Обязательно для новых auth/security/critical изменений |
| API/Integration | Route → deps → service → storage → DB | Желательно для auth/session/permissions/encryption |
| Manual smoke | Пользовательские сценарии | Обязателен при UI/UX-sensitive изменениях |
| E2E | Полный browser flow | Позже, после стабилизации UI |

### Текущее покрытие

Всего: **138 passed** (`.\test.ps1`). Integration-тесты требуют запущенный dev PostgreSQL на alembic head.

| Файл | Что покрыто |
|------|-------------|
| `tests/test_change_password.py` | `service.change_password` — 13 сценариев |
| `tests/test_encryption.py` | `app.core.encryption` — 21 сценарий |
| `tests/test_normalization.py` | `normalize_email` + OTP/storage нормализация — 16 |
| `tests/test_smtp_transport.py` | SMTP TLS/SSL transport — 21 |
| `tests/test_rate_limit.py` | sliding-window limiter (unit) — 18 |
| `tests/test_session_security.py` | generate/hash session token (unit) — 8 |
| `tests/integration/test_email_normalization_api.py` | register/login/reset API — 11 |
| `tests/integration/test_rate_limit_api.py` | 429-поведение auth API — 10 |
| `tests/integration/test_session_token_hashing.py` | hashed tokens end-to-end — 9 |
| `tests/integration/test_legal_basis_api.py` | legal basis records API — 11 |

---

## Архитектура

### Стек

| Слой | Технология |
|------|-----------|
| Backend | Python 3.11+, FastAPI, SQLAlchemy 2.0 (sync), psycopg2 |
| Frontend | React 19, React Router 7, CSS Modules, CRA |
| БД | PostgreSQL 15+ |
| Email | SMTP через smtplib (настроен, работает) |
| Auth | Сессии в БД (`user_sessions`), не JWT |

> **Важно:** SQLAlchemy используется в **синхронном** режиме (psycopg2, не asyncpg).
> Все эндпоинты — `def`, не `async def`. Не менять на async без обсуждения.

---

### Backend: структура модулей

```
mindcare_api/
├── app/
│   ├── main.py              — точка входа FastAPI, подключение роутеров
│   ├── core/
│   │   ├── config.py        — настройки из .env (pydantic-settings)
│   │   ├── encryption.py    — Fernet encrypt/decrypt (enc:v1:) для session_notes
│   │   ├── normalization.py — normalize_email()
│   │   └── rate_limit.py    — in-memory sliding-window limiter для auth (Stage 21)
│   ├── db/
│   │   ├── base.py          — Base = declarative_base()
│   │   ├── session.py       — engine, SessionLocal
│   │   ├── init_db.py       — startup: ensure_database + check_migrations + seed
│   │   ├── seed.py          — идемпотентный seed
│   │   └── models/          — ORM-модели (12 модулей, 48 таблиц; chat.py — Stage 28b)
│   ├── auth/                — аутентификация и авторизация
│   │   ├── audit.py         — log_auth_event() для auth_log
│   │   ├── deps.py          — get_current_user, require_role
│   │   ├── otp_service.py   — создание и верификация OTP
│   │   ├── routes.py        — /api/auth/* эндпоинты (+ rate limiting)
│   │   ├── schemas.py       — Pydantic-схемы auth
│   │   ├── security.py      — generate_session_token(), hash_session_token() (Stage 22b)
│   │   ├── service.py       — бизнес-логика auth
│   │   └── storage.py       — работа с БД (users, sessions hash-on-lookup,
│   │                          last_active с debounce 5 мин — Stage 26, consents)
│   ├── users/               — управление пользователями (admin)
│   │   ├── routes_admin.py  — /api/admin/users/* эндпоинты (только admin)
│   │   ├── schemas.py       — Pydantic-схемы users (+ legal_basis_confirmed)
│   │   ├── service.py       — бизнес-логика users
│   │   └── storage.py       — работа с БД (find_users, create_user + legal basis record)
│   ├── tags/                — управление тегами контента
│   │   ├── routes_admin.py  — /api/admin/tags/* (admin + supervisor)
│   │   ├── routes_public.py — /api/tags/ (autocomplete, без auth)
│   │   ├── schemas.py       — Pydantic-схемы tags
│   │   ├── service.py       — бизнес-логика + нормализация имени
│   │   └── storage.py       — работа с БД, коррелированные подзапросы счётчиков
│   ├── categories/          — управление типами материалов (categories)
│   │   ├── routes_admin.py  — /api/admin/categories/* (admin + supervisor)
│   │   ├── schemas.py       — Pydantic-схемы categories
│   │   ├── service.py       — бизнес-логика + HTTP-статусы через текущий AuthError-паттерн
│   │   └── storage.py       — CRUD, slug generation, soft delete через is_active=False
│   ├── media/               — загрузка изображений
│   │   ├── routes.py        — POST /api/media/upload (auth)
│   │   ├── schemas.py       — MediaFileRead
│   │   └── service.py       — валидация через Pillow, сохранение в media/uploads/YYYY/MM/
│   ├── news/                — новости
│   │   ├── routes_admin.py  — /api/admin/news/* (admin + supervisor)
│   │   ├── routes_public.py — /api/news/* (публичный)
│   │   ├── schemas.py       — NewsCreate, NewsUpdate, NewsRead, NewsListItem
│   │   ├── service.py       — бизнес-логика, title.strip()
│   │   └── storage.py       — _news_to_dict, exclude_unset семантика через dict
│   ├── articles/            — материалы/статьи
│   │   ├── routes_admin.py  — /api/admin/articles/* (admin + supervisor)
│   │   ├── routes_public.py — /api/articles/* (публичный) + /api/articles/categories
│   │   ├── schemas.py       — ArticleCreate, ArticleUpdate, ArticleRead, CategoryRead
│   │   ├── service.py       — бизнес-логика
│   │   └── storage.py       — _article_to_dict, _sync_categories, _sync_tags
│   ├── session_notes/       — /api/session-notes/* (Fernet encrypt-on-write)
│   ├── supervisor/          — /api/supervisor/* (назначения студент ↔ психолог)
│   ├── psychologist/        — /api/psychologist/* (свои студенты)
│   └── services/
│       ├── _smtp.py         — SMTP транспорт (dev/smtp режимы, внутренний)
│       └── email_service.py — формирование писем по событиям
├── scripts/
│   ├── create_admin.py            — создание первого админа (+ legal basis record)
│   ├── ensure_audit_partitions.py — будущие партиции audit-таблиц
│   ├── backfill_legal_basis.py    — backfill legal basis (--dry-run default)
│   └── test_smtp.py               — диагностика SMTP
└── db/
    └── sql/
        ├── full_schema.sql  — полная схема (001-010 склеены)
        ├── 001_extensions_types.sql
        ├── 002_users_auth.sql
        ├── ...
        └── 010_seed_data.sql
```

**Правила бэка:**

```
✅ Все эндпоинты — def (не async def)
✅ Роли проверяются на бэке через require_role — не только на фронте
✅ Email всегда нормализуется: email.lower().strip()
✅ Пароли — bcrypt через passlib. Никакого sha256, md5
✅ OTP-коды — SHA-256 хеш в БД, plaintext только в email. Никакого plaintext.
✅ Токены сброса пароля — хранятся как хеш, не plaintext
✅ Soft delete — deleted_at, не физическое удаление
✅ Внешний API использует users.uuid (UUID), не users.id (INT)
✅ Схема БД — только через Alembic (alembic upgrade head перед стартом)
✅ consent_records — ТОЛЬКО личное согласие субъекта (студент сам принимает политику)
✅ Для admin-created psychologist/supervisor/admin — user_legal_basis_records
   (документированное основание организации; чекбокс в UI формулируется как
   «Подтверждаю наличие документированного основания для создания учётной
   записи и обработки персональных данных пользователя»)
✅ session_notes: psychologist — только свои; supervisor — content только поштучно
   и под audit (session_note_content_read); admin — metadata-only без decrypt
✅ Staff-чтение терапевтического content ОБЯЗАНО писать audit-событие (без plaintext)
✅ Metadata-путь session_notes не должен вызывать decrypt_text
❌ Не расширять admin-доступ к therapeutic content без отдельного compliance-решения
❌ Не использовать consent_records как суррогат legal basis для staff-ролей
❌ Не писать «админ соглашается за пользователя» / «психолог даёт пациентское согласие»
❌ Не использовать fastapi-users — конфликтует с нашей схемой
❌ Не использовать async SQLAlchemy — проект на sync psycopg2
❌ Не вызывать alembic.command.upgrade() из FastAPI lifespan — deadlock
❌ Не вызывать Base.metadata.create_all() — удалён, схема только через Alembic
```

---

### База данных: схема

48 таблиц в 12 модулях. Схема управляется через Alembic.
Миграции: `mindcare_api/alembic/versions/`.

**Миграции (в порядке применения):**

| Revision | Описание |
|----------|----------|
| `af13ad7a133c` | baseline: 38 таблиц (все кроме audit) |
| `3a7c5e2b8f1d` | add_audit_tables: auth_log, audit_log, data_change_log |
| `c5d8a1b4e7f2` | otp_code_varchar64: otp_verifications.code VARCHAR(6→64) для SHA-256 |
| `e9a3d7f2b5c0` | rebuild_audit_indexes: пересоздание индексов audit-таблиц |
| `f4b9e2c6a1d8` | audit_indexes_and_types: индексы + тип data_change_log.changed_fields |
| `a8c3f1d9e2b5` | add_tags_tables: tags, article_tags, news_tags, test_tags |
| `b3c5e7a9f1d2` | extend_auth_log_event: auth_log.event VARCHAR(50→150) |
| `d2e5f8a1b4c7` | add_supervisor_engagement_index: partial unique index |
| `e5a8f3c1d2b6` | add_normalized_email_unique_index: `lower(trim(email))` |
| `b6e1f4a7c9d3` | add_user_legal_basis_records (Stage 23b) |
| `d8f3a6c1e9b4` | add_chat_conversations_and_messages (Stage 28b) — **head** |

**Ключевые таблицы:**

| Таблица | Описание |
|---------|----------|
| `users` | Все пользователи системы. FK из всех модулей |
| `roles`, `user_roles`, `permissions`, `role_permissions` | RBAC. Роли через M:N |
| `student_profiles`, `psychologist_profiles` | Профили 1:1 с users |
| `user_sessions` | Сессии (заменяют JWT). Soft-revoke через `is_revoked` |
| `otp_verifications` | OTP для регистрации и сброса пароля. code = SHA-256 хеш |
| `consents`, `consent_records` | Согласия на ПДн (личное согласие субъекта). Обязательны при регистрации |
| `user_legal_basis_records` | Документированное основание организации для admin-created staff-пользователей. Не путать с consent |
| `chat_conversations`, `chat_messages` | Chat MVP (Stage 28b): one-to-one чат поверх therapy_engagements; одна беседа на engagement (UNIQUE); content — только `enc:v1:` (шифрование — Stage 28c) |
| `appointments` | Записи на консультации |
| `schedule_rules` | Расписание психологов (не материализованные слоты) |
| `tests`, `questions`, `options`, `test_results` | Психодиагностика |
| `categories`, `article_categories`, `test_categories` | Типы материалов/категории. В MVP плоские: `parent_id` не используется в Admin CRUD |
| `tags`, `article_tags`, `news_tags`, `test_tags` | Темы/теги контента. M:N с articles, news, tests. Уникальность через `lower(name)` |
| `auth_log`, `audit_log`, `data_change_log` | Аудит. В prod могут быть партиционированы по месяцам |
| `refresh_tokens`, `user_mfa_methods` | NOT IMPLEMENTED. Таблицы зарезервированы. |

> **Партиционирование audit-таблиц:** `auth_log`/`audit_log`/`data_change_log`
> создаются как `PARTITION BY RANGE (created_at)` с начальными партициями 2026-01..2028-12.
> Будущие партиции управляются через `scripts/ensure_audit_partitions.py`.
> Запускать заблаговременно (не из FastAPI).

**Роли в системе:**

| Роль | Кто | Как создаётся |
|------|-----|---------------|
| `student` | Студент/клиент | Публичная регистрация с OTP |
| `psychologist` | Психолог | Только через `POST /api/admin/users` |
| `admin` | Администратор | Только через `POST /api/admin/users` или `scripts/create_admin.py` |
| `supervisor` | Супервизор | Только через `POST /api/admin/users` |

---

### Frontend: структура

> Полные правила фронта — в `mindcare_web/ARCHITECTURE.md`. Этот раздел — краткое содержание.

```
mindcare_web/src/
├── app/                — shell: App.jsx, AppRoutes.jsx
├── api/                — ВСЕ HTTP-вызовы только здесь
│   ├── client.js       — транспорт: токен + 401 retry
│   ├── auth.api.js
│   ├── users.api.js    — /api/admin/users/* (CRUD пользователей)
│   ├── tags.api.js     — /api/admin/tags/* + /api/tags (UI: «Темы»)
│   ├── categories.api.js — /api/admin/categories/* (UI: «Типы материалов»)
│   ├── news.api.js     — normalizeNewsItem() экспортируется для переиспользования
│   ├── articles.api.js — /api/articles/* + /api/admin/articles/* + categories
│   ├── materials.api.js — реэкспорт getArticles/getArticleById из articles.api.js
│   └── appointments.api.js
├── features/           — бизнес-логика по доменам
│   ├── auth/           — AuthContext, LoginForm, RegisterForm, forgot-password
│   ├── news/           — FeaturedNews, NewsCardSmall, NewsListItem, NewsSection
│   └── admin/          — AdminLayout + модули управления
│       ├── AdminLayout.jsx + .module.css
│       ├── users/      — CRUD пользователей (hooks, components, pages)
│       ├── categories/ — CRUD типов материалов (hooks, components, pages)
│       ├── tags/       — CRUD тем/тегов (hooks, components, pages)
│       ├── news/       — CRUD новостей (NewsTable, NewsFormModal, NewsPage)
│       └── articles/   — CRUD материалов (ArticlesTable, ArticleFormModal, ArticlesPage)
├── components/         — domain-agnostic примитивы
│   ├── Modal/          — Modal.jsx (пропы: open, onClose, wide, zIndex)
│   └── UI/
│       ├── TiptapEditor/   — rich-text редактор (StarterKit, Image, TextAlign)
│       ├── ImageUpload/    — drag-drop загрузка обложки
│       └── ContentPreview/ — предпросмотр новости/материала (DOMPurify)
├── hooks/              — переиспользуемые hooks
│   ├── useNews.js      — публичный список новостей с пагинацией
│   └── useMaterials.js — публичный список материалов (реальный API, single-select категория)
├── pages/              — только композиция, никакого fetch
│   ├── news/           — NewsItemPage (rich HTML через DOMPurify)
│   ├── materials/      — MaterialsPage, MaterialsItemPage (rich HTML через DOMPurify)
│   ├── client/         — ClientDashboard (stub)
│   └── consultant/     — ConsultantDashboard (stub)
├── data/               — только dev/mock данные (постепенно выводятся)
└── styles/             — variables.css, global.css
```

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

### Audit mode

Любой аудит в проекте MindCare выполняется только в режиме READ-ONLY.

Обязательные строки для любого промпта на аудит:

```text
Режим READ-ONLY.

Не менять код.
Не создавать файлы.
Не редактировать JSX/CSS/Python.
Не удалять стили.
Не делать рефакторинг.
Не запускать миграцию.
Только анализ и финальный отчёт.
```

Аудит может:

```text
✅ искать файлы;
✅ классифицировать компоненты;
✅ описывать риски;
✅ находить дубли;
✅ предлагать API будущего компонента;
✅ предлагать план миграции;
✅ давать рекомендации.
```

Аудит не может:

```text
❌ менять JSX;
❌ менять CSS;
❌ менять Python;
❌ создавать компоненты;
❌ удалять классы;
❌ запускать миграцию;
❌ исправлять найденные проблемы без отдельного разрешения.
```

Аудит и миграция — разные этапы:

```text
1. Аудит — только анализ.
2. Миграция — изменение кода только по отдельному промпту.
3. Контрольный отчёт — build, grep, visual risks, accessibility risks.
```

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

### Auth flow

```
Регистрация:
POST /api/auth/register/init  → OTP на email
POST /api/auth/register/confirm → создаёт user + consent_records

Логин:
POST /api/auth/login → session_token в ответе
Фронт хранит token в localStorage
Все запросы: Authorization: Bearer <token>

Выход:
POST /api/auth/logout → отзывает сессию в user_sessions

Восстановление пароля:
POST /api/auth/password/reset/init → OTP на email
POST /api/auth/password/reset/confirm → новый пароль + отзыв всех сессий
```

---

### Реализованные API-эндпоинты

| Метод | URL | Доступ | Статус |
|-------|-----|--------|--------|
| POST | `/api/auth/register/init` | Public | ✅ |
| POST | `/api/auth/register/confirm` | Public | ✅ |
| POST | `/api/auth/login` | Public | ✅ |
| POST | `/api/auth/logout` | Auth | ✅ |
| GET | `/api/auth/me` | Auth | ✅ |
| POST | `/api/auth/password/reset/init` | Public | ✅ |
| POST | `/api/auth/password/reset/confirm` | Public | ✅ |
| GET | `/api/admin/users` | Admin | ✅ |
| POST | `/api/admin/users` | Admin | ✅ |
| PATCH | `/api/admin/users/{id}` | Admin | ✅ |
| DELETE | `/api/admin/users/{id}` | Admin | ✅ |
| GET | `/api/admin/users/{id}` | Admin | ✅ |
| GET | `/api/admin/tags` | Admin, Supervisor | ✅ |
| POST | `/api/admin/tags` | Admin, Supervisor | ✅ |
| PATCH | `/api/admin/tags/{uuid}` | Admin, Supervisor | ✅ |
| DELETE | `/api/admin/tags/{uuid}` | Admin, Supervisor | ✅ |
| GET | `/api/tags` | Public | ✅ |
| GET | `/api/admin/categories` | Admin, Supervisor | ✅ |
| POST | `/api/admin/categories` | Admin, Supervisor | ✅ |
| GET | `/api/admin/categories/{id}` | Admin, Supervisor | ✅ |
| PATCH | `/api/admin/categories/{id}` | Admin, Supervisor | ✅ |
| DELETE | `/api/admin/categories/{id}` | Admin, Supervisor | ✅ |
| POST | `/api/media/upload` | Auth | ✅ |
| GET | `/media/{path}` | Public (static) | ✅ |
| GET | `/api/admin/news` | Admin, Supervisor | ✅ |
| POST | `/api/admin/news` | Admin, Supervisor | ✅ |
| GET | `/api/admin/news/{uuid}` | Admin, Supervisor | ✅ |
| PATCH | `/api/admin/news/{uuid}` | Admin, Supervisor | ✅ |
| DELETE | `/api/admin/news/{uuid}` | Admin, Supervisor | ✅ |
| GET | `/api/news` | Public | ✅ |
| GET | `/api/news/{uuid}` | Public | ✅ |
| GET | `/api/admin/articles` | Admin, Supervisor | ✅ |
| POST | `/api/admin/articles` | Admin, Supervisor | ✅ |
| GET | `/api/admin/articles/{uuid}` | Admin, Supervisor | ✅ |
| PATCH | `/api/admin/articles/{uuid}` | Admin, Supervisor | ✅ |
| DELETE | `/api/admin/articles/{uuid}` | Admin, Supervisor | ✅ |
| GET | `/api/admin/articles/categories` | Admin, Supervisor | ✅ |
| GET | `/api/articles` | Public | ✅ |
| GET | `/api/articles/{uuid}` | Public | ✅ |
| GET | `/api/articles/categories` | Public | ✅ |

## Соглашения по коду

### Backend

**Структура модуля** (по примеру `app/auth/`, `app/users/`):
```
app/<module>/
├── __init__.py
├── routes.py          — публичные эндпоинты (если есть)
├── routes_admin.py    — админские эндпоинты (если есть)
├── schemas.py         — Pydantic-схемы (Create, Update, Read раздельно)
├── service.py         — бизнес-логика, не знает про FastAPI/HTTP
└── storage.py         — SQLAlchemy запросы, изолированы здесь
```

**Pydantic-схемы:**
```python
# Всегда раздельные схемы для разных операций
class UserCreate(BaseModel): ...   # входящие данные
class UserUpdate(BaseModel): ...   # частичное обновление
class UserRead(BaseModel): ...     # исходящие данные

# UserRead НИКОГДА не содержит password_hash или другие чувствительные поля
# model_config = {"from_attributes": True} — для создания из SQLAlchemy-моделей
```

**Защита эндпоинтов:**
```python
# Защита на уровне роутера (предпочтительно) — нельзя забыть на новом эндпоинте
router = APIRouter(
    prefix="/admin/users",
    dependencies=[Depends(require_role("admin"))],
)

# Не защищать только на фронте — всегда на бэке
```

**Работа с БД:**
```python
# Всегда with SessionLocal() as db — автозакрытие сессии
with SessionLocal() as db:
    ...

# db.flush() перед db.commit() если нужен id до коммита
# db.refresh(obj) после commit() если поля генерирует БД (uuid, created_at)

# Soft delete — никогда не удалять физически через основные таблицы
db.query(User).filter(...).update({"deleted_at": datetime.now(timezone.utc)})
```

**Email:**
```python
# Все отправки через BackgroundTasks — не блокировать HTTP-ответ
bg.add_task(send_registration_otp, user.email, code)

# EMAIL_MODE=dev — печатает в stdout, не шлёт реально (для разработки)
# EMAIL_MODE=smtp — реальная отправка
```

**Порядок импортов:**
```python
# 1. Стандартная библиотека
import secrets
from datetime import datetime

# 2. Сторонние пакеты
from fastapi import APIRouter
from sqlalchemy.orm import Session

# 3. Внутренние модули
from app.db.session import SessionLocal
from app.auth.deps import require_role
```

**Логирование:**
```python
# Auth-события (login, logout, failed_login, register, password_reset)
from app.auth.audit import log_auth_event
log_auth_event(event="login", success=True, user_id=..., ...)

# Пока используем print() в стиле проекта
# При переходе на logging — заменить везде сразу, не по одному
print(f"[WARN] ...", file=sys.stderr)   # ошибки
print(f"[INFO] ...")                     # информация
```

---

### Frontend

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

---

### Git

```
Ветки от dev, PR с ревью
main — только прод
Conventional Commits:
  feat: новая функциональность
  fix: исправление бага
  chore: инфраструктура, зависимости
  docs: документация
  refactor: рефакторинг без изменения поведения
```


## Известные проблемы и бэклог

Полный список — в [`docs/BACKLOG.md`](docs/BACKLOG.md).

**Не «исправляй» эти вещи без явного запроса** — они отложены осознанно.

Критические риски (прочитай перед любой работой с auth или БД):
- `refresh_tokens`, `user_mfa_methods` — таблицы в БД, логика НЕ реализована

**Student chat/diary/tasks/calendar — accepted demo/mock (НЕ баг):**
- `/student/chat`, `/student/diary`, `/student/tasks`, `/student/calendar` работают на
  hardcoded mock-данных — это осознанная демо-витрина до отдельного Chat MVP этапа
- НЕ считать это production-чатом и НЕ «чинить» без отдельного этапа
- При старте Chat MVP: всю hardcoded mock-логику (CONTACTS, INITIAL_MESSAGES, MOCK_*)
  можно удалить/сломать; сохранить только дизайн/визуальную структуру компонентов
- One-to-one chat строить поверх `therapy_engagements` (partial unique index
  гарантирует одного активного психолога на студента)
- `questions_answers` — это Q&A-модуль (один вопрос → один ответ), НЕ чат;
  не использовать как основу для чата

Исправлено (больше не критично):
- ~~Партиции audit-таблиц захардкожены до 31.12.2026~~ — закрыто: миграция `3a7c5e2b8f1d` создаёт partitioned tables, `scripts/ensure_audit_partitions.py` управляет будущими партициями
- ~~`session_notes.content` хранится открытым текстом~~ — закрыто: Fernet application-layer encryption в `app/core/encryption.py`; `DATA_ENCRYPTION_KEY` обязателен в `.env`
- OTP-коды теперь хранятся как SHA-256 хеш (migration `c5d8a1b4e7f2`, otp_service.py)
- ~~Нет rate limiting на auth-эндпоинтах~~ — закрыто (Stage 21): `app/core/rate_limit.py`,
  per-process MVP; Redis/shared storage — отдельный этап
- ~~Session-токены plaintext в `user_sessions.id` / `auth_log.session_id`~~ — закрыто (Stage 22b):
  SHA-256 hash-on-lookup; зачистка старых plaintext-строк — отдельный maintenance-этап
- ~~Нет legal basis для admin-created users~~ — закрыто (Stage 23b): `user_legal_basis_records`;
  backfill `--apply` выполнить при деплое
