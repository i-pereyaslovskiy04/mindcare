# CLAUDE.md

Этот файл описывает проект для Claude Code. Прочитай его целиком перед любой задачей.

Актуальный handoff по последнему крупному блоку работ:
`docs/HANDOFFS/2026-07-16-email-domain-policy-self-admin-complete.md`
— управляемый allowlist доменов для создания новых аккаунтов, защита собственной
роли `admin` и реорганизация admin-навигации. Handoff по multi-role модели от
2026-07-14 и appointments/scheduling handoff остаются историческими snapshot.

Актуальная ролевая модель: multi-role user model зафиксирована в
`docs/DECISIONS.md` ADR-018. Пользователь может иметь несколько активных ролей
одновременно; `role` — только legacy/default/effective convenience, не единственный
источник авторизации.

## Рекомендуемый запуск Claude Code

- Обычная реализация и corrective pass: актуальный **Claude Sonnet** (сейчас
  Sonnet 5), усилие `High`.
- Небольшая локальная правка с ясным контрактом: Sonnet, усилие `Medium`.
- Сложная архитектура, auth/security/compliance, миграция с высокой ценой ошибки:
  актуальный **Claude Opus** (сейчас Opus 5), усилие `High`; максимальное усилие
  использовать только для действительно самых тяжёлых задач.
- Конкретный task prompt может переопределить рекомендацию. В промптах, которые
  готовит Codex, модель и усилие должны быть указаны явно.

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

```bash
# Активация виртуального окружения (Linux/macOS, обязательно перед всем остальным)
source .venv/bin/activate
```

```powershell
# Windows: активация виртуального окружения
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
> Все 58 таблиц создаются через `alembic upgrade head`.
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
.venv/bin/python -m compileall app -q
.venv/bin/python -m pytest tests/test_change_password.py -v
.venv/bin/python -m pytest tests/ -v
```

```powershell
# Windows
.venv\Scripts\python.exe -m compileall app -q
.venv\Scripts\python.exe -m pytest tests/ -v
```

**Frontend:**
```bash
cd mindcare_web
npm run lint
npm run build
```

**Через скрипты в корне проекта:**
```bash
./test.sh     # compileall + все backend-тесты (без запуска проекта)  [Linux]
./start.sh    # backend-тесты, затем запуск проекта                   [Linux]
```

```powershell
.\test.ps1    # то же самое на Windows
.\start.ps1
```

### Уровни тестов

| Уровень | Что покрывает | Когда добавлять |
|---------|---------------|-----------------|
| Unit | Service/helper logic, без реальной БД | Обязательно для новых auth/security/critical изменений |
| API/Integration | Route → deps → service → storage → DB | Желательно для auth/session/permissions/encryption |
| Manual smoke | Пользовательские сценарии | Обязателен при UI/UX-sensitive изменениях |
| E2E | Полный browser flow | Позже, после стабилизации UI |

### Текущее покрытие

Тесты: `mindcare_api/tests/` (unit) и `mindcare_api/tests/integration/`.
Состав и охват — `ls` по этим каталогам и docstring'и файлов; полный прогон —
`./test.sh` (Linux) / `.\test.ps1` (Windows). Integration-тесты требуют
запущенный dev PostgreSQL на alembic head.
Frontend: `npm test -- --watchAll=false`, `npm run lint`, `npm run build`.

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

Состав модулей — `ls mindcare_api/app/`. Каждый доменный модуль устроен одинаково:
`routes.py` / `routes_admin.py` · `schemas.py` · `service.py` (без FastAPI/HTTP) ·
`storage.py` (весь SQLAlchemy здесь). Вне этой схемы: `core/` (config, encryption,
normalization, rate_limit), `db/` (session, init_db, seed, models/), `auth/`,
`services/` (SMTP, email), `scripts/` (create_admin, ensure_audit_partitions,
backfill_legal_basis, extend_schedules, repair_missing_chat_conversations,
cleanup_orphan_attachments, test_smtp), `db/sql/` (legacy bootstrap-схема).

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
   role control (там student по-прежнему НЕ selectable). Пароль/ПДн не логировать
✅ `POST /api/admin/users` создаёт staff с одной или несколькими ролями:
   request содержит ровно одно из legacy `role` или `roles[]`; только
   `psychologist`/`supervisor`/`admin`, без `student`. `basis_reference`
   обязателен и trim-ится; на каждую уникальную staff-роль в той же
   транзакции пишется `user_legal_basis_records` с metadata
   `action=user_create`/`created_role`/`roles_after`. Response возвращает
   детерминированный `roles[]` и legacy primary `role`. Welcome email для staff
   role-neutral: без упоминания конкретной роли или прав.
