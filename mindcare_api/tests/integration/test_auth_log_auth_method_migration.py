"""
Round-trip migration test для b8d2f6a3c9e4 (auth_log.auth_method, Stage Social Auth 3A).

ГЕЙТИНГ (не менять schema revision во время обычного full suite):
  - по умолчанию SKIPPED; запускается только при MINDCARE_MIGRATION_ROUNDTRIP=1;
  - при открытом gate любое нарушение безопасности — ОШИБКА, не skip:
      ENV=test, DATABASE_URL присутствует, current_database() ~ mindcare_test_<random>;
  - собственный engine для проверок; DDL — через Alembic (его engine);
  - ТОЧНЫЕ revision ID (не downgrade -1);
  - после проверок БД остаётся на head; одноразовую БД удалит Stage 1 runner.

Отдельный запуск:
  ENV=test MINDCARE_MIGRATION_ROUNDTRIP=1 TEST_DATABASE_URL=... \\
      python scripts/isolated_test_db.py -k auth_log_auth_method_migration -v

Probe-строки — синтетические (без ПДн), с уникальной меткой в user_agent и
ФИКСИРОВАННЫМИ датами внутри baseline-партиций 3a7c5e2b8f1d (2026-01..2028-12);
удаляются в finally. Far-future партиция создаётся тем же DDL, что
scripts/ensure_audit_partitions.py, и удаляется в finally.
"""
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

API_DIR = Path(__file__).resolve().parents[2]
_TEST_DB_RE = re.compile(r"^mindcare_test_[a-z0-9]+$")

PREV_REVISION = "c6e1a4f8b2d7"
REVISION = "b8d2f6a3c9e4"
CHECK_NAME = "ck_auth_log_auth_method"

PROBE_AT = datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)       # auth_log_2026_07
OTHER_AT = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)       # auth_log_2026_01
FUTURE_PARTITION = "auth_log_auth_method_roundtrip_future_probe"
FUTURE_FROM, FUTURE_TO = "2099-03-01", "2099-04-01"
FUTURE_AT = datetime(2099, 3, 15, 12, 0, 0, tzinfo=timezone.utc)

pytestmark = pytest.mark.skipif(
    os.environ.get("MINDCARE_MIGRATION_ROUNDTRIP") != "1",
    reason="round-trip migration disabled (set MINDCARE_MIGRATION_ROUNDTRIP=1)",
)


# ── helpers ──────────────────────────────────────────────────────────────────

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
            c.execute(text(sql), params)
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


def _column_exists(table: str) -> bool:
    return bool(_scalar(
        "SELECT count(*) FROM information_schema.columns "
        "WHERE table_name = :t AND column_name = 'auth_method'", t=table,
    ))


def _partitions() -> list:
    eng = _engine()
    try:
        with eng.connect() as c:
            return [r[0] for r in c.execute(text(
                "SELECT c.relname FROM pg_inherits i "
                "JOIN pg_class p ON p.oid = i.inhparent "
                "JOIN pg_class c ON c.oid = i.inhrelid "
                "JOIN pg_namespace n ON n.oid = p.relnamespace "
                "WHERE n.nspname = 'public' AND p.relname = 'auth_log' "
                "ORDER BY c.relname"
            ))]
    finally:
        eng.dispose()


def _has_check(table: str) -> bool:
    return bool(_scalar(
        "SELECT count(*) FROM pg_constraint con "
        "JOIN pg_class c ON c.oid = con.conrelid "
        "WHERE c.relname = :t AND con.conname = :n AND con.contype = 'c'",
        t=table, n=CHECK_NAME,
    ))


def _insert(marker, *, event, at=PROBE_AT, email="probe@example.invalid",
            reason=None, success=True, method=None):
    cols = "event, user_email, success, failure_reason, user_agent, created_at"
    vals = ":e, :m, :s, :r, :ua, :at"
    params = dict(e=event, m=email, s=success, r=reason, ua=marker, at=at)
    if method is not None:
        cols += ", auth_method"
        vals += ", :am"
        params["am"] = method
    _execute(f"INSERT INTO auth_log ({cols}) VALUES ({vals})", **params)


def _method(marker, event, reason=None, email_present=True):
    return _scalar(
        "SELECT auth_method FROM auth_log WHERE user_agent = :ua AND event = :e "
        "AND failure_reason IS NOT DISTINCT FROM :r "
        "AND (user_email IS NOT NULL) = :ep",
        ua=marker, e=event, r=reason, ep=email_present,
    )


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
    marker = f"roundtrip-auth-method-{uuid.uuid4().hex}"
    yield marker
    _alembic("upgrade", "head")
    _execute("DELETE FROM auth_log WHERE user_agent = :ua", ua=marker)
    _execute(f"DROP TABLE IF EXISTS public.{FUTURE_PARTITION}")


@pytest.fixture()
def downgradable(safe_test_db):
    """Downgrade fail-closed при social-строках. В общем прогоне их пишут
    OAuth-тесты (это несовместимый режим запуска, а не регрессия) — skip."""
    _alembic("upgrade", REVISION)
    if _scalar("SELECT count(*) FROM auth_log WHERE auth_method IN ('yandex', 'vk')"):
        pytest.skip(
            "round-trip requires a DB without social auth_log rows "
            "(run separately with -k auth_log_auth_method_migration)"
        )
    return safe_test_db


