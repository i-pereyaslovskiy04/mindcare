"""
Round-trip migration test для c2a5f7d9e3b1 (сроки и кодовое слово кампании).

Гейтинг — как у test_test_campaigns_migration: SKIPPED без
MINDCARE_MIGRATION_ROUNDTRIP=1; при открытом gate — только на одноразовой
mindcare_test_<random>; после проверок БД возвращается на head.

  ENV=test MINDCARE_MIGRATION_ROUNDTRIP=1 TEST_DATABASE_URL=... \
      python scripts/isolated_test_db.py -k campaign_schedule_code_migration -v
"""
import os
import re
import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from tests.integration.test_test_campaigns_migration import (
    _alembic, _column_exists, _execute, _scalar,
)

_TEST_DB_RE = re.compile(r"^mindcare_test_[a-z0-9]+$")
PREV_REVISION = "b6d2e8f4a1c3"
REVISION = "c2a5f7d9e3b1"
HASH = "$2b$12$" + "a" * 53

pytestmark = pytest.mark.skipif(
    os.environ.get("MINDCARE_MIGRATION_ROUNDTRIP") != "1",
    reason="round-trip migration disabled (set MINDCARE_MIGRATION_ROUNDTRIP=1)",
)


@pytest.fixture()
def safe_test_db():
    if os.environ.get("ENV") != "test":
        raise RuntimeError("roundtrip: ENV must be 'test'.")
    current = _scalar("SELECT current_database()")
    if not (current and _TEST_DB_RE.match(current)):
        raise RuntimeError("roundtrip: current_database() must be mindcare_test_<random>.")
    _alembic("upgrade", REVISION)
    yield
    _alembic("upgrade", "head")


def _campaign() -> tuple[int, int]:
    u = str(uuid.uuid4())
    test_id = _execute("INSERT INTO tests (uuid, lineage_uuid, title) "
                       "VALUES (:u, :u, 'integ_mig_sched') RETURNING id", u=u)
    cid = _execute(
        "INSERT INTO test_campaigns (uuid, test_id, title, link_token_hash, link_token_enc) "
        "VALUES (:u, :t, 'integ', :h, 'enc:v1:x') RETURNING id",
        u=str(uuid.uuid4()), t=test_id, h=uuid.uuid4().hex + uuid.uuid4().hex)
    return test_id, cid


def test_roundtrip_checks_and_fail_closed_downgrade(safe_test_db):
    _alembic("downgrade", PREV_REVISION)
    assert not _column_exists("test_campaigns", "access_code_hash")
    test_id, cid = _campaign()
    try:
        _alembic("upgrade", REVISION)
        for col in ("opens_at", "closes_at", "access_code_hash"):
            assert _column_exists("test_campaigns", col)
        assert _scalar("SELECT opens_at IS NULL AND access_code_hash IS NULL "
                       "FROM test_campaigns WHERE id = :c", c=cid)
        with pytest.raises(IntegrityError):
            _execute("UPDATE test_campaigns SET opens_at = now(), closes_at = now() "
                     "WHERE id = :c", c=cid)
        with pytest.raises(IntegrityError):
            _execute("UPDATE test_campaigns SET access_code_hash = 'plain' WHERE id = :c", c=cid)
        _execute("UPDATE test_campaigns SET access_code_hash = :h WHERE id = :c", h=HASH, c=cid)

        with pytest.raises(Exception):
            _alembic("downgrade", PREV_REVISION)          # fail-closed: задано слово
        assert _column_exists("test_campaigns", "access_code_hash")

        _execute("UPDATE test_campaigns SET access_code_hash = NULL WHERE id = :c", c=cid)
        _alembic("downgrade", PREV_REVISION)
        assert not _column_exists("test_campaigns", "opens_at")
        _alembic("upgrade", REVISION)
    finally:
        _execute("DELETE FROM test_campaigns WHERE id = :c", c=cid)
        _execute("DELETE FROM tests WHERE id = :t", t=test_id)
