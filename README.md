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
│   ├── alembic/                     # Конфиг и версии миграций (14 ревизий, head: a9b3e1f7c2d4)
│   │   ├── env.py
│   │   └── versions/                # af13ad7a133c … d8f3a6c1e9b4 (см. «История ревизий»)
│   ├── app/
│   │   ├── main.py                  # Точка входа: FastAPI app, CORS, lifespan, роутеры
│   │   ├── core/
│   │   │   ├── config.py            # Настройки из .env (pydantic-settings)
│   │   │   ├── encryption.py        # Fernet encrypt/decrypt для session_notes и chat_messages
│   │   │   ├── normalization.py     # normalize_email()
│   │   │   └── rate_limit.py        # In-memory sliding-window limiter для auth (Stage 21)
│   │   ├── db/
│   │   │   ├── base.py              # Base = declarative_base()  ← единственный источник
│   │   │   ├── session.py           # engine, SessionLocal, get_db()
│   │   │   ├── init_db.py           # Startup: ensure_database + check_migrations + seed
│   │   │   ├── seed.py              # Идемпотентный seed: роли, permissions, consents
│   │   │   └── models/              # ORM-модели (12 модулей, 48 таблиц)
│   │   │       ├── auth.py          # users, roles, user_roles, permissions, user_sessions
│   │   │       ├── profiles.py      # student_profiles, psychologist_profiles
│   │   │       ├── consents.py      # consents, consent_records (личное согласие субъекта)
│   │   │       ├── legal_basis.py   # user_legal_basis_records (основание организации, Stage 23b)
│   │   │       ├── media.py         # media_files, media_versions
│   │   │       ├── content.py       # articles, news, categories, help_resources, Q&A
│   │   │       ├── diagnostics.py   # tests, questions, options, test_results
│   │   │       ├── consultations.py # appointments, schedule_rules, session_notes
│   │   │       ├── chat.py          # chat_conversations, chat_messages, chat_attachments (Stage 28b/32b)
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
│   │   │   ├── security.py          # generate_session_token(), hash_session_token()
│   │   │   └── schemas.py           # Pydantic-схемы /api/auth/*
│   │   ├── users/
│   │   │   ├── routes_admin.py      # /api/admin/users/* (только admin)
│   │   │   ├── service.py           # Бизнес-логика: CRUD пользователей
│   │   │   ├── storage.py           # DB-запросы: поиск, создание, обновление
│   │   │   └── schemas.py           # Pydantic-схемы admin user management
│   │   ├── tags/                    # /api/admin/tags/* + /api/tags/ (public)
│   │   ├── categories/              # /api/admin/categories/*
│   │   ├── news/                    # /api/admin/news/* + /api/news/* (public)
│   │   ├── articles/                # /api/admin/articles/* + /api/articles/* (public)
│   │   ├── media/                   # POST /api/media/upload + Pillow resize/WebP
│   │   ├── session_notes/           # /api/session-notes/* + Fernet encrypt-on-write
│   │   ├── chat/                    # /api/chat/* — one-to-one чат (Stage 28c), encrypt-on-write
│   │   ├── supervisor/              # /api/supervisor/* (supervisor role)
│   │   ├── psychologist/            # /api/psychologist/* (psychologist role)
│   │   └── services/
│   │       ├── email_service.py     # Публичный API: send_registration_otp() и др.
│   │       └── _smtp.py             # Внутренний SMTP-транспорт (не импортировать напрямую)
│   ├── scripts/
│   │   ├── create_admin.py                      # Создание первого администратора (интерактивный CLI)
│   │   ├── ensure_audit_partitions.py           # Создание будущих партиций audit-таблиц
│   │   ├── backfill_legal_basis.py              # Backfill legal basis records (--dry-run по умолчанию)
│   │   ├── cleanup_orphan_attachments.py        # Очистка soft-deleted/осиротевших chat_attachments
│   │   ├── repair_missing_chat_conversations.py # Восстановление бесед для существующих engagements
│   │   └── test_smtp.py                         # Диагностика SMTP-соединения
│   ├── tests/                       # 488 тестов: unit + integration (см. «Тестирование»)
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

# Шифрование заметок сессий И сообщений чата (Fernet, обязателен при наличии данных)
# Генерация нового ключа:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Хранить отдельно от резервных копий БД.
# Потеря ключа = потеря зашифрованных заметок (session_notes) и переписки (chat_messages).
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

