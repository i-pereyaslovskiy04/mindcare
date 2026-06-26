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
- Заметки сессий (`session_notes`), сообщения чата (`chat_messages.content`) и данные
  дневника (`diary_entries.mood_score_enc / entry_text_enc / emotions_enc`) шифруются
  на уровне приложения: Fernet, `enc:v1:` prefix, `app/core/encryption.py`;
  не сохранять и не логировать plaintext content
- IP-адреса анонимизируются через 90 дней (`anonymize_old_ips()` в БД)

**Монорепо с двумя проектами:**
- `mindcare_api/` — Python FastAPI бэкенд, порт 8000
- `mindcare_web/` — React 19 фронтенд (CRA), порт 3000

## Правила для всех ИИ: версионные бэкапы изменяемых файлов

**Обязательно для любого ИИ-агента, работающего с проектом.**

Перед изменением любого файла проекта его текущая (до-правочная) версия
сохраняется в папку бэкапов с версионностью — каждая правка создаёт новую
версию, старые не перезаписываются.

> Подключение hook у себя (в т.ч. Windows: Git Bash и PowerShell) — разовый шаг
> по инструкции [`docs/BACKUP_HOOK_SETUP.md`](docs/BACKUP_HOOK_SETUP.md).
> Hook лежит в `.claude/settings.json` (gitignored), поэтому каждый участник
> подключает его вручную; сам скрипт `scripts/backup_hook.py` — в git.

