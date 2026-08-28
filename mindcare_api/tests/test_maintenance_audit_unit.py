"""
Stage 5C-3 — no-DB unit-тесты system maintenance audit.

Покрывает: registry contract 2 SYSTEM-событий (Actor.system(), без ролей);
fail-closed system guard (user actor и наличие request-контекста отвергаются);
completion через UPDATE…RETURNING → per-row события, пустой результат → 0;
per-series lock + перепроверка предиката; dry-run НЕ вызывает record_event;
событие только при фактическом сдвиге; распространение AuditStorageError и
недостижимость commit; отсутствие мутаций в GET/list/register (статический
тест); диагностика скриптов без str(exc). Реальная БД не используется.
"""
import ast
import inspect
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import app.appointments.service as appt_service
import app.appointments.storage as st
from app.audit import Actor, RequestContext
from app.audit.contracts import AuditStorageError
from app.audit.registry import REGISTRY

SYSTEM = Actor.system()
USER = Actor.user(9, "supervisor")
CTX = RequestContext(ip_address="203.0.113.7", user_agent="ua")
_APP = Path(__file__).resolve().parents[1] / "app" / "appointments"
_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


# ══════════════════════════════════════════════════════════════════════════
# 1. Registry contract — 2 SYSTEM-события
# ══════════════════════════════════════════════════════════════════════════

_SYS_EVENTS = {
    "group_session_completed": "group_session",
    "schedule_auto_extended": "schedule_series",
}


def test_registry_system_events_and_count():
    assert len(REGISTRY) == 104
    for name, entity in _SYS_EVENTS.items():
        s = REGISTRY[name]
        assert s.destination.value == "audit_log", name
        assert s.actor_policy.value == "system", name
        assert s.allowed_actor_roles == frozenset(), name   # ролей нет
        assert s.target_policy.value == "required", name
        assert s.entity_type == entity, name
        assert {o.value for o in s.allowed_outcomes} == {"success"}, name
        assert s.allowed_failure_codes == frozenset(), name
        assert dict(s.metadata_schema) == {}, name
        assert s.tx_mode.value == "atomic", name       # сбой аудита откатывает
        assert s.failure_policy.value == "raise", name
        assert s.description_policy.value == "none", name


# ══════════════════════════════════════════════════════════════════════════
# 2. Fail-closed system guard
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("actor,context", [
    (USER, None),          # user actor вместо system
    (None, None),          # вообще не Actor
    (SYSTEM, CTX),         # system actor с request-контекстом
], ids=["user_actor", "not_actor", "system_with_context"])
def test_system_guard_rejects(actor, context):
    with pytest.raises(RuntimeError):
        st._require_system_actor(actor, context)


def test_system_guard_accepts_system_without_context():
    st._require_system_actor(SYSTEM, None)      # не бросает


@pytest.mark.parametrize("call", [
    lambda db: st.complete_due_group_sessions(
        db, datetime.now(), actor=USER, context=None),
    lambda db: st.complete_due_group_sessions(
        db, datetime.now(), actor=SYSTEM, context=CTX),
    lambda db: st.auto_extend_series(
        "S", date(2026, 3, 1), db, actor=USER, context=None),
], ids=["completion_user_actor", "completion_with_ctx", "extend_user_actor"])
def test_maintenance_writers_reject_before_mutation(call):
    db = MagicMock(name="db")
    with pytest.raises(RuntimeError):
        call(db)
    db.execute.assert_not_called()
    db.flush.assert_not_called()


def test_maintenance_writers_actor_keyword_only():
    for fn_name in ("complete_due_group_sessions", "auto_extend_series"):
        p = inspect.signature(getattr(st, fn_name)).parameters["actor"]
        assert p.default is inspect.Parameter.empty, fn_name
        assert p.kind == inspect.Parameter.KEYWORD_ONLY, fn_name


# ══════════════════════════════════════════════════════════════════════════
# 3. Completion: UPDATE…RETURNING → per-row события
# ══════════════════════════════════════════════════════════════════════════

def _spy(monkeypatch):
    calls = []
    monkeypatch.setattr(st, "record_event", lambda **kw: calls.append(kw))
    return calls


def _db_returning(ids):
    db = MagicMock(name="db")
    db.execute.return_value = [(i,) for i in ids]
    return db