✅ Добавление новой staff-роли через admin role management
   (psychologist/supervisor/admin) требует legal basis
   (legal_basis_confirmed + basis_type + basis_reference); добавление роли и запись
   user_legal_basis_records атомарны; metadata: action=role_add/added_role/
   roles_before/roles_after. Удаление staff-роли требует audit trail, но не новый
   legal basis; старые user_legal_basis_records не удаляются.
✅ Роли в admin edit-модалке РЕДАКТИРУЕМЫ как multi-role control / set-based API,
   но безопасно: при добавлении staff/admin роли UI показывает блок legal basis и
   шлёт его поля; backend guard обязателен как defense-in-depth (не полагаться
   только на UI). Запрещено заменять весь набор user_roles одним role.
   В PATCH отсутствие поля `roles` означает «не менять роли», а явный `roles: []` —
   целевой пустой набор staff-ролей: он снимает все staff-роли только если после
   операции остаётся другая активная роль (например, `student`), иначе backend
   отклоняет запрос с 422. Удаление всегда фиксируется в audit trail.
✅ student НЕ selectable в admin role control. Студенты появляются через
   self-registration ИЛИ через staff-created student flow (`POST /api/supervisor/students`);
   существующая роль student показывается read-only badge и не удаляется случайно.
   student как target роли из admin edit UI/API не отправляется без отдельного
   compliance-решения
✅ Администратор не может снять у самого себя membership-роль admin. Backend
   сравнивает actor_id и target user id; frontend lock — только UX-дублирование.
   Другой администратор может изменить роли пользователя.
✅ Все HTTP/API creation flows допускают новый аккаунт только для активного точного
   нормализованного домена из allowed_email_domains: self-registration,
   admin-created staff и supervisor/admin-created student. Existing login/password
   reset не блокировать. Authoritative check выполняется в creation transaction;
   в register confirm — до consume OTP. Локальный bootstrap `scripts/create_admin.py`
   остаётся отдельным privileged ops-path вне allowlist; использовать только при
   развёртывании и вручную выбирать разрешённый организацией домен.
✅ Allowlist управляется только admin через GET/POST/PATCH
   /api/admin/email-domains. DELETE нет; отключённую строку реактивировать PATCH,
   не повторным POST. Последний активный домен отключить нельзя. Audit не содержит
   сырой comment.
❌ Не слать role changes без legal basis при добавлении staff-роли
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
✅ Психодиагностика: вопросы теста, по которому есть test_results, НЕ редактируются.
   student_answers ссылается на questions/options через ON DELETE RESTRICT, поэтому
   замена дерева физически невозможна. service.update_test → TestHasResults → HTTP 409;
   routes_admin дополнительно ловит IntegrityError (defense-in-depth). Штатный путь —
   POST /api/admin/tests/{uuid}/duplicate (копия как черновик is_active=false, version=1).
   Метаданные и test_interpretations менять можно: FK из результатов на них нет,
   а расшифровка снапшотится в test_results/test_result_scales при submit
✅ Admin-конструктор шлёт questions/interpretations в PATCH только если они реально
   изменились (dirty-tracking по снапшоту загрузки) — иначе переименование теста
   с результатами упиралось бы в 409 на ровном месте
✅ Шкалы вопросов — правило «все или ни одной»: scoring.compute_result считает тест
   многошкальным, если config["scale"] есть хоть у одного вопроса, и выбрасывает из
   подсчёта остальные (total_score → NULL). Частичное заполнение отвергается
   service._validate_scale_coverage (422) + предупреждение в QuestionBuilder
✅ Покрытие порогов интерпретации — ПРЕДУПРЕЖДЕНИЕ, не 422: правило проверяемо только
   когда известны И вопросы, И пороги, а PATCH частичный (можно прислать одни
   interpretations). service.analyze_test отдаёт score_bounds + issues
   (gap / out_of_range / unknown_scale) через POST /api/admin/tests/analyze;
   конструктор показывает их в TestAnalysisPanel. Не превращать в 422 — правило
   применится наполовину и будет обходиться частичным PATCH
