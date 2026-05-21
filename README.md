# MindCare

Веб-платформа психологической службы Донецкого государственного университета.

Монорепозиторий: FastAPI backend (`mindcare_api/`) + React frontend (`mindcare_web/`).

---

## Стек технологий

| Слой | Технология |
|------|-----------|
| Backend | Python 3.11+, FastAPI |
| ORM | SQLAlchemy 2.x (синхронный режим, psycopg2) |
| База данных | PostgreSQL 15+ |
| Миграции | Alembic (единственный владелец схемы) |
| Аутентификация | Сессионные токены в `user_sessions` (не JWT) |
| Email | SMTP через smtplib; в dev-режиме — вывод в stdout |
| Frontend | React 19, React Router 7, CSS Modules, CRA |

---

## Архитектура backend

Приложение построено на строгом разделении слоёв:

```
HTTP Request
  → routes.*       — разбор запроса, вызов сервиса, формирование ответа
      → service.*  — бизнес-логика, оркестрация, без HTTP-концепций
          → storage.*  — SQLAlchemy-запросы, только работа с БД
              → db/models/*  — ORM-модели, только определения таблиц
```

| Слой | Правило |
|------|---------|
| `routes.*` | Только HTTP: разбор тела, вызов сервиса, возврат ответа. Нет бизнес-логики, нет прямых запросов в БД |
| `service.*` | Только бизнес-логика. Нет FastAPI-импортов. Оркестрирует вызовы storage, OTP, email |
| `storage.*` | Только SQLAlchemy-запросы. Никаких бизнес-правил |
| `db/models/*` | Только ORM-определения. Никакой логики |
| `services/email_service.py` | Публичный email API (функция на каждое событие) |
| `services/_smtp.py` | Внутренний SMTP-транспорт. Не импортировать напрямую |

---

## Структура проекта

```
mindcare/
├── mindcare_api/                    # FastAPI backend — порт 8000
│   ├── alembic/                     # Конфиг и версии миграций
│   │   ├── env.py
│   │   └── versions/
│   │       ├── af13ad7a133c_baseline_initial_schema.py
│   │       ├── 3a7c5e2b8f1d_add_audit_tables.py
│   │       ├── c5d8a1b4e7f2_otp_code_varchar64.py
│   │       ├── f4b9e2c6a1d8_audit_indexes_and_types.py
│   │       └── e9a3d7f2b5c0_rebuild_audit_indexes.py
│   ├── app/
│   │   ├── main.py                  # Точка входа: FastAPI app, CORS, lifespan, роутеры
│   │   ├── core/
│   │   │   └── config.py            # Настройки из .env (pydantic-settings)
│   │   ├── db/
│   │   │   ├── base.py              # Base = declarative_base()  ← единственный источник
│   │   │   ├── session.py           # engine, SessionLocal, get_db()
│   │   │   ├── init_db.py           # Startup: ensure_database + check_migrations + seed
│   │   │   ├── seed.py              # Идемпотентный seed: роли, permissions, consents
│   │   │   └── models/              # ORM-модели (10 модулей, 41 таблица)
│   │   │       ├── auth.py          # users, roles, user_roles, permissions, user_sessions
│   │   │       ├── profiles.py      # student_profiles, psychologist_profiles
│   │   │       ├── consents.py      # consents, consent_records
│   │   │       ├── media.py         # media_files, media_versions
│   │   │       ├── content.py       # articles, news, categories, help_resources, Q&A
│   │   │       ├── diagnostics.py   # tests, questions, options, test_results
│   │   │       ├── consultations.py # appointments, schedule_rules, session_notes
│   │   │       ├── notifications.py # notification_templates, notifications
│   │   │       ├── audit.py         # auth_log, audit_log, data_change_log
│   │   │       └── otp.py           # otp_verifications
│   │   ├── auth/
│   │   │   ├── routes.py            # /api/auth/* эндпоинты
│   │   │   ├── service.py           # Бизнес-логика аутентификации
│   │   │   ├── storage.py           # DB-запросы: users, sessions, consents
│   │   │   ├── otp_service.py       # OTP: создание (SHA-256 hash), верификация, очистка
│   │   │   ├── audit.py             # log_auth_event() → auth_log
│   │   │   ├── deps.py              # get_current_user, require_role
│   │   │   ├── security.py          # generate_session_token()
│   │   │   └── schemas.py           # Pydantic-схемы /api/auth/*
│   │   ├── users/
│   │   │   ├── routes_admin.py      # /api/admin/users/* (только admin)
│   │   │   ├── service.py           # Бизнес-логика: CRUD пользователей
│   │   │   ├── storage.py           # DB-запросы: поиск, создание, обновление
│   │   │   └── schemas.py           # Pydantic-схемы admin user management
│   │   └── services/
│   │       ├── email_service.py     # Публичный API: send_registration_otp() и др.
│   │       └── _smtp.py             # Внутренний SMTP-транспорт (не импортировать напрямую)
│   ├── scripts/
│   │   ├── create_admin.py          # Создание первого администратора (интерактивный CLI)
│   │   └── test_smtp.py             # Диагностика SMTP-соединения
│   ├── alembic.ini
│   └── requirements.txt
├── mindcare_web/                    # React frontend — порт 3000
│   └── src/
│       ├── api/                     # Все HTTP-вызовы только здесь
│       ├── features/                # Бизнес-логика по доменам (auth, ...)
│       ├── components/              # Переиспользуемые UI-примитивы
│       ├── pages/                   # Только композиция, никаких fetch
│       └── styles/                  # CSS-переменные, глобальные стили
├── ARCHITECTURE.md                  # Обзор архитектуры монорепо
├── CLAUDE.md                        # Контекст для Claude Code
└── README.md
```

