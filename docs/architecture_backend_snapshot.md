# Backend Architecture Snapshot — MindCare API

> **Цель документа:** полный технический snapshot состояния backend-архитектуры на момент 2026-05-20.  
> Предназначен для другого AI-инженера или разработчика перед интеграцией Alembic и production-ready DB architecture.  
> **Ничего не изменяет в проекте.** Только анализ и описание текущего состояния.

---

## 1. Общая структура проекта

```
mindcare/                              ← Монорепо (git root)
├── mindcare_api/                      ← Python FastAPI backend (порт 8000)
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                    ← FastAPI app + lifespan hook
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   └── config.py              ← pydantic-settings (ENV vars)
│   │   ├── db/
│   │   │   ├── __init__.py
│   │   │   ├── base.py                ← declarative_base() — единственный Base
│   │   │   ├── session.py             ← engine, SessionLocal, get_db()
│   │   │   ├── init_db.py             ← ensure_database(), create_tables(), init_db()
│   │   │   ├── seed.py                ← run_seed() — роли, permissions, consents
│   │   │   ├── models.py              ← ⚠️ МЁРТВЫЙ ФАЙЛ (см. §3)
│   │   │   └── models/                ← ORM-пакет (10 файлов моделей)
│   │   │       ├── __init__.py        ← центральный реэкспорт всех 41 таблицы
│   │   │       ├── auth.py            ← Role, Permission, User, UserRole, UserSession, ...
│   │   │       ├── profiles.py        ← StudentProfile, PsychologistProfile, EmergencyContact
│   │   │       ├── consents.py        ← Consent, ConsentRecord
│   │   │       ├── media.py           ← MediaFile, MediaVersion
│   │   │       ├── content.py         ← Category, Article, News, HelpResource, QuestionsAnswers
│   │   │       ├── diagnostics.py     ← Test, Question, Option, TestResult, StudentAnswer, ...
│   │   │       ├── consultations.py   ← TherapyEngagement, Appointment, SessionNote, ...
│   │   │       ├── notifications.py   ← NotificationTemplate, Notification
│   │   │       ├── audit.py           ← AuditLog, AuthLog, DataChangeLog
│   │   │       └── otp.py             ← OtpVerification
│   │   ├── auth/
│   │   │   ├── __init__.py
│   │   │   ├── audit.py               ← log_auth_event() → вставка в auth_log
│   │   │   ├── deps.py                ← get_current_user(), require_role() — FastAPI deps
│   │   │   ├── otp_service.py         ← DB-backed OTP (create/verify/cleanup)
│   │   │   ├── otp_store.py           ← ⚠️ DEPRECATED — raises ImportError
│   │   │   ├── routes.py              ← /api/auth/* эндпоинты
│   │   │   ├── schemas.py             ← Pydantic schemas для auth
│   │   │   ├── security.py            ← generate_session_token()
│   │   │   ├── service.py             ← бизнес-логика auth (no HTTP)
│   │   │   └── storage.py             ← SQLAlchemy запросы: users, sessions, consents
│   │   ├── users/
│   │   │   ├── __init__.py
│   │   │   ├── routes.py              ← пустой (1 строка), не используется
│   │   │   ├── routes_admin.py        ← /api/admin/users/* (только admin)
│   │   │   ├── schemas.py             ← Pydantic schemas для users
│   │   │   ├── service.py             ← бизнес-логика users
│   │   │   └── storage.py             ← SQLAlchemy запросы: find_users, create_user, ...
│   │   └── services/
│   │       ├── __init__.py
│   │       ├── email_sender.py        ← SMTP транспорт (dev/smtp режимы)
│   │       └── email_service.py       ← формирование писем (OTP, welcome)
│   ├── scripts/
│   │   ├── create_admin.py            ← интерактивное создание первого Admin
│   │   └── test_smtp.py               ← диагностика SMTP
│   ├── requirements.txt
│   ├── .env                           ← секреты (не в git)
│   └── .env.example                   ← шаблон конфига
├── mindcare_web/                      ← React 19 frontend (порт 3000)
├── docs/
│   ├── BACKLOG.md
│   ├── COMPLIANCE.md
│   ├── DECISIONS.md
│   └── HANDOFFS/
└── CLAUDE.md                          ← project instructions for Claude Code
```