✅ Предпросмотр методики автором: POST /api/admin/tests/analyze (диапазон+пороги) и
   POST /api/admin/tests/preview-score (пробный подсчёт несохранённого дерева).
   Оба НИЧЕГО не сохраняют и объявлены ДО `/{uuid}`-маршрутов (иначе FastAPI примет
   путь за uuid). Вопросы адресуются по question_order, варианты по option_order —
   у несохранённого дерева нет id
✅ Предпросмотр рендерится ТЕМ ЖЕ QuestionRenderer, что и прохождение студентом
   (`src/features/tests/ui/QuestionRenderer.jsx` — общий слой, не под pages/).
   value_score в предпросмотр не передаётся: студент ключа теста не видит
❌ Не дублировать scoring в JS ради «живых» подсчётов в конструкторе — считает только
   app/tests/scoring.py, фронт ходит на analyze/preview-score. Иначе предупреждения
   разойдутся с реальным результатом студента
❌ Не считать «черновик можно посмотреть студенческим аккаунтом»: student-роутер
   закрыт require_role("student"), а get_active_test_full фильтрует is_active=true
✅ student_answers.free_text_answer_enc — Fernet `enc:v1:`, как session_notes/chat.
   На wire (SubmitIn) поле по-прежнему называется free_text_answer; шифрование —
   в storage.save_result. Plaintext не хранить и не логировать
❌ Не возвращать plaintext-колонку free_text_answer и не писать свободный текст
   ответа в audit/logs
❌ Не считать «результаты тестов не шифруются» распространяющимся на free_text:
   решение опиралось на «не свободный терапевтический текст»
❌ Не давать psychologist доступ к результатам тестов (в MVP закрыто осознанно);
   supervisor-просмотр (Этап E) — отдельный этап, и чтение результата обязано писать
   audit-событие по аналогии с session_note_content_read
