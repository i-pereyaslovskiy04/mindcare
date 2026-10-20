"""
Alembic environment configuration для MindCare API.

Особенности:
  - Синхронный SQLAlchemy (psycopg2, не asyncpg)
  - DATABASE_URL читается из .env через pydantic-settings
  - target_metadata = Base.metadata (все 41 таблица, включая audit)
  - Partition child tables исключены из autogenerate через include_object()

Запуск:
  cd mindcare_api/
  alembic upgrade head          # применить все pending миграции
  alembic revision --autogenerate -m "describe change"
  alembic current               # текущая версия
  alembic history               # история миграций

Примечание по logging:
  fileConfig() намеренно НЕ вызывается — это CLI-инструмент, и
  logging.basicConfig() настроен Python-ом по умолчанию (WARNING уровень),
  чего достаточно для alembic CLI.
  Если нужны подробные логи миграций: alembic --verbose upgrade head
"""

import os
import re
import sys

from sqlalchemy import engine_from_config, pool
from alembic import context

# ── Path setup ────────────────────────────────────────────────────────────────
# Позволяет alembic находить app/ пакет при запуске из mindcare_api/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Принудительно задаём кодировку клиента PostgreSQL (Windows + русская локаль)
os.environ.setdefault("PGCLIENTENCODING", "UTF8")

config = context.config

# ── Models & Metadata ─────────────────────────────────────────────────────────
# КРИТИЧНО: импортировать app.db.models ДО Base.metadata
# чтобы все таблицы были зарегистрированы в metadata.
import app.db.models  # noqa: F401, E402 — регистрирует все 41 таблицу

from app.db.base import Base  # noqa: E402

target_metadata = Base.metadata

# ── DATABASE_URL из .env ──────────────────────────────────────────────────────
from app.core.config import settings  # noqa: E402

# Переопределяем URL из alembic.ini — берём из pydantic-settings (читает .env)
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# ── Autogenerate filter ───────────────────────────────────────────────────────
# В production-БД audit-таблицы партиционированы по месяцам (YYYY_MM).
# Дочерние партиции (auth_log_2026_01 и т.п.) не описаны в ORM и
# не должны попадать в autogenerate diff как "лишние таблицы".
_PARTITION_RE = re.compile(
    r"^(auth_log|audit_log|data_change_log)_\d{4}_\d{2}$"
)


def include_object(obj, name, type_, reflected, compare_to):
    """
    Исключает дочерние партиции из autogenerate diff.

    Родительские таблицы (auth_log, audit_log, data_change_log) управляются
    через Alembic migration и включены в diff.
    Дочерние партиции (auth_log_2026_01, ...) — исключены.
    """
    if type_ == "table" and reflected and _PARTITION_RE.match(name):
        return False
    return True


# ── Migration runners ─────────────────────────────────────────────────────────

def run_migrations_offline() -> None:
    """
    Offline mode: генерирует SQL-скрипт без подключения к БД.

    Полезно для генерации SQL-дампа миграции:
      alembic upgrade head --sql > migration.sql

    compare_type=True включён для корректного autogenerate в offline режиме.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Online mode: подключается к БД и применяет миграции.

    Используется при:
      alembic upgrade head
      alembic downgrade -1

    NullPool: каждый вызов открывает и закрывает соединение.
    Не конкурирует с connection pool основного engine.

    compare_type НЕ включён в online mode — для upgrade он не нужен
    (Alembic не делает schema comparison во время upgrade).
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args={"client_encoding": "utf8"},  # Windows: UTF8 вместо cp1251
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