**Что отсутствует:**
- `alembic/` — Alembic не установлен и не настроен
- `tests/` — тестов нет
- `docker-compose.yml` / `Dockerfile` — Docker не настроен
- `mindcare_api/db/sql/` — SQL-файлы схемы (упомянуты в CLAUDE.md как архив) **физически отсутствуют**
- `CI/CD` конфигурации (GitHub Actions, GitLab CI и т.д.)

---

## 2. Database Architecture

### 2.1 Ключевые компоненты

| Компонент | Файл | Описание |
|-----------|------|----------|
| `Base` | `app/db/base.py` | `declarative_base()` — единственный экземпляр |
| `engine` | `app/db/session.py` | `create_engine(DATABASE_URL, pool_pre_ping=True, ...)` |
| `SessionLocal` | `app/db/session.py` | `sessionmaker(bind=engine, autocommit=False, autoflush=False)` |
| `get_db()` | `app/db/session.py` | FastAPI Depends-dependency (yield-паттерн) |
| `init_db()` | `app/db/init_db.py` | Точка входа инициализации БД |
| `run_seed()` | `app/db/seed.py` | Начальное заполнение данными |

### 2.2 SQLAlchemy — синхронный, psycopg2

```python
# app/db/session.py
engine = create_engine(
    settings.DATABASE_URL,          # postgresql+psycopg2://...
    pool_pre_ping=True,             # проверяет соединение перед выдачей из пула
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
    echo=False,
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
```

- **asyncpg НЕ используется**
- Все эндпоинты `def`, не `async def`
- `get_db()` — синхронный generator с yield

```python
# app/db/session.py
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

### 2.3 Lifespan / Startup

FastAPI lifespan hook в `app/main.py`:

```
uvicorn запускает app → lifespan() → init_db() → cleanup_expired() → yield → shutdown
```

```python
# app/main.py
@asynccontextmanager
async def lifespan(_app: FastAPI):
    # ── Startup ──
    from app.db.init_db import init_db
    init_db()                       # 1. ensure_database + create_tables + seed
    from app.auth.otp_service import cleanup_expired
    removed = cleanup_expired()     # 2. удалить просроченные OTP прошлых запусков
    yield
    # ── Shutdown ──
    from app.db.session import engine
    engine.dispose()
```

### 2.4 Инициализация БД при старте

`init_db()` выполняет три шага подряд:

```
init_db()
  ├─ ensure_database()    — проверяет доступность целевой БД
  │    ├─ engine.connect() → SELECT 1
  │    ├─ если OK → возврат
  │    └─ если "does not exist" → подключается к postgres, CREATE DATABASE
  ├─ create_tables()      — регистрирует все модели, вызывает create_all()
  │    ├─ import app.db.models   (регистрирует 41 таблицу в Base.metadata)
  │    └─ Base.metadata.create_all(bind=engine, checkfirst=True)
  └─ run_seed()           — роли, permissions, consents
       ├─ _seed_roles()
       ├─ _seed_permissions()
       ├─ _seed_role_permissions()
       └─ _seed_consents()