```
✅ Папка бэкапов — ВНУТРИ проекта: `.backups/files/` (НЕ абсолютный путь, НЕ вне проекта)
✅ Структура: `.backups/files/<относительный путь файла>/<UTC-таймстамп><ext>`
✅ Скрипт бэкапа — `scripts/backup_hook.py` (ТРЕКАЕТСЯ в git, общий для команды)
✅ Бэкап автоматизирован PreToolUse-hook'ом (matcher Edit|Write|MultiEdit|NotebookEdit
   в .claude/settings.json); путь к скрипту — через `$CLAUDE_PROJECT_DIR`, без хардкода
✅ В .gitignore — только `.backups/files/` (содержимое бэкапов НЕ коммитится);
   сам скрипт в `scripts/` версионируется
✅ Корень проекта скрипт вычисляет относительно своего расположения
   (`scripts/` на один уровень ниже корня) — не хардкодить абсолютные пути
❌ Не выносить папку бэкапов за пределы проекта и не задавать абсолютным путём
❌ Не отключать hook, не коммитить содержимое `.backups/files/`
❌ Каталог `.backups/` из бэкапа исключён (без рекурсии)
```

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
> Все 49 таблиц создаются через `alembic upgrade head`.
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
npm test -- --testPathPattern=client.test.js
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
✅ Для изменений auth UoW — failure-injection тесты на реальном состоянии БД
❌ Не утверждать "покрыто тестами", если покрыта только конкретная зона
```

Финальный отчёт по любой задаче (особенно docs/fix-промпты) должен содержать:
что изменено · какие тесты добавлены/прогнаны (или почему нет) · что НЕ трогалось ·
оставшиеся pending-риски.

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

Всего backend: **809 passed** (`.\test.ps1` на смерженной ветке dev, alembic head db0b2e177da5) —
включает чат-вложения (Stage 32b–32j), систему записи на консультации (appointments, 112+)
и дневник студента (diary).
Integration-тесты требуют запущенный dev PostgreSQL на alembic head.
Frontend (`npm test -- --watchAll=false`): suites чата/вложений + appointments + diary;
lint — 0 warnings, production build — success; точное число подтверждается прогоном.

| Файл | Что покрыто |
|------|-------------|
| `tests/test_change_password.py` | `service.change_password` — атомарный UoW, мок storage — 13 сценариев |
| `tests/test_encryption.py` | `app.core.encryption` — 26 сценариев |
| `tests/test_normalization.py` | `normalize_email` + OTP/storage нормализация — 16 |
| `tests/test_smtp_transport.py` | SMTP TLS/SSL transport — 21 |
| `tests/test_email_error_sanitization.py` | санитизация SMTP/auth ошибок клиенту (Stage 31m-fix-a) — 11 |
| `tests/test_rate_limit.py` | sliding-window limiter (unit) — 18 |
| `tests/test_session_security.py` | generate/hash session token (unit) — 8 |
| `tests/test_auth_hardening_b1.py` | OTP log masking / consent IP-UA / fail on missing role (Stage 31m-fix-b1) — 6 |
| `tests/integration/test_register_confirm_atomic.py` | атомарный registration confirm UoW + failure-injection (Stage 31m-fix-b2) — 8 |
| `tests/integration/test_register_consent_context.py` | IP/User-Agent в consent_records при confirm — 1 |
| `tests/integration/test_password_uow_atomic.py` | атомарные password reset confirm + change password UoW, failure-injection (Stage 31m-fix-b3) — 11 |
| `tests/integration/test_email_normalization_api.py` | register/login/reset API — 11 |
| `tests/integration/test_rate_limit_api.py` | 429-поведение auth API — 10 |
| `tests/integration/test_session_token_hashing.py` | hashed tokens end-to-end — 9 |
| `tests/integration/test_legal_basis_api.py` | legal basis records API — 11 |
| `tests/integration/test_admin_role_patch_legal_basis.py` | legal basis при смене роли (Stage 31f-fix) — 12 |
| `tests/integration/test_session_notes_api.py` | access policy session_notes (Stage 25b) — 15 |
| `tests/integration/test_touch_session.py` | debounce touch_session (Stage 26) — 9 |
| `tests/integration/test_chat_models.py` | constraints chat-таблиц (Stage 28b) — 6 |
| `tests/integration/test_chat_api.py` | Chat MVP API end-to-end (Stage 28c) — 20 |
| `tests/integration/test_system_conversation.py` | system conversation backend (Stage 29b) — 17 |
| `tests/integration/test_engagement_system_messages.py` | system messages для engagement-событий (Stage 29d) — 11 |
| `tests/integration/test_chat_presence.py` | approximate online/offline presence (Stage 30c) — 12 |
| `tests/integration/test_chat_message_edit.py` | редактирование сообщений chat (Stage 31z) — 10 |
| `tests/integration/test_chat_message_delete.py` | soft delete сообщений chat (Stage 31y) — 10 |
| `tests/integration/test_chat_bootstrap_on_assignment.py` | создание/восстановление беседы при назначении — 4 |
| `tests/integration/test_chat_lifecycle.py` | жизненный цикл engagement-беседы (перевод, закрытие) — 8 |
| `tests/integration/test_chat_attachment_models.py` | constraints chat_attachments (Stage 32b) — 20 |
| `tests/integration/test_chat_attachment_api.py` | upload/download/send/list attachments (Stage 32c) — 37 |
| `tests/integration/test_chat_attachment_edit.py` | редактирование сообщения с вложениями (Stage 32g) — 18 |
| `tests/integration/test_appointments.py` | appointments system: booking validation, slot computation from MeetingType.duration+buffer, group-session slot blocking/lazy completion, recurring breaks (with effective_from/until period filtering), schedule-out-of-range, pending-cancel soft-delete, confirmed-cancel notify, multiple one-off blockers, group sessions, meeting-type role access, bulk schedule rules, optional meeting_type_id on working windows, break period tests, unified schedule create/update (rules+breaks one series), auto_extend requires effective_until, series soft-delete/restore (is_active) hides from active list & slots, soft-delete keeps appointments + future-appt warning, extend-by-month, supervisor manual booking (registered student or unregistered card, occupies slot, 409 on busy, system msg to psychologist, booking_source/created_by audit), auto_extend maintenance (extend+notify, dry-run), read-only frontend support endpoints for student meeting types, psychologist schedule/exceptions, supervisor slots, and schedule v3 working-window behavior — 112+ |
| `tests/integration/test_unregistered_student_cards.py` | карточки незарегистрированных студентов + привязка к аккаунту (этап 2) |
| `tests/integration/test_supervisor_create_student.py` | создание аккаунта студента супервизором (POST /students) |
| `tests/integration/test_auth_profile.py` | self-service профиль (GET/PATCH /api/auth/profile) |
| `tests/integration/test_diary_api.py` | Diary API: endpoints, pagination/summary, student-only 403, cross-student 404, encryption, PATCH/DELETE, soft-delete, malformed UUID 422, empty PATCH no-op; обновлённый каталог (12 активных, tense/irritated/low/lonely, angry/light deprecated) |
| `src/pages/student/StudentHome.smoke.test.jsx` | StudentHome: nextStepCard states, action cards, observationCard, honest session copy, fake metrics/graph removed |
| `src/pages/student/components/Diary/DiaryEntryForm.test.jsx` | Mood-required check-in, optional emotions/text, collapsible details, save/error states |
| `src/pages/student/components/Diary/DiaryEntryItem.test.jsx` | Read/edit/delete modes, confirmation, errors, emotion labels, local date safety |
| `src/pages/student/components/Diary/DiaryHistoryList.test.jsx` | Empty/populated history, actions, load more and error states |
| `src/pages/student/DiaryPage.test.jsx` + smoke | Load/save, pagination, edit/delete sync, history reload offset=0, local today, observation summary, period chips, null filtering, recent marks, refresh after mutations |

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
│   │   ├── encryption.py    — Fernet encrypt/decrypt (enc:v1:) для session_notes и chat_messages
│   │   ├── normalization.py — normalize_email()
│   │   └── rate_limit.py    — in-memory sliding-window limiter для auth (Stage 21)
│   ├── db/
│   │   ├── base.py          — Base = declarative_base()
│   │   ├── session.py       — engine, SessionLocal
│   │   ├── init_db.py       — startup: ensure_database + check_migrations + seed
│   │   ├── seed.py          — идемпотентный seed
│   │   └── models/          — ORM-модели (13 модулей, 51 таблица; chat.py — Stage 28b/32b; diary.py — Diary)
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
│   ├── diary/               — /api/diary/* Дневник студента: одна запись в день,
│   │                          mood_score_enc/entry_text_enc/emotions_enc encrypted-at-rest,
│   │                          history limit/offset, PATCH edit, DELETE soft-delete, summary;
│   │                          справочник эмоций diary_emotions (сидирован); только student
│   ├── chat/                — /api/chat/* Messenger: one-to-one + system conversation,
│   │                          polling, read_at, encrypt-on-write, peer_is_online presence,
│   │                          system_publisher (idempotency event_key); attachments:
│   │                          upload/download/preview (private storage, not public static),
│   │                          send with attachment_uuids, edit remove_attachment_uuids,
│   │                          soft delete via chat_attachments.deleted_at (Stage 32b–32j)
│   ├── supervisor/          — /api/supervisor/* (назначения студент ↔ психолог,
│   │                          создание аккаунта студента: POST /students)
│   ├── appointments/        — /api/* записи на консультации (student/psychologist/
│   │                          supervisor), расписание, типы встреч, групповые сессии
│   ├── psychologist/        — /api/psychologist/* (свои студенты)
│   └── services/
│       ├── _smtp.py         — SMTP транспорт (dev/smtp режимы, внутренний)
│       └── email_service.py — формирование писем по событиям
├── scripts/
│   ├── create_admin.py                      — создание первого админа (+ legal basis record)
│   ├── ensure_audit_partitions.py           — будущие партиции audit-таблиц
│   ├── backfill_legal_basis.py              — backfill legal basis (--dry-run default)
│   ├── repair_missing_chat_conversations.py — восстановление бесед для существующих engagements
│   ├── extend_schedules.py                  — автопродление расписаний с auto_extend
│   │                                          (maintenance, НЕ из lifespan; --dry-run)
│   └── test_smtp.py                         — диагностика SMTP
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
✅ consent_records — ТОЛЬКО личное согласие субъекта (НЕ «согласие за пользователя»):
   студент сам принимает политику при self-registration, ЛИБО staff фиксирует личное
   согласие студента, полученное ОЧНО, при создании аккаунта через
   POST /api/supervisor/students (как у карточки незарег. студента) — это не legal basis
✅ admin/supervisor создаёт ПОЛНОЦЕННЫЙ аккаунт студента через
   POST /api/supervisor/students (temp password, как POST /api/admin/users). Основание
   ПДн — consent_records (личное согласие, получено очно; staff подтверждает
   personal_data_consent), НЕ user_legal_basis_records. Core-запись атомарна:
   User+UserRole(student)+ConsentRecord[]+опц. active TherapyEngagement+AuditLog в одном
   commit; AuditLog обязателен (consent_records не хранит actor); psychologist_id создаёт
   active engagement в ТОЙ ЖЕ транзакции (не отдельным вызовом assign_psychologist);
   карточка незарег. студента с тем же email привязывается (этап 2). Это НЕ admin
   role-dropdown (там student по-прежнему НЕ selectable). Пароль/ПДн не логировать
✅ Для admin-created psychologist/supervisor/admin — user_legal_basis_records
   (документированное основание организации; чекбокс в UI формулируется как
   «Подтверждаю наличие документированного основания для создания учётной
   записи и обработки персональных данных пользователя»)
✅ Смена роли на staff через PATCH /api/admin/users (old_role != new_role,
   new_role ∈ psychologist/supervisor/admin) тоже требует legal basis
   (legal_basis_confirmed + basis_type + basis_reference); смена роли и запись
   user_legal_basis_records атомарны; metadata: action=role_change/old_role/new_role.
   staff → student основания не требует и старые записи не удаляет (Stage 31f-fix)
✅ Роль в admin edit-модалке РЕДАКТИРУЕМА (Stage 31n; правило Stage 31h «role
   read-only» отменено) — но безопасно: при реальной смене на staff/admin UI
   показывает блок legal basis и шлёт его поля; backend PATCH guard обязателен
   как defense-in-depth (не полагаться только на UI)
✅ student НЕ selectable в admin edit-dropdown (Stage 31n-hotfix). Студенты появляются
   через self-registration ИЛИ через staff-created student flow (`POST /api/supervisor/students`);
   текущая роль student показывается через Select displayLabel, но недоступна для выбора.
   student как target роли из admin edit UI не отправляется
❌ Не делать роль read-only в admin edit и не слать role без legal basis при смене на staff
❌ Не писать «админ подтверждает согласие пользователя» — только «документированное
   основание для назначения роли и обработки ПДн». Не смешивать student consent и staff legal basis
✅ session_notes: psychologist — только свои; supervisor — content только поштучно
   и под audit (session_note_content_read); admin — metadata-only без decrypt
✅ Staff-чтение терапевтического content ОБЯЗАНО писать audit-событие (без plaintext)
✅ Metadata-путь session_notes не должен вызывать decrypt_text
✅ Chat content доступен только student/psychologist — участникам therapy_engagement
✅ Chat content шифруется при записи и не попадает в logs/audit
✅ Расписание создаётся серией (POST /api/supervisor/schedules): rules + breaks
   c общим series_id и периодом. meeting_type_id НЕ задаётся для новых рабочих
   окон schedule v3; тип встречи выбирается при поиске/создании записи.
   auto_extend=true требует effective_until (валидация в service → 422)
✅ Soft-delete/restore расписания — на уровне СЕРИИ через is_active (rules+breaks);
   существующие Appointment НЕ удаляются и продолжают занимать слоты. Перед
   деактивацией возвращается счётчик будущих записей в периоде (предупреждение)
✅ Ручная запись supervisor'ом (POST /api/supervisor/appointments) создаёт обычный
   Appointment в pending_confirmation; для зарегистрированного студента требует активного
   engagement студент↔психолог. Для walk-in клиента можно использовать
   unregistered_student_card_id; карточка хранит минимальные ПДн и может привязаться к
   будущему аккаунту по normalized_email. Психолог получает system-сообщение
   (event_key appointment_supervisor_new:{uuid})
✅ Групповые занятия (`group_sessions`) создаёт supervisor; student записывается только
   на `scheduled` + `booking_enabled=true`, без подтверждения психолога. При чтении списков
   lazy-completion переводит начавшиеся/прошедшие `scheduled` в `completed` и выключает
   `booking_enabled`. Student видит только `scheduled`; supervisor/psychologist видят
   `scheduled`/`completed`/`cancelled`
✅ Автопродление расписаний — ТОЛЬКО maintenance (scripts/extend_schedules.py →
   service.auto_extend_schedules); НЕ из FastAPI lifespan. После продления —
   system-сообщение создавшему серию supervisor'у (created_by, soft-fail)
❌ Не запускать auto_extend из FastAPI lifespan; не удалять Appointment при
   деактивации/удалении расписания
✅ Auth бизнес-операции АТОМАРНЫ (Stage 31m-fix-b2/b3): registration confirm,
   password reset confirm, change password — одна SessionLocal() + один commit.
   password+revoke sessions (и consume OTP) — в одной транзакции
✅ OTP consume только ПОСЛЕ успешных core DB-изменений, тем же commit
   (validate без удаления; при сбое core-шага OTP не теряется)
✅ Хеш нового пароля считать ДО открытия транзакции (bcrypt медленный)
✅ Новые auth/security изменения требуют failure-injection тестов на реальном
   состоянии БД (см. test_register_confirm_atomic, test_password_uow_atomic)
❌ Не возвращать старую модель «несколько независимых commit в одной auth-операции»
❌ Не выполнять SMTP/email-отправку внутри core DB-транзакции
❌ Не делать system/auth_log уведомления частью core-транзакции — soft-fail после commit
❌ Не добавлять admin/supervisor доступ к chat content без отдельного compliance/security этапа
❌ Не расширять admin-доступ к therapeutic content без отдельного compliance-решения
❌ Не использовать consent_records как суррогат legal basis для staff-ролей
❌ Не писать «админ соглашается за пользователя» / «психолог даёт пациентское согласие»
❌ Не использовать fastapi-users — конфликтует с нашей схемой
❌ Не использовать async SQLAlchemy — проект на sync psycopg2
❌ Не вызывать alembic.command.upgrade() из FastAPI lifespan — deadlock
❌ Не вызывать Base.metadata.create_all() — удалён, схема только через Alembic
✅ Chat attachments хранятся в private directory (`CHAT_FILE_STORAGE_DIR`),
   не в PostgreSQL и не в public static
✅ storage_key формируется на основе UUID — original filename не используется как filesystem path
✅ Скачивание вложений только через auth backend endpoints (permission check участника)
✅ Chromium download flow использует `showSaveFilePicker`; fallback — anchor download.
   Office-файлы должны скачиваться без top-level navigation на `blob:` URL, чат остаётся открытым
✅ Attachment preview реализован только для `image/jpeg`, `image/png`, `image/webp`,
   `application/pdf` через authenticated blob flow: backend download endpoint → `blob` →
   `URL.createObjectURL(blob)` → `AttachmentPreviewLightbox` → cleanup `URL.revokeObjectURL`
✅ Preview не использует public static, прямые `<img src="/api/...">`/`<iframe src="/api/...">`
   на backend endpoint и токены в query string
✅ MVP file policy: разрешены jpg/jpeg, png, webp, pdf, txt, doc/docx, xls/xlsx, ppt/pptx;
   svg, html/htm, js, exe/bat/cmd/com/msi, sh/ps1, php/jar, vbs/scr заблокированы;
   архивы пока не добавлять как реализованные
✅ Аудит для upload/download событий — content файла в audit не пишется
✅ Для orphan-вложений чата есть helper `scripts/cleanup_orphan_attachments.py`:
   dry-run по умолчанию, `--apply` для выполнения, scope — только `message_id IS NULL`
❌ Не писать, что реализован полный cleanup/retention attachments: physical cleanup
   файлов soft-deleted вложений по retention-политике, CLI tests и cron/systemd timer pending
❌ Не отдавать chat attachments через /static/* или StaticFiles — private storage
❌ Не давать admin/supervisor доступ к chat attachments без отдельного compliance-этапа
❌ Не хранить физический файл чата в PostgreSQL (даже как bytea/blob)
❌ Не писать, что реализованы MIME magic bytes (`python-magic`), antivirus/ClamAV,
   Office/TXT preview, thumbnails, PDF.js, S3/MinIO или at-rest encryption физических файлов
✅ Diary content (mood_score, entry_text, selected emotions) хранится encrypted-at-rest
   через enc:v1: в diary_entries.mood_score_enc / entry_text_enc / emotions_enc
✅ Diary API: GET emotions, GET/PUT today, GET entries?limit&offset,
   PATCH/DELETE entries/{entry_uuid}, GET summary?period=14d|month|year;
   только role=student — остальные роли получают 403
✅ PATCH/DELETE: чужая/удалённая/несуществующая запись → 404; malformed UUID → 422;
   DELETE = soft-delete; empty PATCH {} = no-op и не меняет updated_at
✅ Partial UNIQUE (student_id, entry_date) WHERE deleted_at IS NULL:
   после soft-delete можно создать новую запись на ту же дату
✅ Справочник эмоций diary_emotions хранится в БД (не hardcoded на фронте);
   фронт получает [{key, label, sort_order}] через GET /api/diary/emotions
✅ date policy MVP: backend использует date.today() без timezone; сервер должен быть Moscow UTC+3
✅ summary contract: fixed calendar period frame — нет clamp по первой записи;
   period=14d — последние 14 дней (today-13…today), всегда 14 daily points;
   period=month — с 1-го числа текущего месяца до today, quantity=today.day;
   period=year — monthly aggregated, всегда 12 points (Jan–Dec текущего года);
     будущие месяцы (> current month) включены с mood_score=null;
     entries_count = реальные записи (future null-slots не считаются);
   day/month без записи → mood_score=null; нет записей → полный фрейм с all null;
   empty state определяется на фронте по тому, что все mood_score===null;
   year avg = round(avg, 1) → float;
✅ StudentHome: nextStepCard + actionCardsGrid + observationCard только при entriesCount>0;
   fake GAD-7/sleep/anxiety/appointment/psychologist/date удалены
✅ DiaryPage: quick check-in, mood required, emotions/text optional, collapsible details,
   observation summary, history/load more, edit/delete, inline errors;
   frontend today сравнивается по local date
✅ Diary Analytics Lite: /api/diary/summary?period=14d|month|year используется для
   описательной сводки периода — Отметок, Последняя отметка/Последний период, Диапазон,
   последние 3–5 non-null отметок; save/edit/delete обновляют active period
✅ MoodChart и его test suite удалены после manual UI smoke; в diary UI нет SVG, осей,
   линий, trend claims или медицинской/диагностической интерпретации
⚠️ Audit trail для diary edit/delete не реализован; это compliance backlog
❌ Не логировать entry_text, decrypted mood_score, selected emotions из дневника
❌ Не давать psychologist/supervisor/admin доступ к diary content без compliance-этапа
❌ Не смешивать diary с session_notes — разные таблицы, разные маршруты, разная цель
❌ Не хранить selected emotions пользователя как FK в отдельной связующей таблице —
   только encrypted JSON в diary_entries.emotions_enc
```

