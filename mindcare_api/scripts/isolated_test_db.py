"""
Isolated integration-test database runner (Stage 1).

Создаёт одноразовую PostgreSQL-БД ``mindcare_test_<random>``, применяет Alembic,
запускает pytest на изолированной БД и гарантированно удаляет БД в ``finally`` —
и при успехе, и при падении (Alembic / pytest / cleanup).

Гарантии безопасности:
  * НИКОГДА не использует dev/prod ``DATABASE_URL`` — читает ТОЛЬКО
    ``TEST_DATABASE_URL`` (из окружения, затем из ``mindcare_api/.env``).
  * Не импортирует ``app.*`` (свой admin-engine + локальный settings-класс).
  * child-БД всегда генерируется как ``mindcare_test_<random>`` и удаляется только
    если её создал ЭТОТ запуск.
  * URL и credentials никогда не печатаются; в сообщениях — только имя БД и класс
    исключения (без ``str(exc)`` / raw exception text).

Запуск (через test.ps1 / test.sh, либо напрямую с ЯВНЫМ ``ENV=test``):
    ENV=test TEST_DATABASE_URL=postgresql+psycopg2://postgres:***@host:5432/postgres \
        python scripts/isolated_test_db.py [доп. pytest-аргументы...]
"""
from __future__ import annotations

import base64
import os
import re
import secrets
import subprocess
import sys
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url

# ── Пути (абсолютно, независимо от cwd вызывающего процесса) ───────────────────
API_DIR = Path(__file__).resolve().parents[1]   # mindcare_api/
ENV_FILE = API_DIR / ".env"

# ── Инварианты имён БД ────────────────────────────────────────────────────────
TEST_DB_NAME_RE = re.compile(r"^mindcare_test_[a-z0-9]+$")

FORBIDDEN_DB_NAMES = frozenset({
    "postgres", "template0", "template1",
    "mindcare", "mindcare_dev", "mindcare_prod",
    "mindcare_production", "mindcare_staging",
})

# Единственная разрешённая admin-точка как source database во входном URL.
ALLOWED_SOURCE_DB = "postgres"

# Разрешённые SQLAlchemy drivername: только синхронный psycopg2 PostgreSQL.
# sqlite / mysql / postgresql+asyncpg и прочие — отклоняются.
ALLOWED_DRIVERNAMES = frozenset({"postgresql", "postgresql+psycopg2"})

# Заведомо недоступный DATABASE_URL для pytest-режимов без изолированной test-БД:
# хост:порт 1 не слушает, имя не матчит mindcare_test_ → integration отклоняются,
# а случайный доступ к БД падает громко вместо тихого коннекта к dev.
SENTINEL_DATABASE_URL = (
    "postgresql+psycopg2://sentinel:sentinel@127.0.0.1:1/mindcare_unit_sentinel"
)

# Синтетический Fernet-ключ ТОЛЬКО для тестов: 32 байта → urlsafe base64.
# Не dev/prod-ключ и не секрет — фиксированное детерминированное значение.
# Приложение (assert_encryption_ready) требует валидный DATA_ENCRYPTION_KEY
# при старте lifespan; в тестах используем именно этот, а не ключ из .env.
TEST_ONLY_ENCRYPTION_KEY = base64.urlsafe_b64encode(
    b"mindcare-test-only-key-32-bytes!"
).decode()

# Детерминированные безопасные значения тестового окружения (не наследуем dev).
SAFE_TEST_ENV = {
    "DEBUG": "false",
    "EMAIL_MODE": "dev",
    "DATA_ENCRYPTION_KEY": TEST_ONLY_ENCRYPTION_KEY,
}


class _RunnerSettings(BaseSettings):
    """Локальный settings-класс runner'а. НЕ импортирует app.core.config.

    Приоритет: переменная окружения → mindcare_api/.env (абсолютный путь).
    """
    TEST_DATABASE_URL: Optional[str] = None
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )


# ── Резолв / валидация входного URL ───────────────────────────────────────────

def resolve_test_url() -> URL:
    """Возвращает TEST_DATABASE_URL как SQLAlchemy URL.

    Никогда не читает DATABASE_URL. Отсутствие значения → fail-fast.
    """
    raw = _RunnerSettings().TEST_DATABASE_URL
    if not raw or not raw.strip():
        raise RuntimeError(
            "TEST_DATABASE_URL не задан (ни в окружении, ни в mindcare_api/.env). "
            "Integration-тесты требуют отдельный PostgreSQL — см. .env.example."
        )
    # make_url может бросить ArgumentError с исходным URL в тексте —
    # это исключение перехватывается в main() и НЕ печатается как str(exc).
    return make_url(raw.strip())


def _assert_allowed_driver(url: URL) -> None:
    """Разрешён только синхронный PostgreSQL (postgresql / postgresql+psycopg2).

    Ошибка не содержит исходный URL/пароль/raw exception.
    """
    if url.drivername not in ALLOWED_DRIVERNAMES:
        raise RuntimeError(
            "TEST_DATABASE_URL: недопустимый драйвер БД — разрешены только "
            "postgresql и postgresql+psycopg2."
        )