```

### 2.5 Seed system

Файл `app/db/seed.py`. Идемпотентен (query-first, insert-if-missing).

Что создаётся:

| Тип | Данные |
|-----|--------|
| Роли | `student`, `psychologist`, `admin`, `supervisor` |
| Permissions | 23 кода в 8 модулях (auth, users, appointments, tests, content, notes, qa, admin) |
| RolePermissions | `admin` → все 23, `supervisor` → 9 |
| Consents | `privacy_policy` v1, `data_processing` v1 |

> **Критически важно:** без `privacy_policy` и `data_processing` в таблице `consents`  
> эндпоинт `POST /api/auth/register/confirm` вернёт HTTP 500.

---

## 3. ORM Models Analysis

### 3.1 Количество таблиц

**41 таблица** зарегистрированы в `Base.metadata` при импорте `app.db.models`.

### 3.2 Распределение по файлам

| Файл | Таблицы | Кол-во |
|------|---------|--------|
| `models/auth.py` | roles, permissions, role_permissions, users, user_roles, user_sessions, refresh_tokens, user_mfa_methods | 8 |
| `models/profiles.py` | student_profiles, psychologist_profiles, emergency_contacts | 3 |
| `models/consents.py` | consents, consent_records | 2 |
| `models/media.py` | media_files, media_versions | 2 |
| `models/content.py` | categories, articles, article_categories, news, help_resources, questions_answers | 6 |
| `models/diagnostics.py` | tests, test_categories, questions, options, question_media, option_media, test_results, test_result_scales, student_answers | 9 |
| `models/consultations.py` | therapy_engagements, schedule_rules, schedule_exceptions, appointments, session_notes | 5 |
| `models/notifications.py` | notification_templates, notifications | 2 |
| `models/audit.py` | audit_log, auth_log, data_change_log | 3 |
| `models/otp.py` | otp_verifications | 1 |
| **Итого** | | **41** |

### 3.3 ⚠️ Мёртвый файл models.py

В директории `app/db/` существует **оба** объекта:
- `app/db/models.py` — файл-шим (re-export обёртка)
- `app/db/models/` — пакет (директория с `__init__.py`)

**В Python пакет всегда имеет приоритет над модулем с тем же именем.**  
Поэтому `app/db/models.py` **никогда не импортируется** — он физически недоступен через `app.db.models`.  
Весь код корректно использует `from app.db.models import ...` → импортирует из пакета (`__init__.py`).

`models.py` является мёртвым файлом, который не ломает систему (никто его не импортирует), но создаёт путаницу. При подготовке к Alembic его стоит удалить.

### 3.4 Relationships

Все cross-file связи используют **строковые ссылки** (`"ClassName"`) для избежания циклических импортов:

```python
# app/db/models/auth.py — User ссылается на классы из других файлов
user_roles = relationship("UserRole", foreign_keys="UserRole.user_id", ...)
student_profile = relationship("StudentProfile", uselist=False, ...)
emergency_contacts = relationship("EmergencyContact", ...)
mfa_methods = relationship("UserMfaMethod", ...)
```

Внутри одного файла используются прямые ссылки на классы:

```python
# в том же файле — OK
role = relationship("Role", back_populates="user_roles")
```

Самореференциальная связь (только в `content.py`):

```python
class Category(Base):
    parent_id = Column(Integer, ForeignKey("categories.id", ondelete="SET NULL"))
    parent   = relationship("Category", remote_side="Category.id")
    children = relationship("Category", back_populates="parent", overlaps="parent")
```

### 3.5 PostgreSQL-специфичные типы

| Тип | Модели | Атрибут |
|-----|--------|---------|
| `UUID(as_uuid=True)` | User, MediaFile, Article, News, Test, TestResult, Appointment, TherapyEngagement, SessionNote, QuestionsAnswers | `uuid` |
| `JSONB` | MediaFile, Question, TestResultScale, AuditLog, DataChangeLog, Notification | `file_metadata`, `config`, `scale_metadata`, `metadata`, `old_values`, `new_values`, `params` |
| `ARRAY(Integer)` | StudentAnswer | `selected_options` |
| `ARRAY(String)` | DataChangeLog | `changed_fields` |
| `INET` | UserSession, RefreshToken, ConsentRecord, AuditLog, AuthLog, DataChangeLog | `ip_address` |

### 3.6 Алиасинг имён колонок

Три случая когда атрибут модели ≠ имя колонки в БД:

```python
# profiles.py — "relationship" зарезервировано в SQLAlchemy
contact_rel = Column("relationship", String(100))

# media.py — "metadata" — потенциальный конфликт с MetaData
file_metadata = Column("metadata", JSONB, default=dict)

# diagnostics.py
scale_metadata = Column("metadata", JSONB, default=dict)

