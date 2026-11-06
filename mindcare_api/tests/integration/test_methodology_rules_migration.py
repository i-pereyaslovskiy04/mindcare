"""
Round-trip migration test для b6d2e8f4a1c3 (ADR-037, правила методик как данные).

Гейтинг — как у test_test_campaigns_migration: SKIPPED без
MINDCARE_MIGRATION_ROUNDTRIP=1; при открытом gate — только на одноразовой
mindcare_test_<random>; после проверок БД возвращается на head.

  ENV=test MINDCARE_MIGRATION_ROUNDTRIP=1 TEST_DATABASE_URL=... \
      python scripts/isolated_test_db.py -k methodology_rules_migration -v
"""
import json
import os
import re
import uuid

import pytest

from tests.integration.test_test_campaigns_migration import (
    _alembic, _column_exists, _execute, _scalar,
)

_TEST_DB_RE = re.compile(r"^mindcare_test_[a-z0-9]+$")
PREV_REVISION = "a3e7c1f9d5b2"
REVISION = "b6d2e8f4a1c3"

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


def _upgraded() -> bool:
    return all(_column_exists("tests", c) for c in
               ("scoring_rules", "lineage_uuid", "superseded_at")) and \
        _column_exists("test_results", "rule_summary")


def test_roundtrip_and_ito_backfill(safe_test_db):
    _alembic("downgrade", PREV_REVISION)
    assert not _column_exists("tests", "scoring_rules")
    tid = _execute(
        "INSERT INTO tests (uuid, title, scoring_profile, campaign_only) "
        "VALUES (:u, 'integ_mig_ito', 'ito_sobchik', true) RETURNING id",
        u=str(uuid.uuid4()),
    )
    plain = _execute(
        "INSERT INTO tests (uuid, title) VALUES (:u, 'integ_mig_plain') RETURNING id",
        u=str(uuid.uuid4()),
    )
    try:
        _alembic("upgrade", REVISION)
        assert _upgraded()
        rules = _scalar("SELECT scoring_rules FROM tests WHERE id = :t", t=tid)
        rules = rules if isinstance(rules, dict) else json.loads(rules)
        from app.tests.profiles import ito_sobchik
        assert rules == ito_sobchik.scoring_rules()
        assert _scalar("SELECT scoring_rules IS NULL FROM tests WHERE id = :t", t=plain)
        assert _scalar("SELECT lineage_uuid = uuid FROM tests WHERE id = :t", t=plain)
        # CHECK снят: произвольная legacy-метка больше не ошибка схемы.
        _execute("UPDATE tests SET scoring_profile = 'x' WHERE id = :t", t=plain)
        _execute("UPDATE tests SET scoring_profile = NULL WHERE id = :t", t=plain)

        _alembic("downgrade", PREV_REVISION)
        assert not _column_exists("tests", "lineage_uuid")
        _alembic("upgrade", REVISION)
        assert _upgraded()
    finally:
        _execute("DELETE FROM tests WHERE id IN (:a, :b)", a=tid, b=plain)


@pytest.mark.parametrize("setup_sql, match", [
    ("UPDATE tests SET scoring_rules = '{\"version\": 1}'::jsonb WHERE id = :t",
     "scoring rules"),
    ("INSERT INTO tests (uuid, title, lineage_uuid) "
     "SELECT gen_random_uuid(), 'integ_mig_v2', lineage_uuid FROM tests WHERE id = :t",
     "version"),
])
def test_downgrade_refuses(safe_test_db, setup_sql, match):
    tid = _execute(
        "INSERT INTO tests (uuid, title, lineage_uuid) VALUES (:u, 'integ_mig_ref', :u) "
        "RETURNING id", u=str(uuid.uuid4()),
    )
    try:
        _execute(setup_sql, t=tid)
        with pytest.raises(RuntimeError, match=match):
            _alembic("downgrade", PREV_REVISION)
        assert _upgraded()   # отказ — до любых изменений
    finally:
        _execute("DELETE FROM tests WHERE title LIKE 'integ_mig_%'")