def validate_source_url(url: URL) -> None:
    """Source URL: только psycopg2 PostgreSQL и admin-точка 'postgres'."""
    _assert_allowed_driver(url)
    src = (url.database or "").strip()
    if src == ALLOWED_SOURCE_DB:
        return
    if src in FORBIDDEN_DB_NAMES:
        raise RuntimeError(
            f"TEST_DATABASE_URL source database '{src}' запрещена (dev/prod). "
            "Укажите admin-точку 'postgres'; runner создаст mindcare_test_<random>."
        )
    raise RuntimeError(
        "TEST_DATABASE_URL source database должна быть 'postgres' (admin-точка); "
        "фактическая test-БД создаётся автоматически."
    )


# ── Имена / окружение ─────────────────────────────────────────────────────────

def generate_test_db_name() -> str:
    """Уникальное имя дочерней test-БД. Только [a-z0-9] после префикса."""
    return "mindcare_test_" + secrets.token_hex(8)


def assert_safe_db_name(name: str) -> None:
    if not TEST_DB_NAME_RE.match(name) or name in FORBIDDEN_DB_NAMES:
        raise RuntimeError(f"Небезопасное имя тестовой БД: {name!r}")


def require_test_env() -> None:
    """Defense-in-depth: destructive-операции только при ENV=test."""
    if os.environ.get("ENV") != "test":
        raise RuntimeError("ENV != 'test': отказ от операций над БД.")


def admin_url_for(url: URL) -> URL:
    return url.set(database=ALLOWED_SOURCE_DB)


def child_url_for(url: URL, name: str) -> URL:
    return url.set(database=name)


# ── Root-conftest helper (какой DATABASE_URL отдать pytest) ───────────────────

def resolve_pytest_database_url(environ: dict) -> str:
    """Каким DATABASE_URL должен пользоваться pytest. Никогда не dev .env value.

    Приоритет:
      1. MINDCARE_UNIT_ONLY=1 → недоступный sentinel (TEST_DATABASE_URL игнор.);
      2. TEST_DATABASE_URL при ENV=test → принять ТОЛЬКО если имя БД матчит
         ^mindcare_test_[a-z0-9]+$ (admin 'postgres', dev 'mindcare', произвольные
         имена, отсутствующее имя и malformed URL — отклонить);
      3. иначе → sentinel.

    Ошибки не содержат URL/пароль/raw exception. Source/admin URL никогда не
    становится DATABASE_URL: он не проходит проверку имени.
    """
    if environ.get("MINDCARE_UNIT_ONLY") == "1":
        return SENTINEL_DATABASE_URL
    test_url = environ.get("TEST_DATABASE_URL")
    if not test_url:
        return SENTINEL_DATABASE_URL
    if environ.get("ENV") != "test":
        raise RuntimeError("TEST_DATABASE_URL задан, но ENV != 'test' — отказ.")
    try:
        parsed = make_url(test_url)
    except Exception:
        # malformed URL: НЕ раскрываем исходную строку/пароль.
        raise RuntimeError(
            "TEST_DATABASE_URL malformed — ожидается PostgreSQL URL "
            "с БД mindcare_test_<random>."
        ) from None
    _assert_allowed_driver(parsed)     # sqlite/mysql/asyncpg и пр. — отклонить
    db_name = parsed.database or ""
    if not TEST_DB_NAME_RE.match(db_name):
        raise RuntimeError(
            "TEST_DATABASE_URL для pytest должен указывать на изолированную "
            "mindcare_test_<random> (admin 'postgres', dev и произвольные имена "
            "запрещены)."
        )
    return test_url


# ── Менеджер одноразовой БД ───────────────────────────────────────────────────

