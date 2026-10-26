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
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import func

from app.audit import service as audit_service
from app.auth import otp_service, service as auth_service, storage as auth_storage
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
