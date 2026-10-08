"""
ADR-029 — unit-тесты санитизации технических сбоев записи в
app/student_verification/storage.py БЕЗ подключения к БД.

Синтетические SQLAlchemy-ошибки несут маркеры в SQL, параметрах и исходном
исключении драйвера. Проверяется:
  * известные конфликты (ux_svr_user_pending / ux_svr_user_approved) → typed
    VerificationError, как раньше;
  * любая иная SQLAlchemyError flush/commit → VerificationStorageError: не
    VerificationError, без __cause__/__context__, текст фиксированный;
  * откат выполнен; диагностика — только op/phase/класс; ни маркеров, ни SQL
    нет в stderr и в отформатированном traceback;
  * success-аудит при сбое flush не пишется.
"""
import traceback
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import DataError, IntegrityError, OperationalError

import app.student_verification.storage as sv_storage
from app.student_verification import errors

SQL_MARKER = "SQL-MARKER-7f3a"
CIPHER_MARKER = "enc:v1:CIPHER-MARKER-7f3a"
PLAIN_MARKER = "PLAIN-MARKER-7f3a"
MARKERS = (SQL_MARKER, CIPHER_MARKER, PLAIN_MARKER, "INSERT INTO", "UPDATE student")


def _orig(constraint_name=None):
    return SimpleNamespace(
        diag=SimpleNamespace(constraint_name=constraint_name),
        __str__=lambda self=None: f"driver says {PLAIN_MARKER}",
    )


def _synthetic(cls, constraint_name=None):
    return cls(
        f"INSERT INTO student_verification_requests (ticket_number_enc) "
        f"VALUES (%(t)s) /* {SQL_MARKER} */",
        {"t": CIPHER_MARKER, "plain": PLAIN_MARKER},
        _orig(constraint_name),
    )


class _FakeQuery:
    def filter(self, *a, **k):
        return self

    def all(self):
        return []


class _FakeDb:
    def __init__(self, flush_exc=None, commit_exc=None):
        self.flush_exc = flush_exc
        self.commit_exc = commit_exc
        self.rolled_back = 0
        self.committed = 0

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def query(self, *a):
        return _FakeQuery()

    def add(self, obj):
        self.obj = obj

    def flush(self):
        if self.flush_exc:
            raise self.flush_exc
        self.obj.id = 41

    def commit(self):
        if self.commit_exc:
            raise self.commit_exc
        self.committed += 1

    def rollback(self):
        self.rolled_back += 1


@pytest.fixture
def submit_env(monkeypatch):
    events = []
    monkeypatch.setattr(sv_storage, "lock_user", lambda db, uid: SimpleNamespace(
        id=7, is_active=True, deleted_at=None))
    monkeypatch.setattr(sv_storage, "get_active_role_names", lambda db, uid: ["student"])
    monkeypatch.setattr(sv_storage, "encrypt_text", lambda value: CIPHER_MARKER)
    monkeypatch.setattr(sv_storage, "record_event", lambda **kw: events.append(kw))

    def _run(db):
        monkeypatch.setattr(sv_storage, "SessionLocal", lambda: db)
        return sv_storage.submit_atomic(7, faculty_code="law", ticket_number=PLAIN_MARKER)
    return _run, events


def _assert_sanitized(exc, captured_err):
    assert isinstance(exc, errors.VerificationStorageError)
    assert not isinstance(exc, errors.VerificationError)
    assert exc.__cause__ is None and exc.__context__ is None
    assert str(exc) == "student verification storage failure"
    rendered = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    for marker in MARKERS:
        assert marker not in rendered, marker
        assert marker not in captured_err, marker


@pytest.mark.parametrize("constraint,expected", [
    ("ux_svr_user_pending", errors.VerificationPendingExists),
    ("ux_svr_user_approved", errors.AlreadyVerified),
])
def test_known_constraint_conflicts_keep_typed_codes(submit_env, constraint, expected):
    run, events = submit_env
    db = _FakeDb(flush_exc=_synthetic(IntegrityError, constraint))
    with pytest.raises(expected) as info:
        run(db)
    assert info.value.__context__ is None
    assert db.rolled_back == 1 and db.committed == 0 and events == []


@pytest.mark.parametrize("exc", [
    _synthetic(IntegrityError, "ck_svr_ticket_encrypted"),
    _synthetic(IntegrityError, None),
    _synthetic(DataError),
    _synthetic(OperationalError),
])
def test_unknown_flush_error_is_sanitized(submit_env, capsys, exc):
    run, events = submit_env
    db = _FakeDb(flush_exc=exc)
    with pytest.raises(errors.VerificationStorageError) as info:
        run(db)
    err = capsys.readouterr().err
    _assert_sanitized(info.value, err)
    assert f"op=submit phase=flush error={type(exc).__name__}" in err
    assert db.rolled_back == 1 and db.committed == 0
    assert events == []          # success-аудит не стейджился


