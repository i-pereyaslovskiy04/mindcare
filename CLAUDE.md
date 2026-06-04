# CLAUDE.md

Этот файл описывает проект для Claude Code. Прочитай его целиком перед любой задачей.

## О проекте

**MindCare** — веб-платформа психологической службы Донецкого государственного университета.

Функциональность:
- Запись студентов на консультации к штатным психологам
- Онлайн-психодиагностика (тесты с автоподсчётом результатов)
- Блог, новости, справочник ресурсов помощи
- Модуль вопросов и ответов (Q&A)
- Личные кабинеты по ролям (студент, психолог, админ)
- Административная панель

**Критически важно:** платформа работает с психологическими и медицинскими данными.
Она попадает под **ФЗ-152 РФ** (защита персональных данных). Это влияет на:
- Все данные пользователей хранятся на серверах в РФ
- Согласие на обработку ПДн фиксируется в `consent_records` при регистрации
- Перед каждым тестом и записью на консультацию проверяется актуальность согласия
- Заметки сессий (`session_notes`) должны шифроваться на уровне приложения (TODO: не реализовано)
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
> Все 41 таблица создаётся через `alembic upgrade head`.
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
│   │   └── config.py        — настройки из .env (pydantic-settings)
│   ├── db/
│   │   ├── session.py       — engine, SessionLocal, Base
│   │   └── models.py        — все SQLAlchemy модели
│   ├── auth/                — аутентификация и авторизация
│   │   ├── audit.py         — log_auth_event() для auth_log
│   │   ├── deps.py          — get_current_user, require_role
│   │   ├── otp_service.py   — создание и верификация OTP
│   │   ├── routes.py        — /api/auth/* эндпоинты
│   │   ├── schemas.py       — Pydantic-схемы auth
│   │   ├── security.py      — генерация токенов сессии
│   │   ├── service.py       — бизнес-логика auth
│   │   └── storage.py       — работа с БД (users, sessions, consents)
│   ├── users/               — управление пользователями (admin)
│   │   ├── routes_admin.py  — /api/admin/users/* эндпоинты
│   │   ├── schemas.py       — Pydantic-схемы users
│   │   ├── service.py       — бизнес-логика users
│   │   └── storage.py       — работа с БД (find_users, create_user)
│   ├── tags/                — управление тегами контента
│   │   ├── routes_admin.py  — /api/admin/tags/* (admin + supervisor)
│   │   ├── routes_public.py — /api/tags/ (autocomplete, без auth)
│   │   ├── schemas.py       — Pydantic-схемы tags
│   │   ├── service.py       — бизнес-логика + нормализация имени
│   │   └── storage.py       — работа с БД, коррелированные подзапросы счётчиков
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
│   └── services/
│       ├── email_sender.py  — SMTP транспорт (dev/smtp режимы)
│       └── email_service.py — формирование писем по событиям
├── scripts/
│   ├── create_admin.py      — создание первого админа (интерактивный)
│   └── test_smtp.py         — диагностика SMTP
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
❌ Не использовать fastapi-users — конфликтует с нашей схемой
❌ Не использовать async SQLAlchemy — проект на sync psycopg2
❌ Не вызывать alembic.command.upgrade() из FastAPI lifespan — deadlock
❌ Не вызывать Base.metadata.create_all() — удалён, схема только через Alembic
```

---

### База данных: схема

45 таблиц в 10 модулях. Схема управляется через Alembic.
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

**Ключевые таблицы:**

| Таблица | Описание |
|---------|----------|
| `users` | Все пользователи системы. FK из всех модулей |
| `roles`, `user_roles`, `permissions`, `role_permissions` | RBAC. Роли через M:N |
| `student_profiles`, `psychologist_profiles` | Профили 1:1 с users |
| `user_sessions` | Сессии (заменяют JWT). Soft-revoke через `is_revoked` |
| `otp_verifications` | OTP для регистрации и сброса пароля. code = SHA-256 хеш |
| `consents`, `consent_records` | Согласия на ПДн. Обязательны при регистрации |
| `appointments` | Записи на консультации |
| `schedule_rules` | Расписание психологов (не материализованные слоты) |
| `tests`, `questions`, `options`, `test_results` | Психодиагностика |
| `tags`, `article_tags`, `news_tags`, `test_tags` | Теги контента. M:N с articles, news, tests. Уникальность через `lower(name)` |
| `auth_log`, `audit_log`, `data_change_log` | Аудит. В prod могут быть партиционированы по месяцам |
| `refresh_tokens`, `user_mfa_methods` | NOT IMPLEMENTED. Таблицы зарезервированы. |

> **Критический риск:** если в prod-БД `auth_log`/`audit_log`/`data_change_log`
> партиционированы, партиции захардкожены до **31.12.2026**. После этой даты
> INSERT упадёт и логин сломается. Нужен скрипт автогенерации партиций — в бэклоге.

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
│   ├── tags.api.js     — /api/admin/tags/* + /api/tags (autocomplete)
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
│       ├── tags/       — CRUD тегов (hooks, components, pages)
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
| GET | `/api/admin/users` | Admin, Supervisor | ✅ |
| POST | `/api/admin/users` | Admin, Supervisor | ✅ |
| PATCH | `/api/admin/users/{id}` | Admin, Supervisor | ✅ |
| DELETE | `/api/admin/users/{id}` | Admin, Supervisor | ✅ |
| GET | `/api/admin/users/{id}` | Admin, Supervisor | ✅ |
| GET | `/api/admin/tags` | Admin, Supervisor | ✅ |
| POST | `/api/admin/tags` | Admin, Supervisor | ✅ |
| PATCH | `/api/admin/tags/{uuid}` | Admin, Supervisor | ✅ |
| DELETE | `/api/admin/tags/{uuid}` | Admin, Supervisor | ✅ |
| GET | `/api/tags` | Public | ✅ |
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
- Партиции `auth_log`, `audit_log`, `data_change_log` (если партиционированы в prod) захардкожены до **31.12.2026** → после этой даты логин сломается (silent fail в audit.py, но потеря аудита)
- `session_notes.content` хранится открытым текстом — шифрование не реализовано (нарушение ФЗ-152 для специальных категорий ПДн)
- `refresh_tokens`, `user_mfa_methods` — таблицы в БД, логика НЕ реализована

Исправлено (больше не критично):
- OTP-коды теперь хранятся как SHA-256 хеш (migration `c5d8a1b4e7f2`, otp_service.py)