# Приватная директория для хранения файлов чата (chat_attachments, НЕ public static)
# default: storage/private/chat_attachments
CHAT_FILE_STORAGE_DIR=storage/private/chat_attachments

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
a9b3e1f7c2d4      ← текущий head
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
| `d2e5f8a1b4c7` | Supervisor engagement unique index |
| `e5a8f3c1d2b6` | Normalized email unique index: `lower(trim(email))` |
| `b6e1f4a7c9d3` | user_legal_basis_records (Stage 23b) |
| `d8f3a6c1e9b4` | chat_conversations + chat_messages (Stage 28b) |
| `c4f7a2e9d1b8` | system conversation support: type/recipient_id + message_kind/event_key (Stage 29b) |
| `f7e9c2a4b8d1` | chat_messages.edited_at (Stage 31z) |
| `a9b3e1f7c2d4` | chat_attachments table + FK (Stage 32b) — **head** |

### ORM-модели (48 таблиц, 12 модулей)

| Модуль | Таблицы |
|--------|---------|
| `auth.py` | users, roles, user_roles, permissions, role_permissions, user_sessions, refresh_tokens\*, user_mfa_methods\* |
| `profiles.py` | student_profiles, psychologist_profiles, emergency_contacts |
| `consents.py` | consents, consent_records |
| `legal_basis.py` | user_legal_basis_records |
| `media.py` | media_files, media_versions |
| `content.py` | categories, articles, article_categories, news, help_resources, questions_answers |
| `diagnostics.py` | tests, test_categories, questions, options, question_media, option_media, test_results, test_result_scales, student_answers |
| `consultations.py` | therapy_engagements, schedule_rules, schedule_exceptions, appointments, session_notes |
| `chat.py` | chat_conversations, chat_messages, chat_attachments |
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

## Тестирование

Текущий статус: **488 passed** (unit + API/integration; integration-тесты требуют запущенный dev PostgreSQL на alembic head).
Frontend после Stage 32 attachment hotfixes: **32 suites / 325 passed** (`npm test -- --watchAll=false`).

```bash
# Backend
cd mindcare_api
python -m compileall app scripts -q
pytest tests/ -v
```

```powershell
# Из корня проекта (compileall + все backend-тесты)
.\test.ps1
```

```bash
# Frontend
cd mindcare_web
npm run lint
npm run build
```

| Файл | Покрытие |
|------|----------|
| `tests/test_change_password.py` | смена пароля — атомарный UoW, мок storage (13) |
| `tests/test_encryption.py` | Fernet encryption helper (26) |
| `tests/test_normalization.py` | нормализация email (16) |
| `tests/test_smtp_transport.py` | SMTP TLS/SSL transport (21) |
| `tests/test_email_error_sanitization.py` | санитизация SMTP/auth ошибок клиенту (11) |
| `tests/test_rate_limit.py` | rate limiter unit (18) |
| `tests/test_session_security.py` | session token hashing unit (8) |
| `tests/test_auth_hardening_b1.py` | OTP log masking / consent IP-UA / fail on missing role (6) |
| `tests/integration/test_register_confirm_atomic.py` | атомарный registration confirm UoW + failure-injection (8) |
| `tests/integration/test_register_consent_context.py` | IP/User-Agent в consent_records при confirm (1) |
| `tests/integration/test_password_uow_atomic.py` | атомарные password reset confirm + change password UoW, failure-injection (11) |
| `tests/integration/test_email_normalization_api.py` | register/login/reset API (11) |
| `tests/integration/test_rate_limit_api.py` | 429-поведение auth API (10) |
| `tests/integration/test_session_token_hashing.py` | hashed tokens end-to-end (9) |
| `tests/integration/test_legal_basis_api.py` | legal basis records API (11) |
| `tests/integration/test_session_notes_api.py` | access policy session_notes (15) |
| `tests/integration/test_touch_session.py` | debounce touch_session (9) |
| `tests/integration/test_chat_models.py` | constraints chat-таблиц (6) |
| `tests/integration/test_chat_api.py` | Chat MVP API end-to-end (20) |
| `tests/integration/test_system_conversation.py` | system conversation backend (17) |
| `tests/integration/test_engagement_system_messages.py` | system messages для engagement-событий (11) |
| `tests/integration/test_chat_presence.py` | approximate online/offline presence (12) |

---

## Безопасность

