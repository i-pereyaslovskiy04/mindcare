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
  alembic/               - конфиг и версии миграций (5 ревизий)
  app/
    main.py              - точка входа FastAPI, lifespan, роутеры
    auth/
      routes.py          - HTTP /api/auth/*
      service.py         - бизнес-логика
      storage.py         - DB-запросы
      otp_service.py     - OTP (SHA-256 hash, DB-backed)
      audit.py           - log_auth_event() -> auth_log
      deps.py            - get_current_user, require_role
      security.py        - generate_session_token()
      schemas.py         - Pydantic schemas
    users/
      routes_admin.py    - HTTP /api/admin/users/*
      service.py         - бизнес-логика
      storage.py         - DB-запросы
      schemas.py         - Pydantic schemas
    core/
      config.py          - настройки из .env (pydantic-settings)
    db/
      base.py            - Base = declarative_base()
      session.py         - engine, SessionLocal, get_db()
      init_db.py         - startup: ensure_database + check_migrations + seed
      seed.py            - идемпотентный seed: роли, permissions, consents
      models/            - ORM-модели (10 модулей, 41 таблица)
    services/
      email_service.py   - высокоуровневые email-функции (per-event)
      _smtp.py           - SMTP-транспорт (внутренний)
  scripts/
    create_admin.py      - CLI: создание первого администратора
    test_smtp.py         - CLI: диагностика SMTP
```

**Полная документация:** `CLAUDE.md`, `docs/backend_architecture.md`

---

## Frontend: `mindcare_web/`

**Стек:** React 19, React Router 7, CSS Modules, CRA (порт 3000)

**Полная документация:** `mindcare_web/ARCHITECTURE.md`

---

## База данных

PostgreSQL 15+, 41 таблица, схема управляется только через Alembic.

| Revision | Описание |
|----------|----------|
| af13ad7a133c | baseline: 38 таблиц |
| 3a7c5e2b8f1d | audit tables: auth_log, audit_log, data_change_log |
| c5d8a1b4e7f2 | otp_verifications.code VARCHAR(64) для SHA-256 |
| f4b9e2c6a1d8 | audit indexes + ARRAY(Text) fix |
| e9a3d7f2b5c0 | rebuild audit indexes (согласованы с ORM) |

---

## Документация

| Файл | Содержание |
|------|-----------|
| CLAUDE.md | Главный контекст для Claude Code |
| docs/backend_architecture.md | Подробная архитектура бэкенда |
| docs/backend_cleanup_audit.md | Аудит мёртвого кода 2026-05-21 |
| mindcare_web/ARCHITECTURE.md | Полные правила фронтенда |
| docs/BACKLOG.md | Технический долг |
