"""
Round-trip migration test для a3e7c1f9d5b2 (ADR-036, тестовые кампании).

ГЕЙТИНГ (не менять schema revision во время обычного full suite):
  - по умолчанию SKIPPED; запускается только при MINDCARE_MIGRATION_ROUNDTRIP=1;
  - при открытом gate любое нарушение безопасности — ОШИБКА, не skip:
      ENV=test, DATABASE_URL присутствует, current_database() ~ mindcare_test_<random>;
  - собственный engine для проверок; DDL — через Alembic;
  - ТОЧНЫЕ revision ID (не downgrade -1);
  - после проверок БД возвращается на REVISION.

Отдельный запуск:
  ENV=test MINDCARE_MIGRATION_ROUNDTRIP=1 TEST_DATABASE_URL=... \
      python scripts/isolated_test_db.py -k test_campaigns_migration -v
"""
import hashlib
import os
import re
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

API_DIR = Path(__file__).resolve().parents[2]
_TEST_DB_RE = re.compile(r"^mindcare_test_[a-z0-9]+$")

PREV_REVISION = "d0ee44dc2527"
REVISION = "a3e7c1f9d5b2"
TABLES = (
    "test_campaigns", "campaign_responses",
    "campaign_response_scales", "campaign_response_answers",
)

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
    eng = _engine()
    try:
        with eng.begin() as c:
            result = c.execute(text(sql), params)
            return result.scalar() if result.returns_rows else None
    finally:
        eng.dispose()


def _table_exists(name: str) -> bool:
    return _scalar("SELECT to_regclass(:n) IS NOT NULL", n=f"public.{name}")


def _column_exists(table: str, column: str) -> bool:
    return bool(_scalar(
        "SELECT count(*) FROM information_schema.columns "
        "WHERE table_name = :t AND column_name = :c",
        t=table, c=column,
    ))


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


def _assert_upgraded() -> None:
    for t in TABLES:
        assert _table_exists(t), t
    assert _column_exists("tests", "scoring_profile")
    assert _column_exists("tests", "campaign_only")


def test_downgrade_and_upgrade_roundtrip(safe_test_db):
    _alembic("upgrade", REVISION)
    _assert_upgraded()
    _alembic("downgrade", PREV_REVISION)
    for t in TABLES:
        assert not _table_exists(t), t
    assert not _column_exists("tests", "scoring_profile")
    assert not _column_exists("tests", "campaign_only")
    _alembic("upgrade", REVISION)
    _assert_upgraded()


def test_downgrade_refuses_when_campaign_exists(safe_test_db):
    _alembic("upgrade", REVISION)
    test_id = _execute(
        "INSERT INTO tests (uuid, title) VALUES (:u, 'integ_mig_campaign') "
        "RETURNING id", u=str(uuid.uuid4()),
    )
    _execute(
        "INSERT INTO test_campaigns (uuid, test_id, title, link_token_hash, "
        "link_token_enc) VALUES (:u, :t, 'integ', :h, 'enc:v1:x')",
        u=str(uuid.uuid4()), t=test_id,
        h=hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
    )
    try:
        with pytest.raises(RuntimeError, match="test campaign"):
            _alembic("downgrade", PREV_REVISION)
        _assert_upgraded()  # отказ — до любых изменений
    finally:
        _execute("DELETE FROM test_campaigns WHERE test_id = :t", t=test_id)
        _execute("DELETE FROM tests WHERE id = :t", t=test_id)


def test_downgrade_refuses_when_test_flagged(safe_test_db):
    _alembic("upgrade", REVISION)
    test_id = _execute(
        "INSERT INTO tests (uuid, title, campaign_only) "
        "VALUES (:u, 'integ_mig_flag', true) RETURNING id", u=str(uuid.uuid4()),
    )
    try:
        with pytest.raises(RuntimeError, match="campaign_only"):
            _alembic("downgrade", PREV_REVISION)
        _assert_upgraded()
    finally:
        _execute("DELETE FROM tests WHERE id = :t", t=test_id)
