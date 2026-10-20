"""
Harness safety unit-тесты для scripts/isolated_test_db.py (Stage 1).

ВСЕ тесты — БЕЗ подключения к реальной БД: create_engine / subprocess /
методы менеджера мокаются. Проверяют guard-логику, отсутствие утечки
credentials и корректный lifecycle до/после создания временной БД.
"""
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.engine import make_url

# scripts/ на путь → импорт runner-модуля (тот же, что грузит root conftest).
_SCRIPTS_DIR = Path(__file__).resolve().parents[0].parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import isolated_test_db as h  # noqa: E402


# ── Имена БД ──────────────────────────────────────────────────────────────────

def test_generated_name_matches_pattern():
    for _ in range(200):
        name = h.generate_test_db_name()
        assert h.TEST_DB_NAME_RE.match(name), name


@pytest.mark.parametrize("bad", [
    "postgres", "template0", "template1",
    "mindcare", "mindcare_dev", "mindcare_prod",
    "mindcare_production", "mindcare_staging",
])
def test_assert_safe_db_name_rejects_forbidden(bad):
    with pytest.raises(RuntimeError):
        h.assert_safe_db_name(bad)


@pytest.mark.parametrize("bad", [
    "foo", "mindcare_testX", "mindcare_test_", "mindcare_test_ABC",
    "mindcare_test_a-b", "", "public",
])
def test_assert_safe_db_name_rejects_non_pattern(bad):
    with pytest.raises(RuntimeError):
        h.assert_safe_db_name(bad)


def test_assert_safe_db_name_accepts_generated():
    h.assert_safe_db_name(h.generate_test_db_name())  # без исключения


# ── ENV / резолв ──────────────────────────────────────────────────────────────

def test_require_test_env(monkeypatch):
    monkeypatch.setenv("ENV", "development")
    with pytest.raises(RuntimeError):
        h.require_test_env()
    monkeypatch.setenv("ENV", "test")
    h.require_test_env()


def test_resolve_missing_raises_and_ignores_database_url(monkeypatch):
    # _RunnerSettings отдаёт None (пусто и в env, и в .env) → fail-fast.
    monkeypatch.setattr(
        h, "_RunnerSettings",
        lambda: SimpleNamespace(TEST_DATABASE_URL=None),
    )
    # DATABASE_URL присутствует, но НЕ должен использоваться как fallback.
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg2://u:p@h/mindcare")
    with pytest.raises(RuntimeError):
        h.resolve_test_url()


def test_resolve_from_env_file_only(monkeypatch):
    # TEST_DATABASE_URL «только в .env» (env пуст) — резолв всё равно работает.
    url = "postgresql+psycopg2://u:p@localhost:5432/postgres"
    monkeypatch.setattr(
        h, "_RunnerSettings",
        lambda: SimpleNamespace(TEST_DATABASE_URL=url),
    )
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    resolved = h.resolve_test_url()
    assert resolved.database == "postgres"


def test_env_file_path_is_absolute_and_cwd_independent(monkeypatch, tmp_path):
    assert h.ENV_FILE.is_absolute()
    assert h.ENV_FILE == h.API_DIR / ".env"
    assert h.API_DIR.name == "mindcare_api"
    before = h.ENV_FILE
    monkeypatch.chdir(tmp_path)
    assert h.ENV_FILE == before  # cwd не влияет


# ── Валидация source URL ──────────────────────────────────────────────────────

@pytest.mark.parametrize("src", [
    "mindcare", "mindcare_dev", "mindcare_prod", "foo", "template1",
])
def test_validate_source_url_rejects(src):
    url = make_url(f"postgresql+psycopg2://u:p@h:5432/{src}")
    with pytest.raises(RuntimeError):
        h.validate_source_url(url)


def test_validate_source_url_accepts_postgres():
    url = make_url("postgresql+psycopg2://u:p@h:5432/postgres")
    h.validate_source_url(url)  # без исключения


# ── Credentials не утекают ────────────────────────────────────────────────────

