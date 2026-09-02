# CLAUDE.md

Этот файл описывает проект для Claude Code. Прочитай его целиком перед любой задачей.

Актуальный handoff: `docs/HANDOFFS/2026-09-02-test-moderation-followups.md` —
доработки модерации тестов поверх Этапов E/F1/F2: (1) модерация тестов открыта
supervisor во фронтенде (`/supervisor/tests`, был только backend-доступ, UI
отсутствовал — реальный баг, не недоделка; `AdminTestsPage`/`TestFormPage`
параметризованы `cabinetRole`); (2) быстрая деактивация/активация теста из
списка (иконка `power`); (3) **Этап F2.1** — психолог дорабатывает СВОЙ
`published`-тест, правка атомарно снимает публикацию (`status→draft`, audit
`test_unpublished_for_edit`), диалог-предупреждение перед редактированием;
(4) **Этап F2.2** — психолог дублирует СВОЙ тест в ЛЮБОМ статусе источника
(включая published/in_review — не мутирует оригинал), `test_duplicated`
расширен на psychologist. REGISTRY 110 → 111.

Предыдущий крупный блок работ:
`docs/HANDOFFS/2026-09-01-admin-impersonation.md` —
impersonation администратором («Зайти под именем» в `/admin/users`, **ADR-025**):
`user_sessions.impersonator_user_id` (миграция `a1c2e3f4b5d6`), `/me` отдаёт
`impersonating`/`impersonator_name`, `POST /api/admin/users/{uuid}/impersonate`,
audit `admin_user_impersonated` (REGISTRY 110), фронт — `ImpersonationBanner`
возврата в профиль админа, кнопка «Зайти» в `UsersTable`.

Ещё раньше:
`docs/HANDOFFS/2026-08-30-test-question-option-media-images.md` — медиа в вопросах/
вариантах тестов + отложенные функции. **Блок 1:** изображения (связки
`question_media`/`option_media` сквозь schemas/storage/service и фронт). **Блок 2**
(тот же файл, §9): несколько медиа на вопрос; audio/video в вопросах (новый
`POST /api/media/upload/av`, компонент `MediaUpload`, `MediaOut.kind`); upload
расширен до supervisor + новое audit-событие `media_uploaded` (REGISTRY 105);
`weighted` scoring (`config["weight"]`); CSV-экспорт результата; клиентский
тайм-лимит (`SubmitIn.timed_out`); случайный порядок вопросов/вариантов (миграция
`d9f2a1c7b3e4`, `tests.shuffle_questions`/`shuffle_options`). **Блок 3** (§ «Блок 3»):
**Этап E** — staff-доступ к результатам (`GET /api/staff/test-results`,
`app/tests/routes_staff.py`; supervisor любой, psychologist по `TherapyEngagement`,
admin нет; audit `test_result_content_read`, REGISTRY 106; фронт —
`StudentTestResults` в карточке психолога и модалке супервизора). **Блок 4**
(§ «Блок 4»): **Этап F1** — moderation workflow тестов (миграция `e1b4c8f2a6d9`,
`tests.status` draft/in_review/published/needs_changes; state-machine в
`app/tests/service.py`; роуты `/admin/tests/{uuid}/publish`|`/return` и новый
`app/tests/routes_psych.py` submit-for-review; 3 audit-события, REGISTRY 109;
фронт — статус-бейдж/действия в `TestsTable`/`AdminTestsPage`, селектор статуса
в `TestFormPage`). **Этап F2** — авторство psychologist: ownership-scoped CRUD
(`routes_psych.py` расширен, `service._own_editable_test`/`create_my_test`
форсирует draft), медиа-загрузка и `test_created/updated/deleted` audit
расширены на psychologist (REGISTRY count не меняется — 109); фронт —
`TestFormPage` параметризован через `config` (admin/psychologist один
компонент), `PsychologistTestsPage`/`PsychologistTestFormPage`, nav «Тесты» в
кабинете психолога. Отложены: caption вариантов, `duration_seconds`,
PDF-экспорт, серверный тайм-лимит, `custom` scoring, duplicate для psychologist.

Предыдущий крупный блок:
`docs/HANDOFFS/2026-08-29-staff-student-role-admin-nav-dark-theme.md` — роль
`student` всем staff (функциональный доступ к кабинету студента, изоляция от
реальных списков студентов; **ADR-024**), скрытие student при логине и в
`/admin/users`, иконка предпросмотра теста, ссылка «На главную» из всех
кабинетов/админки, доводка тёмной темы (переключатель кабинетов, выбор роли,
Hero-баннер не инвертируется в тёмных палитрах).