---

### База данных: схема

51 таблица в 13 модулях. Схема управляется через Alembic.
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
| `d8f3a6c1e9b4` | add_chat_conversations_and_messages (Stage 28b) |
| `c4f7a2e9d1b8` | add_system_conversation_support: type/recipient_id + message_kind/event_key (Stage 29b) |
| **Ветка psychodiagnostics+chat (dev):** | |
| `f7e9c2a4b8d1` | add_chat_message_edited_at: chat_messages.edited_at (Stage 31z) |
| `a9b3e1f7c2d4` | add_chat_attachments: chat_attachments table + FK (Stage 32b) |
| `c1d4e7a2f9b3` | add_test_interpretations: пороги интерпретации тестов (психодиагностика, Этап A) — **head A** |
| **Ветка appointments (alex):** | |
| `e1a2b3c4d5f6` | add_appointments_system: meeting_types, group_sessions, group_session_registrations, appointments.meeting_type_id+decline_reason; appointments.status VARCHAR(20→30); partial unique index `ux_gsr_active` (status='registered'); БЕЗ ALTER TYPE и БЕЗ повторного ends_at (он уже в baseline) |
| `71dfb9c56b13` | add_online_to_appointment_modality: идемпотентный DO $$ (enum только для legacy SQL-bootstrap DBs; в Alembic-chain modality уже VARCHAR(20)) |
| `9e193b84bba8` | rework_schedule_slot_model: meeting_types +description/+buffer_minutes; schedule_rules +meeting_type_id/+period/+series_id, −slot_duration_minutes/−break_minutes; новая schedule_breaks (recurring breaks); schedule_exceptions enum→varchar + снята уникальность `(psychologist_id, exception_date)`; group_sessions +description; view `v_schedule_active` пересоздан без slot/break |
| `c9a3f2e1d8b6` | schedule_rule_not_null_break_periods: schedule_rules.meeting_type_id→NOT NULL (FK→RESTRICT); schedule_breaks +effective_from (NOT NULL) +effective_until (nullable) |
| `b2d4f6a8c1e3` | schedule_auto_extend_created_by: schedule_rules +auto_extend (BOOL NOT NULL default false) +created_by (FK users→SET NULL); только ADD COLUMN/FK, обратимо |
| `d3e6f9a2b5c8` | appointments_booking_source_created_by: appointments +booking_source (default `student_self`) +created_by (FK users→SET NULL) для аудита студентской и supervisor-created записи |
| `f1a4c7e0b9d2` | schedule_rule_meeting_type_optional: schedule_rules.meeting_type_id снова nullable; расписание v3 хранит рабочие окна психолога без привязки к типу встречи, а MeetingType выбирается при поиске/создании записи |
| `a1b2c3d4e5f6` | add_unregistered_student_cards: карточки walk-in клиентов без аккаунта; appointments.client_id nullable + unregistered_student_card_id; CHECK ровно один субъект записи |
| `b7c8d9e0f1a2` | index_card_linked_user_id: индекс для привязки карточек незарегистрированных студентов к созданному/зарегистрированному аккаунту — **head B** |
| `be8d3ad39b3a` | merge_appointments_and_psychodiagnostics_heads: merge-миграция (`alembic merge`), объединяет две ветви (A: `c1d4e7a2f9b3` психодиагностика+чат, B: `b7c8d9e0f1a2` appointments) в один head. Без операций над схемой (upgrade/downgrade = pass) |
| **Ветка diary (igor, от `a9b3e1f7c2d4`):** | |
| `b2e4d7f1a9c3` | add_diary_tables: diary_emotions (catalog), diary_entries (partial UNIQUE active per student+date) |
| `c3a7f8e2d1b9` | update_diary_emotions_catalog: deactivate angry/light, add tense/irritated/low/lonely, reorder to 12 active states |
| `db0b2e177da5` | merge_diary_into_dev_heads: вторая merge-миграция (`alembic merge`), объединяет `be8d3ad39b3a` (dev) и `c3a7f8e2d1b9` (diary) в один head. Без операций над схемой (upgrade/downgrade = pass) — **head** |

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
| `chat_conversations`, `chat_messages` | Messenger (Stage 28b/29b): `type` engagement/system; engagement-беседа — одна на engagement (UNIQUE), system-беседа — одна на `recipient_id` (partial UNIQUE); `chat_messages.message_kind` user/system, `event_key` для idempotency system-сообщений; content — только `enc:v1:` |
| `chat_attachments` | Вложения чата (Stage 32b): metadata (original_filename, mime_type, file_size, storage_key, checksum, is_image); физический файл — в `CHAT_FILE_STORAGE_DIR` (private FS, не public static); soft delete через `deleted_at`; скачивание только через auth backend endpoint |
| `appointments` | Записи на консультации |
| `unregistered_student_cards` | Карточки walk-in клиентов без аккаунта: минимальные ПДн, consent_source/created_by, archived, optional linked_user_id. Используются supervisor manual booking через `unregistered_student_card_id`; при регистрации/создании аккаунта могут привязаться по normalized_email |
| `meeting_types` | Типы встреч; владеют `duration_minutes` + `buffer_minutes` (по ним строятся слоты), `description`, форматами, `is_group/is_active/is_bookable` |
| `schedule_rules` | Рабочие окна психолога (только доступность; `meeting_type_id` опционален/legacy и НЕ ограничивает тип встречи в schedule v3, `period`, `series_id` для серии rules+breaks, `auto_extend`, `created_by`). Длительность/буфер — НЕ здесь, а в `meeting_types`. Soft-delete/restore расписания — через `is_active` на уровне серии (не трогает Appointment) |
| `schedule_breaks` | Повторяющиеся перерывы по дню недели (например обед 13:00–14:00); вырезают пересекающиеся слоты. Перерыв, созданный вместе с расписанием, разделяет `series_id` и период с правилами |
| `schedule_exceptions` | Разовые изменения на дату: `day_off` / `unavailable` / `extra_availability`; на одну дату допускается несколько (без уникальности) |
| `tests`, `questions`, `options`, `test_results` | Психодиагностика |
| `categories`, `article_categories`, `test_categories` | Типы материалов/категории. В MVP плоские: `parent_id` не используется в Admin CRUD |
| `tags`, `article_tags`, `news_tags`, `test_tags` | Темы/теги контента. M:N с articles, news, tests. Уникальность через `lower(name)` |
| `auth_log`, `audit_log`, `data_change_log` | Аудит. В prod могут быть партиционированы по месяцам |
| `diary_emotions` | Справочник эмоций дневника: 12 активных состояний (after c3a7f8e2d1b9); key, label, sort_order, is_active; angry/light — деактивированы (is_active=false), legacy labels в DiaryEntryItem.jsx |
| `diary_entries` | Дневник студента: одна активная запись в день (partial UNIQUE по student_id + entry_date WHERE NOT deleted); mood_score_enc, entry_text_enc, emotions_enc — Fernet encrypted; только student |
| `refresh_tokens`, `user_mfa_methods` | NOT IMPLEMENTED. Таблицы зарезервированы. |

