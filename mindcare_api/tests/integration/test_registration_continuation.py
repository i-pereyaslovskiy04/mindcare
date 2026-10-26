"""
Подтверждение регистрации по ссылке из письма (PostgreSQL, isolated test DB).

Registration reference = otp_verifications.id выпуска кода обычной
регистрации (UUIDv4, без новой колонки и миграции). Ссылка в письме:
{FRONTEND_PUBLIC_URL}/register/confirm#r=<reference>.

  * каждый успешный register/init - новая запись с новым UUID; прежний выпуск
    (код и reference) после commit не действует;
  * отказ по cooldown, rollback выпуска - прежний выпуск действует как был;
  * сбой SMTP после commit - новый выпуск остаётся, прежний не возвращается;
  * confirm {registration_reference, code}: 201 {message, email}; запись
    удаляется, reference больше не действует;
  * confirm {email, code}: прежний контракт, ответ без email;
  * неизвестный / заменённый / использованный reference, истёкший код,
    неверный код, исчерпанные попытки - стабильные коды ошибок;
  * записи reset и регистрации через провайдера (без хеша пароля) обычным
    confirm не выбираются, их попытки не тратятся;
  * параллельные init / confirm сериализуются advisory lock по email;
  * в журнал не попадают reference и код; сбой журнала регистрацию не ломает.

Потоки вызывают service напрямую (TestClient не потокобезопасен).
"""
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch

import pytest
import sqlalchemy as sa
from sqlalchemy import func

from app.audit import service as audit_service
from app.auth import otp_service, service as auth_service, storage as auth_storage
from app.core.normalization import normalize_email
from app.db.models import AuthLog, OtpVerification, User
from app.db.session import SessionLocal

CONFIRM = "/api/auth/register/confirm"
INIT = "/api/auth/register/init"
PASSWORD = "Integration-Pass-1"
_REF_RE = re.compile(r"/register/confirm#r=([0-9a-f-]{36})")
THREADS = 4


@pytest.fixture
def letters():
    """Перехват писем регистрации: {recipient: [(code, reference|None), ...]}."""
    sent: dict[str, list[tuple[str, str | None]]] = {}

    def _fake(to, subject, body, html=None):
        code = re.search(r"Ваш код: (\d{6})", body)
        ref = _REF_RE.search(body)
        html_ref = _REF_RE.search(html or "")
        assert (ref and ref.group(1)) == (html_ref and html_ref.group(1))
        if code:
            sent.setdefault(to, []).append((code.group(1), ref.group(1) if ref else None))

    with patch("app.services.email_service.send_email", side_effect=_fake):
        yield sent


def _init(client, email):
    return client.post(INIT, json={"name": "Интеграционный Студент",
                                   "email": email, "password": PASSWORD})


def _rows(email):
    with SessionLocal() as db:
        rows = db.query(OtpVerification).filter(OtpVerification.email == email).all()
        for r in rows:
            db.expunge(r)
        return rows


def _users(email):
    with SessionLocal() as db:
        return db.query(func.count(User.id)).filter(User.email == email).scalar()


def _skip_cooldown(email):
    with SessionLocal() as db:
        db.query(OtpVerification).filter(OtpVerification.email == email).update(
            {"last_sent_at": otp_service._utcnow() - timedelta(seconds=120)})
        db.commit()


def _by_ref(client, ref, code):
    return client.post(CONFIRM, json={"registration_reference": ref, "code": code})


def _auth_mark():
    with SessionLocal() as db:
        return db.query(func.coalesce(func.max(AuthLog.id), 0)).scalar()


def _auth_rows_since(mark, event):
    with SessionLocal() as db:
        rows = (db.query(AuthLog)
                .filter(AuthLog.id > mark, AuthLog.event == event)
                .order_by(AuthLog.id).all())
        for r in rows:
            db.expunge(r)
        return rows


def _wrong(code):
    return f"{(int(code) + 1) % 1_000_000:06d}"