Предшествующий крупный блок:
`docs/HANDOFFS/2026-08-28-service-cards-cms-complete.md` — карточки услуг
`/services` как CMS (модуль `service_cards`); предыдущий блок того же паттерна —
`docs/HANDOFFS/2026-08-27-hero-banner-cms-complete.md` (баннер Hero,
`banner_slides`). **Общая архитектура обоих CMS-модулей и инструкция «как
добавить третий» — `docs/MODULES/content_cms_implementation.md`** (читать её,
а не копировать код, при следующей задаче «вынести вшитый в JSX блок витрины
в админку»).

Ещё ранее:
`docs/HANDOFFS/2026-08-21-admin-audit-viewer-api-complete.md`
— read-only admin API просмотра трёх журналов (Stage 8, ADR-023). Предыдущий
блок — `docs/HANDOFFS/2026-08-20-audit-hardening-stages-1-7-complete.md`
(запись журналов). Handoff от 2026-07-16
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

## Язык ответов Claude Code

**Всегда отвечай пользователю на русском языке.** Это правило распространяется
на промежуточные сообщения, уточняющие вопросы, планы, объяснения, отчёты о
реализации, результаты проверок и финальные ответы — даже если задача, приложенный
отчёт или часть контекста написаны на английском.

Английский сохраняй только там, где он технически необходим: в коде,
идентификаторах, командах, точных именах файлов/API/классов, дословном выводе
инструментов и в документах, которые уже ведутся на английском. Пользователь может
явно попросить другой язык для конкретного ответа или документа — такая просьба
имеет приоритет.

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
- IP-адреса в трёх audit-журналах (`audit_log`, `auth_log`, `data_change_log`)
  обнуляются через 90 дней функцией `public.anonymize_old_ips(integer)`
  (ревизия `c8e2b5f7a3d1`). Это НЕ происходит само: функцию вызывает
  `scripts/anonymize_old_ips.py` по таймеру `mindcare-anonymize-ips.timer`,
  который `deploy.sh` устанавливает, но **не активирует** (первый прогон
  необратим). Источник IP — `request.client.host`, то есть за reverse-proxy
  это адрес прокси, а не конечного пользователя (доверенные прокси —
  отдельный этап). `user_sessions`, `consent_records` и
  `user_legal_basis_records` в охват НЕ входят: там IP другого назначения

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

### Backend (`mindcare_api/`) и База данных

Активация venv, запуск uvicorn, alembic-команды, maintenance-скрипты
(create_admin, ensure_audit_partitions, anonymize_old_ips, extend_schedules,
complete_group_sessions) и порядок запуска (alembic upgrade head → uvicorn) —
`mindcare_api/CLAUDE.md` (загружается при работе с файлами под `mindcare_api/`).

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
`./test.sh` (Linux) / `.\test.ps1` (Windows).
**Integration-тесты больше НЕ работают с dev-БД (Stage 1):** каждый полный прогон
идёт на одноразовой `mindcare_test_<random>`, которую `scripts/isolated_test_db.py`
создаёт, мигрирует (`alembic upgrade head`) и удаляет в `finally`. Нужен отдельный
`TEST_DATABASE_URL` (admin-точка `postgres`) с привилегией CREATEDB; `ENV=test`
выставляют сами скрипты; Docker не требуется. Прямой `pytest tests/integration/`
против dev-БД заблокирован fail-fast'ом; unit-only — `.\test.ps1 -UnitOnly` /
`./test.sh --unit-only` (без test-БД). Root `tests/conftest.py` гарантирует, что ни
один pytest-режим не грузит dev `DATABASE_URL` (тестовый URL либо недоступный sentinel).
Frontend: `npm test -- --watchAll=false`, `npm run lint`, `npm run build`.

---

## Архитектура

### Стек

Актуальные версии — `mindcare_api/requirements.txt` и `mindcare_web/package.json`.

> **Важно:** SQLAlchemy используется в **синхронном** режиме (psycopg2, не asyncpg).
> Все эндпоинты — `def`, не `async def`. Не менять на async без обсуждения.

---

### Backend: структура модулей, схема БД, журналы аудита

Структура доменных модулей (`routes.py`/`schemas.py`/`service.py`/`storage.py`),
полный чек-лист бизнес-правил backend ("Правила бэка"), схема БД и история
миграций Alembic, устройство трёх журналов аудита (`auth_log`/`audit_log`/
`data_change_log`) и read-only admin viewer журналов (Stage 8) — всё в
`mindcare_api/CLAUDE.md` (загружается при работе с файлами под `mindcare_api/`).

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

Backend-специфичные code conventions (Pydantic-схемы, работа с DB-сессией,
email через BackgroundTasks, порядок импортов, audit-impact review чек-лист)
— `mindcare_api/CLAUDE.md` (загружается при работе с файлами под `mindcare_api/`).

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
