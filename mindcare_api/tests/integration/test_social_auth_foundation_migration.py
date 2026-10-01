"""
Round-trip migration test для c6e1a4f8b2d7 (social auth foundation).

ГЕЙТИНГ (не менять schema revision во время обычного full suite):
  - по умолчанию SKIPPED; запускается только при MINDCARE_MIGRATION_ROUNDTRIP=1;
  - при открытом gate любое нарушение безопасности — ОШИБКА, не skip:
      ENV=test, DATABASE_URL присутствует, current_database() ~ mindcare_test_<random>;
  - собственный engine для проверок; DDL — через Alembic (его engine);
  - ТОЧНЫЕ revision ID (не downgrade -1);
  - после проверок БД остаётся на head; одноразовую БД удалит Stage 1 runner.

Отдельный запуск:
  ENV=test MINDCARE_MIGRATION_ROUNDTRIP=1 TEST_DATABASE_URL=... \
      python scripts/isolated_test_db.py -k social_auth_foundation_migration -v
"""
import os
import re
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

API_DIR = Path(__file__).resolve().parents[2]
_TEST_DB_RE = re.compile(r"^mindcare_test_[a-z0-9]+$")

PREV_REVISION = "f3b8d1e6a4c2"
REVISION = "c6e1a4f8b2d7"
NEW_TABLES = ("user_oauth_identities", "oauth_auth_requests", "oauth_pending_tickets")

pytestmark = pytest.mark.skipif(
    os.environ.get("MINDCARE_MIGRATION_ROUNDTRIP") != "1",
    reason="round-trip migration disabled (set MINDCARE_MIGRATION_ROUNDTRIP=1)",
)


def _engine():
    return create_engine(
        os.environ["DATABASE_URL"], connect_args={"client_encoding": "utf8"}
    )


def _scalar(sql, **params):
    eng = _engine()
    try:
        with eng.connect() as c:
            return c.execute(text(sql), params).scalar()
    finally:
        eng.dispose()


def _execute(sql, **params):
    """Выполняет в своей транзакции; RETURNING-значение читается до закрытия."""
    eng = _engine()
    try:
        with eng.begin() as c:
            result = c.execute(text(sql), params)
            return result.scalar() if result.returns_rows else None
    finally:
        eng.dispose()


def _nullable(table: str, column: str) -> bool:
    return _scalar(
        "SELECT is_nullable FROM information_schema.columns "
        "WHERE table_name = :t AND column_name = :c",
        t=table, c=column,
    ) == "YES"


def _existing_tables() -> set:
    return {
        name for name in NEW_TABLES
        if _scalar("SELECT to_regclass(:n) IS NOT NULL", n=f"public.{name}")
    }


def _alembic(action: str, revision: str) -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_DIR / "alembic"))
    if action == "upgrade":
        command.upgrade(cfg, revision)
    else:
        command.downgrade(cfg, revision)


def _insert_user(email: str, password_hash) -> int:
    return _execute(
        "INSERT INTO users (uuid, full_name, email, password_hash) "
        "VALUES (:u, 'Migration Probe', :e, :p) RETURNING id",
        u=str(uuid.uuid4()), e=email, p=password_hash,
    )


def _delete_user(user_id: int) -> None:
    _execute("DELETE FROM users WHERE id = :i", i=user_id)


@pytest.fixture()
def safe_test_db():
    if os.environ.get("ENV") != "test":
        raise RuntimeError("roundtrip: ENV must be 'test'.")
    if not os.environ.get("DATABASE_URL"):
        raise RuntimeError("roundtrip: DATABASE_URL must be present.")
    current = _scalar("SELECT current_database()")
    if not (current and _TEST_DB_RE.match(current)):
        raise RuntimeError(
            "roundtrip: current_database() must be mindcare_test_<random>."
        )
    if _scalar("SELECT COUNT(*) FROM users WHERE password_hash IS NULL"):
        pytest.skip("round-trip requires a DB without passwordless users")
    yield
    _alembic("upgrade", REVISION)


def _email() -> str:
    return f"integ_{uuid.uuid4().hex[:12]}@donnu.ru"


def test_upgrade_state_matches_contract(safe_test_db):
    _alembic("upgrade", REVISION)
    assert _existing_tables() == set(NEW_TABLES)
    assert _nullable("users", "password_hash")
    assert _nullable("otp_verifications", "password_hash")


def test_downgrade_restores_previous_schema_and_upgrade_is_repeatable(safe_test_db):
    _alembic("upgrade", REVISION)
    user_id = _insert_user(_email(), "$2b$04$probe")   # пароль есть — откат разрешён
    try:
        _alembic("downgrade", PREV_REVISION)
        assert _existing_tables() == set()
        assert not _nullable("users", "password_hash")
        assert not _nullable("otp_verifications", "password_hash")

        _alembic("upgrade", REVISION)
        assert _existing_tables() == set(NEW_TABLES)
        assert _nullable("users", "password_hash")
        assert _scalar("SELECT password_hash FROM users WHERE id = :i", i=user_id) == (
            "$2b$04$probe"
        )
    finally:
        _delete_user(user_id)


def test_downgrade_drops_pending_reset_otps(safe_test_db):
    _alembic("upgrade", REVISION)
    email = _email()
    now = datetime.utcnow()
    _execute(
        "INSERT INTO otp_verifications "
        "(id, email, code, name, password_hash, attempts, expires_at, created_at, last_sent_at) "
        "VALUES (:id, :e, :c, 'Probe', NULL, 0, :exp, :now, :now)",
        id=str(uuid.uuid4()), e=email, c="0" * 64,
        exp=now + timedelta(minutes=10), now=now,
    )
    _alembic("downgrade", PREV_REVISION)
    assert _scalar(
        "SELECT COUNT(*) FROM otp_verifications WHERE email = :e", e=email
    ) == 0


def test_downgrade_fails_closed_with_passwordless_user(safe_test_db):
    _alembic("upgrade", REVISION)
    user_id = _insert_user(_email(), None)
    try:
        with pytest.raises(RuntimeError, match="no password"):
            _alembic("downgrade", PREV_REVISION)
        # Ничего не изменено: ревизия, таблицы, nullable, сам пользователь.
        assert _scalar("SELECT version_num FROM alembic_version") == REVISION
        assert _existing_tables() == set(NEW_TABLES)
        assert _nullable("users", "password_hash")
        assert _scalar("SELECT COUNT(*) FROM users WHERE id = :i", i=user_id) == 1
    finally:
        _delete_user(user_id)