class IsolatedTestDB:
    def __init__(self, admin_url: URL, db_name: str):
        self.admin_url = admin_url
        self.db_name = db_name
        self.db_url: Optional[URL] = None
        self.created = False
        self._admin_engine = None
        self._verify_engine = None

    def _admin(self):
        if self._admin_engine is None:
            self._admin_engine = create_engine(
                self.admin_url,
                isolation_level="AUTOCOMMIT",
                connect_args={"client_encoding": "utf8"},
            )
        return self._admin_engine

    def preflight(self) -> None:
        require_test_env()
        assert_safe_db_name(self.db_name)
        with self._admin().connect() as conn:
            can_create = conn.execute(text(
                "SELECT (rolcreatedb OR rolsuper) FROM pg_roles "
                "WHERE rolname = current_user"
            )).scalar()
        if not can_create:
            raise RuntimeError(
                "Текущий пользователь PostgreSQL не имеет привилегии CREATEDB. "
                "Выдайте её: ALTER USER <user> CREATEDB;"
            )

    def create(self) -> None:
        # db_name сгенерирован нами и провалидирован; параметризация имени БД в
        # DDL невозможна, поэтому повторно проверяем безопасность строки.
        assert_safe_db_name(self.db_name)
        with self._admin().connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{self.db_name}"'))
        self.created = True

    def verify(self) -> None:
        """current_database() == db_name и матч шаблону. Вызывается ДО Alembic."""
        if self.db_url is None:
            raise RuntimeError("db_url не установлен перед verify().")
        self._verify_engine = create_engine(
            self.db_url, connect_args={"client_encoding": "utf8"}
        )
        with self._verify_engine.connect() as conn:
            actual = conn.execute(text("SELECT current_database()")).scalar()
        if actual != self.db_name or not TEST_DB_NAME_RE.match(actual or ""):
            raise RuntimeError(
                f"verify: current_database()={actual!r} != {self.db_name!r}"
            )

    def child_env_url(self) -> str:
        """Строка URL с реальным паролем — ТОЛЬКО для env дочернего процесса."""
        assert self.db_url is not None
        return self.db_url.render_as_string(hide_password=False)

    def _dispose_verify(self) -> None:
        if self._verify_engine is not None:
            self._verify_engine.dispose()
            self._verify_engine = None

    def drop(self) -> None:
        # guard: удаляем только то, что создал ЭТОТ запуск, и только по шаблону.
        if not self.created or not TEST_DB_NAME_RE.match(self.db_name):
            print(
                f"[DROP SKIP] db={self.db_name} — не создавалась этим runner",
                file=sys.stderr,
            )
            return
        # 1) освободить собственные соединения к child-БД до DROP.
        self._dispose_verify()
        try:
            with self._admin().connect() as conn:
                # 2) завершить оставшиеся подключения к точному имени.
                conn.execute(
                    text(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname = :n AND pid <> pg_backend_pid()"
                    ),
                    {"n": self.db_name},
                )
                # 3) удалить точное имя.
                conn.execute(text(f'DROP DATABASE IF EXISTS "{self.db_name}"'))
        finally:
            # 4) dispose admin-engine в finally.
            if self._admin_engine is not None:
                self._admin_engine.dispose()
                self._admin_engine = None

    def dispose_engines(self) -> None:
        """Идемпотентный dispose всех engine (страховка из main.finally)."""
        self._dispose_verify()
        if self._admin_engine is not None:
            self._admin_engine.dispose()
            self._admin_engine = None


# ── Дочерние процессы (мокаются в harness-тестах) ─────────────────────────────

def _build_child_env(child_url: str) -> dict:
    """Env для дочерних процессов (alembic/pytest).

    Изолированная test-БД + детерминированные безопасные значения
    (DEBUG=false, EMAIL_MODE=dev, синтетический DATA_ENCRYPTION_KEY).
    Унаследованный MINDCARE_UNIT_ONLY удаляется — полный режим не unit-only.
    """
    env = dict(os.environ)
    env.pop("MINDCARE_UNIT_ONLY", None)
    env.update(SAFE_TEST_ENV)
    env["ENV"] = "test"
    env["PGCLIENTENCODING"] = "UTF8"
    env["TEST_DATABASE_URL"] = child_url
    env["DATABASE_URL"] = child_url
    return env


def _run_alembic(env: dict) -> int:
    return subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(API_DIR),
        env=env,
    ).returncode


def _run_pytest(args: list, env: dict) -> int:
    return subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", *args],
        cwd=str(API_DIR),
        env=env,
    ).returncode


# ── Точка входа ───────────────────────────────────────────────────────────────

def main(argv: list) -> int:
    """preflight → create → verify → alembic → pytest → finally drop.

    Внешняя безопасная граница исключений охватывает ВЕСЬ main(), включая
    resolve/URL-parse/validate/генерацию имени/создание менеджера: ни pydantic,
    ни SQLAlchemy URL parser не должны выдать traceback с исходным URL.
    """
    mgr: Optional[IsolatedTestDB] = None
    result = 1
    cleanup_failed = False
    try:
        url = resolve_test_url()
        validate_source_url(url)
        mgr = IsolatedTestDB(
            admin_url=admin_url_for(url),
            db_name=generate_test_db_name(),
        )
        mgr.db_url = child_url_for(url, mgr.db_name)
        print(f"[isolated-test-db] временная БД: {mgr.db_name}")

        mgr.preflight()
        mgr.create()
        mgr.verify()                      # verify ДО Alembic

        env = _build_child_env(mgr.child_env_url())
        arc = _run_alembic(env)
        if arc != 0:
            print(f"[ALEMBIC FAIL] db={mgr.db_name} rc={arc}", file=sys.stderr)
            result = arc or 1             # pytest НЕ запускаем
        else:
            result = _run_pytest(argv, env)   # сохраняем returncode pytest
    except Exception as exc:
        # Только класс исключения и безопасное имя — без str(exc)/repr(exc)/URL.
        name = mgr.db_name if mgr is not None else "(not-created)"
        print(f"[RUN FAIL] db={name} {type(exc).__name__}", file=sys.stderr)
        result = 1
    finally:
        if mgr is not None:               # если manager не создан — чистить нечего
            try:
                mgr.drop()
            except Exception as exc:
                cleanup_failed = True
                print(
                    f"[CLEANUP FAIL] db={mgr.db_name} {type(exc).__name__}",
                    file=sys.stderr,
                )
            finally:
                mgr.dispose_engines()

    if cleanup_failed and result == 0:
        result = 1                        # cleanup-ошибка → ненулевой код
    return result


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