# ── Выпуск кода: новый UUID, замена, cooldown, rollback, SMTP ─────────────────

def test_init_creates_uuid_reference_in_letter(client, letters, test_email):
    assert _init(client, test_email).status_code == 200
    (code, ref), = letters[test_email]
    (row,) = _rows(test_email)
    assert row.id == ref
    assert re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", ref)
    assert row.attempts == 0 and row.password_hash is not None


def test_resend_after_cooldown_new_uuid_old_one_dead(client, letters, test_email):
    _init(client, test_email)
    _skip_cooldown(test_email)
    assert _init(client, test_email).status_code == 200
    (old_code, old_ref), (new_code, new_ref) = letters[test_email]
    assert old_ref != new_ref
    assert [r.id for r in _rows(test_email)] == [new_ref]       # прежняя запись удалена

    r = _by_ref(client, old_ref, old_code)
    assert r.status_code == 400 and r.json()["code"] == "registration_reference_invalid"
    r = _by_ref(client, new_ref, new_code)
    assert r.status_code == 201, r.text
    assert r.json() == {"message": "Регистрация завершена", "email": test_email}


def test_cooldown_rejection_keeps_old_issue(client, letters, test_email):
    _init(client, test_email)
    (before,) = _rows(test_email)
    r = _init(client, test_email)
    assert r.status_code == 429
    (after,) = _rows(test_email)
    assert (after.id, after.code, after.expires_at, after.attempts) == (
        before.id, before.code, before.expires_at, before.attempts,
    )
    assert len(letters[test_email]) == 1
    code, ref = letters[test_email][0]
    assert _by_ref(client, ref, code).status_code == 201


def test_rollback_of_issue_keeps_old_issue(client, letters, test_email):
    _init(client, test_email)
    (before,) = _rows(test_email)
    _skip_cooldown(test_email)
    # Сбой уже после удаления прежней записи в сессии, но до commit.
    with patch.object(otp_service.uuid, "uuid4", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError):
            otp_service.issue_registration_otp(test_email, "Имя Фамилия", "bcrypt$x")
    (after,) = _rows(test_email)
    assert after.id == before.id and after.code == before.code
    code, ref = letters[test_email][0]
    assert _by_ref(client, ref, code).status_code == 201


def test_smtp_failure_after_commit_keeps_new_issue(client, letters, test_email):
    _init(client, test_email)
    (old_code, old_ref), = letters[test_email]
    _skip_cooldown(test_email)
    issued = {}
    real_issue = otp_service.issue_registration_otp

    def _spy_issue(*a, **kw):
        issued["issue"] = real_issue(*a, **kw)
        return issued["issue"]

    with patch.object(otp_service, "issue_registration_otp", side_effect=_spy_issue), \
         patch("app.services.email_service.send_email", side_effect=OSError("smtp down")):
        r = _init(client, test_email)
    assert r.status_code == 500
    new = issued["issue"]
    assert [row.id for row in _rows(test_email)] == [new.registration_reference]
    assert _by_ref(client, old_ref, old_code).json()["code"] == "registration_reference_invalid"
    assert _by_ref(client, new.registration_reference, new.code).status_code == 201


def test_init_for_registered_email_after_lock_is_409(client, letters, test_email):
    _init(client, test_email)
    code, ref = letters[test_email][0]
    assert _by_ref(client, ref, code).status_code == 201
    with pytest.raises(auth_service.AuthError) as ei:
        with patch.object(auth_service.storage, "email_exists_any", return_value=False):
            auth_service.register_init("Имя Фамилия", test_email, PASSWORD)
    assert ei.value.status_code == 409
    assert _rows(test_email) == []


# ── Confirm ──────────────────────────────────────────────────────────────────

def test_inline_email_contract_still_works_without_email_in_response(client, letters, test_email):
    _init(client, test_email)
    code, _ = letters[test_email][0]
    r = client.post(CONFIRM, json={"email": test_email, "code": code})
    assert r.status_code == 201, r.text
    assert r.json() == {"message": "Регистрация завершена"}
    assert _users(test_email) == 1 and _rows(test_email) == []