**Аутентификация.** Клиент получает opaque-токен (`secrets.token_urlsafe`); в таблице `user_sessions` хранится только его **SHA-256 hash** (Stage 22b) — значение из дампа БД нельзя использовать как Bearer. Все защищённые эндпоинты проверяют токен через `deps.get_current_user()` (hash-on-lookup): находит сессию, проверяет `is_revoked` и `expires_at`, обновляет `last_active`. JWT не используется.

**Rate limiting (Stage 21).** Auth-эндпоинты (login, register init/confirm, password reset init/confirm) защищены in-memory sliding-window лимитером (`app/core/rate_limit.py`): лимиты по IP и нормализованному email, 429 с единым сообщением без раскрытия существования аккаунта. **MVP-ограничение:** состояние per-process, сбрасывается при рестарте; для multi-worker/multi-instance production нужен Redis/shared storage (отдельный этап).

**OTP-коды.** Plaintext-код отправляется пользователю по email. В БД хранится только `SHA-256(code)` в `otp_verifications`. Код действителен 10 минут. Верификация — сравнение хешей. В атомарных flows (registration confirm, password reset confirm) OTP **валидируется без удаления** и потребляется (удаляется) тем же commit, что и основная операция — при сбое core-шага OTP не теряется. INFO-логи OTP маскируют email (`mask_email`).

**Пароли.** bcrypt напрямую (`import bcrypt`). Никакого MD5/SHA для паролей.

**Атомарность auth-операций (Stage 31m-fix-b2/b3).** Бизнес-операции auth выполняются как единый unit-of-work — одна `SessionLocal()` + один финальный `commit`, без нескольких независимых commit внутри одной операции:
- **registration confirm** — validate OTP → создать/реактивировать пользователя → роль `student` → все `consent_records` → consume OTP → commit. Сбой любого core-шага откатывает пользователя/роль/согласия, OTP остаётся;
- **password reset confirm** — validate OTP → `password_hash` → revoke всех сессий → consume OTP → commit;
- **change password** — verify current password → `password_hash` → revoke всех сессий → commit.

Хеш нового пароля считается **до** открытия транзакции (bcrypt медленный). Email отправляется на init-шаге (вне транзакции); welcome/security system-уведомления публикуются **после** commit и остаются best-effort/soft-fail (их сбой не откатывает основную операцию и не раскрывает plaintext). `auth_log` — fire-and-forget вне core-транзакции. Transactional outbox на текущем этапе отсутствует. Покрыто failure-injection тестами: `tests/integration/test_register_confirm_atomic.py`, `tests/integration/test_password_uow_atomic.py`.

**Санитизация ошибок (Stage 31m-fix-a).** Raw SMTP/auth exceptions не отдаются клиенту; frontend `api/client.js` корректно парсит FastAPI/Pydantic 422 `detail` (array of objects) и не показывает `[object Object]`; email в auth/SMTP логах маскируется через `mask_email`.

**Аудит.** Все auth-события (login, logout, failed_login, register, password_reset) пишутся в `auth_log` через `audit.log_auth_event()`. Fire-and-forget, ошибки записи не влияют на основной ответ.

**RBAC.** Роли проверяются на бэке через `require_role()` на уровне роутера — нельзя случайно пропустить на новом эндпоинте. Фронтенд не является рубежом безопасности.

**Идентификаторы.** Внешний API использует `users.uuid` (UUID), не `users.id` (INT).

**Soft delete.** Физического удаления пользователей нет — `deleted_at` timestamp + отзыв всех сессий.

**Закрытые риски:**
- ~~`session_notes.content` не шифруется~~ ✅ Закрыто — реализовано Fernet application-layer шифрование:
  `app/core/encryption.py`, `enc:v1:` prefix, encrypt-on-write/decrypt-on-read в `app/session_notes/storage.py`.
  **Операционное требование:** `DATA_ENCRYPTION_KEY` должен быть настроен и резервно скопирован отдельно от бэкапов БД.
  Потеря ключа = невозможность восстановить зашифрованные заметки **и переписку чата** —
  с Stage 28c тот же ключ шифрует `chat_messages.content`.
- ~~Партиции audit-таблиц захардкожены до 31.12.2026~~ ✅ Закрыто — `scripts/ensure_audit_partitions.py` управляет
  будущими партициями; начальные партиции 2026-01..2028-12 созданы миграцией `3a7c5e2b8f1d`.
