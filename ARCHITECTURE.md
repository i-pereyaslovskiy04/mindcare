# MindCare — Architecture Overview

Монорепо с двумя проектами.
За деталями — смотри документацию каждого проекта отдельно.

---

## Backend: `mindcare_api/`

**Стек:** Python 3.11+, FastAPI, SQLAlchemy 2.x (sync, psycopg2), PostgreSQL 15+, Alembic

**Startup sequence:**
```bash
cd mindcare_api/
alembic upgrade head       # 1. Применить миграции (CLI)
uvicorn app.main:app       # 2. Запустить приложение
```

**Структура модулей:**
```
mindcare_api/
  alembic/               - конфиг и версии миграций (11 ревизий, head: d8f3a6c1e9b4)
  app/
    main.py              - точка входа FastAPI, lifespan, роутеры
    core/
      config.py          - настройки из .env (pydantic-settings)
      encryption.py      - Fernet encrypt/decrypt для session_notes и chat_messages
      normalization.py   - normalize_email()
      rate_limit.py      - in-memory rate limiter для auth-эндпоинтов (Stage 21)
    auth/                - /api/auth/* (+ hashed session tokens, Stage 22b)
    users/               - /api/admin/users/* (только admin)
    tags/                - /api/admin/tags/* + /api/tags/ (public)
    categories/          - /api/admin/categories/*
    news/                - /api/admin/news/* + /api/news/* (public)
    articles/            - /api/admin/articles/* + /api/articles/* (public)
    media/               - POST /api/media/upload (Pillow, WebP)
    session_notes/       - /api/session-notes/* (encrypt-on-write)
    chat/                - /api/chat/* — Messenger (Stage 28–30c): one-to-one чат
                           student ↔ psychologist + read-only system conversation;
                           polling (after=<id>), encrypt-on-write (enc:v1:), read_at receipts,
                           peer_is_online presence (по user_sessions.last_active, порог 10 мин);
                           доступ к engagement-беседам только участникам (admin/supervisor — 403);
                           system messages публикует только internal publisher (idempotency event_key)
    supervisor/          - /api/supervisor/* (supervisor role)
    psychologist/        - /api/psychologist/* (psychologist role)
    db/
      base.py            - Base = declarative_base()
      session.py         - engine, SessionLocal, get_db()
      init_db.py         - startup: ensure_database + check_migrations + seed
      seed.py            - идемпотентный seed: роли, permissions, consents
      models/            - ORM-модели (12 модулей, 48 таблиц; chat.py — Stage 28b)
    services/
      email_service.py   - высокоуровневые email-функции (per-event)
      _smtp.py           - SMTP-транспорт (внутренний)
  scripts/
    create_admin.py             - CLI: создание первого администратора (+ legal basis record)
    ensure_audit_partitions.py  - CLI: создание будущих партиций audit-таблиц
    backfill_legal_basis.py     - CLI: backfill legal basis records (--dry-run default)
    test_smtp.py                - CLI: диагностика SMTP
  tests/                 - 282 теста (unit + integration), запуск: .\test.ps1
```

**Auth: атомарность операций (Stage 31m-fix-b2/b3).** Бизнес-операции auth —
unit-of-work в одной `SessionLocal()` с одним финальным `commit`:
- **registration confirm** — user/reactivate + role + все consent_records + consume OTP;
- **password reset confirm** — update password_hash + revoke sessions + consume OTP;
- **change password** — verify current + update password_hash + revoke sessions.

SMTP/email не выполняется внутри DB-транзакции (письмо — на init-шаге). `auth_log`
и system-уведомления — soft-fail вне core-транзакции (после commit). Transactional
outbox на текущем этапе отсутствует. Failure-injection тесты обязательны для изменений
этих UoW (`test_register_confirm_atomic`, `test_password_uow_atomic`).

**Полная документация:** `CLAUDE.md`, `docs/backend_architecture.md`

---

## Frontend: `mindcare_web/`

**Стек:** React 19, React Router 7, CSS Modules, CRA (порт 3000)

**Messenger (Stage 28–30d):** единый раздел «Сообщения». Общие компоненты —
`src/features/chat/` (ChatSidebar/ChatWindow/ChatHeader/ChatListItem, `useSystemConversation`,
`mergeMessages`, `messagesEvents`, `LinkifiedText`); `src/api/chat.api.js`. Student —
`pages/student/Chat/` (`useStudentChat.js`), psychologist — `pages/psychologist/Chat/`
(`usePsychologistChat.js`). Polling 8s/30s (`after=<id>`); **VK-like entry** (диалог не
открывается автоматически, mark-read только по явному клику); unread — глобальный nav badge +
per-dialog; system conversation всегда видна и **последняя** в списке (read-only, без composer);
live refresh snapshot=50 + `mergeMessages` (read_at без F5); read receipts ✓/✓✓; online/offline
точкой (approximate, без WebSocket, без last-seen). WebSocket/group chat/attachments — postponed.
Diary/tasks/calendar студента остаются accepted demo/mock.

