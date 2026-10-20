"""
Stage Social Auth 2B — конкурентность social login core на реальном PostgreSQL.

  * параллельные callback с одним state → ровно один login-ticket;
  * параллельные complete с одним ticket → ровно одна сессия;
  * первый complete падает технически (rollback) → второй вправе завершить
    вход, но сессия всё равно ровно одна.

Потоки вызывают service напрямую (TestClient не потокобезопасен); у каждого
вызова своя SessionLocal-транзакция — сериализацию обеспечивает блокировка
строки в UPDATE ... RETURNING.
"""
import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.db.models import OAuthAuthRequest, OAuthPendingTicket, UserOAuthIdentity, UserSession
from app.db.session import SessionLocal
from app.oauth import service as oauth_service
from app.oauth import storage as oauth_storage
from app.oauth.errors import OAuthTicketInvalidError
from tests.integration.conftest import create_test_user
from tests.oauth_fakes import FakeProvider, registered, state_from_authorize_url

THREADS = 4


@pytest.fixture(autouse=True)
def _cleanup_userless_rows(client):
    yield
    with SessionLocal() as db:
        db.query(OAuthAuthRequest).filter(OAuthAuthRequest.user_id.is_(None)).delete()
        db.query(OAuthPendingTicket).filter(OAuthPendingTicket.user_id.is_(None)).delete()
        db.commit()


@pytest.fixture
def fake():
    with registered(FakeProvider("yandex")) as provider:
        yield provider


def _link(email, fake) -> int:
    user_id = int(create_test_user(email)["id"])
    with SessionLocal() as db:
        db.add(UserOAuthIdentity(user_id=user_id, provider="yandex", provider_subject=fake.subject))
        db.commit()
    return user_id


def _run_parallel(fn, n=THREADS):
    barrier = threading.Barrier(n)

    def _task(_):
        barrier.wait()
        try:
            return ("ok", fn())
        except Exception as exc:   # noqa: BLE001 — собираем исходы потоков
            return ("error", exc)

    with ThreadPoolExecutor(max_workers=n) as pool:
        return list(pool.map(_task, range(n)))


def _ticket_for(fake) -> str:
    start = oauth_service.start_login("yandex")
    state = start.state
    outcome = oauth_service.handle_callback(
        "yandex", {"state": state, "code": fake.issue_code(state)}, state,
    )
    assert outcome.fragment.get("result") == "login", outcome.fragment
    return outcome.fragment["ticket"]


def _sessions(user_id) -> int:
    with SessionLocal() as db:
        return db.query(UserSession).filter(UserSession.user_id == user_id).count()


def test_parallel_callbacks_issue_exactly_one_ticket(client, fake, test_email):
    user_id = _link(test_email, fake)
    start = oauth_service.start_login("yandex")
    state = state_from_authorize_url(start.authorize_url)
    query = {"state": state, "code": fake.issue_code(state)}

    results = _run_parallel(lambda: oauth_service.handle_callback("yandex", query, state))

    fragments = [res.fragment for kind, res in results if kind == "ok"]
    assert len(fragments) == THREADS                       # никто не упал исключением
    assert sum("ticket" in f for f in fragments) == 1
    assert sum(f == {"error": "oauth_failed"} for f in fragments) == THREADS - 1
    with SessionLocal() as db:
        assert db.query(OAuthPendingTicket).filter_by(user_id=user_id).count() == 1
    assert fake.resolve_calls == 1                         # провайдер вызван один раз


def test_parallel_complete_creates_exactly_one_session(client, fake, test_email):
    user_id = _link(test_email, fake)
    ticket = _ticket_for(fake)

    results = _run_parallel(lambda: oauth_service.complete_login(ticket))

    successes = [res for kind, res in results if kind == "ok"]
    failures = [res for kind, res in results if kind == "error"]
    assert len(successes) == 1
    assert len(failures) == THREADS - 1
    assert all(isinstance(exc, OAuthTicketInvalidError) for exc in failures)
    assert _sessions(user_id) == 1


def test_rollback_of_first_complete_lets_exactly_one_other_succeed(
    client, fake, test_email, monkeypatch,
):
    user_id = _link(test_email, fake)
    ticket = _ticket_for(fake)
    original = oauth_storage.create_session_in_tx
    lock = threading.Lock()
    failed = {"done": False}

    def _fail_first_call(*args, **kwargs):
        with lock:
            if not failed["done"]:
                failed["done"] = True
                raise RuntimeError("transient session insert failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(oauth_storage, "create_session_in_tx", _fail_first_call)

    results = _run_parallel(lambda: oauth_service.complete_login(ticket))

    kinds = [kind for kind, _ in results]
    errors = [exc for kind, exc in results if kind == "error"]
    assert kinds.count("ok") == 1
    assert sum(isinstance(e, RuntimeError) for e in errors) == 1
    assert sum(isinstance(e, OAuthTicketInvalidError) for e in errors) == THREADS - 2
    assert _sessions(user_id) == 1
    with SessionLocal() as db:
        row = db.get(OAuthPendingTicket, hashlib.sha256(ticket.encode()).hexdigest())
        assert row.consumed_at is not None