# audit.py
log_metadata = Column("metadata", JSONB, default=dict)
```

Alembic autogenerate обрабатывает это корректно (использует имя колонки из аргумента, не атрибута).

### 3.7 Специфика таблиц audit

`AuditLog`, `AuthLog`, `DataChangeLog` объявлены как обычные таблицы в ORM, но в production БД (созданной через `full_schema.sql`) они являются **партиционированными по `created_at`** с партициями до 31.12.2026.

При `create_all()` с `checkfirst=True` — если таблицы уже существуют (в т.ч. как родительские партиционированные), они пропускаются.

### 3.8 Naming conventions

| Объект | Конвенция | Пример |
|--------|-----------|--------|
| Таблицы | `snake_case`, множественное число | `user_roles`, `test_results` |
| Атрибуты моделей | `snake_case` | `full_name`, `is_active` |
| Первичные ключи | `id` (Integer), исключение: `user_sessions.id` (String — токен) | |
| UUID-поля | `uuid` (UUID(as_uuid=True)) | |
| Временные метки | `created_at`, `updated_at`, `deleted_at` | |
| Soft delete | `deleted_at` IS NULL = активная запись | |
| server_default | `func.now()` для `created_at` | |

---

## 4. Startup Flow

Пошаговая последовательность при `uvicorn app.main:app --reload`:

```
1. Python загружает app/main.py
   ├─ os.environ.setdefault("PGCLIENTENCODING", "UTF8")   ← фикс cp1251 на Windows
   ├─ logging.basicConfig(...)
   └─ import app.auth.routes, app.users.routes_admin      ← вызывает цепочку импортов

2. Цепочка импортов (до lifespan):
   app.auth.routes
     → app.auth.service → app.auth.storage
       → app.db.session
         → app.core.config  (читает .env, создаёт settings)
         → app.db.base      (declarative_base() → Base)
         → create_engine()  ← engine создаётся здесь, но соединение НЕ открывается
         → sessionmaker()   ← SessionLocal создаётся
       → app.db.models      → imports all 10 model files (Base.metadata populated)
   
   ВАЖНО: engine = create_engine() НЕ открывает соединение с БД.
   Соединение открывается только при первом engine.connect() в init_db().

3. FastAPI app создаётся (lifespan=lifespan)

4. Lifespan startup запускается:
   ├─ from app.db.init_db import init_db
   ├─ init_db()
   │    ├─ ensure_database()
   │    │    └─ engine.connect() → SELECT 1    ← ПЕРВОЕ обращение к БД
   │    ├─ create_tables()
   │    │    ├─ import app.db.models           ← уже в sys.modules (no-op)
   │    │    └─ Base.metadata.create_all(...)
   │    └─ run_seed()
   │         └─ SessionLocal() → INSERT OR SKIP
   ├─ cleanup_expired()                        ← DELETE FROM otp_verifications
   └─ yield

5. Сервер готов принимать запросы

6. Shutdown (Ctrl+C или сигнал):
   └─ engine.dispose()                         ← закрывает все соединения из пула
```

### Где создаётся engine

`app/db/session.py`, строка модульного уровня — при первом импорте модуля.  
Это происходит **до** запуска lifespan, при разрешении зависимостей imports.

### Где открывается соединение с БД

Первый вызов `engine.connect()` внутри `ensure_database()` в `init_db.py`.  
До lifespan соединений с БД нет.

---

## 5. Environment Configuration

### 5.1 Используемые ENV переменные

| Переменная | Тип | Default | Описание |
|-----------|-----|---------|----------|
| `DATABASE_URL` | `str` | — (обязательна) | `postgresql+psycopg2://USER:PASS@HOST:PORT/DBNAME` |
| `SESSION_EXPIRE_DAYS` | `int` | `7` | Срок действия сессии (дни) |
| `EMAIL_MODE` | `str` | `"dev"` | `"dev"` (print) или `"smtp"` (реальная отправка) |
| `SMTP_HOST` | `str` | `""` | SMTP-сервер |
| `SMTP_PORT` | `int` | `587` | SMTP-порт |
| `SMTP_USER` | `str` | `""` | SMTP-логин |
| `SMTP_PASSWORD` | `str` | `""` | SMTP-пароль |
| `SMTP_FROM` | `str` | `""` | Email отправителя |
| `DEBUG` | `bool` | `False` | Режим отладки |
| `ENV` | `str` | `"production"` | Среда (`development` / `production`) |

Дополнительно, **не через pydantic-settings**:

| Переменная | Где задаётся | Назначение |
|-----------|-------------|-----------|
| `PGCLIENTENCODING` | `os.environ.setdefault` в `main.py` | Фикс UnicodeDecodeError на Windows с русской локалью PostgreSQL |

### 5.2 Чтение конфига

```python
# app/core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    DATABASE_URL: str
    SESSION_EXPIRE_DAYS: int = 7
    EMAIL_MODE: str = "dev"
    # ...

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",    # лишние переменные в .env не вызывают ошибки
    )

settings = Settings()
SESSION_EXPIRE_DAYS = settings.SESSION_EXPIRE_DAYS  # реэкспорт для удобства
```

`.env` файл живёт в `mindcare_api/` (рядом с `requirements.txt`).  
Uvicorn запускается из `mindcare_api/`, поэтому `.env` находится в CWD.

---

## 6. Docker / Infrastructure

**Docker отсутствует.** Нет `docker-compose.yml`, `Dockerfile`, `.dockerignore`.

Текущая инфраструктура разработки:
- PostgreSQL установлен локально (Windows)
- Пользователь и пароль настроены вручную через `psql`
- Никаких init-скриптов для контейнеров

Для будущего Docker-деплоя потребуется:
1. `Dockerfile` для FastAPI (uvicorn)
2. `docker-compose.yml` с `postgres` сервисом
3. Передача `DATABASE_URL` через env / secrets
4. Init-скрипт или wait-for-postgres хук перед стартом приложения

---

## 7. Existing DB Initialization Logic

### 7.1 `Base.metadata.create_all()`

Используется в `app/db/init_db.py → create_tables()`:

```python
Base.metadata.create_all(bind=engine, checkfirst=True)
```

- `checkfirst=True` — пропускает существующие таблицы (IF NOT EXISTS)
- Вызывается при **каждом** старте приложения (в lifespan)
- Безопасен для повторного запуска
- Создаёт только таблицы, о которых знает `Base.metadata` (требует предварительного импорта всех моделей)

### 7.2 Health check

Эндпоинт `GET /api/health`:

```python
# app/db/init_db.py → health_check()
{
    "status": "ok",
    "db": "connected",
    "tables": 41          # число таблиц в Base.metadata
}
```

При ошибке соединения: `{"status": "error", "db": "disconnected", "detail": "..."}`.

### 7.3 Auto-create database

`ensure_database()` умеет создать БД если её нет:

1. Пробует `engine.connect()` → `SELECT 1`
2. Если `OperationalError` с "does not exist" → создаёт новое соединение к системной БД `postgres`
3. Выполняет `CREATE DATABASE "mindcare"`
4. Если другая ошибка (неверный пароль, сеть) → `raise RuntimeError` с диагностическим текстом

Требует права `CREATEDB` у пользователя из `DATABASE_URL`.

### 7.4 Retry logic

**Retry-логики нет.** Один попытка; при ошибке — `raise`. FastAPI не стартует с неработающей БД (исключение из lifespan прерывает запуск).

### 7.5 OTP cleanup

`cleanup_expired()` при старте удаляет просроченные OTP из прошлых запусков:

```python
db.query(OtpVerification).filter(OtpVerification.expires_at < now).delete()
```

---

## 8. Alembic Readiness Analysis

### 8.1 Что уже хорошо для Alembic

| Пункт | Статус | Комментарий |
|-------|--------|-------------|
| Единственный `Base` | ✅ | `app/db/base.py` — чистое разделение |
| Все модели в одном пакете | ✅ | `app/db/models/` с `__init__.py` |
| Правильный порядок импортов | ✅ | auth → profiles → consents → ... → otp |
| Синхронный SQLAlchemy | ✅ | Alembic нативно поддерживает sync |
| `DATABASE_URL` в `.env` | ✅ | Легко подключить к `alembic.ini` |
| Строковые relationship-ссылки | ✅ | Не вызовут проблем при импорте в env.py |
| FK с `ondelete` | ✅ | Alembic autogenerate включит их |

### 8.2 Проблемы перед интеграцией Alembic

#### 🔴 Критические

**1. `create_all()` конфликтует с Alembic**