---

## Локальная разработка

### Требования

- Python 3.11+
- PostgreSQL 15+
- Node.js 18+ (для frontend)

### Backend

```powershell
cd mindcare_api

# Создать и активировать виртуальное окружение (Windows)
python -m venv .venv
.venv\Scripts\Activate.ps1
# Если PowerShell блокирует скрипты:
# Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

# Установить зависимости
pip install -r requirements.txt
```

### Настройка .env

Создать файл `mindcare_api/.env`:

```env
# Обязательные
DATABASE_URL=postgresql://MindcareUser:password@localhost/mindcare

# Email: "dev" — печатает в stdout, "smtp" — реальная отправка
EMAIL_MODE=dev

# Только при EMAIL_MODE=smtp:
# SMTP_HOST=smtp.example.com
# SMTP_PORT=587
# SMTP_USER=user@example.com
# SMTP_PASSWORD=secret
# SMTP_FROM=noreply@example.com

# Опциональные
SESSION_EXPIRE_DAYS=7
DEBUG=false
```

### PostgreSQL

```sql
-- Создать пользователя и базу данных
CREATE USER MindcareUser WITH PASSWORD 'password' CREATEDB;
CREATE DATABASE mindcare OWNER MindcareUser;
```

### Запуск backend

```bash
# 1. Применить миграции (ОБЯЗАТЕЛЬНО перед первым запуском)
cd mindcare_api
alembic upgrade head

# 2. Запустить сервер
uvicorn app.main:app --reload
# → http://localhost:8000
# → http://localhost:8000/docs  (Swagger UI)

# 3. Создать первого администратора
python scripts/create_admin.py
```

### Frontend

```bash
cd mindcare_web
npm install
npm start
# → http://localhost:3000
```

> Proxy в `mindcare_web/package.json` перенаправляет все `/api/*` запросы на `localhost:8000`.
> Для full-stack разработки нужны оба сервера.

---

## База данных

### Alembic — единственный владелец схемы

Схема БД управляется **исключительно через Alembic**. Это не конвенция — это архитектурное требование:

| Правило | Обоснование |
|---------|-------------|
| `Base.metadata.create_all()` **не используется и удалён** | Обходит версионирование, создаёт дрейф схемы |
| Миграции **не запускаются при старте приложения** | Deadlock при совместном старте; migrations — ответственность ops/CI |
| `alembic upgrade head` **выполняется до `uvicorn`** | Приложение не стартует, если DB не на head |
| `alembic/env.py` **не вызывает `fileConfig()`** | Исключает перезапись логгеров при запуске миграций |

При старте FastAPI `init_db()` только **читает** версию из `alembic_version` и бросает `RuntimeError`, если DB отстаёт от head. Схема не меняется.

### Таблица `alembic_version`

Alembic хранит текущую ревизию в одной строке:

```
alembic_version
───────────────────
version_num
e9a3d7f2b5c0      ← текущий head
```

Каждая команда `alembic upgrade head` применяет все недостающие ревизии по цепочке и обновляет эту строку.

### История ревизий

| Revision | Описание |
|----------|----------|
| `af13ad7a133c` | Baseline: 38 таблиц (всё кроме audit) |
| `3a7c5e2b8f1d` | Audit tables: auth_log, audit_log, data_change_log |
| `c5d8a1b4e7f2` | otp_verifications.code VARCHAR(6→64) для SHA-256 хешей |
| `f4b9e2c6a1d8` | Audit indexes + ARRAY(Text) fix |
| `e9a3d7f2b5c0` | Rebuild audit indexes (согласовано с ORM) — **head** |

### ORM-модели (41 таблица, 10 модулей)

| Модуль | Таблицы |
|--------|---------|
| `auth.py` | users, roles, user_roles, permissions, role_permissions, user_sessions, refresh_tokens\*, user_mfa_methods\* |
| `profiles.py` | student_profiles, psychologist_profiles, emergency_contacts |
| `consents.py` | consents, consent_records |
| `media.py` | media_files, media_versions |
| `content.py` | categories, articles, article_categories, news, help_resources, questions_answers |
| `diagnostics.py` | tests, test_categories, questions, options, question_media, option_media, test_results, test_result_scales, student_answers |
| `consultations.py` | therapy_engagements, schedule_rules, schedule_exceptions, appointments, session_notes |
| `notifications.py` | notification_templates, notifications |
| `audit.py` | auth_log, audit_log, data_change_log |
| `otp.py` | otp_verifications |

\* `refresh_tokens`, `user_mfa_methods` — таблицы зарезервированы, логика не реализована.

---

## Миграции

```bash
cd mindcare_api

# Применить все ожидающие миграции
alembic upgrade head

# Создать новую миграцию после изменения ORM-модели
alembic revision --autogenerate -m "describe_change"
# Проверить сгенерированный файл в alembic/versions/, затем:
alembic upgrade head

# Проверить текущую ревизию
alembic current

# Проверить наличие дрейфа схемы (для CI: exit 0 = чисто, exit 1 = дрейф)
alembic check

# Полная история ревизий
alembic history

# Откат на одну ревизию назад
alembic downgrade -1
```

> **Workflow:** изменил ORM → `alembic revision --autogenerate` → просмотрел файл → `alembic upgrade head` → запустил `uvicorn`.

---

## Порядок запуска

```
alembic upgrade head        # CLI/CI: применяет миграции, обновляет alembic_version
        ↓
uvicorn app.main:app        # Запускает FastAPI
        ↓
lifespan() startup
  ├── init_db()
  │     ├── ensure_database()    — подключается к БД; создаёт её если отсутствует (dev)
  │     ├── check_migrations()   — READ-ONLY: читает alembic_version
  │     │                          RuntimeError → uvicorn не стартует, если DB не на head
  │     └── run_seed()           — идемпотентный seed: роли, permissions, consents
  └── cleanup_expired()          — удаляет просроченные OTP из прошлых сессий
        ↓
"Application startup complete."
```

Схема БД при старте **не изменяется**. Все запросы в БД в lifespan — только чтение.

---

## Безопасность

