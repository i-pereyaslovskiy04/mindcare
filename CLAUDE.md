# CLAUDE.md

Этот файл описывает проект для Claude Code. Прочитай его целиком перед любой задачей.

## О проекте

**MindCare** — веб-платформа психологической службы Донецкого государственного университета.

Функциональность:
- Запись студентов на консультации к штатным психологам
- Онлайн-психодиагностика (тесты с автоподсчётом результатов)
- Блог, новости, справочник ресурсов помощи
- Модуль вопросов и ответов (Q&A)
- Личные кабинеты по ролям (студент, психолог, админ)
- Административная панель

**Критически важно:** платформа работает с психологическими и медицинскими данными.
Она попадает под **ФЗ-152 РФ** (защита персональных данных). Это влияет на:
- Все данные пользователей хранятся на серверах в РФ
- Согласие на обработку ПДн фиксируется в `consent_records` при регистрации
- Перед каждым тестом и записью на консультацию проверяется актуальность согласия
- Заметки сессий (`session_notes`) должны шифроваться на уровне приложения (TODO: не реализовано)
- IP-адреса анонимизируются через 90 дней (`anonymize_old_ips()` в БД)

**Монорепо с двумя проектами:**
- `mindcare_api/` — Python FastAPI бэкенд, порт 8000
- `mindcare_web/` — React 19 фронтенд (CRA), порт 3000

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
```

### База данных

```bash
# Первичная инициализация БД (применяет все миграции 001-010)
psql -U postgres -d mindcare -f db/sql/full_schema.sql

# Подключение к БД для ручных запросов
psql -U MindcareUser -d mindcare
```

> **Важно:** миграции применяются через SQL-файлы, не через Alembic.
> `Base.metadata.create_all()` в `main.py` создаёт **только** таблицу `otp_verifications`
> которой нет в SQL-схеме. Остальные 38 таблиц — только через `full_schema.sql`.

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
npm test -- --testPathPattern=App.test.js
```

