"""
Stage 6-0 — статический контроль production call sites record_data_change.

Парность строк audit_log ↔ data_change_log — caller-инвариант, а не гарантия
facade или БД. Один из механизмов, удерживающих его, — этот тест: множество
production-вызовов должно быть ТОЧНО равно утверждённому.

Используется AST, а не grep: строковый поиск ловит комментарии, docstring'и и
имена в `__all__`, и не отличает вызов от определения.

Stage 6-0 ввела writer без единого caller'а (ожидаемое множество было пустым).
Stage 6-B подключила две config-таблицы, Stage 6-C — две ПДн-таблицы
(name-only). Итоговые ЧЕТЫРЕ и только четыре утверждённых caller'а:
    app/appointments/storage.py :: update_meeting_type               (Stage 6-B)
    app/appointments/storage.py :: update_group_session              (Stage 6-B)
    app/appointments/storage.py :: update_unregistered_student_card  (Stage 6-C)
    app/users/storage.py        :: _apply_role_and_scalar_changes    (Stage 6-C)
"""
import ast
from pathlib import Path

import pytest

_API_ROOT = Path(__file__).resolve().parents[1]
_APP_DIR = _API_ROOT / "app"

# Модуль-определение writer'а: его собственный `def` и внутренние ссылки
# вызовами не считаются.
_WRITER_MODULE = _APP_DIR / "audit" / "data_change.py"

_TARGET = "record_data_change"

# Stage 6-C (финальное множество этапа 6): ровно четыре caller'а.
_EXPECTED_CALL_SITES: frozenset = frozenset({
    # Stage 6-B — config-таблицы (есть value-enabled поля).
    ("app/appointments/storage.py", "update_meeting_type"),
    ("app/appointments/storage.py", "update_group_session"),
    # Stage 6-C — ПДн-таблицы, СТРОГО name-only (values всегда None).
    ("app/appointments/storage.py", "update_unregistered_student_card"),
    ("app/users/storage.py", "_apply_role_and_scalar_changes"),
})


def _callee_name(func: ast.expr):
    """Имя вызываемого: покрывает record_data_change(...) и
    <module>.record_data_change(...)."""
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


class _CallSiteVisitor(ast.NodeVisitor):
    """Собирает (модуль, объемлющая функция) для каждого ast.Call к _TARGET."""

    def __init__(self, module: str):
        self.module = module
        self._stack: list = []
        self.found: set = set()

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self._stack.append(node.name)
        self.generic_visit(node)
        self._stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef   # type: ignore[assignment]

    def visit_Call(self, node: ast.Call):
        if _callee_name(node.func) == _TARGET:
            enclosing = self._stack[-1] if self._stack else "<module>"
            self.found.add((self.module, enclosing))
        self.generic_visit(node)


def _collect_call_sites() -> set:
    found: set = set()
    for path in sorted(_APP_DIR.rglob("*.py")):
        if path == _WRITER_MODULE:
            continue
        module = path.relative_to(_API_ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        visitor = _CallSiteVisitor(module)
        visitor.visit(tree)
        found |= visitor.found
    return found


def test_production_call_sites_match_the_approved_set():
    assert _collect_call_sites() == _EXPECTED_CALL_SITES


def test_stage_6_c_has_exactly_the_four_approved_callers():
    """Явное подтверждение финального объёма Stage 6: ровно четыре caller'а —
    две config-таблицы (6-B) и две ПДн-таблицы в name-only режиме (6-C)."""
    found = _collect_call_sites()
    assert found == {
        ("app/appointments/storage.py", "update_meeting_type"),
        ("app/appointments/storage.py", "update_group_session"),
        ("app/appointments/storage.py", "update_unregistered_student_card"),
        ("app/users/storage.py", "_apply_role_and_scalar_changes"),
    }
    assert len(found) == 4


def test_user_dcl_writer_lives_in_the_shared_core_not_in_update_user():
    """Точка вызова для users — _apply_role_and_scalar_changes (рядом с
    admin_user_updated), а НЕ update_user: тот владеет SessionLocal/commit."""
    found = _collect_call_sites()
    assert ("app/users/storage.py", "_apply_role_and_scalar_changes") in found
    assert ("app/users/storage.py", "update_user") not in found


def test_no_auth_self_profile_caller():
    """Stage 6-C не подключает self-profile flow (app/auth/*)."""
    found = _collect_call_sites()
    assert not any(module.startswith("app/auth/") for module, _ in found)


def test_writer_module_is_excluded_but_exists():
    assert _WRITER_MODULE.is_file()
    source = _WRITER_MODULE.read_text(encoding="utf-8")
    assert f"def {_TARGET}(" in source


# ── Позитивный контроль самого детектора ─────────────────────────────────────

def _detect(source: str) -> set:
    visitor = _CallSiteVisitor("probe.py")
    visitor.visit(ast.parse(source))
    return visitor.found


def test_detector_finds_bare_call():
    assert _detect(
        "def caller():\n    record_data_change(table='x')\n"
    ) == {("probe.py", "caller")}


def test_detector_finds_attribute_calls():
    assert _detect(
        "def caller():\n    audit.record_data_change(table='x')\n"
    ) == {("probe.py", "caller")}
    assert _detect(
        "def caller():\n    data_change.record_data_change(table='x')\n"
    ) == {("probe.py", "caller")}


def test_detector_attributes_call_to_innermost_function():
    source = (
        "def outer():\n"
        "    def inner():\n"
        "        record_data_change(table='x')\n"
        "    return inner\n"
    )
    assert _detect(source) == {("probe.py", "inner")}


def test_detector_reports_module_level_calls():
    assert _detect("record_data_change(table='x')\n") == {
        ("probe.py", "<module>"),
    }


def test_definition_and_mentions_are_not_calls():
    """`def`, импорт, строка в __all__ и комментарий вызовами не считаются."""
    source = (
        "from app.audit import record_data_change\n"
        "__all__ = ['record_data_change']\n"
        "# record_data_change(table='x')\n"
        "def record_data_change(**kw):\n"
        "    '''record_data_change docstring'''\n"
        "    return None\n"
    )
    assert _detect(source) == set()


def test_detector_ignores_similarly_named_calls():
    source = (
        "def caller():\n"
        "    record_data_changes(table='x')\n"
        "    record_event(event='y')\n"
    )
    assert _detect(source) == set()


def test_all_app_modules_are_parseable():
    """Если модуль не парсится, тест обязан упасть, а не молча пропустить его."""
    files = list(_APP_DIR.rglob("*.py"))
    assert files
    for path in files:
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:            # pragma: no cover
            pytest.fail(f"unparseable module: {path.name} ({type(exc).__name__})")