def test_completion_writes_one_event_per_returned_id(monkeypatch):
    calls = _spy(monkeypatch)
    db = _db_returning([11, 22, 33])
    result = st.complete_due_group_sessions(
        db, datetime.now(), actor=SYSTEM, context=None)

    assert result == [11, 22, 33]
    assert [c["event"] for c in calls] == ["group_session_completed"] * 3
    assert [c["target"].entity_id for c in calls] == [11, 22, 33]
    for c in calls:
        assert c["actor"] is SYSTEM
        assert c["target"].entity_type == "group_session"
        assert c["metadata"] == {}
        assert c["context"] is None        # у job нет request-контекста
        assert c["db"] is db               # ATOMIC: та же транзакция


def test_completion_empty_result_writes_nothing(monkeypatch):
    calls = _spy(monkeypatch)
    db = _db_returning([])
    assert st.complete_due_group_sessions(
        db, datetime.now(), actor=SYSTEM, context=None) == []
    assert calls == []


def test_completion_uses_single_atomic_update_returning():
    """Одностатементный UPDATE…RETURNING — иначе два конкурентных прогона
    выбрали бы одни и те же строки и записали дублирующие события."""
    src = (_APP / "storage.py").read_text(encoding="utf-8")
    body = src.split("def complete_due_group_sessions", 1)[1].split(
        "\ndef ", 1)[0]
    assert ".returning(" in body
    assert "sa.update(" in body
    # предикат перехода: только scheduled и только наступившие
    assert 'GroupSession.status == "scheduled"' in body
    assert "GroupSession.starts_at <= now" in body


def test_completion_audit_failure_propagates_and_no_commit(monkeypatch):
    def _boom(**kw):
        raise AuditStorageError("audit down")
    monkeypatch.setattr(st, "record_event", _boom)
    db = _db_returning([11])
    with pytest.raises(AuditStorageError):
        st.complete_due_group_sessions(
            db, datetime.now(), actor=SYSTEM, context=None)
    db.commit.assert_not_called()


def test_completion_job_service_commit_not_reached(monkeypatch):
    db = MagicMock(name="owner_db")
    sess = MagicMock()
    sess.return_value.__enter__ = MagicMock(return_value=db)
    sess.return_value.__exit__ = MagicMock(return_value=False)
    monkeypatch.setattr(appt_service, "SessionLocal", sess)

    def _boom(*a, **kw):
        raise AuditStorageError("audit down")
    monkeypatch.setattr(appt_service.storage, "complete_due_group_sessions",
                        _boom)
    with pytest.raises(AuditStorageError):
        appt_service.complete_due_group_sessions_job()
    db.commit.assert_not_called()


def test_completion_job_uses_system_actor_without_context(monkeypatch):
    db = MagicMock(name="owner_db")
    sess = MagicMock()
    sess.return_value.__enter__ = MagicMock(return_value=db)
    sess.return_value.__exit__ = MagicMock(return_value=False)
    monkeypatch.setattr(appt_service, "SessionLocal", sess)
    seen = {}

    def _spy_fn(db_, now, *, actor, context):
        seen["actor"], seen["context"] = actor, context
        return [1, 2]
    monkeypatch.setattr(appt_service.storage, "complete_due_group_sessions",
                        _spy_fn)

    assert appt_service.complete_due_group_sessions_job() == {
        "completed_sessions": 2}
    assert seen["actor"].kind == "system"
    assert seen["actor"].user_id is None and seen["actor"].role is None
    assert seen["context"] is None
    db.commit.assert_called_once()


# ══════════════════════════════════════════════════════════════════════════
# 4. GET/list/register больше НЕ мутируют (регрессия варианта B)
# ══════════════════════════════════════════════════════════════════════════