> **Партиционирование audit-таблиц:** `auth_log`/`audit_log`/`data_change_log`
> создаются как `PARTITION BY RANGE (created_at)` с начальными партициями 2026-01..2028-12.
> Будущие партиции управляются через `scripts/ensure_audit_partitions.py`.
> Запускать заблаговременно (не из FastAPI).

**Роли в системе:**

| Роль | Кто | Как создаётся |
|------|-----|---------------|
| `student` | Студент/клиент | Публичная регистрация с OTP, либо admin/supervisor через `POST /api/supervisor/students` (очное согласие, consent_records) |
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
│   ├── diary.api.js    — /api/diary/* (getDiaryEmotions, getTodayDiaryEntry, saveTodayDiaryEntry,
│   │                     getDiaryEntries, updateDiaryEntry, deleteDiaryEntry, getDiarySummary)
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
| POST | `/api/chat/student/conversations/{uuid}/attachments` | Student | ✅ |
| GET | `/api/chat/student/conversations/{uuid}/attachments/{att_uuid}/download` | Student | ✅ |
| POST | `/api/chat/conversations/{uuid}/attachments` | Psychologist | ✅ |
| GET | `/api/chat/conversations/{uuid}/attachments/{att_uuid}/download` | Psychologist | ✅ |
| GET | `/api/diary/emotions` | Student | ✅ |
| GET | `/api/diary/today` | Student | ✅ |
| PUT | `/api/diary/today` | Student | ✅ |
| GET | `/api/diary/entries` | Student | ✅ |
| PATCH | `/api/diary/entries/{entry_uuid}` | Student | ✅ |
| DELETE | `/api/diary/entries/{entry_uuid}` | Student | ✅ |
| GET | `/api/diary/summary` | Student | ✅ |

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

**Student tasks — accepted demo/mock (НЕ баг). Diary и calendar — уже на real API:**
- `/student/tasks` работает на hardcoded mock-данных — осознанная демо-витрина до отдельного этапа
- `/student/calendar` подключён к real appointments API: тип встречи → формат →
  дата → доступные слоты назначенного психолога; upcoming/history показывают реальные записи
- **`/student/diary` подключён к real API** (Stage Diary Frontend Integration):
  одна активная запись в день, mood score 1–10, optional text/emotions, history/load more,
  edit/delete и soft-delete; backend encrypted-at-rest; мок-данные удалены
- **StudentHome после UX redesign:** nextStepCard показывает no-entry/today-entry state,
  action cards ведут на реальные маршруты, observationCard виден только при наличии записей;
  график и fake dashboard metrics удалены
- **Diary Analytics Lite завершён:** DiaryPage показывает сводку периода поверх summary API;
  MoodChart удалён, линейный график не возвращать без отдельной UX-validation
- **Diary pending:** audit trail edit/delete; timezone-aware backend date policy;
  psychologist access только после отдельной consent/legal policy; advanced observation
  insights — только отдельный этап без обязательного line-chart формата
- `/student/chat` и `/psychologist/chat` уже работают с real `/api/chat`:
  единый Messenger (one-to-one поверх `therapy_engagements` + read-only system
  conversation), polling, read/unread через `read_at`, VK-like entry (mark-read
  только по явному клику), глобальный nav badge + per-dialog unread, system-беседа
  последняя в списке, approximate online/offline (`peer_is_online`, порог 10 мин)
- **Действия со своим сообщением (Stage 31y/31y-hotfix):** меню «…» (`MessageActionsMenu`,
  не отдельная кнопка-карандаш) — «Редактировать»/«Удалить»; удаление — через confirm-диалог,
  soft delete на backend; удалённые сообщения скрыты из ленты БЕЗ плейсхолдера «Сообщение
  удалено» (техническая запись остаётся только для audit/security, участникам не показывается)
- **MessageBubble (Stage 31z/31z-hotfix):** визуальное облачко сообщения — отдельный
  feature-specific компонент `src/features/chat/components/MessageBubble` (НЕ глобальный
  shared UI, не переносить в `src/components/UI` без второго независимого потребителя);
  meta (время/«изменено»/✓/✓✓) внутри bubble, компактно для коротких сообщений, с переносом
  вниз-направо для длинных (Telegram-style); system-сообщения всегда как bubble от «MindCare»,
  без меню действий, без «изменено», без read receipts
- **Polling reconcile (Stage 31ab):** `reconcileMessagesSnapshot` в `pollNew` (student +
  psychologist) — удалённое сообщение исчезает у собеседника после следующего polling tick
  (≤ 8 сек) без переоткрытия диалога; без WebSocket/SSE; без placeholder; `mergeMessages`
  сохранён (add/update); MVP-ограничение: reconcile только для последних 50 сообщений
  (история старше snapshot window — при переоткрытии)
- **Chat hook architecture (Stage 31ad):** `useStudentChat` и `usePsychologistChat` —
  thin wrappers поверх `useChatCore(adapter)` (`features/chat/hooks/useChatCore.js`);
  public return shape не изменился; `useSystemConversation` — отдельный hook, не входит
  в `useChatCore`; backend/API/Alembic/UI-компоненты (`ChatWindow`, `MessageList`,
  `MessageBubble`) не менялись; 409 Conflict — через optional `getConversation` (student:
  null → silent list reload; psychologist: `getPsychologistConversation` → точечный refresh)
- **Attachments Stage 32b–32j + hotfixes:** upload через скрепку / drag&drop; text+attachments;
  attachment-only message; карточки вложений (`AttachmentCard`/`AttachmentList`);
  files-first layout: в сообщении с файлами и текстом сначала файлы, затем divider,
  затем текст как caption и meta внизу; attachment-only — без divider;
  скачивание через auth backend endpoint (private storage, не public static);
  Chromium safe save через `showSaveFilePicker`, fallback — anchor download; Office download
  не должен переводить SPA на `blob:` URL и не должен закрывать чат;
  preview для `image/jpeg`, `image/png`, `image/webp`, `application/pdf` через
  `AttachmentPreviewLightbox` (`AttachmentPreviewLightbox.jsx/.module.css/.test.jsx`):
  `AttachmentCard` локально управляет preview state, использует authenticated download handler,
  создаёт object URL и очищает его через `URL.revokeObjectURL`; lightbox закрывается через X,
  overlay, Esc; клик по image/pdf content не закрывает preview; URL страницы не меняется;
  file policy: jpg/jpeg, png, webp, pdf, txt, doc/docx, xls/xlsx, ppt/pptx разрешены;
  svg/html/js/executable/script extensions заблокированы; архивы отложены; Office/TXT/SVG/unknown
  MIME остаются download-only;
  edit-mode удаление отдельных файлов (`EditableAttachmentList`, `remove_attachment_uuids`);
  удаление сообщения/вложения — soft delete (`chat_attachments.deleted_at`);
  физический файл не удаляется сразу.
  **Pending:** thumbnails; Office/TXT preview; PDF.js integration при необходимости;
  upload progress %; retry queue; MIME magic bytes; antivirus; at-rest encryption физических файлов;
  добавление файлов в edit-mode. Для orphan-вложений (`message_id IS NULL`) уже есть
  helper `scripts/cleanup_orphan_attachments.py` с dry-run по умолчанию и явным `--apply`.
  **Pending cleanup/retention:** физическое удаление файлов soft-deleted вложений после
  retention-периода, тесты cleanup CLI и cron/systemd timer после ручной проверки.
  Компоненты attachment UI (feature-specific, не global shared UI):
  `AttachmentCard`, `AttachmentList`, `SelectedAttachmentList` (pre-send picker),
  `EditableAttachmentList` (edit-mode), `DragDropOverlay`, `AttachmentPreviewLightbox` —
  проверить перед созданием новых
- Runtime student chat mock (CONTACTS, INITIAL_MESSAGES, MOCK_*) удалён
- **Mobile (Stage 30d):** Messenger `≤900px` — list/thread (back-кнопка в шапке чата);
  CabinetLayout `>980px` full sidebar / `601–980px` icon-rail / `≤600px` мобильный drawer
  (`sidebarInner` переиспользуется; collapse-правила заскоуплены под `.sidebar`); на `≤600px`
  `.app`=`grid 1fr` (фикс пустого кабинета) и разгруженный topbar (скрыты bell/mail).
  Breakpoints разные по слоям: Messenger=900px, Cabinet=600px (+980 icon-rail) — не «выравнивать»
- **Ограничения MVP** (не баги): presence приблизительный (порог 10 мин, не realtime);
  read-receipt live только в snapshot `limit=50`; без WebSocket/SSE; drawer без focus-trap;
  snapshot reconcile ограничен последними 50 сообщениями (история старше snapshot window
  синхронизируется только при переоткрытии диалога)
- **Group chat — postponed/future**: отдельный этап после стабилизации Messenger,
  обязателен READ-ONLY design audit (см. `docs/BACKLOG.md`); учебная группа ≠
  автоматический чат. Не начинать group chat без отдельного этапа
- Не добавлять WebSocket/SSE, Action Center/колокольчик или
  staff-доступ к content без отдельного этапа
- `questions_answers` — это Q&A-модуль (один вопрос → один ответ), НЕ чат;
  не использовать как основу для чата

Исправлено (больше не критично):
- ~~Партиции audit-таблиц захардкожены до 31.12.2026~~ — закрыто: миграция `3a7c5e2b8f1d` создаёт partitioned tables, `scripts/ensure_audit_partitions.py` управляет будущими партициями
- ~~`session_notes.content` хранится открытым текстом~~ — закрыто: Fernet application-layer encryption в `app/core/encryption.py`; `DATA_ENCRYPTION_KEY` обязателен в `.env` и также защищает `chat_messages.content`
- OTP-коды теперь хранятся как SHA-256 хеш (migration `c5d8a1b4e7f2`, otp_service.py)
- ~~Нет rate limiting на auth-эндпоинтах~~ — закрыто (Stage 21): `app/core/rate_limit.py`,
  per-process MVP; Redis/shared storage — отдельный этап
- ~~Session-токены plaintext в `user_sessions.id` / `auth_log.session_id`~~ — закрыто (Stage 22b):
  SHA-256 hash-on-lookup; зачистка старых plaintext-строк — отдельный maintenance-этап
- ~~Нет legal basis для admin-created users~~ — закрыто (Stage 23b): `user_legal_basis_records`;
  backfill `--apply` выполнить при деплое
- ~~Raw SMTP/auth ошибки клиенту, `[object Object]` на 422, незамаскированный email в логах~~ —
  закрыто (Stage 31m-fix-a): client.js парсит 422 detail array, SMTP/auth errors санитизированы,
  email маскируется `mask_email`
- ~~OTP INFO-логи раскрывают email; confirm не передаёт IP/UA в consent; `_assign_role` silent skip~~ —
  закрыто (Stage 31m-fix-b1): OTP-логи маскируют email, consent получает IP/User-Agent, роль обязана существовать
- ~~Registration confirm не атомарен (user без consent при сбое)~~ — закрыто (Stage 31m-fix-b2):
  один UoW/commit (user/role/consent + consume OTP); welcome — soft-fail после commit
- ~~Password reset confirm / change password не атомарны (пароль изменён, старые сессии живы)~~ —
  закрыто (Stage 31m-fix-b3): password_hash + revoke sessions (+ consume OTP) в одной транзакции;
  system-уведомление soft-fail после commit
- Остаётся pending (deferred): OTP concurrency / `SELECT … FOR UPDATE`; `_get_primary_role`
  read-fallback `"student"`; transactional outbox для post-commit уведомлений