Когда Alembic управляет схемой, `create_all()` при каждом старте может:
- Создать таблицу без истории миграций
- Разойтись с состоянием Alembic revision head
- При `alembic upgrade head` — падение если таблица уже существует

**Решение:** убрать `create_all()` из `init_db.py` после создания baseline-миграции, заменить на `alembic upgrade head` в startup или CI.

**2. Партиционированные таблицы аудита**

`auth_log`, `audit_log`, `data_change_log` — в production они партиционированы (`PARTITION BY RANGE`). ORM-модели объявляют их как **обычные таблицы** (без `postgresql_partition_by`).

Alembic autogenerate **не знает о партиционировании**. Если выполнить `alembic revision --autogenerate` на production БД:
- Он увидит существующие таблицы как обычные → может попытаться их изменить
- Или пропустит если `checkfirst=True` — зависит от настройки

**Решение:** добавить эти три таблицы в `exclude_tables` в `env.py`:
```python
def include_object(object, name, type_, reflected, compare_to):
    if type_ == "table" and name in ("auth_log", "audit_log", "data_change_log"):
        return False
    return True
```

**3. Мёртвый файл `app/db/models.py`**

Файл физически существует, но никогда не импортируется (пакет `models/` имеет приоритет). При `alembic revision --autogenerate` не создаёт проблем, но вводит в заблуждение разработчиков.

**Решение:** удалить `app/db/models.py`.

#### 🟡 Потенциальные проблемы

**4. PostgreSQL-специфичные типы в autogenerate**

| Тип | Проблема |
|-----|---------|
| `UUID(as_uuid=True)` | Может рендериться как `UUID()` без параметра — проверить вывод |
| `JSONB` | Корректно рендерится через `sqlalchemy.dialects.postgresql.JSONB` |
| `ARRAY(Integer)` / `ARRAY(String)` | Требует `render_as_batch=False` и postgres-dialect в env.py |
| `INET` | Кастомный тип — может рендериться некорректно в autogenerate |

Alembic env.py для PostgreSQL должен явно указывать:
```python
from sqlalchemy.dialects import postgresql
```

**5. Алиасинг колонок**

```python
contact_rel  = Column("relationship", String(100))   # атрибут ≠ имя колонки
file_metadata = Column("metadata", JSONB)
```

Alembic autogenerate корректно обработает это (использует имя колонки из первого аргумента), но нужно проверить рендеринг миграции.

**6. Самореференциальная Category**

```python
parent = relationship("Category", remote_side="Category.id")
children = relationship("Category", back_populates="parent", overlaps="parent")
```

`overlaps="parent"` — может генерировать SAWarning при автогенерации, но не блокирует миграции.

**7. `UserRole.granted_by` — несимметричный FK**

```python
granted_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
```

Нет explicit relationship. Alembic autogenerate создаст FK-constraint корректно, но relationship нужно добавить вручную если потребуется.

**8. Нет baseline-миграции**

Если БД уже создана через `create_all()` (текущий state), для Alembic нужна "пустая" начальная миграция (baseline), чтобы пометить текущее состояние как revision 0.

```bash
alembic stamp head   # после создания initial migration без --autogenerate
```

### 8.3 Async/sync compatibility

Проблем нет. Проект **синхронный**. Стандартный Alembic (sync engine) полностью совместим.

### 8.4 Metadata discovery

Для `env.py` достаточно:

```python
import app.db.models  # noqa — триггерит импорт всех 41 таблицы
from app.db.base import Base

target_metadata = Base.metadata
```

Круговых импортов нет. Все модели корректно разрешаются при импорте пакета.

---

## 9. Technical Risks

### 9.1 Критические (могут сломать прод)

| Риск | Где | Описание |
|------|-----|----------|
| **Партиции до 31.12.2026** | `auth_log`, `audit_log`, `data_change_log` | После 31.12.2026 любой INSERT в эти таблицы упадёт → логин сломается. Нужен скрипт автогенерации партиций или `pg_partman`. |
| **`session_notes.content` plaintext** | `models/consultations.py` | Клинические заметки хранятся без шифрования. Нарушение ФЗ-152. |
| **OTP plaintext в БД** | `otp_verifications.code` | 6-значный код хранится как есть. При утечке БД — компрометация аккаунтов в 10-минутном окне. |