def test_reference_success_consumes_and_used_reference_dead(client, letters, test_email):
    _init(client, test_email)
    code, ref = letters[test_email][0]
    r = _by_ref(client, ref, code)
    assert r.status_code == 201
    assert r.json()["email"] == test_email
    assert _users(test_email) == 1 and _rows(test_email) == []
    again = _by_ref(client, ref, code)
    assert again.status_code == 400
    assert again.json()["code"] == "registration_reference_invalid"
    assert _users(test_email) == 1


def test_unknown_reference(client):
    r = _by_ref(client, "8a62d590-71a1-4b17-90f7-4a5ff0c9d782", "123456")
    assert r.status_code == 400
    assert r.json() == {
        "detail": "Ссылка недействительна или срок её действия истёк. "
                  "Начните регистрацию заново.",
        "code": "registration_reference_invalid",
    }


@pytest.mark.parametrize("body", [
    {"code": "123456"},
    {"email": "integ_x@donnu.ru", "registration_reference":
        "8a62d590-71a1-4b17-90f7-4a5ff0c9d782", "code": "123456"},
    {"registration_reference": "not-a-uuid", "code": "123456"},
    {"registration_reference": "8a62d590-71a1-4b17-90f7-4a5ff0c9d782", "code": "12345"},
])
def test_malformed_bodies_rejected(client, body):
    assert client.post(CONFIRM, json=body).status_code == 422


def test_expired_code_then_reference_dead(client, letters, test_email):
    _init(client, test_email)
    code, ref = letters[test_email][0]
    with SessionLocal() as db:
        db.query(OtpVerification).filter(OtpVerification.id == ref).update(
            {"expires_at": otp_service._utcnow() - timedelta(seconds=1)})
        db.commit()
    r = _by_ref(client, ref, code)
    assert r.status_code == 400 and r.json()["code"] == "otp_expired"
    assert _rows(test_email) == []
    assert _by_ref(client, ref, code).json()["code"] == "registration_reference_invalid"
    assert _users(test_email) == 0


def test_wrong_code_counts_attempts_then_exhausted(client, letters, test_email):
    _init(client, test_email)
    code, ref = letters[test_email][0]
    for left in range(otp_service.MAX_ATTEMPTS - 1, 0, -1):
        r = _by_ref(client, ref, _wrong(code))
        assert r.status_code == 400 and r.json()["code"] == "otp_invalid"
        assert f"Осталось попыток: {left}" in r.json()["detail"]
    r = _by_ref(client, ref, _wrong(code))
    assert r.json()["code"] == "otp_attempts_exhausted"
    assert _rows(test_email) == []
    # Верный код после исчерпания уже ничего не подтверждает.
    assert _by_ref(client, ref, code).json()["code"] == "registration_reference_invalid"
    assert _users(test_email) == 0


def test_leading_zero_code(client, letters, test_email):
    with patch.object(otp_service, "_new_code", return_value="000123"):
        _init(client, test_email)
    code, ref = letters[test_email][0]
    assert code == "000123"
    assert _by_ref(client, ref, "000123").status_code == 201


@pytest.mark.parametrize("flow", ["reset", "social"])
def test_passwordless_rows_not_usable_by_ordinary_confirm(client, test_email, flow):
    # reset-OTP и код регистрации через провайдера хранятся без хеша пароля.
    code = otp_service.create_or_update_otp(test_email, "Имя Фамилия", None)
    (row,) = _rows(test_email)

    r = _by_ref(client, row.id, code)
    assert r.status_code == 400 and r.json()["code"] == "registration_reference_invalid"
    r = client.post(CONFIRM, json={"email": test_email, "code": code})
    assert r.status_code == 400 and r.json()["code"] == "otp_invalid"

    (still,) = _rows(test_email)
    assert still.id == row.id and still.attempts == 0        # попытки не потрачены
    assert _users(test_email) == 0