```

---

### База данных: схема

58 таблиц в 14 доменных модулях. Схема управляется через Alembic.
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
| `db0b2e177da5` | merge_diary_into_dev_heads: вторая merge-миграция (`alembic merge`), объединяет `be8d3ad39b3a` (dev) и `c3a7f8e2d1b9` (diary) в один head. Без операций над схемой (upgrade/downgrade = pass) |
| **Ветка themes (dev, от `db0b2e177da5`):** | |
| `e7c1a9d4b385` | add_user_ui_theme_prefs: users.ui_theme_palette / ui_theme_mode (тема в профиле) |
| **Ветка tests-fix (vb, от `e7c1a9d4b385`):** | |
| `a4f2c8e1b7d9` | encrypt_student_answer_free_text: student_answers.free_text_answer (plaintext) → free_text_answer_enc (Fernet `enc:v1:`). Backfill не требовался — free_text-вопросов не создавалось; открытая колонка удалена, чтобы не осталась ловушкой |
| **Ветка email-domains (alex, от `db0b2e177da5`):** | |
| `c7f1a9e4d2b8` | add_allowed_email_domains: таблица `allowed_email_domains`, уникальный нормализованный domain, active/comment/created_by/timestamps и seed 11 начальных доменов |
| `27202a87a892` | merge_email_domains_and_ui_theme_heads: merge-миграция (`alembic merge`), объединяет `e7c1a9d4b385` (themes) и `c7f1a9e4d2b8` (email-domains) в один head. Без операций над схемой (upgrade/downgrade = pass) |
| `3b46b9d94c08` | merge_tests_fix_and_email_domains_theme_heads: четвёртая merge-миграция (`alembic merge`), объединяет `a4f2c8e1b7d9` (tests-fix, dev) и `27202a87a892` (email-domains+themes, mindcare_alex) в один head. Без операций над схемой (upgrade/downgrade = pass) — **head**

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
| `allowed_email_domains` | Управляемый allowlist точных нормализованных доменов для создания новых аккаунтов; отключённые строки сохраняются для истории и могут быть реактивированы |
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

**Multi-role policy (ADR-018):**
- `user_roles` — источник прав доступа. У одного пользователя может быть несколько
  активных ролей одновременно, например `["admin", "supervisor", "psychologist"]`.
- Auth/session/profile API должны возвращать `roles: Role[]`. Поле `role` можно
  временно сохранять как primary/default/effective role для совместимости, но
  backend authorization не должен полагаться только на него.
- Backend `require_role(...)` проверяет пересечение allowed roles с
  `current_user.roles`. Frontend `RoleRoute` проверяет `user.roles`.
- Для экранов и аудита, где важно “в каком кабинете действует пользователь”,
  использовать `active_role`/`effective_role`, валидированный по `user_roles`.
  Клиентский выбор роли — только hint; backend всё равно проверяет membership.
- Admin role edit должен быть set-based: добавлять/удалять конкретные роли, не
  удаляя весь набор `user_roles`. Запрещён destructive replace-all roles.
- Для PATCH отсутствие `roles` означает «не менять роли»; явный `roles: []`
  означает снять все staff-роли. Операция допустима только если у пользователя
  остаётся другая активная роль; оставить аккаунт без ролей нельзя.
- Admin create принимает ровно одно из `role`/`roles[]`; admin list,
  single-read и create response возвращают активные `roles[]` и legacy primary
  `role` (может быть `null` только у аккаунта без активных ролей).
- Добавление staff-роли (`psychologist`, `supervisor`, `admin`) требует
  `user_legal_basis_records`; роль `student` не назначается через admin role
  control без отдельного compliance-решения.
- Пользователь с `admin` + `supervisor` попадает в `/admin/*` по роли `admin`.
  Чистая роль `supervisor` не наследует доступ к admin panel.
- Администратор не может снять у самого себя активную membership-роль `admin`.
  Guard авторитетно работает на backend по стабильному actor/user id; другой
  администратор может изменить этот набор ролей. Самодеактивация и самоудаление
  этим guard не запрещены и требуют отдельного продуктового решения.

**Email-domain policy для новых аккаунтов (ADR-019):**
- Через HTTP/API новый аккаунт можно создать только с точным нормализованным
  доменом, для которого в `allowed_email_domains` есть активная строка. Отсутствие
  домена в allowlist означает запрет; отдельного denylist нет.
- Политика применяется к self-registration, admin-created staff и
  supervisor/admin-created student. В registration flow ранняя проверка выполняется
  до отправки OTP, а authoritative проверка — в транзакции confirm до consume OTP.
- Существующие пользователи с доменом, который отсутствует или был отключён,
  сохраняют login и password reset. Политика не является ретроактивной блокировкой.
- Реактивация soft-deleted пользователя считается созданием/возвратом аккаунта и
  требует активного домена.
- Admin API: `GET/POST/PATCH /api/admin/email-domains`; физического DELETE нет.
  Повторный POST существующего отключённого домена даёт 409, реактивация делается
  только PATCH `is_active=true`. Последний активный домен отключить нельзя.
- Это управляемая организационная политика проекта, а не утверждение об
  официальном или исчерпывающем государственном перечне почтовых сервисов.
- `scripts/create_admin.py` — отдельный локальный bootstrap/ops path и сейчас не
  проверяет allowlist. Не использовать его как обычный account-creation API.

---

### Frontend

> Структура `src/`, правила API-слоя, дизайн-токены и темы, режим для слабовидящих
> (ГОСТ Р 52872-2019), UI governance и чек-лист фронтовой задачи — в
> `mindcare_web/CLAUDE.md` (загружается при работе с файлами под `mindcare_web/`).
> Полные правила — `mindcare_web/ARCHITECTURE.md`, `docs/UI_COMPONENTS_GUIDE.md`,
> `docs/UI_TECH_DEBT.md`, `docs/FRONTEND_CHECKLIST.md`, `docs/AUDIT_RULES.md`.

Терминология админки: `/admin/categories` в UI — «Типы материалов»,
`/admin/tags` — «Темы». API paths, модели и файлы под UI-label не переименовывать.

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

Актуальный список — роутеры `mindcare_api/app/*/routes*.py` и OpenAPI на `/docs`
запущенного бэкенда. В CLAUDE.md список не дублируется: он устаревал быстрее,
чем правился (appointments, supervisor, session_notes в нём отсутствовали).

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

> Именование, hook-контракты, правила API-вызовов и CSS — в `mindcare_web/CLAUDE.md`
> (загружается при работе с фронтом) и `mindcare_web/ARCHITECTURE.md`.

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

- `/student/tasks` — hardcoded mock-данные, осознанная демо-витрина до отдельного этапа
- `/student/diary`, `/student/calendar`, `/student/chat`, `/psychologist/chat` —
  уже на real API, мок-данные удалены (подробности — в `docs/BACKLOG.md`)
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
- Остаётся pending (deferred): OTP concurrency / `SELECT … FOR UPDATE`;
  transactional outbox для post-commit уведомлений
- ~~`_get_primary_role` read-fallback `"student"`~~ — закрыто в ADR-018:
  отсутствие активных ролей возвращает `role=null`, доступ отклоняется; источник
  истины — активные `roles[]`