def test_password_never_rendered_plain():
    url = h.child_url_for(
        make_url("postgresql+psycopg2://u:SECR%40T:p@h:5432/postgres"),
        "mindcare_test_abc123",
    )
    safe = url.render_as_string(hide_password=True)
    assert "SECR" not in safe and "***" in safe


def test_child_env_url_is_str_with_password():
    mgr = h.IsolatedTestDB(
        admin_url=make_url("postgresql+psycopg2://u:pw@h/postgres"),
        db_name="mindcare_test_abc123",
    )
    mgr.db_url = make_url("postgresql+psycopg2://u:pw123@h/mindcare_test_abc123")
    child = mgr.child_env_url()
    assert isinstance(child, str)
    assert "pw123" in child  # реальный пароль — только для env дочернего процесса


# ── resolve_pytest_database_url (логика root conftest) ────────────────────────

def test_unit_only_forces_sentinel_even_with_test_url():
    env = {
        "MINDCARE_UNIT_ONLY": "1",
        "TEST_DATABASE_URL": "postgresql://x@h/mindcare_test_abc",
        "ENV": "test",
    }
    assert h.resolve_pytest_database_url(env) == h.SENTINEL_DATABASE_URL


def test_unit_only_never_uses_admin_url():
    out = h.resolve_pytest_database_url({"MINDCARE_UNIT_ONLY": "1"})
    assert out == h.SENTINEL_DATABASE_URL
    assert make_url(out).database == "mindcare_unit_sentinel"


def test_test_url_requires_env_test():
    env = {"TEST_DATABASE_URL": "postgresql://x@h/mindcare_test_abc"}
    with pytest.raises(RuntimeError):
        h.resolve_pytest_database_url(env)  # ENV != test


def test_test_url_passthrough_when_env_test():
    url = "postgresql://x@h/mindcare_test_abc"
    env = {"TEST_DATABASE_URL": url, "ENV": "test"}
    assert h.resolve_pytest_database_url(env) == url


def test_no_test_url_defaults_to_sentinel():
    assert h.resolve_pytest_database_url({}) == h.SENTINEL_DATABASE_URL


# ── resolve_pytest_database_url: строгая проверка имени БД ────────────────────

def test_resolve_pytest_url_rejects_admin_postgres():
    secret = "ADMINpw_SECRET"
    env = {
        "TEST_DATABASE_URL": f"postgresql+psycopg2://u:{secret}@h/postgres",
        "ENV": "test",
    }
    with pytest.raises(RuntimeError) as ei:
        h.resolve_pytest_database_url(env)
    assert secret not in str(ei.value)  # пароль не утекает


def test_resolve_pytest_url_rejects_dev_mindcare():
    env = {
        "TEST_DATABASE_URL": "postgresql+psycopg2://u:p@h/mindcare",
        "ENV": "test",
    }
    with pytest.raises(RuntimeError):
        h.resolve_pytest_database_url(env)


def test_resolve_pytest_url_rejects_arbitrary_name():
    env = {
        "TEST_DATABASE_URL": "postgresql+psycopg2://u:p@h/some_other_db",
        "ENV": "test",
    }
    with pytest.raises(RuntimeError):
        h.resolve_pytest_database_url(env)


def test_resolve_pytest_url_rejects_missing_db_name():
    env = {"TEST_DATABASE_URL": "postgresql+psycopg2://u:p@h:5432", "ENV": "test"}
    with pytest.raises(RuntimeError):
        h.resolve_pytest_database_url(env)


def test_resolve_pytest_url_accepts_generated():
    name = h.generate_test_db_name()
    env = {
        "TEST_DATABASE_URL": f"postgresql+psycopg2://u:p@h:5432/{name}",
        "ENV": "test",
    }
    assert h.resolve_pytest_database_url(env).endswith(name)


def test_resolve_pytest_url_malformed_hides_password():
    secret = "SUPERSECRETpw"
    env = {"TEST_DATABASE_URL": f"::: {secret} garbage", "ENV": "test"}
    with pytest.raises(RuntimeError) as ei:
        h.resolve_pytest_database_url(env)
    assert secret not in str(ei.value)


