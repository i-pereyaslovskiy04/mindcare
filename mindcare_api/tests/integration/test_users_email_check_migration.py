"""
Round-trip migration test для f3b8d1e6a4c2 (users.email CHECK + автонормализация).

ГЕЙТИНГ (не менять schema revision во время обычного full suite):
  - по умолчанию SKIPPED; запускается только при MINDCARE_MIGRATION_ROUNDTRIP=1;
  - при открытом gate любое нарушение безопасности — ОШИБКА, не skip:
      ENV=test, DATABASE_URL присутствует, current_database() ~ mindcare_test_<random>;
  - собственный engine для проверок; DDL — через Alembic (его engine);
  - ТОЧНЫЕ revision ID (не downgrade -1);
  - после проверок БД остаётся на head; одноразовую БД удалит Stage 1 runner.

Отдельный запуск:
  ENV=test MINDCARE_MIGRATION_ROUNDTRIP=1 TEST_DATABASE_URL=... \
      python scripts/isolated_test_db.py -k users_email_check_migration -v

Email — с префиксом integ_ (после нормализации их удаляет cleanup_test_records;
teardown safe_test_db возвращает head раньше, чем cleanup).
"""
import os
import re
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

API_DIR = Path(__file__).resolve().parents[2]
_TEST_DB_RE = re.compile(r"^mindcare_test_[a-z0-9]+$")

PREV_REVISION = "a1c2e3f4b5d6"
REVISION = "f3b8d1e6a4c2"
CHECK_NAME = "ck_users_email_normalized"

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


def _check_exists() -> bool:
    return bool(_scalar(
        "SELECT count(*) FROM pg_constraint "
        "WHERE conrelid = 'users'::regclass AND conname = :n",
        n=CHECK_NAME,
    ))


def _insert_user(email: str, deleted: bool = False) -> int:
    eng = _engine()
    try:
        with eng.begin() as c:
            return c.execute(text(
                "INSERT INTO users (uuid, full_name, email, password_hash, deleted_at) "
                "VALUES (:u, 'Migration Probe', :e, 'x', "
                "CASE WHEN :d THEN now() ELSE NULL END) RETURNING id"
            ), {"u": str(uuid.uuid4()), "e": email, "d": deleted}).scalar()
    finally:
        eng.dispose()


def _alembic(action: str, revision: str) -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_DIR / "alembic"))
    if action == "upgrade":
        command.upgrade(cfg, revision)
    else:
        command.downgrade(cfg, revision)


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
    yield
    _alembic("upgrade", REVISION)


def _local() -> str:
    return f"integ_{uuid.uuid4().hex[:12]}"


def test_upgrade_normalizes_existing_emails_then_adds_check(safe_test_db):
    _alembic("downgrade", PREV_REVISION)
    assert not _check_exists()

    probes = {
        "mixed":   (f"{_local().upper()}@DonNU.ru", False),
        "spaces":  (f"  {_local()}@donnu.ru ", False),
        "deleted": (f"{_local().upper()}@donnu.ru", True),   # soft-deleted тоже
        "ok":      (f"{_local()}@donnu.ru", False),
    }
    ids = {k: _insert_user(email, deleted) for k, (email, deleted) in probes.items()}

    _alembic("upgrade", REVISION)

    assert _check_exists()
    for key, (email, _) in probes.items():
        stored = _scalar("SELECT email FROM users WHERE id = :i", i=ids[key])
        assert stored == email.strip().lower(), key
    assert _scalar(
        "SELECT count(*) FROM users WHERE email <> lower(trim(email))"
    ) == 0


def test_normalized_unique_index_rules_out_collisions_before_upgrade(safe_test_db):
    # Обоснование безопасной автонормализации: ещё ДО этой миграции
    # ux_users_email_normalized не даёт существовать Ivan@x рядом с ivan@x.
    _alembic("downgrade", PREV_REVISION)
    local = _local()
    _insert_user(f"{local}@donnu.ru")
    with pytest.raises(IntegrityError) as exc_info:
        _insert_user(f"{local.upper()}@donnu.ru")
    assert exc_info.value.orig.diag.constraint_name == "ux_users_email_normalized"


def test_downgrade_drops_only_the_check(safe_test_db):
    _alembic("upgrade", REVISION)
    assert _check_exists()
    _alembic("downgrade", PREV_REVISION)
    assert not _check_exists()
    assert _scalar(
        "SELECT count(*) FROM pg_indexes WHERE indexname = 'ux_users_email_normalized'"
    ) == 1
    _alembic("upgrade", REVISION)
    assert _check_exists()
