# MindCare — Architecture Overview

Монорепо с двумя проектами. Этот файл — навигационная точка входа.
За деталями — смотри документацию каждого проекта отдельно.

---

## Backend: `mindcare_api/`

**Стек:** Python 3.11+, FastAPI, SQLAlchemy 2.0 (sync, psycopg2), PostgreSQL 15+

**Важно:**
- SQLAlchemy в синхронном режиме — все эндпоинты `def`, не `async def`
- Миграции через SQL-файлы в `db/sql/`, не через Alembic
- Auth — сессии в `user_sessions`, не JWT
- Soft delete везде — физического удаления нет

**Структура модулей:**
```
mindcare_api/app/
├── auth/        — регистрация, логин, OTP, сброс пароля
├── users/       — CRUD пользователей (admin only)
├── core/        — конфиг, настройки
├── db/          — модели SQLAlchemy, сессия
└── services/    — email (SMTP)
```

Полный список эндпоинтов и правила — в `CLAUDE.md`.

---

## Frontend: `mindcare_web/`

**Стек:** React 19, React Router 7, CSS Modules, CRA (порт 3000)

**Полная документация архитектуры:** [`mindcare_web/ARCHITECTURE.md`](mindcare_web/ARCHITECTURE.md)

Краткие правила:
- Все HTTP-запросы только через `src/api/*.api.js`
- Pages — только композиция, никакого fetch
- Фильтрация и пагинация списков — только на сервере
- CSS Modules, один файл на компонент, классы в camelCase

**Структура:**
```
mindcare_web/src/
├── api/         — весь HTTP (client.js + *.api.js)
├── app/         — App.jsx, AppRoutes.jsx
├── features/    — бизнес-логика по доменам (auth, admin-users, ...)
├── components/  — domain-agnostic примитивы (Modal, Navbar, Footer, ...)
├── pages/       — только композиция (home, admin, student, ...)
├── hooks/       — переиспользуемые hooks (useDebounce, ...)
└── styles/      — variables.css, global.css
```

---

## База данных

PostgreSQL 15+, 38 таблиц, миграции в `mindcare_api/db/sql/`.

Применение схемы:
```bash
psql -U postgres -d mindcare -f db/sql/full_schema.sql
```

---

## Документация проекта

| Файл | Содержание |
|------|-----------|
| `CLAUDE.md` | Главный контекст для Claude Code — читать перед любой задачей |
| `mindcare_web/ARCHITECTURE.md` | Полные правила фронтенда |
| `docs/BACKLOG.md` | Технический долг и известные проблемы |
| `docs/HANDOFFS/` | Состояние проекта по этапам разработки |
| `docs/DECISIONS.md` | Ключевые архитектурные решения |
| `docs/COMPLIANCE.md` | Требования ФЗ-152 |