def test_legacy_duplicates_choose_newest_deterministically(client, test_email):
    now = otp_service._utcnow()
    with SessionLocal() as db:
        for i, plain in enumerate(["111111", "222222"]):
            db.add(OtpVerification(
                email=test_email, code=otp_service._hash_code(plain), name="Имя Фамилия",
                password_hash="bcrypt$x", attempts=0, expires_at=now + timedelta(minutes=10),
                created_at=now - timedelta(seconds=60 - i), last_sent_at=now - timedelta(seconds=60 - i),
            ))
        db.commit()
    newest = max(_rows(test_email), key=lambda r: r.last_sent_at)
    r = client.post(CONFIRM, json={"email": test_email, "code": "111111"})
    assert r.status_code == 400 and r.json()["code"] == "otp_invalid"
    attempts = {row.id: row.attempts for row in _rows(test_email)}
    assert attempts[newest.id] == 1 and sum(attempts.values()) == 1
    r = client.post(CONFIRM, json={"email": test_email, "code": "222222"})
    assert r.status_code == 201


# ── Параллельные запросы ─────────────────────────────────────────────────────

def _run_parallel(calls):
    barrier = threading.Barrier(len(calls))

    def _task(fn):
        barrier.wait()
        try:
            return ("ok", fn())
        except Exception as exc:   # noqa: BLE001 - собираем исходы потоков
            return ("error", exc)

    with ThreadPoolExecutor(max_workers=len(calls)) as pool:
        return list(pool.map(_task, calls))


def _confirm_ref(ref, code):
    return lambda: auth_service.register_confirm(code=code, registration_reference=ref)


def test_parallel_init_one_row(client, letters, test_email):
    results = _run_parallel([
        lambda: auth_service.register_init("Имя Фамилия", test_email, PASSWORD)
        for _ in range(THREADS)
    ])
    ok = [r for kind, r in results if kind == "ok"]
    errors = [r for kind, r in results if kind == "error"]
    assert len(ok) == 1
    assert all(isinstance(e, auth_service.AuthError) and e.status_code == 429 for e in errors)
    (row,) = _rows(test_email)
    assert [ref for _, ref in letters[test_email]] == [row.id]


def test_parallel_init_after_cooldown_one_row(client, letters, test_email):
    _init(client, test_email)
    _skip_cooldown(test_email)
    _run_parallel([
        lambda: auth_service.register_init("Имя Фамилия", test_email, PASSWORD)
        for _ in range(THREADS)
    ])
    (row,) = _rows(test_email)
    assert letters[test_email][-1][1] == row.id


def test_parallel_confirm_same_reference_one_user(client, letters, test_email):
    _init(client, test_email)
    code, ref = letters[test_email][0]
    results = _run_parallel([_confirm_ref(ref, code) for _ in range(THREADS)])
    ok = [r for kind, r in results if kind == "ok"]
    errors = [r for kind, r in results if kind == "error"]
    assert len(ok) == 1 and ok[0]["email"] == test_email
    assert {e.error_code for e in errors} == {"registration_reference_invalid"}
    assert _users(test_email) == 1 and _rows(test_email) == []


def test_parallel_confirm_reference_and_email_one_user(client, letters, test_email):
    _init(client, test_email)
    code, ref = letters[test_email][0]
    results = _run_parallel([
        _confirm_ref(ref, code),
        lambda: auth_service.register_confirm(email=test_email, code=code),
    ])
    assert sum(kind == "ok" for kind, _ in results) == 1
    assert _users(test_email) == 1 and _rows(test_email) == []


