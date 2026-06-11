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
│   │   │   ├── config.py            # Настройки из .env (pydantic-settings)
│   │   │   └── encryption.py        # Fernet encrypt/decrypt для session_notes
│   │   ├── db/
│   │   │   ├── base.py              # Base = declarative_base()  ← единственный источник
│   │   │   ├── session.py           # engine, SessionLocal, get_db()
│   │   │   ├── init_db.py           # Startup: ensure_database + check_migrations + seed
│   │   │   ├── seed.py              # Идемпотентный seed: роли, permissions, consents
│   │   │   └── models/              # ORM-модели (10 модулей, 45 таблиц)
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
│   │   │   ├── routes_admin.py      # /api/admin/users/* (admin, supervisor)
│   │   │   ├── service.py           # Бизнес-логика: CRUD пользователей
│   │   │   ├── storage.py           # DB-запросы: поиск, создание, обновление
│   │   │   └── schemas.py           # Pydantic-схемы admin user management
│   │   ├── tags/                    # /api/admin/tags/* + /api/tags/ (public)
│   │   ├── categories/              # /api/admin/categories/*
│   │   ├── news/                    # /api/admin/news/* + /api/news/* (public)
│   │   ├── articles/                # /api/admin/articles/* + /api/articles/* (public)
│   │   ├── media/                   # POST /api/media/upload + Pillow resize/WebP
│   │   ├── session_notes/           # /api/session-notes/* + Fernet encrypt-on-write
│   │   ├── supervisor/              # /api/supervisor/* (supervisor role)
│   │   ├── psychologist/            # /api/psychologist/* (psychologist role)
│   │   └── services/
│   │       ├── email_service.py     # Публичный API: send_registration_otp() и др.
│   │       └── email_sender.py      # Внутренний SMTP-транспорт (не импортировать напрямую)
│   ├── scripts/
│   │   ├── create_admin.py              # Создание первого администратора (интерактивный CLI)
│   │   ├── ensure_audit_partitions.py   # Создание будущих партиций audit-таблиц
│   │   └── test_smtp.py                 # Диагностика SMTP-соединения
│   ├── tests/
│   │   └── test_encryption.py       # Unit-тесты для app/core/encryption.py (21 test)
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

Создать файл `mindcare_api/.env` (образец: `mindcare_api/.env.example`):

```env
# Обязательные
DATABASE_URL=postgresql://MindcareUser:password@localhost/mindcare

# Шифрование заметок сессий (Fernet, обязателен при наличии данных)
# Генерация нового ключа:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Хранить отдельно от резервных копий БД. Потеря ключа = потеря зашифрованных заметок.
DATA_ENCRYPTION_KEY=

# Email: "dev" — печатает в stdout, "smtp" — реальная отправка
EMAIL_MODE=dev

# Только при EMAIL_MODE=smtp:
# SMTP_HOST=smtp.example.com
# SMTP_PORT=587
# SMTP_USER=user@example.com
# SMTP_PASSWORD=secret
# SMTP_FROM=noreply@example.com
# SMTP_TLS=True
# SMTP_SSL=False

# CORS: разрешённые origin'ы фронтенда (через запятую)
ALLOWED_ORIGINS=http://localhost:3000

# Максимальный размер загружаемого изображения в МБ (JPEG/PNG/WebP)
# При nginx: client_max_body_size должен быть NEWS_IMAGE_MAX_SIZE_MB + 5
NEWS_IMAGE_MAX_SIZE_MB=20

# Опциональные
SESSION_EXPIRE_DAYS=7
DEBUG=false
ENV=development
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
d2e5f8a1b4c7      ← текущий head
```

Каждая команда `alembic upgrade head` применяет все недостающие ревизии по цепочке и обновляет эту строку.

### История ревизий

| Revision | Описание |
|----------|----------|
| `af13ad7a133c` | Baseline: 38 таблиц (всё кроме audit) |
| `3a7c5e2b8f1d` | Audit tables: auth_log, audit_log, data_change_log (партиционированные) |
| `c5d8a1b4e7f2` | otp_verifications.code VARCHAR(6→64) для SHA-256 хешей |
| `f4b9e2c6a1d8` | Audit indexes + ARRAY(Text) fix |
| `e9a3d7f2b5c0` | Rebuild audit indexes (согласованы с ORM) |
| `a8c3f1d9e2b5` | Tags tables: tags, article_tags, news_tags, test_tags |
| `b3c5e7a9f1d2` | auth_log.event VARCHAR(50→150) |
| `d2e5f8a1b4c7` | Supervisor engagement unique index — **head** |

