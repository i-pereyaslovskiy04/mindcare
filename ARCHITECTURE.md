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
  alembic/               - конфиг и версии миграций (10 ревизий, head: b6e1f4a7c9d3)
  app/
    main.py              - точка входа FastAPI, lifespan, роутеры
    core/
      config.py          - настройки из .env (pydantic-settings)
      encryption.py      - Fernet encrypt/decrypt для session_notes
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
    supervisor/          - /api/supervisor/* (supervisor role)
    psychologist/        - /api/psychologist/* (psychologist role)
    db/
      base.py            - Base = declarative_base()
      session.py         - engine, SessionLocal, get_db()
      init_db.py         - startup: ensure_database + check_migrations + seed
      seed.py            - идемпотентный seed: роли, permissions, consents
      models/            - ORM-модели (11 модулей, 46 таблиц; legal_basis.py — Stage 23b)
    services/
      email_service.py   - высокоуровневые email-функции (per-event)
      _smtp.py           - SMTP-транспорт (внутренний)
  scripts/
    create_admin.py             - CLI: создание первого администратора (+ legal basis record)
    ensure_audit_partitions.py  - CLI: создание будущих партиций audit-таблиц
    backfill_legal_basis.py     - CLI: backfill legal basis records (--dry-run default)
    test_smtp.py                - CLI: диагностика SMTP
  tests/                 - 138 тестов (unit + integration), запуск: .\test.ps1
```

**Полная документация:** `CLAUDE.md`, `docs/backend_architecture.md`

---

## Frontend: `mindcare_web/`

**Стек:** React 19, React Router 7, CSS Modules, CRA (порт 3000)

**Полная документация:** `mindcare_web/ARCHITECTURE.md`

---

## База данных

PostgreSQL 15+, 46 таблиц, схема управляется только через Alembic.

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
| b6e1f4a7c9d3 | user_legal_basis_records (Stage 23b) — **head** |

---

## Документация

| Файл | Содержание |
|------|-----------|
| CLAUDE.md | Главный контекст для Claude Code |
| docs/backend_architecture.md | Подробная архитектура бэкенда |
| docs/backend_cleanup_audit.md | Аудит мёртвого кода 2026-05-21 |
| mindcare_web/ARCHITECTURE.md | Полные правила фронтенда |
| docs/BACKLOG.md | Технический долг |