def test_parallel_init_and_confirm_consistent(client, letters, test_email):
    _init(client, test_email)
    code, ref = letters[test_email][0]
    _skip_cooldown(test_email)
    results = _run_parallel([
        _confirm_ref(ref, code),
        lambda: auth_service.register_init("Имя Фамилия", test_email, PASSWORD),
    ])
    (confirm_kind, confirm_res), (init_kind, init_res) = results
    rows = _rows(test_email)
    if confirm_kind == "ok":
        # confirm первым: пользователь создан, новый выпуск отклонён (409).
        assert _users(test_email) == 1 and rows == []
        assert init_kind == "error" and init_res.status_code == 409
    else:
        # init первым: прежний reference заменён, действует только новый.
        assert confirm_res.error_code == "registration_reference_invalid"
        assert init_kind == "ok" and _users(test_email) == 0
        assert [r.id for r in rows] == [letters[test_email][-1][1]] != [ref]


# ── Аудит ────────────────────────────────────────────────────────────────────

def test_audit_success_and_reference_failure_without_secrets(client, letters, test_email, caplog):
    caplog.set_level(logging.DEBUG)
    _init(client, test_email)
    code, ref = letters[test_email][0]
    mark = _auth_mark()

    unknown = "0f8f2f44-2a8e-4c1e-9d55-0c3b1d1e2a77"
    assert _by_ref(client, unknown, code).status_code == 400
    assert _by_ref(client, ref, _wrong(code)).status_code == 400
    assert _by_ref(client, ref, code).status_code == 201

    failed = _auth_rows_since(mark, "registration_failed")
    assert [(r.failure_reason, r.user_email) for r in failed] == [
        ("registration_reference_invalid", None),
        ("otp_invalid", test_email),
    ]
    (ok,) = _auth_rows_since(mark, "registration_succeeded")
    assert ok.user_email == test_email and ok.user_id is not None
    for row in failed + [ok]:
        dumped = repr({c.name: getattr(row, c.name) for c in AuthLog.__table__.columns})
        assert ref not in dumped and unknown not in dumped and code not in dumped
    assert ref not in caplog.text and unknown not in caplog.text and code not in caplog.text


def test_reference_failure_rollback_keeps_issue(client, letters, test_email):
    # Сбой core-шага после верного кода: регистрация откатывается, выпуск цел.
    _init(client, test_email)
    code, ref = letters[test_email][0]
    with patch.object(auth_storage, "enqueue_registration_invite_in_tx",
                      side_effect=RuntimeError("core failure")):
        with pytest.raises(RuntimeError):
            auth_service.register_confirm(code=code, registration_reference=ref)
    assert _users(test_email) == 0
    (row,) = _rows(test_email)
    assert row.id == ref and row.attempts == 0
    assert _by_ref(client, ref, code).status_code == 201


def test_audit_writer_failure_does_not_break_registration(client, letters, test_email, monkeypatch):
    _init(client, test_email)
    code, ref = letters[test_email][0]

    def _no_audit_db():
        raise RuntimeError("audit db down")

    monkeypatch.setattr(audit_service, "SessionLocal", _no_audit_db)
    r = _by_ref(client, ref, code)
    assert r.status_code == 201 and r.json()["email"] == test_email
    assert _users(test_email) == 1


# ── Время после ожидания lock ────────────────────────────────────────────────
#
# Запрос ждёт advisory lock по email, который держит другая транзакция; пока
# он ждёт, контролируемые часы переходят через срок кода / конец cooldown.
# Решение обязано приниматься по времени ПОСЛЕ получения lock.
#
# Ожидание подтверждается по pg_locks ИМЕННО для проверяемой транзакции:
# backend PID её соединения (pg_backend_pid() в той же сессии, что затем зовёт
# lock_email_otp) + ключ lock этого email + текущая БД. Посторонний waiter
# сигнал не даёт (см. test_foreign_waiter_does_not_trigger_on_waiting).

# Настоящий lock - до любых monkeypatch (держатель lock им пользуется напрямую).
_REAL_LOCK_EMAIL_OTP = otp_service.lock_email_otp
_OID_MASK = 0xFFFFFFFF   # pg_locks.classid/objid - oid (беззнаковые 32 бита)


class _Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