- ~~Нет rate limiting на auth-эндпоинтах~~ ✅ Закрыто (Stage 21) — см. «Rate limiting» выше.
- ~~Session-токены хранились plaintext в `user_sessions.id` и `auth_log.session_id`~~ ✅ Закрыто (Stage 22b) —
  в БД хранится `sha256(raw_token)`, lookup/revoke/touch — hash-on-lookup; новые `auth_log.session_id` пишут hash.
  Деплой инвалидировал старые plaintext-сессии (one-time re-login).
  Остаток (отдельные maintenance-этапы): зачистка старых строк `user_sessions WHERE length(id) <> 64`
  и маскирование исторических plaintext `auth_log.session_id`.

**Доступ к `session_notes` (Stage 25b).** Психолог видит только свои заметки;
supervisor — списки metadata-only, content конкретной заметки доступен, но каждое
такое чтение пишется в `audit_log` (`session_note_content_read`, без plaintext);
admin — metadata-only везде, расшифрованный терапевтический content недоступен
(metadata-путь не вызывает decrypt). H3 закрыт для MVP; supervision-scope модель
и break-glass admin access — отдельные будущие решения.

**Messenger MVP (Stage 28b–30d).** Единый раздел «Сообщения» — one-to-one чат
student ↔ psychologist поверх `therapy_engagements` + read-only system conversation.
Роуты `/student/chat` и `/psychologist/chat` сохранены. **Реализован**:

*Backend:*
- DB foundation: `chat_conversations` (type `engagement`/`system`, nullable `engagement_id`/
  `recipient_id`) + `chat_messages` (`message_kind` `user`/`system`, `event_key` idempotency);
- polling-based (`messages?after=<id>` раз в 7–10 секунд), без WebSocket;
- `chat_messages.content` шифруется at-rest (Fernet, `enc:v1:`, тот же `DATA_ENCRYPTION_KEY`);
- доступ только участникам engagement: **admin/supervisor получают 403 на все engagement
  chat-роуты**, staff-доступа к содержимому нет by design (break-glass — отдельное решение);
- read/unread через `chat_messages.read_at`; rate limit отправки 30/мин/пользователь;
- audit: только `chat_conversation_created` (содержимое сообщений не логируется);
- **system conversation** read-only: `GET/POST /api/chat/system-conversation*` (своя беседа,
  любая авторизованная роль), без write-эндпоинта; события публикует только internal
  publisher (idempotency по `event_key`): **welcome**, **password_changed**,
  **engagement_assigned**, **engagement_transferred**, **engagement_closed**;
- **presence** `peer_is_online` (approximate) по `user_sessions.last_active`, порог 10 минут.

*Frontend:*
- VK-like entry: при входе диалог не открывается автоматически, mark-read только после
  явного клика (placeholder справа);
- unread: глобальный nav badge (по числу диалогов) + per-dialog badge/маркер/bold/фон;
- system conversation: всегда видна, **последняя** в списке, read-only, без composer;
- live refresh: snapshot polling (limit=50) + `reconcileMessagesSnapshot` (`pollNew`) —
  `read_at` обновляется и удалённые сообщения синхронизируются без F5; сообщение,
  удалённое участником A, исчезает у участника B после следующего polling tick (≤ 8 сек),
  без плейсхолдера, без переоткрытия диалога; `mergeMessages` (add/update) сохранён;
  MVP-ограничение: reconcile покрывает только последние 50 сообщений;
- linkify http/https only (без `dangerouslySetInnerHTML`, `target=_blank rel=noopener noreferrer`);
- read receipts ✓/✓✓ по `read_at`; online/offline точкой в списке и шапке (без last-seen-текста);
- **действия со своим сообщением (Stage 31y):** меню «…» (`MessageActionsMenu`) вместо отдельной
  кнопки-карандаша — «Редактировать»/«Удалить»; меню недоступно в закрытой/архивной беседе и для
  system-сообщений;
- **удаление (Stage 31y-hotfix):** удаление подтверждается диалогом (`DeleteMessageDialog`),
  затем soft delete на backend; удалённое сообщение пропадает из ленты **без плейсхолдера**
  «Сообщение удалено» — техническая запись (шифротекст) остаётся для audit/security, не
  отображается участникам;
