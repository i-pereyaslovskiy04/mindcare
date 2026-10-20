"""
Unit-тесты scripts/anonymize_old_ips.py (Stage 7B) — БЕЗ подключения к БД.

Engine и connection подменяются фейками, поэтому проверяется именно control
flow скрипта: порядок preflight относительно рабочей функции, выбор функции по
режиму, минимизация диагностики и освобождение ресурсов.

Отдельно проверяется drift между runtime-контрактом скрипта и миграцией
`c8e2b5f7a3d1`: скрипт намеренно НЕ импортирует модуль ревизии (тот тянет
alembic и не предназначен для продакшн-импорта), поэтому сигнатуры, список
журналов и advisory-ключ обязаны сверяться тестом.

Покрытие: T20, T21, T25, T43, T44, T46, T47.
"""
import ast
import importlib.util
import logging
import sys
from pathlib import Path

import pytest

_API_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS_DIR = _API_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import anonymize_old_ips as cli  # noqa: E402

MIGRATION_PATH = (
    _API_ROOT / "alembic" / "versions" / "c8e2b5f7a3d1_adopt_ip_anonymization.py"
)
PARTITIONS_SCRIPT = _SCRIPTS_DIR / "ensure_audit_partitions.py"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ── Статический разбор скрипта ───────────────────────────────────────────────
# Проверки идут по AST, а не подстрочным поиском: docstring'и и комментарии в
# этом скрипте подробно ОБСУЖДАЮТ запреты («не логировать str(exc)», «ни
# SessionLocal, ни app.main»), и текстовый поиск срабатывал бы именно на них.

def _cli_ast() -> ast.Module:
    return ast.parse(
        (_SCRIPTS_DIR / "anonymize_old_ips.py").read_text(encoding="utf-8")
    )