def _email_lock_ids(email):
    """(key1, key2) pg_advisory_xact_lock(int4, int4) - тем же кодом, что у
    lock_email_otp, без повторения алгоритма."""
    return (otp_service._OTP_EMAIL_LOCK_KEY1,
            otp_service._email_lock_key(normalize_email(email)))


def _waits_on(pid, lock_ids):
    """PID ждёт (NOT granted) именно advisory lock (key1, key2) в этой БД.
    Двухаргументная форма: classid=key1, objid=key2, objsubid=2."""
    key1, key2 = lock_ids
    with SessionLocal() as db:
        return bool(db.execute(sa.text(
            "SELECT EXISTS (SELECT 1 FROM pg_locks"
            " WHERE locktype = 'advisory' AND NOT granted AND pid = :pid"
            "   AND database = (SELECT oid FROM pg_database"
            "                   WHERE datname = current_database())"
            "   AND classid::bigint = :c AND objid::bigint = :o AND objsubid = 2)"
        ), {"pid": pid, "c": key1 & _OID_MASK, "o": key2 & _OID_MASK}).scalar())


def _when_target_waits(pid, lock_ids, on_waiting, *, on_poll=None, deadline_s=15):
    """on_waiting() - ровно тогда, когда pid ждёт именно lock_ids. Без пауз:
    каждый шаг - запрос к pg_locks; on_poll() - после каждой отрицательной
    проверки (для теста самого helper)."""
    end = time.monotonic() + deadline_s
    while time.monotonic() < end:
        if _waits_on(pid, lock_ids):
            on_waiting()
            return
        if on_poll is not None:
            on_poll()
    raise AssertionError("целевая транзакция не встала в ожидание своего lock")


class _LockProbe:
    """Подменяет lock_email_otp (в otp_service и storage) обёрткой: сначала
    pg_backend_pid() в ТОЙ ЖЕ сессии, что затем ждёт lock, затем - по желанию
    - остановка на gate, затем настоящий lock. Production-код не меняется."""

    def __init__(self, monkeypatch, gate=None):
        self.pid = None
        self.reported = threading.Event()
        self._gate = gate

        def _probe(db, email):
            self.pid = db.execute(sa.text("SELECT pg_backend_pid()")).scalar()
            self.reported.set()
            if self._gate is not None:
                assert self._gate.wait(30)
            return _REAL_LOCK_EMAIL_OTP(db, email)

        monkeypatch.setattr(otp_service, "lock_email_otp", _probe)
        monkeypatch.setattr(auth_storage, "lock_email_otp", _probe)


def _hold_advisory_lock(lock_ids, held, release, pid_box=None, pid_ready=None):
    """Держит advisory lock (key1, key2) до release. pid_box/pid_ready - PID
    соединения, которое затем берёт (или ждёт) этот lock."""
    with SessionLocal() as db:
        if pid_box is not None:
            pid_box.append(db.execute(sa.text("SELECT pg_backend_pid()")).scalar())
            pid_ready.set()
        db.execute(sa.text("SELECT pg_advisory_xact_lock(:k1, :k2)"),
                   {"k1": lock_ids[0], "k2": lock_ids[1]})
        held.set()
        release.wait(timeout=30)
        db.rollback()


def _hold_email_lock(email, held, release):
    with SessionLocal() as db:
        _REAL_LOCK_EMAIL_OTP(db, email)
        held.set()
        release.wait(timeout=30)
        db.rollback()


def _run_while_lock_held(monkeypatch, email, fn, on_waiting):
    """fn() в отдельном потоке, пока lock email держит другая транзакция;
    on_waiting() - когда соединение fn() уже ждёт ИМЕННО этот lock; затем
    lock отпускается."""
    held, release = threading.Event(), threading.Event()
    holder = threading.Thread(target=_hold_email_lock, args=(email, held, release))
    holder.start()
    probe = _LockProbe(monkeypatch)
    try:
        assert held.wait(15)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(fn)
            assert probe.reported.wait(15), "fn() не дошла до lock_email_otp"
            _when_target_waits(probe.pid, _email_lock_ids(email), on_waiting)
            release.set()
            try:
                return ("ok", future.result(timeout=30))
            except Exception as exc:   # noqa: BLE001 - исход проверяет тест
                return ("error", exc)
    finally:
        release.set()
        holder.join(15)