def test_completion_not_called_from_read_or_register_paths():
    """Статический тест: `complete_due_group_sessions` вызывается только из
    maintenance-job, но не из list/GET и не из регистрации студента."""
    src = (_APP / "service.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if node.name == "complete_due_group_sessions_job":
            continue                        # единственный легальный caller
        for sub in ast.walk(node):
            if (isinstance(sub, ast.Call)
                    and isinstance(sub.func, ast.Attribute)
                    and sub.func.attr == "complete_due_group_sessions"):
                offenders.append(node.name)
    assert offenders == [], offenders


@pytest.mark.parametrize("fn_name", [
    "list_group_sessions", "list_group_sessions_psychologist",
    "list_group_sessions_student",
])
def test_list_functions_have_no_commit(fn_name):
    """GET/list стали действительно read-only — мутаций и commit нет."""
    src = (_APP / "service.py").read_text(encoding="utf-8")
    body = src.split(f"def {fn_name}(", 1)[1].split("\ndef ", 1)[0]
    assert "db.commit()" not in body, fn_name


def test_register_group_has_single_commit():
    """После удаления lazy-maintenance регистрация — одна транзакция."""
    src = (_APP / "service.py").read_text(encoding="utf-8")
    body = src.split("def student_register_group(", 1)[1].split(
        "\ndef ", 1)[0]
    assert body.count("db.commit()") == 1


# ══════════════════════════════════════════════════════════════════════════
# 5. Auto-extend: lock, перепроверка предиката, dry-run без record_event
# ══════════════════════════════════════════════════════════════════════════

def test_lock_uses_skip_locked():
    src = (_APP / "storage.py").read_text(encoding="utf-8")
    body = src.split("def lock_series_for_maintenance", 1)[1].split(
        "\ndef ", 1)[0]
    assert "with_for_update(skip_locked=True)" in body
    assert "ScheduleSeries.series_uuid" in body      # блокировка по identity


def test_auto_extend_series_writes_system_event(monkeypatch):
    calls = _spy(monkeypatch)
    monkeypatch.setattr(st, "apply_series_extension", lambda s, u, db: 2)
    db = MagicMock(name="db")
    db.query.return_value.filter.return_value.first.return_value = (
        SimpleNamespace(id=55))

    changed = st.auto_extend_series(
        "S", date(2026, 3, 1), db, actor=SYSTEM, context=None)

    assert changed == 2
    assert [c["event"] for c in calls] == ["schedule_auto_extended"]
    assert calls[0]["actor"] is SYSTEM
    assert calls[0]["target"].entity_type == "schedule_series"
    assert calls[0]["target"].entity_id == 55
    assert calls[0]["metadata"] == {} and calls[0]["context"] is None


def test_auto_extend_series_no_shift_is_noop(monkeypatch):
    calls = _spy(monkeypatch)
    monkeypatch.setattr(st, "apply_series_extension", lambda s, u, db: 0)
    db = MagicMock(name="db")
    db.query.return_value.filter.return_value.first.return_value = (
        SimpleNamespace(id=55))
    assert st.auto_extend_series(
        "S", date(2026, 3, 1), db, actor=SYSTEM, context=None) == 0
    assert calls == []


def _svc_session(monkeypatch):
    db = MagicMock(name="db")
    sess = MagicMock()
    sess.return_value.__enter__ = MagicMock(return_value=db)
    sess.return_value.__exit__ = MagicMock(return_value=False)
    monkeypatch.setattr(appt_service, "SessionLocal", sess)
    return db


def _due_rule(**over):
    base = dict(effective_until=date(2026, 1, 31), auto_extend=True,
                is_active=True, created_by=None)
    base.update(over)
    return SimpleNamespace(**base)


def test_dry_run_never_calls_record_event(monkeypatch):
    """Единый контракт: dry-run не зависит от доступности audit storage."""
    calls = _spy(monkeypatch)
    _svc_session(monkeypatch)
    monkeypatch.setattr(appt_service.storage, "get_auto_extend_series_due",
                        lambda t, db: ["S1", "S2"])
    monkeypatch.setattr(appt_service.storage, "get_series_rules",
                        lambda s, db: [_due_rule()])
    locked = []
    monkeypatch.setattr(appt_service.storage, "lock_series_for_maintenance",
                        lambda s, db: locked.append(s))

    result = appt_service.auto_extend_schedules(dry_run=True)

    assert result["dry_run"] is True
    assert result["extended_series"] == 2
    assert result["notified"] == 0
    assert calls == []                 # record_event НЕ вызывался
    assert locked == []                # блокировки не берутся


def test_dry_run_does_not_mutate(monkeypatch):
    _svc_session(monkeypatch)
    monkeypatch.setattr(appt_service.storage, "get_auto_extend_series_due",
                        lambda t, db: ["S1"])
    monkeypatch.setattr(appt_service.storage, "get_series_rules",
                        lambda s, db: [_due_rule()])
    applied = []
    monkeypatch.setattr(appt_service.storage, "apply_series_extension",
                        lambda *a, **kw: applied.append(a))
    monkeypatch.setattr(appt_service.storage, "auto_extend_series",
                        lambda *a, **kw: applied.append(a))

    appt_service.auto_extend_schedules(dry_run=True)
    assert applied == []


def test_skip_locked_series_is_skipped(monkeypatch):
    """Второй worker получает None и серию пропускает."""
    _svc_session(monkeypatch)
    monkeypatch.setattr(appt_service.storage, "get_auto_extend_series_due",
                        lambda t, db: ["S1"])
    monkeypatch.setattr(appt_service.storage, "lock_series_for_maintenance",
                        lambda s, db: None)
    extended = []
    monkeypatch.setattr(appt_service.storage, "auto_extend_series",
                        lambda *a, **kw: extended.append(a))

    result = appt_service.auto_extend_schedules()
    assert result["extended_series"] == 0
    assert extended == []


def test_predicate_rechecked_after_lock(monkeypatch):
    """Если первый worker уже сдвинул границу, второй ничего не делает."""
    _svc_session(monkeypatch)
    monkeypatch.setattr(appt_service.storage, "get_auto_extend_series_due",
                        lambda t, db: ["S1"])
    monkeypatch.setattr(appt_service.storage, "lock_series_for_maintenance",
                        lambda s, db: SimpleNamespace(id=55))
    # после блокировки видно уже продлённую серию (граница далеко в будущем)
    monkeypatch.setattr(
        appt_service.storage, "get_series_rules",
        lambda s, db: [_due_rule(effective_until=date(2099, 1, 1))])
    extended = []
    monkeypatch.setattr(appt_service.storage, "auto_extend_series",
                        lambda *a, **kw: extended.append(a))

    result = appt_service.auto_extend_schedules()
    assert result["extended_series"] == 0
    assert extended == []               # повторного продления нет


def test_real_shift_writes_once_per_series(monkeypatch):
    _svc_session(monkeypatch)
    monkeypatch.setattr(appt_service.storage, "get_auto_extend_series_due",
                        lambda t, db: ["S1", "S2"])
    monkeypatch.setattr(appt_service.storage, "lock_series_for_maintenance",
                        lambda s, db: SimpleNamespace(id=55))
    monkeypatch.setattr(appt_service.storage, "get_series_rules",
                        lambda s, db: [_due_rule()])
    seen = []

    def _extend(sid, new_until, db, *, actor, context):
        seen.append((sid, actor.kind, context))
        return 1
    monkeypatch.setattr(appt_service.storage, "auto_extend_series", _extend)
    monkeypatch.setattr(appt_service, "_notify_schedule_extended",
                        lambda *a, **kw: True)

    result = appt_service.auto_extend_schedules()
    assert result["extended_series"] == 2
    assert [s[1] for s in seen] == ["system", "system"]
    assert all(s[2] is None for s in seen)      # context=None


def test_auto_extend_audit_failure_does_not_commit_that_series(monkeypatch):
    db = _svc_session(monkeypatch)
    monkeypatch.setattr(appt_service.storage, "get_auto_extend_series_due",
                        lambda t, db_: ["S1"])
    monkeypatch.setattr(appt_service.storage, "lock_series_for_maintenance",
                        lambda s, db_: SimpleNamespace(id=55))
    monkeypatch.setattr(appt_service.storage, "get_series_rules",
                        lambda s, db_: [_due_rule()])

    def _boom(*a, **kw):
        raise AuditStorageError("audit down")
    monkeypatch.setattr(appt_service.storage, "auto_extend_series", _boom)

    with pytest.raises(AuditStorageError):
        appt_service.auto_extend_schedules()
    db.commit.assert_not_called()


def test_per_series_transaction_not_batch():
    """Транзакция открывается ВНУТРИ цикла по сериям."""
    src = (_APP / "service.py").read_text(encoding="utf-8")
    body = src.split("def auto_extend_schedules(", 1)[1].split(
        "\ndef ", 1)[0]
    live = body.split("notifications:", 1)[1]      # non-dry-run часть
    assert live.index("for series_id in series_ids:") < live.index(
        "with SessionLocal() as db:")


# ══════════════════════════════════════════════════════════════════════════
# 6. Диагностика скриптов: только phase/error-class, exit code ≠ 0
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("script", [
    "extend_schedules.py", "complete_group_sessions.py",
])
def test_script_diagnostics_have_no_exception_value(script):
    src = (_SCRIPTS / script).read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in ("error", "warning", "info", "debug")):
            continue
        for arg in node.args:
            # запрещён голый `exc` как аргумент логгера (str(exc) в выводе)
            assert not (isinstance(arg, ast.Name) and arg.id == "exc"), script
            assert not (isinstance(arg, ast.Call)
                        and isinstance(arg.func, ast.Name)
                        and arg.func.id == "str"), script