# ── drivername allowlist (только psycopg2 PostgreSQL) ────────────────────────

@pytest.mark.parametrize("url", [
    "sqlite:///mindcare_test_abc",
    "mysql://u:p@h:3306/mindcare_test_abc",
    "postgresql+asyncpg://u:p@h:5432/mindcare_test_abc",
])
def test_resolve_pytest_url_rejects_bad_driver(url):
    with pytest.raises(RuntimeError):
        h.resolve_pytest_database_url({"TEST_DATABASE_URL": url, "ENV": "test"})


@pytest.mark.parametrize("scheme", ["postgresql", "postgresql+psycopg2"])
def test_resolve_pytest_url_accepts_allowed_drivers(scheme):
    name = h.generate_test_db_name()
    url = f"{scheme}://u:p@h:5432/{name}"
    assert h.resolve_pytest_database_url(
        {"TEST_DATABASE_URL": url, "ENV": "test"}
    ) == url


def test_resolve_pytest_url_bad_driver_hides_password():
    secret = "DRIVER_SECRETpw"
    url = f"postgresql+asyncpg://u:{secret}@h:5432/mindcare_test_abc"
    with pytest.raises(RuntimeError) as ei:
        h.resolve_pytest_database_url({"TEST_DATABASE_URL": url, "ENV": "test"})
    assert secret not in str(ei.value)


def test_validate_source_url_rejects_bad_driver():
    url = make_url("postgresql+asyncpg://u:p@h:5432/postgres")
    with pytest.raises(RuntimeError):
        h.validate_source_url(url)


# ── _build_child_env: безопасное детерминированное окружение ──────────────────

def test_build_child_env_safe_and_no_unit_only(monkeypatch):
    monkeypatch.setenv("MINDCARE_UNIT_ONLY", "1")
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("EMAIL_MODE", "smtp")
    child = "postgresql+psycopg2://u:pw@h/mindcare_test_deadbeef"
    env = h._build_child_env(child)
    assert "MINDCARE_UNIT_ONLY" not in env      # не наследуется в полном режиме
    assert env["ENV"] == "test"
    assert env["DEBUG"] == "false"
    assert env["EMAIL_MODE"] == "dev"
    assert env["DATABASE_URL"] == child
    assert env["TEST_DATABASE_URL"] == child
    # синтетический DATA_ENCRYPTION_KEY валиден для Fernet.
    from cryptography.fernet import Fernet
    Fernet(env["DATA_ENCRYPTION_KEY"].encode())


# ── drop(): порядок и guard ───────────────────────────────────────────────────

def test_drop_skips_when_not_created():
    mgr = h.IsolatedTestDB(
        admin_url=make_url("postgresql://u:p@h/postgres"),
        db_name="mindcare_test_abc123",
    )
    mgr.created = False
    mgr._admin = MagicMock()
    mgr._dispose_verify = MagicMock()
    mgr.drop()
    mgr._admin.assert_not_called()
    mgr._dispose_verify.assert_not_called()


def test_drop_disposes_verify_before_terminate_and_drop():
    mgr = h.IsolatedTestDB(
        admin_url=make_url("postgresql://u:p@h/postgres"),
        db_name="mindcare_test_abc123",
    )
    mgr.created = True
    parent = MagicMock()
    mgr._dispose_verify = parent.dispose_verify
    admin_engine = MagicMock(name="admin_engine")
    parent.attach_mock(admin_engine, "admin_engine")
    mgr._admin_engine = admin_engine
    mgr.drop()
    seq = [c[0] for c in parent.mock_calls]
    connect_calls = [i for i, n in enumerate(seq) if n == "admin_engine.connect"]
    disposes = [i for i, n in enumerate(seq) if n == "dispose_verify"]
    assert disposes and connect_calls
    assert disposes[0] < connect_calls[0]  # verify disposed до DROP