### 9.2 Архитектурные риски

| Риск | Описание |
|------|----------|
| **`create_all()` при каждом старте** | Конфликтует с Alembic. После добавления Alembic нужно убрать. |
| **Мёртвый файл `models.py`** | Вводит в заблуждение, должен быть удалён. |
| **`otp_store.py` raises ImportError** | Устарелый файл-ловушка. При случайном импорте — `ImportError`. |
| **`_get_primary_role()` недетерминирован** | При нескольких ролях у юзера — `.first()` без `ORDER BY` вернёт случайную роль. |
| **Email не нормализуется в OTP** | `otp_verifications.email` сохраняется без `.lower().strip()`. Регистр email в init vs confirm может привести к "OTP not found". |
| **Нет rate limiting** | API открыт для brute-force. Нет ограничений на число запросов. |
| **SSL_CERT_NONE в SMTP** | `ctx.verify_mode = ssl.CERT_NONE` отключает проверку сертификата — уязвимость MITM. |
| **`_hash` приватная функция используется снаружи** | `users/service.py` делает `from app.auth.service import _hash`. |
| **`datetime.utcnow()` в otp_service.py** | Deprecated в Python 3.12, удалён в 3.14. |
| **Отсутствие тестов** | Нет unit/integration тестов. Изменения не верифицируются автоматически. |

### 9.3 Legacy архитектура

| Объект | Статус |
|--------|--------|
| `app/auth/otp_store.py` | Deprecated, raises ImportError. Должен быть удалён. |
| `app/db/models.py` | Мёртвый шим. Должен быть удалён. |
| `app/users/routes.py` | Пустой файл (1 строка). |
| `db/sql/*.sql` | Упомянуты в CLAUDE.md как архив, физически отсутствуют. |

### 9.4 Migration risks

| Риск | Описание |
|------|----------|
| **`create_all()` → Alembic race** | Одновременное использование обоих механизмов может привести к расхождению состояния. |
| **Baseline на existing DB** | Если БД создана через `create_all()`, Alembic не знает об этом состоянии. Нужна `alembic stamp head` или baseline-миграция. |
| **Партиции не в ORM** | `auth_log`, `audit_log`, `data_change_log` партиционированы в production, но ORM этого не знает — autogenerate может создать конфликт. |

---

## 10. Recommended Next Steps

### 10.1 Что уже сделано хорошо ✅

- Чистая `Base` в отдельном файле — правильный фундамент
- Все модели в пакете с явным `__init__.py` — правильная структура для Alembic
- Синхронный SQLAlchemy — совместим с Alembic "из коробки"
- String-based relationship ссылки — нет circular import проблем
- Idempotent seed — безопасен при повторных запусках
- `.env` через pydantic-settings — легко интегрируется с `alembic.ini`
- Soft delete везде — безопасная история данных
- Layered architecture (routes → service → storage) — чистое разделение ответственностей

### 10.2 Что нужно сделать перед Alembic

| Приоритет | Действие | Файл |
|-----------|----------|------|
| 🔴 | Удалить `app/db/models.py` (мёртвый шим) | `app/db/models.py` |
| 🔴 | Удалить `app/auth/otp_store.py` (deprecated ловушка) | `app/auth/otp_store.py` |
| 🔴 | Выбрать стратегию для audit-таблиц: exclude из autogenerate или добавить `postgresql_partition_by` в ORM | `models/audit.py`, Alembic `env.py` |
| 🟡 | Установить Alembic: `pip install alembic` | `requirements.txt` |
| 🟡 | Инициализировать: `alembic init alembic` | `mindcare_api/alembic/` |
| 🟡 | Настроить `alembic.ini`: `sqlalchemy.url = %(DATABASE_URL)s` | `alembic.ini` |
| 🟡 | Настроить `env.py`: импорт `Base`, `target_metadata`, exclude партиций | `alembic/env.py` |

### 10.3 Что нужно сделать для production-ready migrations