def test_foreign_waiter_does_not_trigger_on_waiting(client, test_email, monkeypatch):
    """Посторонний waiter (другой PID и другой ключ) не даёт сигнала: сигнал -
    только когда целевая транзакция ждёт свой lock."""
    foreign_ids = _email_lock_ids(f"foreign-{test_email}")       # lock A
    target_ids = _email_lock_ids(test_email)                     # lock B
    assert foreign_ids != target_ids
    releases = []

    def _spawn_holder(lock_ids, pid_box=None, pid_ready=None):
        held, release = threading.Event(), threading.Event()
        t = threading.Thread(target=_hold_advisory_lock,
                             args=(lock_ids, held, release, pid_box, pid_ready))
        t.start()
        releases.append((release, t))
        return held

    gate = threading.Event()
    calls = []
    negative_polls = threading.Event()
    try:
        # 1-2. Посторонний lock A и постороннее соединение, которое его ждёт.
        assert _spawn_holder(foreign_ids).wait(15)
        foreign_pid, foreign_pid_ready = [], threading.Event()
        _spawn_holder(foreign_ids, foreign_pid, foreign_pid_ready)   # ждёт A
        assert foreign_pid_ready.wait(15)
        foreign_waiting = threading.Event()
        _when_target_waits(foreign_pid[0], foreign_ids, foreign_waiting.set)
        assert foreign_waiting.is_set()

        # Lock B держит другая транзакция - целевому worker будет кого ждать.
        assert _spawn_holder(target_ids).wait(15)

        # 3. Целевой worker остановлен на gate ДО вызова настоящего lock_email_otp.
        probe = _LockProbe(monkeypatch, gate=gate)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                otp_service.create_or_update_otp, test_email, "Имя Фамилия", None,
            )
            assert probe.reported.wait(15)
            target_pid = probe.pid
            assert target_pid != foreign_pid[0]
            # Прежний глобальный признак («любой NOT granted advisory») здесь
            # уже сработал бы - а целевая транзакция ещё ничего не ждёт.
            with SessionLocal() as db:
                any_waiter = db.execute(sa.text(
                    "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND NOT granted"
                )).scalar()
            assert any_waiter >= 1
            assert not _waits_on(target_pid, target_ids)

            # 4-5. Helper наблюдает pg_locks, пока worker стоит на gate: ни одного
            # вызова on_waiting, хотя посторонний waiter есть.
            def _on_waiting():
                calls.append(_waits_on(target_pid, target_ids))

            def _on_poll():
                negative_polls.set()
                if not gate.is_set():
                    assert calls == []
                    gate.set()           # 6. worker продолжает - к своему lock B

            # 7-8. Сигнал - только когда worker ждёт именно B.
            _when_target_waits(target_pid, target_ids, _on_waiting, on_poll=_on_poll)
            assert negative_polls.is_set()
            assert calls == [True]
            for release, _ in releases:
                release.set()
            future.result(timeout=30)
    finally:
        gate.set()
        for release, t in releases:
            release.set()
            t.join(15)