### ORM-модели (45 таблиц, 10 модулей)

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

**Пароли.** bcrypt напрямую (`import bcrypt`). Никакого MD5/SHA для паролей.

**Аудит.** Все auth-события (login, logout, failed_login, register, password_reset) пишутся в `auth_log` через `audit.log_auth_event()`. Fire-and-forget, ошибки записи не влияют на основной ответ.

**RBAC.** Роли проверяются на бэке через `require_role()` на уровне роутера — нельзя случайно пропустить на новом эндпоинте. Фронтенд не является рубежом безопасности.

**Идентификаторы.** Внешний API использует `users.uuid` (UUID), не `users.id` (INT).

**Soft delete.** Физического удаления пользователей нет — `deleted_at` timestamp + отзыв всех сессий.

**Закрытые риски:**
- ~~`session_notes.content` не шифруется~~ ✅ Закрыто — реализовано Fernet application-layer шифрование:
  `app/core/encryption.py`, `enc:v1:` prefix, encrypt-on-write/decrypt-on-read в `app/session_notes/storage.py`.
  **Операционное требование:** `DATA_ENCRYPTION_KEY` должен быть настроен и резервно скопирован отдельно от бэкапов БД.
  Потеря ключа = невозможность восстановить зашифрованные заметки.
- ~~Партиции audit-таблиц захардкожены до 31.12.2026~~ ✅ Закрыто — `scripts/ensure_audit_partitions.py` управляет
  будущими партициями; начальные партиции 2026-01..2028-12 созданы миграцией `3a7c5e2b8f1d`.

**Открытые compliance-риски:**

- **Legal basis для пользователей, созданных администратором.**  
  `consent_records` нельзя трактовать только как "согласие пациента". Для студентов/пациентов это может быть личное согласие на обработку данных и получение психологической помощи. Для психологов, супервизоров и администраторов основанием обработки ПДн может быть служебное, трудовое, договорное, административное или иное документированное основание.  
  Текущий риск: при создании пользователя через админку необходимо фиксировать не то, что "админ дал согласие за пользователя", а то, что у организации есть документированное основание для создания учётной записи и обработки персональных данных этого пользователя. Это требует отдельной модели provenance/source/actor для `consent_records` или связанного audit/legal-basis механизма.

---

## API

**Интерактивная документация:** [http://localhost:8000/docs](http://localhost:8000/docs) (Swagger UI)

**Health check:** `GET /api/health`

```json
{
  "status": "ok",
  "db": "connected",
  "tables": 45,
  "revision": "d2e5f8a1b4c7"
}
```

**Реализованные эндпоинты** (полный список — `/docs` Swagger UI)**:**

| Группа | Методы | Доступ |
|--------|--------|--------|
| `/api/auth/*` | register/init, register/confirm, login, logout, me, password reset | Public / Auth |
| `/api/admin/users/*` | GET list, GET one, POST, PATCH, DELETE | Admin, Supervisor |
| `/api/admin/tags/*` + `/api/tags` | CRUD tags + public autocomplete | Admin, Supervisor / Public |
| `/api/admin/categories/*` | CRUD categories | Admin, Supervisor |
| `/api/admin/news/*` + `/api/news/*` | CRUD news + public list/item | Admin, Supervisor / Public |
| `/api/admin/articles/*` + `/api/articles/*` | CRUD articles + public list/item | Admin, Supervisor / Public |
| `/api/media/upload` | POST upload image | Auth |
| `/api/session-notes/*` | CRUD session notes (enc:v1: ciphertext) | Psychologist (own) / Admin, Supervisor |
| `/api/supervisor/*` | Student list, psychologist list, engagements | Supervisor |
| `/api/psychologist/*` | Cabinet: clients, schedule, appointments | Psychologist |
| `/api/health` | Health check: status, tables, revision | Public |

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