**Message actions / bubble (Stage 31y–31z-hotfix):** свои сообщения в активной беседе —
меню «…» (`MessageActionsMenu`) с «Редактировать»/«Удалить» вместо отдельной кнопки-карандаша;
удаление — через confirm-диалог (`DeleteMessageDialog`), soft delete на backend, удалённые
сообщения скрыты из ленты без плейсхолдера. Визуальное облачко выделено в отдельный
feature-specific `MessageBubble` (не shared UI): meta (время/«изменено»/✓/✓✓) — внутри bubble,
компактно для коротких сообщений и с переносом вниз-направо для длинных (Telegram-style);
system-сообщения всегда bubble от «MindCare», без меню действий и без read receipts. Подробнее —
`mindcare_web/ARCHITECTURE.md`.

**Mobile (Stage 30d):** breakpoints различаются по слоям — Messenger переключается в
list/thread на `≤900px` (в шапке чата кнопка «назад»); CabinetLayout: `>980px` full sidebar,
`601–980px` icon-rail, `≤600px` мобильный drawer (`sidebarInner` переиспользуется из desktop
sidebar; правила сворачивания заскоуплены под `.sidebar`, чтобы drawer оставался полным).
На `≤600px` `.app` = `grid-template-columns: 1fr` (фикс пустого кабинета), topbar разгружен
(скрыты bell/mail, оставлены hamburger + breadcrumb + logout). Drawer пока без focus-trap.

**Admin users — смена роли (Stage 31n / 31n-hotfix):** в `UserEditModal` роль
редактируема (правило Stage 31h «read-only» отменено). Поле «Роль пользователя» —
под ФИО; edit-options только `psychologist`/`supervisor`/`admin` (`student` не
selectable, отображается через `Select` `displayLabel`). При реальной смене роли на
staff/admin `useUserForm` показывает блок legal basis и шлёт `role` + legal basis
поля в PATCH (иначе `role` не отправляется); валидация требует основание только при
смене на staff/admin. Backend policy без изменений: PATCH роли на staff/admin требует
запись `user_legal_basis_records` атомарно (defense-in-depth, не заменяется UI).

**Shared `Select` `displayLabel` (Stage 31n-hotfix):** опциональный prop — показывает
текущее значение, которого намеренно нет в `options` (как выбранное, но без появления
в dropdown). Backward-compatible: без него поведение прежнее (placeholder при value не
из options). Подробнее — `docs/UI_COMPONENTS_GUIDE.md`.

**Полная документация:** `mindcare_web/ARCHITECTURE.md`

---

## База данных

PostgreSQL 15+, 48 таблиц, схема управляется только через Alembic.

| Revision | Описание |
|----------|----------|
| af13ad7a133c | baseline: 38 таблиц |
| 3a7c5e2b8f1d | audit tables: auth_log, audit_log, data_change_log (партиционированные) |
| c5d8a1b4e7f2 | otp_verifications.code VARCHAR(64) для SHA-256 |
| f4b9e2c6a1d8 | audit indexes + ARRAY(Text) fix |
| e9a3d7f2b5c0 | rebuild audit indexes (согласованы с ORM) |
| a8c3f1d9e2b5 | tags tables: tags, article_tags, news_tags, test_tags |
| b3c5e7a9f1d2 | auth_log.event VARCHAR(50→150) |
| d2e5f8a1b4c7 | supervisor engagement unique index |
| e5a8f3c1d2b6 | normalized email unique index: lower(trim(email)) |
| b6e1f4a7c9d3 | user_legal_basis_records (Stage 23b) |
| d8f3a6c1e9b4 | chat_conversations + chat_messages (Stage 28b) |
| c4f7a2e9d1b8 | system conversation support: type/recipient_id + message_kind/event_key (Stage 29b) — **head** |

---

## Документация

| Файл | Содержание |
|------|-----------|
| CLAUDE.md | Главный контекст для Claude Code |
| docs/backend_architecture.md | Подробная архитектура бэкенда |
| docs/backend_cleanup_audit.md | Аудит мёртвого кода 2026-05-21 |
| mindcare_web/ARCHITECTURE.md | Полные правила фронтенда |
| docs/BACKLOG.md | Технический долг |