def test_unknown_commit_error_is_sanitized(submit_env, capsys):
    run, events = submit_env
    db = _FakeDb(commit_exc=_synthetic(OperationalError))
    with pytest.raises(errors.VerificationStorageError) as info:
        run(db)
    err = capsys.readouterr().err
    _assert_sanitized(info.value, err)
    assert "op=submit phase=commit error=OperationalError" in err
    assert db.rolled_back == 1
    # Событие было застейджено в ту же (откатанную) транзакцию — не записано.
    assert [e["event"] for e in events] == ["student_verification_submitted"]


def test_commit_helper_sanitizes_and_survives_failing_rollback(capsys):
    class _Db:
        def commit(self):
            raise _synthetic(OperationalError)

        def rollback(self):
            raise RuntimeError(f"rollback failed {PLAIN_MARKER}")

    with pytest.raises(errors.VerificationStorageError) as info:
        sv_storage._commit(_Db(), "decide")
    err = capsys.readouterr().err
    _assert_sanitized(info.value, err)
    assert "op=decide phase=rollback error=RuntimeError" in err
    assert "op=decide phase=commit error=OperationalError" in err


def test_non_sqlalchemy_errors_are_not_reclassified(submit_env):
    run, _ = submit_env
    db = _FakeDb(flush_exc=RuntimeError("plain bug"))
    with pytest.raises(RuntimeError, match="plain bug"):
        run(db)


def test_storage_error_is_not_mapped_by_routes():
    """Route ловит только VerificationError: технический сбой → 500, не *_failed."""
    assert not issubclass(errors.VerificationStorageError, errors.VerificationError)
    assert issubclass(errors.VerificationStorageError, RuntimeError)


def test_synthetic_errors_really_carry_the_markers():
    """Контроль самого теста: без санитизации SQL и параметры видны в str(exc)."""
    raw = str(_synthetic(OperationalError))
    assert SQL_MARKER in raw and CIPHER_MARKER in raw and PLAIN_MARKER in raw


# ── Чтения: list_requests / get_latest_for_user / get_card / блокировки ───────

class _FailingReadQuery:
    """Любой терминальный вызов запроса → синтетическая OperationalError."""

    def __init__(self, exc):
        self._exc = exc

    def __getattr__(self, name):
        if name in ("all", "first", "one", "scalar"):
            def _boom(*a, **k):
                raise self._exc
            return _boom
        return lambda *a, **k: self


class _ReadDb(_FakeDb):
    def __init__(self, exc):
        super().__init__()
        self._read_exc = exc

    def query(self, *a):
        return _FailingReadQuery(self._read_exc)


@pytest.mark.parametrize("op,call", [
    ("list", lambda: sv_storage.list_requests(
        status="pending", page=1, size=20, search=PLAIN_MARKER)),
    ("status", lambda: sv_storage.get_latest_for_user(7)),
    ("card", lambda: sv_storage.get_card("1b4e28ba-2fa1-11d2-883f-0016d3cca427")),
    ("decide", lambda: sv_storage.decide_atomic(
        "1b4e28ba-2fa1-11d2-883f-0016d3cca427", decision="approve", reviewer_id=9)),
])
def test_unknown_read_error_is_sanitized(monkeypatch, capsys, op, call):
    db = _ReadDb(_synthetic(OperationalError))
    monkeypatch.setattr(sv_storage, "SessionLocal", lambda: db)
    with pytest.raises(errors.VerificationStorageError) as info:
        call()
    err = capsys.readouterr().err
    _assert_sanitized(info.value, err)
    assert f"op={op} phase=read error=OperationalError" in err
    assert db.rolled_back == 1


def test_unknown_read_error_on_submit_lock_is_sanitized(submit_env, monkeypatch, capsys):
    run, events = submit_env

    def _lock_fails(db, uid):
        raise _synthetic(OperationalError)
    monkeypatch.setattr(sv_storage, "lock_user", _lock_fails)
    db = _FakeDb()
    with pytest.raises(errors.VerificationStorageError) as info:
        run(db)
    err = capsys.readouterr().err
    _assert_sanitized(info.value, err)
    assert "op=submit phase=read error=OperationalError" in err
    assert events == [] and db.committed == 0


def test_domain_refusals_inside_read_section_are_not_reclassified(submit_env, monkeypatch):
    run, _ = submit_env
    monkeypatch.setattr(sv_storage, "lock_user", lambda db, uid: SimpleNamespace(
        id=7, is_active=False, deleted_at=None))
    with pytest.raises(errors.AccountInactive):
        run(_FakeDb())

    class _NoRows(_FakeDb):
        def query(self, *a):
            q = _FakeQuery()
            q.first = lambda: None
            return q
    monkeypatch.setattr(sv_storage, "SessionLocal", lambda: _NoRows())
    with pytest.raises(errors.VerificationNotFound):
        sv_storage.decide_atomic("1b4e28ba-2fa1-11d2-883f-0016d3cca427",
                                 decision="approve", reviewer_id=9)