@pytest.mark.parametrize("script", [
    "extend_schedules.py", "complete_group_sessions.py",
])
def test_script_exits_nonzero_on_failure(script):
    src = (_SCRIPTS / script).read_text(encoding="utf-8")
    assert "sys.exit(1)" in src
    # обработчик покрывает вызов service (мутация/audit/commit)
    assert "except Exception as exc:" in src


def test_completion_script_documents_scheduler_requirement():
    src = (_SCRIPTS / "complete_group_sessions.py").read_text(encoding="utf-8")
    assert "ЭКСПЛУАТАЦИОННОЕ ТРЕБОВАНИЕ" in src
    for token in ("cron", "systemd", "Task Scheduler"):
        assert token in src


# ══════════════════════════════════════════════════════════════════════════
# 7. Deployment: обязательные job'ы подключены к поддерживаемому процессу
# ══════════════════════════════════════════════════════════════════════════

_DEPLOY = Path(__file__).resolve().parents[2] / "deploy"


@pytest.mark.parametrize("unit,script", [
    ("mindcare-complete-group-sessions", "complete_group_sessions.py"),
    ("mindcare-extend-schedules", "extend_schedules.py"),
])
def test_systemd_units_exist_and_run_the_right_script(unit, script):
    svc = (_DEPLOY / f"{unit}.service").read_text(encoding="utf-8")
    timer = (_DEPLOY / f"{unit}.timer").read_text(encoding="utf-8")
    # oneshot-job, запускающий именно наш скрипт
    assert "Type=oneshot" in svc
    assert script in svc
    # exit-code мониторинг: падение поднимает шаблонный обработчик
    assert f"OnFailure=mindcare-maintenance-failure@{unit}.service" in svc
    # таймер привязан к своему юниту и переживает простой
    assert f"Unit={unit}.service" in timer
    assert "Persistent=true" in timer
    assert "WantedBy=timers.target" in timer