| Шаг | Действие |
|-----|----------|
| 1 | Создать baseline-миграцию для существующей БД: `alembic revision --autogenerate -m "baseline"` |
| 2 | Просмотреть и скорректировать autogenerate (особенно UUID, INET, ARRAY типы) |
| 3 | Применить: `alembic stamp head` (если БД уже в целевом состоянии) |
| 4 | Убрать `Base.metadata.create_all()` из `init_db.py` |
| 5 | Добавить `alembic upgrade head` в startup (или CI/CD pipeline) |
| 6 | Добавить `ALEMBIC_URL` / читать из settings в `env.py` |
| 7 | Настроить автогенерацию партиций для audit-таблиц (pg_partman или скрипт) |

### 10.4 Что желательно оставить как есть

| Объект | Причина |
|--------|---------|
| Синхронный SQLAlchemy (psycopg2) | Вся кодовая база sync, переход на async — большой рефакторинг |
| Layered architecture (routes/service/storage) | Правильная структура, не трогать без причины |
| pydantic-settings конфиг | Удобен, хорошо интегрируется с Alembic |
| Session-based auth (user_sessions) | Дизайн-решение вместо JWT — не менять |
| Soft delete (deleted_at) | Требование для психологических данных и ФЗ-152 |
| `PGCLIENTENCODING=UTF8` в main.py | Критичен для Windows dev-среды с Russian PostgreSQL |

---

## Appendix A: Модели и их PK-типы

| Таблица | PK | PK-тип |
|---------|----|----|
| roles | id | Integer |
| permissions | id | Integer |
| role_permissions | id | Integer |
| **users** | id | Integer (uuid — отдельное поле UUID) |
| user_roles | id | Integer |
| **user_sessions** | id | String(255) — токен сессии |
| refresh_tokens | id | Integer |
| user_mfa_methods | id | Integer |
| student_profiles | id | Integer |
| psychologist_profiles | id | Integer |
| emergency_contacts | id | Integer |
| consents | id | Integer |
| consent_records | id | Integer |
| media_files | id | Integer |
| media_versions | id | Integer |
| categories | id | Integer |
| articles | id | Integer |
| article_categories | (article_id, category_id) | Composite PK |
| news | id | Integer |
| help_resources | id | Integer |
| questions_answers | id | Integer |
| tests | id | Integer |
| test_categories | (test_id, category_id) | Composite PK |
| questions | id | Integer |
| options | id | Integer |
| question_media | id | Integer |
| option_media | id | Integer |
| test_results | id | Integer |
| test_result_scales | id | Integer |
| student_answers | id | Integer |
| therapy_engagements | id | Integer |
| schedule_rules | id | Integer |
| schedule_exceptions | id | Integer |
| appointments | id | Integer |
| session_notes | id | Integer |
| notification_templates | id | Integer |
| **notifications** | id | BigInteger |
| **audit_log** | id | BigInteger |
| **auth_log** | id | BigInteger |
| **data_change_log** | id | BigInteger |
| **otp_verifications** | id | String(36) — UUID string |

---

## Appendix B: Реализованные API endpoints

| Метод | URL | Auth | Модуль |
|-------|-----|------|--------|
| POST | `/api/auth/register/init` | Public | auth/routes.py |
| POST | `/api/auth/register/confirm` | Public | auth/routes.py |
| POST | `/api/auth/login` | Public | auth/routes.py |
| POST | `/api/auth/logout` | Bearer | auth/routes.py |
| GET | `/api/auth/me` | Bearer | auth/routes.py |
| POST | `/api/auth/password/reset/init` | Public | auth/routes.py |
| POST | `/api/auth/password/reset/confirm` | Public | auth/routes.py |
| GET | `/api/admin/users` | Admin | users/routes_admin.py |
| POST | `/api/admin/users` | Admin | users/routes_admin.py |
| GET | `/api/admin/users/{uuid}` | Admin | users/routes_admin.py |
| PATCH | `/api/admin/users/{uuid}` | Admin | users/routes_admin.py |
| DELETE | `/api/admin/users/{uuid}` | Admin | users/routes_admin.py |
| GET | `/api/health` | Public | main.py |
| GET | `/api/hello` | Public | main.py |

---

*Snapshot создан: 2026-05-20. Автор: Claude Sonnet 4.6 (Code First migration session).*