> **Важно:** для full-stack разработки нужно запустить **оба** сервера одновременно.
> Фронт проксирует `/api/*` запросы на `http://localhost:8000` через настройку в `package.json`.

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
│   │   └── config.py        — настройки из .env (pydantic-settings)
│   ├── db/
│   │   ├── session.py       — engine, SessionLocal, Base
│   │   └── models.py        — все SQLAlchemy модели
│   ├── auth/                — аутентификация и авторизация
│   │   ├── audit.py         — log_auth_event() для auth_log
│   │   ├── deps.py          — get_current_user, require_role
│   │   ├── otp_service.py   — создание и верификация OTP
│   │   ├── routes.py        — /api/auth/* эндпоинты
│   │   ├── schemas.py       — Pydantic-схемы auth
│   │   ├── security.py      — генерация токенов сессии
│   │   ├── service.py       — бизнес-логика auth
│   │   └── storage.py       — работа с БД (users, sessions, consents)
│   ├── users/               — управление пользователями (admin)
│   │   ├── routes_admin.py  — /api/admin/users/* эндпоинты
│   │   ├── schemas.py       — Pydantic-схемы users
│   │   ├── service.py       — бизнес-логика users
│   │   └── storage.py       — работа с БД (find_users, create_user)
│   └── services/
│       ├── email_sender.py  — SMTP транспорт (dev/smtp режимы)
│       └── email_service.py — формирование писем по событиям
├── scripts/
│   ├── create_admin.py      — создание первого админа (интерактивный)
│   └── test_smtp.py         — диагностика SMTP
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
✅ Токены сброса пароля — хранятся как хеш, не plaintext
✅ Soft delete — deleted_at, не физическое удаление
✅ Внешний API использует users.uuid (UUID), не users.id (INT)
❌ Не использовать fastapi-users — конфликтует с нашей схемой
❌ Не использовать async SQLAlchemy — проект на sync psycopg2
❌ Не добавлять Alembic для основных таблиц — они через SQL-файлы
```

---

### База данных: схема

38 таблиц в 7 модулях. Миграции в `db/sql/`, применяются через `psql`.

**Ключевые таблицы:**

| Таблица | Описание |
|---------|----------|
| `users` | Все пользователи системы. FK из всех модулей |
| `roles`, `user_roles`, `permissions`, `role_permissions` | RBAC. Роли через M:N |
| `student_profiles`, `psychologist_profiles` | Профили 1:1 с users |
| `user_sessions` | Сессии (заменяют JWT). Soft-revoke через `is_revoked` |
| `otp_verifications` | OTP для регистрации и сброса пароля. Создаётся через `create_all` |
| `consents`, `consent_records` | Согласия на ПДн. Обязательны при регистрации |
| `appointments` | Записи на консультации. EXCLUDE USING gist против пересечений |
| `schedule_rules` | Расписание психологов (не материализованные слоты) |
| `tests`, `questions`, `options`, `test_results` | Психодиагностика |
| `auth_log`, `audit_log`, `data_change_log` | Аудит. Партиционированы по месяцам до 2026-12-31 |

> **Критический риск:** партиции `auth_log`, `audit_log`, `data_change_log`
> захардкожены до **31.12.2026**. После этой даты INSERT упадёт и логин сломается.
> Нужен скрипт автогенерации партиций — в бэклоге.

**Роли в системе:**

| Роль | Кто | Как создаётся |
|------|-----|---------------|
| `student` | Студент/клиент | Публичная регистрация с OTP |
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
│   ├── news.api.js
│   ├── materials.api.js
│   └── appointments.api.js
├── features/           — бизнес-логика по доменам
│   ├── auth/           — AuthContext, LoginForm, RegisterForm, forgot-password
│   └── news/
├── components/         — domain-agnostic примитивы (Modal, Navbar, Footer)
├── hooks/              — переиспользуемые hooks
├── pages/              — только композиция, никакого fetch
│   ├── admin/          — AdminDashboard (stub, требует реализации)
│   ├── client/         — ClientDashboard (stub)
│   └── consultant/     — ConsultantDashboard (stub)
├── data/               — только dev/mock данные
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
| PATCH | `/api/admin/users/{id}` | Admin | 🔲 в работе |
| DELETE | `/api/admin/users/{id}` | Admin | 🔲 в работе |
| GET | `/api/admin/users/{id}` | Admin | 🔲 в работе |

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

Этот раздел описывает намеренные упрощения MVP и известный техдолг.
**Не «исправляй» эти вещи без явного запроса** — они отложены осознанно.

---

### 🔴 Критические (влияют на прод)

**Партиции audit-таблиц закончатся 31.12.2026**
- Таблицы `auth_log`, `audit_log`, `data_change_log` партиционированы по месяцам
- Партиции захардкожены только до конца 2026 года
- После 31.12.2026 любой INSERT в эти таблицы упадёт → логин сломается
- Нужен скрипт автогенерации партиций или `pg_partman`
- Файл: `db/sql/008_audit.sql`

**`session_notes.content` не шифруется**
- В схеме БД написано «шифруется на уровне приложения» — это не реализовано
- Клинические заметки хранятся открытым текстом
- Нужен `cryptography.fernet` с ключом из env
- Файл: будущий модуль `app/appointments/`

---

### 🟡 Важные (влияют на качество)

**OTP-коды хранятся в открытом виде**
- `otp_verifications.code` — plaintext, не хеш
- При утечке БД можно сбросить пароль любого юзера в окне 10 минут
- Нужен `sha256(code)` при сохранении, сравнение по хешу
- Файл: `app/db/models.py` (OtpVerification), `app/auth/otp_service.py`

**`_get_primary_role` недетерминирован при нескольких ролях**
- Использует `.first()` без `ORDER BY`
- Если у юзера две роли — вернёт случайную
- Сейчас безопасно (один юзер = одна роль), но сломается при расширении
- Нужен `ORDER BY granted_at DESC` или явный приоритет ролей
- Файл: `app/auth/storage.py`

**Email без нормализации в `register_init`**
- `save_user` нормализует email (`.lower().strip()`)
- Но `otp_verifications.email` сохраняется как есть (без нормализации)
- Если юзер введёт `Ivan@MAIL.ru` при init и `ivan@mail.ru` при confirm — не найдёт OTP
- Нужна нормализация в `otp_service.create_or_update_otp`
- Файл: `app/auth/otp_service.py`

**Нет `consent_records` для юзеров созданных через `POST /api/admin/users`**
- Психологи и админы создаются без фиксации согласия на ПДн
- Юридически: согласие должно быть получено при первом входе
- Нужен флаг `must_accept_consent` и проверка при логине
- Файл: `app/users/service.py`, `app/auth/service.py`

---

### 🟢 Технический долг (не срочно)

**`datetime.utcnow()` в `otp_service.py`**
- Deprecated в Python 3.12+, удалён в 3.14
- Заменить на `datetime.now(timezone.utc)` везде
- Файл: `app/auth/otp_service.py`

**`print()` вместо `logging`**
- Весь проект использует `print()` для диагностики
- Нужен переход на `logging` с уровнями (DEBUG/INFO/WARNING/ERROR)
- Менять везде сразу, не по одному файлу

**`ssl.CERT_NONE` в email_sender.py**
- Отключена проверка SSL-сертификата SMTP-сервера
- Уязвимость к MITM-атаке на SMTP
- Вернуть нормальную проверку перед деплоем в прод
- Файл: `app/services/email_sender.py`

**`_hash` приватная функция используется снаружи**
- `app/users/service.py` импортирует `_hash` из `app/auth/service.py`
- Нарушение инкапсуляции
- Вынести в `app/core/security.py` и сделать публичной
- Файл: `app/auth/service.py`, `app/core/` (создать `security.py`)

**`store/store.js` на фронте не реализован**
- Файл существует как заглушка
- Redux/Context не подключён
- AuthContext покрывает текущие потребности
- Нужен ли Redux — решать когда появится необходимость

**Раздел 1 в `ARCHITECTURE.md` устарел**
- Project Tree не отражает реальную структуру `mindcare_web/src/`
- Обновить когда структура стабилизируется

---

### 🔲 Отложено на Этап 2 (не MVP)

Следующие функции **намеренно не реализованы** в MVP:

- MFA / двухфакторная аутентификация (таблица `user_mfa_methods` готова в БД)
- Интеграция с Яндекс.Календарь
- Видеоконсультации (Rutube / SberJazz)
- Telegram-бот и Telegram-уведомления
- ИИ-анализ (видеокамера, распознавание эмоций)
- Платные услуги
- Полнотекстовый поиск с морфологией
- Экспорт данных (Excel, PDF-отчёты)
- Принудительная смена пароля при первом входе
- Rate limiting на API-эндпоинты
- Автогенерация партиций audit-таблиц (pg_partman)