# ── tests ────────────────────────────────────────────────────────────────────

def test_upgrade_adds_column_and_check_to_every_partition(safe_test_db):
    _alembic("upgrade", REVISION)
    assert _column_exists("auth_log") and _has_check("auth_log")
    assert _scalar(
        "SELECT is_nullable || ':' || data_type || ':' || character_maximum_length "
        "FROM information_schema.columns "
        "WHERE table_name = 'auth_log' AND column_name = 'auth_method'"
    ) == "YES:character varying:20"
    partitions = _partitions()
    assert len(partitions) >= 36, partitions
    for partition in partitions:
        assert _column_exists(partition), partition
        assert _has_check(partition), partition
    assert not _scalar(
        "SELECT count(*) FROM pg_indexes WHERE tablename = 'auth_log' "
        "AND indexdef ILIKE '%auth_method%'"
    )


def test_check_enforced_in_selected_partitions(safe_test_db):
    _alembic("upgrade", REVISION)
    for at in (PROBE_AT, OTHER_AT):
        for method in ("password", "yandex", "vk"):
            _insert(safe_test_db, event="login", at=at, method=method)
        with pytest.raises(IntegrityError):
            _insert(safe_test_db, event="login", at=at, method="google")
        with pytest.raises(IntegrityError):
            _insert(safe_test_db, event="login", at=at, method="PASSWORD")


def test_future_partition_inherits_column_and_check(safe_test_db):
    _alembic("upgrade", REVISION)
    _execute(
        f"CREATE TABLE public.{FUTURE_PARTITION} PARTITION OF public.auth_log "
        f"FOR VALUES FROM ('{FUTURE_FROM}') TO ('{FUTURE_TO}')"
    )
    assert _column_exists(FUTURE_PARTITION) and _has_check(FUTURE_PARTITION)
    _insert(safe_test_db, event="login", at=FUTURE_AT, method="yandex")
    with pytest.raises(IntegrityError):
        _insert(safe_test_db, event="login", at=FUTURE_AT, method="totp")
    _execute("DELETE FROM auth_log WHERE user_agent = :ua", ua=safe_test_db)


def test_backfill_on_populated_db(downgradable):
    marker = downgradable
    _alembic("downgrade", PREV_REVISION)
    assert not _column_exists("auth_log")

    _insert(marker, event="login")
    _insert(marker, event="failed_login", success=False, reason="invalid_credentials")
    _insert(marker, event="failed_login", success=False,
            reason="Неверный email или пароль")                  # legacy free text
    _insert(marker, event="failed_login", success=False, reason="account_disabled")
    # OAuth-подобные (Stage 2B пишет failed_login без email) — неоднозначны:
    _insert(marker, event="failed_login", success=False, reason="account_disabled",
            email=None)
    _insert(marker, event="failed_login", success=False,
            reason="oauth_identity_unknown", email=None)
    _insert(marker, event="failed_login", success=False,
            reason="oauth_provider_error")                       # OAuth-код с email
    _insert(marker, event="failed_login", success=False,
            reason="social_login_not_allowed")
    _insert(marker, event="logout")
    _insert(marker, event="registration_succeeded")
    _insert(marker, event="password_reset")
    _insert(marker, event="register")                            # legacy-событие

    _alembic("upgrade", REVISION)

    assert _method(marker, "login") == "password"
    assert _method(marker, "failed_login", "invalid_credentials") == "password"
    assert _method(marker, "failed_login", "Неверный email или пароль") == "password"
    assert _method(marker, "failed_login", "account_disabled") == "password"
    assert _method(marker, "failed_login", "account_disabled", email_present=False) is None
    assert _method(marker, "failed_login", "oauth_identity_unknown",
                   email_present=False) is None
    assert _method(marker, "failed_login", "oauth_provider_error") is None
    assert _method(marker, "failed_login", "social_login_not_allowed") is None
    for event in ("logout", "registration_succeeded", "password_reset", "register"):
        assert _method(marker, event) is None, event
    assert not _scalar(
        "SELECT count(*) FROM auth_log WHERE user_agent = :ua "
        "AND auth_method IN ('yandex', 'vk')", ua=marker,
    )


def test_downgrade_without_social_rows_succeeds_and_upgrade_repeats(downgradable):
    _alembic("downgrade", PREV_REVISION)
    assert not _column_exists("auth_log") and not _has_check("auth_log")
    for partition in _partitions():
        assert not _column_exists(partition), partition
    assert _scalar("SELECT version_num FROM alembic_version") == PREV_REVISION

    _alembic("upgrade", REVISION)
    assert _column_exists("auth_log") and _has_check("auth_log")


def test_downgrade_refuses_with_social_rows(downgradable):
    marker = downgradable
    _insert(marker, event="login", method="yandex")
    try:
        with pytest.raises(RuntimeError, match="social auth_method"):
            _alembic("downgrade", PREV_REVISION)
        assert _scalar("SELECT version_num FROM alembic_version") == REVISION
        assert _column_exists("auth_log") and _has_check("auth_log")
        assert _scalar(
            "SELECT auth_method FROM auth_log WHERE user_agent = :ua", ua=marker,
        ) == "yandex"
    finally:
        _execute("DELETE FROM auth_log WHERE user_agent = :ua", ua=marker)
