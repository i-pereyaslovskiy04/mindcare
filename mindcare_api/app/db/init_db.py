"""
Инициализация базы данных при старте приложения.

Функции:
  check_connection()    — проверяет доступность PostgreSQL
  ensure_database()     — создаёт БД если отсутствует
  check_migrations()    — проверяет, что DB на актуальной revision (read-only)
  run_migrations()      — CLI/CI: alembic upgrade head (НЕ вызывать из FastAPI)
  init_db()             — точка входа FastAPI: ensure_database + check + seed
  health_check()        — для /api/health endpoint

╔══════════════════════════════════════════════════════════════╗
║  КРИТИЧЕСКИ ВАЖНО: ПОРЯДОК ЗАПУСКА                          ║
║                                                              ║
║  1. alembic upgrade head   ← применить миграции (CLI/CI)    ║
║  2. uvicorn app.main:app   ← стартовать приложение          ║
║                                                              ║
║  Миграции НЕ запускаются автоматически при старте FastAPI.  ║
║  init_db() выполняет только проверку версии и seed.         ║
╚══════════════════════════════════════════════════════════════╝
"""

import logging
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

log = logging.getLogger(__name__)


# ─── Connection & DB existence ────────────────────────────────────────────────

def check_connection() -> bool:
    """
    Проверяет, что PostgreSQL доступен и принимает запросы.
    Возвращает True если OK, иначе False.
    """
    from app.db.session import engine
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except OperationalError as exc:
        log.error("[DB] Connection check failed: %s", exc)
        return False


def ensure_database() -> None:
    """
    Гарантирует, что целевая БД существует.

    Алгоритм:
      1. Пробуем подключиться к целевой БД.
      2. Если OK — ничего не делаем.
      3. Если падает OperationalError с "does not exist" — подключаемся
         к системной БД 'postgres' и создаём целевую базу.
      4. Если создать не удалось — бросаем RuntimeError с понятным текстом.

    В production-окружениях (Railway, Supabase, etc.) БД создаётся заранее —
    эта функция пройдёт ветку 1 и ничего не сделает.
    Требует привилегию CREATEDB только при первом создании БД.
    """
    from app.db.session import engine
    from app.core.config import settings
    from sqlalchemy import create_engine

    # ── шаг 1: целевая БД доступна? ──────────────────────────────────────────
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        log.info("[DB] Database connection OK")
        return
    except OperationalError as exc:
        err_msg = str(exc).lower()
        if "does not exist" not in err_msg:
            log.error("[DB] Cannot connect: %s", exc)
            raise RuntimeError(
                f"Cannot connect to PostgreSQL: {exc}\n"
                "Проверь DATABASE_URL в .env и доступность сервера."
            ) from exc

    # ── шаг 2: создаём БД через подключение к 'postgres' ────────────────────
    db_url = settings.DATABASE_URL
    base_url, _, db_name = db_url.rpartition("/")

    log.warning("[DB] Database '%s' does not exist, attempting to create...", db_name)

    admin_url = f"{base_url}/postgres"
    try:
        admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
        with admin_engine.connect() as conn:
            result = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": db_name},
            )
            if not result.fetchone():
                conn.execute(text(f'CREATE DATABASE "{db_name}"'))
                log.info("[DB] Database '%s' created successfully", db_name)
            else:
                log.info("[DB] Database '%s' already exists", db_name)
        admin_engine.dispose()
    except Exception as exc:
        raise RuntimeError(
            f"Cannot create database '{db_name}': {exc}\n"
            "Создай БД вручную: psql -U postgres -c 'CREATE DATABASE mindcare;'\n"
            "Или выдай права: psql -U postgres -c 'ALTER USER MindcareUser CREATEDB;'"
        ) from exc


# ─── Migration status check ───────────────────────────────────────────────────