# ── main(): lifecycle через моки ──────────────────────────────────────────────

def _patch_main_happy(monkeypatch, alembic_rc=0, pytest_rc=0):
    """Возвращает (parent, mgr_mock). CREATE/DROP через моки, без БД."""
    parent = MagicMock()
    mgr = parent.mgr
    mgr.db_name = "mindcare_test_deadbeef"
    mgr.created = True
    mgr.child_env_url.return_value = (
        "postgresql+psycopg2://u:pw@h/mindcare_test_deadbeef"
    )
    monkeypatch.setattr(h, "resolve_test_url",
                        lambda: make_url("postgresql://u:p@h/postgres"))
    monkeypatch.setattr(h, "validate_source_url", lambda url: None)
    monkeypatch.setattr(h, "admin_url_for", lambda url: url)
    monkeypatch.setattr(h, "child_url_for", lambda url, n: url)
    monkeypatch.setattr(h, "generate_test_db_name",
                        lambda: "mindcare_test_deadbeef")
    monkeypatch.setattr(h, "IsolatedTestDB", lambda **kw: mgr)
    monkeypatch.setattr(h, "_run_alembic", parent.alembic)
    monkeypatch.setattr(h, "_run_pytest", parent.pytest)
    parent.alembic.return_value = alembic_rc
    parent.pytest.return_value = pytest_rc
    return parent, mgr


def test_main_verify_runs_before_alembic(monkeypatch):
    parent, mgr = _patch_main_happy(monkeypatch)
    h.main([])
    names = [c[0] for c in parent.mock_calls]
    assert names.index("mgr.verify") < names.index("alembic")


def test_main_child_env_has_env_test_and_str_database_url(monkeypatch):
    parent, mgr = _patch_main_happy(monkeypatch)
    h.main([])
    env = parent.alembic.call_args.args[0]
    assert env["ENV"] == "test"
    assert isinstance(env["DATABASE_URL"], str)
    assert env["DATABASE_URL"] == mgr.child_env_url.return_value


def test_main_alembic_failure_skips_pytest_and_drops(monkeypatch):
    parent, mgr = _patch_main_happy(monkeypatch, alembic_rc=3)
    rc = h.main([])
    assert rc != 0
    parent.pytest.assert_not_called()
    mgr.drop.assert_called_once()


def test_main_preserves_pytest_returncode(monkeypatch):
    parent, mgr = _patch_main_happy(monkeypatch, pytest_rc=5)
    assert h.main([]) == 5


def test_main_cleanup_error_forces_nonzero(monkeypatch):
    parent, mgr = _patch_main_happy(monkeypatch, pytest_rc=0)
    mgr.drop.side_effect = RuntimeError("boom")
    rc = h.main([])
    assert rc != 0
    mgr.dispose_engines.assert_called_once()


def test_main_invalid_url_with_secret_is_safe(monkeypatch, capsys):
    secret = "SECRET_xyz987"
    monkeypatch.setattr(
        h, "_RunnerSettings",
        lambda: SimpleNamespace(TEST_DATABASE_URL=f"not-a-url {secret}"),
    )
    # create_engine не должен вызываться (до preflight не доходим).
    ce = MagicMock(side_effect=AssertionError("create_engine must not run"))
    monkeypatch.setattr(h, "create_engine", ce)
    rc = h.main([])
    out = capsys.readouterr()
    assert rc != 0
    assert secret not in out.out and secret not in out.err
    assert "not-a-url" not in out.out and "not-a-url" not in out.err
    ce.assert_not_called()


def test_main_missing_test_url_fails_not_skips(monkeypatch, capsys):
    monkeypatch.setattr(
        h, "_RunnerSettings",
        lambda: SimpleNamespace(TEST_DATABASE_URL=None),
    )
    ce = MagicMock(side_effect=AssertionError("create_engine must not run"))
    monkeypatch.setattr(h, "create_engine", ce)
    assert h.main([]) != 0
    ce.assert_not_called()