@pytest.mark.parametrize("mode", ["reference", "email"])
def test_code_expiring_while_waiting_for_lock_is_expired(
    client, letters, test_email, monkeypatch, mode,
):
    _init(client, test_email)
    code, ref = letters[test_email][0]
    base = otp_service._utcnow()
    with SessionLocal() as db:
        db.query(OtpVerification).filter(OtpVerification.id == ref).update(
            {"expires_at": base + timedelta(seconds=30)})
        db.commit()
    clock = _Clock(base)                       # до ожидания lock код ещё действует
    monkeypatch.setattr(auth_storage, "_utcnow", clock)

    if mode == "reference":
        def confirm():
            return auth_service.register_confirm(code=code, registration_reference=ref)
    else:
        def confirm():
            return auth_service.register_confirm(email=test_email, code=code)

    def _expire():
        clock.now = base + timedelta(seconds=60)

    kind, result = _run_while_lock_held(monkeypatch, test_email, confirm, _expire)
    assert kind == "error", "истёкший во время ожидания lock код принят"
    assert result.error_code == "otp_expired"
    assert _users(test_email) == 0 and _rows(test_email) == []


def test_registration_cooldown_ending_while_waiting_for_lock(
    client, letters, test_email, monkeypatch,
):
    _init(client, test_email)
    (old,) = _rows(test_email)
    base = otp_service._utcnow()
    with SessionLocal() as db:
        db.query(OtpVerification).filter(OtpVerification.id == old.id).update(
            {"last_sent_at": base})
        db.commit()
    clock = _Clock(base + timedelta(seconds=30))     # cooldown ещё действует
    monkeypatch.setattr(otp_service, "_utcnow", clock)
    decided_at = base + timedelta(seconds=120)

    def _pass_cooldown():
        clock.now = decided_at

    kind, issue = _run_while_lock_held(
        monkeypatch, test_email,
        lambda: otp_service.issue_registration_otp(test_email, "Имя Фамилия", "bcrypt$x"),
        _pass_cooldown,
    )
    assert kind == "ok", issue
    (row,) = _rows(test_email)
    assert row.id == issue.registration_reference != old.id
    # Срок и время отправки - от того же момента решения после lock.
    assert row.last_sent_at == decided_at == row.created_at
    assert row.expires_at == decided_at + otp_service.OTP_TTL


def test_shared_issue_helper_cooldown_ending_while_waiting_for_lock(
    client, test_email, monkeypatch,
):
    # create_or_update_otp_in_tx - общий выпуск кода (reset, регистрация через
    # провайдера); здесь через create_or_update_otp, как у password_reset_init.
    otp_service.create_or_update_otp(test_email, "Имя Фамилия", None)
    base = otp_service._utcnow()
    with SessionLocal() as db:
        db.query(OtpVerification).filter(OtpVerification.email == test_email).update(
            {"last_sent_at": base})
        db.commit()
    clock = _Clock(base + timedelta(seconds=30))
    monkeypatch.setattr(otp_service, "_utcnow", clock)
    decided_at = base + timedelta(seconds=120)

    def _pass_cooldown():
        clock.now = decided_at

    kind, result = _run_while_lock_held(
        monkeypatch, test_email,
        lambda: otp_service.create_or_update_otp(test_email, "Имя Фамилия", None),
        _pass_cooldown,
    )
    assert kind == "ok", result
    (row,) = _rows(test_email)
    assert row.last_sent_at == decided_at
    assert row.expires_at == decided_at + otp_service.OTP_TTL


def test_cooldown_still_active_after_lock_is_rejected(client, letters, test_email, monkeypatch):
    # Обратный случай: ожидание lock не продлевает и не обходит cooldown.
    _init(client, test_email)
    (old,) = _rows(test_email)
    base = otp_service._utcnow()
    with SessionLocal() as db:
        db.query(OtpVerification).filter(OtpVerification.id == old.id).update(
            {"last_sent_at": base})
        db.commit()
    clock = _Clock(base + timedelta(seconds=10))
    monkeypatch.setattr(otp_service, "_utcnow", clock)

    def _still_cooldown():
        clock.now = base + timedelta(seconds=40)

    kind, exc = _run_while_lock_held(
        monkeypatch, test_email,
        lambda: otp_service.issue_registration_otp(test_email, "Имя Фамилия", "bcrypt$x"),
        _still_cooldown,
    )
    assert kind == "error" and "через 20 с" in str(exc)
    (row,) = _rows(test_email)
    assert row.id == old.id