- **MessageBubble (Stage 31z/31z-hotfix):** визуальное облачко вынесено в отдельный
  feature-specific компонент (`incoming`/`outgoing`/`system`); meta (время · «изменено» · ✓/✓✓)
  — внутри bubble, компактно для короткого текста, с переносом вниз-направо для длинного
  (Telegram-style); меню действий — рядом с bubble, не внутри него.
- **Chat hook architecture (Stage 31ad, frontend-only):** `useStudentChat` и
  `usePsychologistChat` — thin wrappers поверх общего `useChatCore(adapter)`
  (`features/chat/hooks/`); public API и поведение хуков не изменились;
  `useSystemConversation` — отдельный hook, не входит в `useChatCore`;
  backend/API/Alembic/UI-компоненты не менялись.

*Mobile (Stage 30d + hotfixes):*
- Messenger `≤900px` — режим list/thread (Telegram/VK): сначала список диалогов, по
  клику открывается чат, в шапке чата кнопка «назад» к списку;
- Cabinet `>980px` — полный sidebar; `601–980px` — icon-rail; `≤600px` — мобильный
  drawer (открывается по hamburger, закрывается backdrop/✕/Escape/кликом по пункту);
- `≤600px` topbar разгружен: скрыты колокольчик/почта, оставлены hamburger + breadcrumb + logout;
- фикс пустого кабинета на `<600px`: при скрытом sidebar `.app` остаётся `grid-template-columns: 1fr`.

*Ограничения MVP:* presence приблизительный (не realtime, порог 10 минут, зависит от
`user_sessions.last_active` и debounce `touch_session` 300с); read-receipt live-обновление —
только в пределах snapshot `limit=50`; без WebSocket/SSE; mobile drawer пока без focus-trap/`inert`.

**Вложения (Stage 32b–32g + hotfixes):** файлы в student↔psychologist engagement чате; отправка через
скрепку + drag & drop; несколько файлов в одном сообщении; attachment-only message;
карточки вложений в bubble (`AttachmentCard`/`AttachmentList`); в сообщениях с файлами и текстом
сначала показываются файлы, затем тонкий divider и текст как caption; attachment-only сообщения
без divider. Скачивание идёт через auth backend (private storage, не public static); Chromium
использует safe save flow через `showSaveFilePicker`, fallback — anchor download, Office-файлы
скачиваются без top-level navigation на `blob:` URL. Разрешены jpg/jpeg, png, webp, pdf, txt,
doc/docx, xls/xlsx, ppt/pptx; svg/html/js/executable/script extensions заблокированы; архивы
пока отложены. Редактирование сообщения поддерживает удаление отдельных файлов
(`EditableAttachmentList`); system conversation — upload запрещён. Pending: image preview/lightbox;
upload progress; retry queue; MIME magic bytes; antivirus; at-rest file encryption; добавление
файлов в edit-mode; периодическая очистка soft-deleted файлов
(`scripts/cleanup_orphan_attachments.py --apply`).

*Future / postponed:* **group chat** (отдельный этап после стабилизации, обязателен
READ-ONLY design audit — см. `docs/BACKLOG.md`); preview последнего сообщения в списке;
WebSocket/SSE realtime presence; Action Center / колокольчик;
staff break-glass access; усиление a11y mobile drawer; глубокий рефакторинг chat-модуля.
Учебная группа ≠ автоматический чат.

Ручной browser smoke обоих кабинетов (desktop / tablet / mobile) остаётся рекомендованным перед demo/deploy.

**Открытые security-направления** (подробности — `docs/BACKLOG.md`):
- HttpOnly Secure SameSite cookie + CSRF вместо localStorage-токена;
- Redis/shared storage для rate limiting при multi-worker деплое;
- request-scoped DB session (debounce `touch_session` закрыт в Stage 26);
- `target_user_id` в auth_log для поиска операций по субъекту;
- retention policy для chat_messages (открытый продуктовый вопрос);
- OTP concurrency / row locking: атомарные confirm-flows не берут `SELECT … FOR UPDATE`, при гонке двух confirm возможен двойной проход валидации (deferred);
- `_get_primary_role` read-fallback `"student"` при отсутствии активной роли (auth/storage) — cleanup deferred;
- transactional outbox для гарантированной доставки post-commit уведомлений (deferred);
- UI просмотра `user_legal_basis_records` в карточке пользователя админки.

**Закрытые compliance-риски:**