def _docstring_ids(tree: ast.Module) -> set:
    """id() строковых констант, которые являются docstring'ами."""
    out = set()
    holders = (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    for node in ast.walk(tree):
        if not isinstance(node, holders):
            continue
        body = getattr(node, "body", None)
        if (body and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            out.add(id(body[0].value))
    return out


def _cli_sql() -> str:
    """Все строковые литералы кода, КРОМЕ docstring'ов, склеенные в одну строку.

    Комментарии в AST не попадают вовсе, поэтому кириллические пояснения
    проверкам не мешают.
    """
    tree = _cli_ast()
    skip = _docstring_ids(tree)
    parts = [
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in skip
    ]
    return "\n".join(parts)


# ── Фейковые engine/connection ───────────────────────────────────────────────

class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


class _FakeConn:
    """Записывает выполненный SQL и отвечает по подставной таблице ответов."""

    def __init__(self, answers):
        self.statements = []
        self._answers = answers

    def execute(self, statement, params=None):
        sql = str(statement)
        self.statements.append(sql)
        value = self._answers(sql)
        if isinstance(value, Exception):
            raise value
        return _FakeResult(value)


class _FakeTx:
    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self._conn

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeEngine:
    def __init__(self, conn):
        self.conn = conn
        self.disposed = 0
        self.begin_calls = 0

    def begin(self):
        self.begin_calls += 1
        return _FakeTx(self.conn)

    def dispose(self):
        self.disposed += 1


def _classify(sql: str) -> str:
    """Грубая классификация запроса по характерному фрагменту."""
    if "to_regprocedure" in sql:
        return "exists"
    if "has_function_privilege" in sql:
        return "function_privilege"
    if "has_column_privilege" in sql:
        return "table_privilege"
    if "anonymize_old_ips" in sql:
        return "anonymize"
    if "count_old_ips" in sql:
        return "count"
    return "other"


def _answers(*, exists=True, func_priv=True, table_priv=True, result=7):
    def answer(sql):
        kind = _classify(sql)
        if kind == "exists":
            return exists
        if kind == "function_privilege":
            return func_priv
        if kind == "table_privilege":
            return table_priv
        if kind in ("anonymize", "count"):
            return result
        raise AssertionError(f"unexpected statement: {sql[:60]}")
    return answer


@pytest.fixture()
def engine_factory(monkeypatch):
    """Подменяет create_engine_for и database_url — реальная БД не нужна."""
    created = {}

    def make(answers):
        conn = _FakeConn(answers)
        engine = _FakeEngine(conn)
        created["engine"] = engine
        created["conn"] = conn
        monkeypatch.setattr(cli, "database_url", lambda: "postgresql://unused")
        monkeypatch.setattr(cli, "create_engine_for", lambda url: engine)
        return engine, conn

    make.created = created
    return make


def _kinds(conn) -> list:
    return [_classify(sql) for sql in conn.statements]


# ── T43 / T46: порядок и выбор рабочей функции ───────────────────────────────

def test_work_function_runs_only_after_all_three_preflights(engine_factory):
    """T43 — рабочая функция вызывается ПОСЛЕ всех трёх проверок, не раньше."""
    engine, conn = engine_factory(_answers(result=5))

    assert cli.main(["--days", "90"]) == 0

    assert _kinds(conn) == [
        "exists", "function_privilege", "table_privilege", "anonymize"
    ]
    # Единственная transaction boundary: отдельного conn.begin() нет.
    assert engine.begin_calls == 1


def test_dry_run_calls_only_count_function(engine_factory):
    """T46 — dry-run вызывает count_old_ips и НИКОГДА не anonymize_old_ips."""
    engine, conn = engine_factory(_answers(result=3))

    assert cli.main(["--days", "90", "--dry-run"]) == 0

    kinds = _kinds(conn)
    assert kinds[-1] == "count"
    assert "anonymize" not in kinds


def test_dry_run_does_not_require_update_privilege(engine_factory):
    """dry-run не должен требовать UPDATE: параметр live уходит False."""
    engine, conn = engine_factory(_answers())

    cli.main(["--days", "90", "--dry-run"])

    # Проверка прав выполняется, но с live=False — сам SQL один и тот же,
    # разницу задаёт связанный параметр, поэтому проверяем вызов напрямую.
    calls = []

    class _Recorder:
        def execute(self, statement, params=None):
            calls.append(params)
            return _FakeResult(True)

    cli.preflight_table_privileges(_Recorder(), live=False)
    assert calls[-1]["live"] is False

    calls.clear()
    cli.preflight_table_privileges(_Recorder(), live=True)
    assert calls[-1]["live"] is True


# ── T44: отказ любой фазы preflight не пускает к рабочей функции ─────────────

@pytest.mark.parametrize("kwargs, expected_phase", [
    ({"exists": False}, cli.PHASE_MISSING_FUNCTION),
    ({"func_priv": False}, cli.PHASE_INSUFFICIENT_FUNCTION_PRIVILEGE),
    ({"table_priv": False}, cli.PHASE_INSUFFICIENT_TABLE_PRIVILEGE),
])
def test_preflight_failure_blocks_work_function(engine_factory, caplog,
                                                kwargs, expected_phase):
    """T44 — при отказе любой фазы ни count, ни anonymize не вызываются."""
    engine, conn = engine_factory(_answers(**kwargs))

    with caplog.at_level(logging.ERROR, logger="anonymize_old_ips"):
        assert cli.main(["--days", "90"]) == 1

    kinds = _kinds(conn)
    assert "anonymize" not in kinds
    assert "count" not in kinds
    assert f"phase={expected_phase}" in caplog.text


def test_preflight_phases_are_distinct_and_stable():
    """Фазы не совпадают между собой — оператор различает причины по phase."""
    assert len(set(cli.PREFLIGHT_PHASES)) == 3
    assert cli.PHASE_MISSING_FUNCTION != cli.PHASE_INSUFFICIENT_FUNCTION_PRIVILEGE
    assert (cli.PHASE_INSUFFICIENT_FUNCTION_PRIVILEGE
            != cli.PHASE_INSUFFICIENT_TABLE_PRIVILEGE)


def test_function_existence_is_checked_before_privileges(engine_factory):
    """has_function_privilege() на несуществующей функции бросает исключение,
    поэтому проверка существования обязана идти первой."""
    engine, conn = engine_factory(_answers(exists=False))

    cli.main(["--days", "90"])

    assert _kinds(conn) == ["exists"]


# ── T21: невалидный --days отсекается ДО подключения ─────────────────────────

@pytest.mark.parametrize("days", ["0", "-1", "-90"])
def test_invalid_days_rejected_before_connecting(monkeypatch, caplog, days):
    """T21 — при days < 1 ни database_url(), ни create_engine_for() не зовутся."""
    touched = []
    monkeypatch.setattr(
        cli, "database_url", lambda: touched.append("url") or "postgresql://x"
    )
    monkeypatch.setattr(
        cli, "create_engine_for",
        lambda url: touched.append("engine") or _FakeEngine(None),
    )

    with caplog.at_level(logging.ERROR, logger="anonymize_old_ips"):
        assert cli.main(["--days", days]) == 1

    assert touched == []
    assert f"phase={cli.PHASE_CONFIG}" in caplog.text


def test_valid_days_boundary_is_accepted(engine_factory):
    """Граница ретенции >= 1: единица допустима."""
    engine, conn = engine_factory(_answers(result=0))

    assert cli.main(["--days", "1"]) == 0
    assert _kinds(conn)[-1] == "anonymize"


def test_default_days_is_90():
    assert cli.parse_args([]).days == cli.DEFAULT_DAYS == 90
    assert cli.parse_args([]).dry_run is False


# ── T20: минимизация диагностики ─────────────────────────────────────────────

def test_work_failure_logs_only_phase_and_exception_class(engine_factory, caplog):
    """T20 — в лог уходят фаза и класс исключения, без str(exc)."""
    secret = "duplicate key value violates unique constraint 203.0.113.7"

    engine, conn = engine_factory(_answers(result=RuntimeError(secret)))

    with caplog.at_level(logging.ERROR, logger="anonymize_old_ips"):
        assert cli.main(["--days", "90"]) == 1

    assert f"phase={cli.PHASE_ANONYMIZE}" in caplog.text
    assert "error=RuntimeError" in caplog.text
    assert secret not in caplog.text
    assert "203.0.113.7" not in caplog.text


def test_dry_run_failure_reports_count_phase(engine_factory, caplog):
    engine, conn = engine_factory(_answers(result=RuntimeError("boom")))

    with caplog.at_level(logging.ERROR, logger="anonymize_old_ips"):
        assert cli.main(["--days", "90", "--dry-run"]) == 1

    assert f"phase={cli.PHASE_COUNT}" in caplog.text
    assert "boom" not in caplog.text


def test_phase_error_message_carries_only_phase():
    """Сообщение PhaseError — только имя фазы: оно попадает в traceback."""
    exc = cli.PhaseError(cli.PHASE_ANONYMIZE, "ProgrammingError")
    assert str(exc) == cli.PHASE_ANONYMIZE
    assert exc.error_name == "ProgrammingError"


def test_database_url_is_never_logged(engine_factory, caplog):
    """DATABASE_URL не пишется в лог вообще — даже маскированным."""
    engine, conn = engine_factory(_answers(result=1))

    with caplog.at_level(logging.DEBUG, logger="anonymize_old_ips"):
        cli.main(["--days", "90"])

    assert "postgresql" not in caplog.text
    assert "DATABASE_URL" not in caplog.text


def test_source_has_no_url_masking_helper():
    """Скрипт не логирует URL, поэтому и маскирующего хелпера в нём быть не должно."""
    tree = _cli_ast()
    names = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    assert "_mask_db_url" not in names


def test_no_str_exc_anywhere_in_code():
    """`str(exc)` не должен попадать в диагностику ни в одном виде.

    Проверка по AST, а не по тексту: docstring'и и комментарии обсуждают запрет
    словами, и подстрочный поиск ловил бы именно их.
    """
    tree = _cli_ast()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "str"):
            arg = node.args[0] if node.args else None
            if isinstance(arg, ast.Name) and arg.id in {"exc", "e", "error", "err"}:
                pytest.fail(f"str({arg.id}) at line {node.lineno}")


# ── T47: освобождение ресурсов ───────────────────────────────────────────────

def test_engine_disposed_on_success(engine_factory):
    engine, conn = engine_factory(_answers(result=0))

    assert cli.main(["--days", "90"]) == 0
    assert engine.disposed == 1


@pytest.mark.parametrize("kwargs", [
    {"exists": False},
    {"func_priv": False},
    {"table_priv": False},
    {"result": RuntimeError("x")},
])
def test_engine_disposed_on_failure(engine_factory, kwargs):
    """T47 — dispose() вызывается при отказе на любой фазе."""
    engine, conn = engine_factory(_answers(**kwargs))

    assert cli.main(["--days", "90"]) == 1
    assert engine.disposed == 1


def test_engine_not_created_means_nothing_to_dispose(monkeypatch):
    """Сбой до создания engine не должен приводить к обращению к нему."""
    monkeypatch.setattr(
        cli, "database_url",
        lambda: (_ for _ in ()).throw(RuntimeError("no settings")),
    )
    monkeypatch.setattr(
        cli, "create_engine_for",
        lambda url: pytest.fail("engine must not be created"),
    )

    assert cli.main(["--days", "90"]) == 1


# ── Corrective pass: _setup_logging внутри safety-границы main() ────────────

def test_logging_setup_failure_returns_one_and_touches_neither_db_nor_engine(
    monkeypatch, capsys
):
    """`_setup_logging` — часть safety-границы: её сбой не должен приводить к
    неперехваченному traceback и не должен идти дальше к БД/engine.

    В момент сбоя логгера ещё нет, поэтому диагностика уходит в stderr тем же
    форматом, что и обычная лог-строка `[error] phase=... error=...`.
    """
    secret_payload = "S3cr3t-connection-string-marker"
    calls = []

    def boom(log_dir):
        raise RuntimeError(secret_payload)

    monkeypatch.setattr(cli, "_setup_logging", boom)
    monkeypatch.setattr(
        cli, "database_url", lambda: calls.append("database_url") or "x"
    )
    monkeypatch.setattr(
        cli, "create_engine_for",
        lambda url: calls.append("create_engine_for") or _FakeEngine(None),
    )

    assert cli.main(["--days", "90"]) == 1

    assert calls == [], "database_url/create_engine_for must not run"

    out, err = capsys.readouterr()
    assert f"phase={cli.PHASE_CONFIG}" in err
    assert "error=RuntimeError" in err
    assert secret_payload not in err
    assert secret_payload not in out
    assert "Traceback" not in err
    assert "anonymize_old_ips.py" not in err   # no frame/file path leaked


def test_logging_setup_failure_does_not_dispose_nonexistent_engine(monkeypatch):
    """engine остаётся None -> `finally` не обращается к нему вовсе."""
    monkeypatch.setattr(
        cli, "_setup_logging",
        lambda log_dir: (_ for _ in ()).throw(OSError("disk full")),
    )
    # Если бы код всё же дошёл до create_engine_for, эта заглушка бросила бы
    # AttributeError на .dispose() — тест ловит именно такой регресс.
    monkeypatch.setattr(cli, "create_engine_for", lambda url: object())

    assert cli.main(["--days", "90"]) == 1


def test_create_engine_failure_reports_connect_phase(monkeypatch, caplog):
    """create_engine_for() падает ДО begin() -> phase=connect."""
    monkeypatch.setattr(cli, "database_url", lambda: "postgresql://unused")
    monkeypatch.setattr(
        cli, "create_engine_for",
        lambda url: (_ for _ in ()).throw(RuntimeError("driver init failed")),
    )

    with caplog.at_level(logging.ERROR, logger="anonymize_old_ips"):
        assert cli.main(["--days", "90"]) == 1

    assert f"phase={cli.PHASE_CONNECT}" in caplog.text
    assert "error=RuntimeError" in caplog.text
    assert "driver init failed" not in caplog.text


class _FailingBeginEngine:
    """engine.begin() падает: это НЕ preflight, а сам вход в транзакцию."""

    def __init__(self, exc):
        self._exc = exc
        self.disposed = 0

    def begin(self):
        raise self._exc

    def dispose(self):
        self.disposed += 1


def test_engine_begin_failure_reports_connect_phase(monkeypatch, caplog):
    """Сбой самого `engine.begin()` (не SQL внутри транзакции) -> phase=connect,
    а НЕ одна из preflight-фаз — до входа в транзакцию preflight не начинался."""
    monkeypatch.setattr(cli, "database_url", lambda: "postgresql://unused")
    engine = _FailingBeginEngine(RuntimeError("could not connect to server"))
    monkeypatch.setattr(cli, "create_engine_for", lambda url: engine)

    with caplog.at_level(logging.ERROR, logger="anonymize_old_ips"):
        assert cli.main(["--days", "90"]) == 1

    assert f"phase={cli.PHASE_CONNECT}" in caplog.text
    assert "could not connect to server" not in caplog.text
    # engine БЫЛ создан -> dispose() обязан быть вызван, несмотря на сбой begin().
    assert engine.disposed == 1


# ── Corrective pass: сбой самого conn.execute() внутри preflight ────────────

@pytest.mark.parametrize("kwargs, expected_phase", [
    ({"exists": RuntimeError("db unreachable")}, cli.PHASE_MISSING_FUNCTION),
    (
        {"func_priv": RuntimeError("db unreachable")},
        cli.PHASE_INSUFFICIENT_FUNCTION_PRIVILEGE,
    ),
    (
        {"table_priv": RuntimeError("db unreachable")},
        cli.PHASE_INSUFFICIENT_TABLE_PRIVILEGE,
    ),
])
def test_preflight_sql_failure_maps_to_its_own_phase(
    engine_factory, caplog, kwargs, expected_phase
):
    """Сбой `conn.execute()` ВНУТРИ preflight переупаковывается в фазу ЭТОЙ
    проверки — не путается с явным отрицательным результатом (False) и не
    ускользает в общий `except Exception` в main() с фазой config/connect."""
    engine, conn = engine_factory(_answers(**kwargs))

    with caplog.at_level(logging.ERROR, logger="anonymize_old_ips"):
        assert cli.main(["--days", "90"]) == 1

    assert f"phase={expected_phase}" in caplog.text
    assert "error=RuntimeError" in caplog.text
    assert "db unreachable" not in caplog.text

    kinds = _kinds(conn)
    assert "anonymize" not in kinds
    assert "count" not in kinds
    assert engine.disposed == 1


def test_explicit_false_and_raised_exception_report_the_same_phase():
    """Явный отрицательный результат (False) и брошенное исключение внутри той
    же preflight-фазы дают ОДИН phase — оператор не обязан различать их."""
    for kwargs in ({"func_priv": False}, {"func_priv": RuntimeError("x")}):
        conn = _FakeConn(_answers(**kwargs))
        with pytest.raises(cli.PhaseError) as excinfo:
            cli.preflight_function_privileges(conn)
        assert excinfo.value.phase == cli.PHASE_INSUFFICIENT_FUNCTION_PRIVILEGE


# ── Corrective pass: schema-qualified table-preflight ────────────────────────

def test_table_privilege_params_are_schema_qualified():
    """`has_column_privilege()` получает `public.<table>`, а не голое имя —
    иначе резолв таблицы зависел бы от `search_path` вызывающей роли."""
    calls = []

    class _Recorder:
        def execute(self, statement, params=None):
            calls.append(params)
            return _FakeResult(True)

    cli.preflight_table_privileges(_Recorder(), live=True)

    tables = calls[-1]["tables"]
    assert tables == [f"public.{t}" for t in cli.AUDIT_TABLES]
    assert all(t.startswith("public.") for t in tables)
    # Контракт с миграцией не меняется: AUDIT_TABLES сам остаётся голыми именами.
    assert cli.AUDIT_TABLES == ("audit_log", "auth_log", "data_change_log")


# ── T25 + drift: контракт скрипта против миграции и соседнего job'а ──────────

def test_contract_matches_migration():
    """Сигнатуры и список журналов в скрипте совпадают с ревизией."""
    migration = _load_module("stage7a_migration_for_cli_test", MIGRATION_PATH)

    assert cli.ANONYMIZE_SIGNATURE == migration.ANONYMIZE_SIGNATURE
    assert cli.COUNT_SIGNATURE == migration.COUNT_SIGNATURE
    assert cli.AUDIT_TABLES == migration.AUDIT_TABLES


def test_advisory_lock_key_differs_from_partitions_job():
    """T25 — общий ключ заставил бы два независимых job'а блокировать друг друга."""
    migration = _load_module("stage7a_migration_for_key_test", MIGRATION_PATH)
    partitions_source = PARTITIONS_SCRIPT.read_text(encoding="utf-8")

    assert "_ADVISORY_LOCK_KEY = 5_566_827_076_427_522_049" in partitions_source
    assert migration.ADVISORY_LOCK_KEY != 5_566_827_076_427_522_049
    # Ключ обязан помещаться в bigint — иначе PostgreSQL отвергнет вызов.
    assert 0 < migration.ADVISORY_LOCK_KEY < 2 ** 63


def test_cli_does_not_take_advisory_lock():
    """Единственный источник истины о параллельном запуске — сама функция."""
    assert "pg_try_advisory" not in _cli_sql()


def test_cli_does_not_import_application_runtime():
    """Ни SessionLocal, ни app.main; app.core.config — только отложенно."""
    tree = _cli_ast()

    # 1. На уровне модуля приложение не импортируется вовсе.
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("app"), alias.name
        elif isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith("app"), node.module

    # 2. Единственный импорт приложения — отложенный, внутри функции, и это
    #    именно app.core.config.
    lazy = [
        node.module
        for func in ast.walk(tree)
        if isinstance(func, ast.FunctionDef)
        for node in ast.walk(func)
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("app")
    ]
    assert lazy == ["app.core.config"], lazy

    # 3. Runtime-объекты приложения не упоминаются в коде (docstring'и и
    #    комментарии обсуждают запрет словами и сюда не попадают).
    identifiers = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    identifiers |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert "SessionLocal" not in identifiers


def test_cli_issues_no_ddl_or_delete():
    """Скрипт не удаляет строки и не трогает партиции ни при каких аргументах."""
    sql = _cli_sql().upper()

    for forbidden in ("DELETE FROM", "DROP TABLE", "DETACH PARTITION",
                      "TRUNCATE", "CASCADE"):
        assert forbidden not in sql, forbidden