def check_migrations() -> bool:
    """
    Проверяет, что DB находится на актуальной Alembic revision.

    READ-ONLY: только проверка, никаких миграций не выполняется.
    Логирует WARNING если DB отстаёт от head.

    Возвращает True если DB на head, False если есть pending миграции.

    Вызывается из init_db() при старте приложения.
    Если забыли запустить 'alembic upgrade head' — увидишь WARNING в логах.
    """
    import os
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from alembic.runtime.migration import MigrationContext
    from app.db.session import engine

    ini_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "alembic.ini",
    )

    try:
        alembic_cfg = Config(ini_path)
        script = ScriptDirectory.from_config(alembic_cfg)
        heads = set(script.get_heads())

        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            current = ctx.get_current_revision()

        if current in heads:
            log.info("[DB] Schema is up to date (revision: %s)", current)
            return True
        else:
            log.warning(
                "[DB] *** MIGRATION WARNING ***\n"
                "[DB]   Database is at revision: %s\n"
                "[DB]   Latest revision(s):      %s\n"
                "[DB]   Run 'alembic upgrade head' before starting the application.",
                current,
                ", ".join(heads),
            )
            return False
    except Exception as exc:
        log.warning("[DB] Could not check migration status: %s", exc)
        return False


# ─── Migration runner (CLI/CI only) ──────────────────────────────────────────

def run_migrations() -> None:
    """
    Применяет все pending Alembic миграции (alembic upgrade head).

    ⚠️  НЕ ВЫЗЫВАТЬ из FastAPI lifespan / async context.
        Sync psycopg2 + async event loop = deadlock / startup freeze.

    Предназначена для:
      - CLI:      cd mindcare_api && alembic upgrade head
      - CI/CD:    python -c "from app.db.init_db import run_migrations; run_migrations()"
      - dev setup скрипты (вне async контекста)

    Idempotent: если DB уже на head — ничего не происходит.
    """
    import os
    from alembic.config import Config
    from alembic import command

    ini_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "alembic.ini",
    )

    log.info("[DB] Running alembic upgrade head (ini: %s)...", ini_path)
    try:
        alembic_cfg = Config(ini_path)
        command.upgrade(alembic_cfg, "head")
        log.info("[DB] Alembic upgrade head completed OK")
    except Exception as exc:
        log.error("[DB] Alembic upgrade head failed: %s", exc, exc_info=True)
        raise


# ─── Health check ─────────────────────────────────────────────────────────────

def health_check() -> dict:
    """
    Возвращает словарь с состоянием БД.
    Используется в /api/health эндпоинте.

    Пример ответа:
        {"status": "ok", "db": "connected", "tables": 41, "revision": "af13ad7a133c"}
    """
    from app.db.session import engine
    from app.db.base import Base
    import app.db.models  # noqa: F401

    try:
        from alembic.runtime.migration import MigrationContext
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            ctx = MigrationContext.configure(conn)
            revision = ctx.get_current_revision()

        return {
            "status": "ok",
            "db": "connected",
            "tables": len(Base.metadata.tables),
            "revision": revision,
        }
    except Exception as exc:
        return {
            "status": "error",
            "db": "disconnected",
            "detail": str(exc),
        }


# ─── Main entry point (FastAPI runtime) ──────────────────────────────────────

def init_db() -> None:
    """
    FastAPI startup hook — вызывается из app/main.py lifespan.

    Выполняет ТОЛЬКО:
      1. ensure_database()  — создаёт БД если нет (dev convenience)
      2. check_migrations() — WARNING если DB не на head (read-only)
      3. run_seed()         — базовые данные (идемпотентно)

    Миграции НЕ выполняются здесь.
    Запустите 'alembic upgrade head' ПЕРЕД стартом приложения.

    При любой критической ошибке бросает исключение —
    FastAPI не стартует с неработающей БД.
    """
    log.info("[DB] ══════════════════════════════════════════════")
    log.info("[DB]  Database initialization starting")
    log.info("[DB] ══════════════════════════════════════════════")

    try:
        ensure_database()
        check_migrations()

        from app.db.seed import run_seed
        run_seed()

        log.info("[DB] ══════════════════════════════════════════════")
        log.info("[DB]  Initialization complete")
        log.info("[DB] ══════════════════════════════════════════════")

    except Exception as exc:
        log.critical(
            "[DB] FATAL: Database initialization failed: %s", exc, exc_info=True
        )
        raise