def test_failure_handler_unit_exists_and_is_templated():
    p = _DEPLOY / "mindcare-maintenance-failure@.service"
    src = p.read_text(encoding="utf-8")
    assert "%i" in src                      # шаблон по имени упавшего юнита
    assert "daemon.err" in src


@pytest.mark.parametrize("unit,marker", [
    ("mindcare-complete-group-sessions.timer", "OnUnitActiveSec=10min"),
    ("mindcare-extend-schedules.timer", "OnCalendar="),
])
def test_timers_declare_explicit_periodicity(unit, marker):
    assert marker in (_DEPLOY / unit).read_text(encoding="utf-8")


def test_deployment_runbook_covers_both_supported_paths():
    """Одношаговый upgrade head без простоя не поддерживается: runbook обязан
    описывать либо гарантированный downtime, либо поэтапный expand/contract."""
    src = (_DEPLOY / "STAGE_5C_DEPLOYMENT.md").read_text(encoding="utf-8")
    assert "a1c4e8b2f7d3" in src and "b5d7f0a3c9e1" in src
    assert "upgrade a1c4e8b2f7d3" in src        # раздельная накатка
    assert "upgrade b5d7f0a3c9e1" in src
    assert "небезопас" in src                   # объяснение окна совместимости
    for token in ("systemctl is-failed", "OnFailure", "--dry-run"):
        assert token in src