- ~~**Legal basis для пользователей, созданных администратором.**~~ ✅ Закрыто (Stage 23b) —
  отдельная таблица `user_legal_basis_records` фиксирует документированное основание
  организации при создании psychologist/supervisor/admin через админку, bootstrap-скрипт
  и backfill. Подробности — ниже и в `docs/COMPLIANCE.md`.

### Legal basis для пользователей, созданных администратором

Важно не смешивать личное согласие субъекта и документированное основание обработки персональных данных.

`consent_records` используется для фиксации личного согласия пользователя, например студента/пациента, который самостоятельно принимает политику конфиденциальности и условия обработки данных.

Для пользователей с ролями `psychologist`, `supervisor`, `admin`, созданных администратором, речь не должна идти о том, что «администратор соглашается за пользователя». В этом случае организация фиксирует наличие документированного основания для создания учётной записи и обработки персональных данных пользователя.

Возможные основания:
- трудовой договор;
- служебная необходимость;
- приказ;
- договор;
- административное назначение;
- иной документированный basis/основание, которое при необходимости можно предъявить или приложить.

Формулировка для UI:

> При создании: Подтверждаю наличие документированного основания для создания учётной записи и обработки персональных данных пользователя.
>
> При смене роли: Подтверждаю наличие документированного основания для назначения этой роли и обработки персональных данных.

Реализация: отдельная сущность `user_legal_basis_records` (миграция `b6e1f4a7c9d3`, модель `app/db/models/legal_basis.py`). Не использовать `consent_records` как суррогат legal basis для психологов, супервизоров и администраторов. Основание требуется и при создании staff (`POST /api/admin/users`), и при смене роли на staff (`PATCH /api/admin/users/{uuid}`, Stage 31f-fix): смена роли и запись основания атомарны; `staff → student` основания не требует.

**Смена роли в админке (Stage 31n / 31n-hotfix).** Роль пользователя **редактируема** в edit-модалке админки (ранее, Stage 31h, была read-only — правило отменено). UI-поведение:
- поле «Роль пользователя» расположено сразу под ФИО; при реальной смене роли на `psychologist`/`supervisor`/`admin` появляется блок legal basis (тип основания, документ-основание, опц. комментарий, чекбокс подтверждения) и его поля уходят в PATCH; без документа-основания submit не проходит;
- если роль не менялась — `role` в PATCH не отправляется и legal basis не требуется;
- `student` **не предлагается** в edit-dropdown (студенты появляются через self-registration); текущая роль `student` отображается как значение (shared `Select` `displayLabel`), но недоступна для повторного выбора;
- backend PATCH guard (Stage 31f-fix) остаётся обязательным defense-in-depth — UI-проверка его не заменяет.

---

## API

**Интерактивная документация:** [http://localhost:8000/docs](http://localhost:8000/docs) (Swagger UI)

**Health check:** `GET /api/health`

```json
{
  "status": "ok",
  "db": "connected",
  "tables": 48,
  "revision": "a9b3e1f7c2d4"
}
```

**Реализованные эндпоинты** (полный список — `/docs` Swagger UI)**:**

| Группа | Методы | Доступ |
|--------|--------|--------|
| `/api/auth/*` | register/init, register/confirm, login, logout, me, password reset, change-password | Public / Auth |
| `/api/admin/users/*` | GET list, GET one, POST, PATCH, DELETE | Admin |
| `/api/admin/tags/*` + `/api/tags` | CRUD tags + public autocomplete | Admin, Supervisor / Public |
| `/api/admin/categories/*` | CRUD categories | Admin, Supervisor |
| `/api/admin/news/*` + `/api/news/*` | CRUD news + public list/item | Admin, Supervisor / Public |
| `/api/admin/articles/*` + `/api/articles/*` | CRUD articles + public list/item | Admin, Supervisor / Public |
| `/api/media/upload` | POST upload image | Auth |
| `/api/session-notes/*` | Session notes (enc:v1: ciphertext): psychologist — свои с content; supervisor — meta-list + audited content read; admin — metadata-only | Psychologist / Supervisor / Admin |
| `/api/chat/*` | One-to-one чат (enc:v1: ciphertext): student — my-conversation; psychologist — conversations; polling `after=<id>`, read receipts, `peer_is_online` presence; attachments upload/download (private storage) | Student / Psychologist (admin/supervisor — 403) |
| `/api/chat/system-conversation*` | Read-only system conversation (своя беседа): GET conversation/messages, POST read; write только internal publisher | Auth (любая роль — к своей беседе) |
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