**Аутентификация.** Сессионные токены (`secrets.token_urlsafe`) хранятся в таблице `user_sessions`. Все защищённые эндпоинты проверяют токен через `deps.get_current_user()`: находит сессию, проверяет `is_revoked` и `expires_at`, обновляет `last_active`. JWT не используется.

**OTP-коды.** Plaintext-код отправляется пользователю по email. В БД хранится только `SHA-256(code)` в `otp_verifications`. Код действителен 10 минут. Верификация — сравнение хешей. После успешной верификации запись удаляется.

**Пароли.** bcrypt через passlib. Никакого MD5/SHA для паролей.

**Аудит.** Все auth-события (login, logout, failed_login, register, password_reset) пишутся в `auth_log` через `audit.log_auth_event()`. Fire-and-forget, ошибки записи не влияют на основной ответ.

**RBAC.** Роли проверяются на бэке через `require_role()` на уровне роутера — нельзя случайно пропустить на новом эндпоинте. Фронтенд не является рубежом безопасности.

**Идентификаторы.** Внешний API использует `users.uuid` (UUID), не `users.id` (INT).

**Soft delete.** Физического удаления пользователей нет — `deleted_at` timestamp + отзыв всех сессий.

**Известные риски (бэклог):**
- `session_notes.content` хранится открытым текстом — шифрование Fernet не реализовано (ФЗ-152)
- Партиции audit-таблиц (если применимо в prod) захардкожены до 31.12.2026

---

## API

**Интерактивная документация:** [http://localhost:8000/docs](http://localhost:8000/docs) (Swagger UI)

**Health check:** `GET /api/health`

```json
{
  "status": "ok",
  "db": "connected",
  "tables": 41,
  "revision": "e9a3d7f2b5c0"
}
```

**Реализованные эндпоинты:**

| Метод | URL | Доступ |
|-------|-----|--------|
| POST | `/api/auth/register/init` | Public |
| POST | `/api/auth/register/confirm` | Public |
| POST | `/api/auth/login` | Public |
| POST | `/api/auth/logout` | Authenticated |
| GET | `/api/auth/me` | Authenticated |
| POST | `/api/auth/password/reset/init` | Public |
| POST | `/api/auth/password/reset/confirm` | Public |
| GET | `/api/admin/users` | Admin |
| POST | `/api/admin/users` | Admin |
| GET | `/api/admin/users/{uuid}` | Admin |
| PATCH | `/api/admin/users/{uuid}` | Admin |
| DELETE | `/api/admin/users/{uuid}` | Admin |
| GET | `/api/health` | Public |

---

## Правила разработки

### База данных

```
❌ Base.metadata.create_all()       — удалён, никогда не использовать
❌ alembic.command.upgrade()        — никогда из кода FastAPI (deadlock)
❌ engine.execute("CREATE TABLE …") — прямые DDL-запросы запрещены
✅ Изменения схемы ТОЛЬКО через:   alembic revision --autogenerate → alembic upgrade head
```

### Слои приложения

```
✅ routes.*   — только HTTP: разобрать запрос, вызвать сервис, вернуть ответ
✅ service.*  — только бизнес-логика, нет FastAPI-импортов
✅ storage.*  — только SQLAlchemy-запросы, нет бизнес-правил
❌ routes.*/pages не должны содержать SQL-запросы или бизнес-правила напрямую
```

### Синхронный SQLAlchemy

```
✅ Все эндпоинты — def (не async def)
✅ psycopg2, не asyncpg
❌ Не переключать на async SQLAlchemy без командного решения
```

### Стиль кода

```python
# Сессии БД — всегда через with
with SessionLocal() as db:
    ...

# Soft delete — никогда физически
db.query(User).filter(...).update({"deleted_at": datetime.now(timezone.utc)})

# Email через BackgroundTasks — не блокировать HTTP-ответ
bg.add_task(send_registration_otp, user.email, code)

# Нормализация email
email = email.lower().strip()

# Логирование
log = logging.getLogger(__name__)
log.info("…")   # не print()
```
