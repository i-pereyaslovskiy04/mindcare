"""
Доработка ADR-029 (2026-10-13) — gated integration на реальном PostgreSQL
(isolated runner): счётчик очереди и полная история подтверждения в карточке.

Счётчик GET /api/supervisor/student-verifications/pending-count:
  * число = заявки status='pending' (те же критерии, что очередь), меняется
    после подачи и решения;
  * доступ: supervisor и прямой admin+supervisor — 200; admin без supervisor,
    psychologist, student, impersonation-сессия supervisor'а — 403;
  * без аудита (ни одной строки ни в одном журнале), Cache-Control no-store;
  * статический маршрут не перехватывается /{request_uuid}.

История (карточка + GET …/{uuid}/history?before=&size=):
  * все заявки пользователя от новых к старым, включая текущую — ровно раз;
  * «подана» — только самая ранняя заявка (в любой порции), далее «подана
    повторно»; решения — с проверявшим и пояснением отказа; одобрение — без
    причины; проверявший недоступен → actor null;
  * без исторических номеров билетов; без чужих заявок; курсор чужой заявки
    → 404;
  * content_read — по одному на каждую заявку с раскрытым пояснением,
    текущая заявка карточки не дублируется; порция без пояснений не аудируется;
  * keyset: новая подача между порциями не даёт дублей и пропусков;
  * fail-closed: сбой записи content_read на любом событии → 503 без номера
    и без пояснений.
"""
import json
import uuid as _uuid

import pytest
from sqlalchemy import update

import app.student_verification.service as sv_service
import app.student_verification.storage as sv_storage
from app.audit.contracts import AuditStorageError
from app.db.models import (
    AuditLog, AuthLog, DataChangeLog, StudentVerificationRequest as SVR, User,
)
from app.db.session import SessionLocal
from tests.integration.conftest import create_multi_role_user, create_test_user

PASSWORD = "SecurePass42!"
ME_URL = "/api/student-verification/me"
LIST_URL = "/api/supervisor/student-verifications"
COUNT_URL = f"{LIST_URL}/pending-count"


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _student(client=None):
    email = f"integ_svh_{_uuid.uuid4().hex[:10]}@example.com"
    uid = int(create_test_user(email, PASSWORD)["id"])
    token = None
    if client is not None:
        r = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
        assert r.status_code == 200, r.text
        token = r.json()["session_token"]
    return uid, token


def _supervisor(client, *extra):
    token, uid, _ = create_multi_role_user(client, ["supervisor", "student", *extra])
    return uid, token


def _uuid_of(user_id):
    with SessionLocal() as db:
        return str(db.get(User, user_id).uuid)


def _request_id(req_uuid):
    with SessionLocal() as db:
        return db.query(SVR.id).filter(SVR.uuid == req_uuid).scalar()


def _db_pending():
    with SessionLocal() as db:
        return db.query(SVR).filter(SVR.status == "pending").count()


def _marks():
    with SessionLocal() as db:
        return tuple(
            db.query(m.id).order_by(m.id.desc()).limit(1).scalar() or 0
            for m in (AuditLog, AuthLog, DataChangeLog)
        )


def _rows_since(marks):
    out = []
    with SessionLocal() as db:
        for model, mark in zip((AuditLog, AuthLog, DataChangeLog), marks):
            rows = db.query(model).filter(model.id > mark).order_by(model.id).all()
            for r in rows:
                db.expunge(r)
            out.append(rows)
    return out


def _content_reads(marks):
    audit, auth, dcl = _rows_since(marks)
    assert auth == [] and dcl == []
    assert all(a.event_type == "student_verification_content_read" for a in audit)
    return audit


def _submit(uid, faculty="law", ticket="000123"):
    return sv_storage.submit_atomic(uid, faculty_code=faculty, ticket_number=ticket)


def _reject(req, sup, reason):
    sv_storage.decide_atomic(_uuid.UUID(req["uuid"]), decision="reject",
                             reviewer_id=sup, reason=reason)


def _approve(req, sup):
    sv_storage.decide_atomic(_uuid.UUID(req["uuid"]), decision="approve",
                             reviewer_id=sup)


def _events(card_history):
    return [(i["uuid"], [e["type"] for e in i["events"]]) for i in card_history["items"]]


# ── счётчик ───────────────────────────────────────────────────────────────────

def test_pending_count_matches_queue_and_follows_decisions(client):
    sup_id, sup = _supervisor(client)
    uid, _ = _student()
    before = client.get(COUNT_URL, headers=_auth(sup))
    assert before.status_code == 200, before.text
    assert before.headers["cache-control"] == "no-store, private"
    assert set(before.json()) == {"count"}
    assert before.json()["count"] == _db_pending()
    queue_total = client.get(LIST_URL, headers=_auth(sup)).json()["total"]
    assert before.json()["count"] == queue_total

    req = _submit(uid)
    assert client.get(COUNT_URL, headers=_auth(sup)).json()["count"] == before.json()["count"] + 1
    _reject(req, sup_id, "Нет")
    assert client.get(COUNT_URL, headers=_auth(sup)).json()["count"] == before.json()["count"]


def test_pending_count_writes_no_journals(client):
    _, sup = _supervisor(client)
    _submit(_student()[0])
    marks = _marks()
    r = client.get(COUNT_URL, headers=_auth(sup))
    assert r.status_code == 200
    assert all(rows == [] for rows in _rows_since(marks))


def test_pending_count_access_matrix(client):
    _submit(_student()[0])
    admin_sup, _, _ = create_multi_role_user(client, ["admin", "supervisor"])
    assert client.get(COUNT_URL, headers=_auth(admin_sup)).status_code == 200
    for roles in (["admin"], ["psychologist"], ["student"]):
        token, _, _ = create_multi_role_user(client, roles)
        r = client.get(COUNT_URL, headers=_auth(token))
        assert r.status_code == 403, roles
        assert "count" not in r.json()
    assert client.get(COUNT_URL).status_code == 401


def test_pending_count_is_forbidden_in_impersonation(client):
    admin_token, _, _ = create_multi_role_user(client, ["admin"])
    sup_id, _ = _supervisor(client)
    r = client.post(f"/api/admin/users/{_uuid_of(sup_id)}/impersonate",
                    headers=_auth(admin_token))
    assert r.status_code == 200, r.text
    imp = r.json()["session_token"]
    marks = _marks()
    r = client.get(COUNT_URL, headers=_auth(imp))
    assert r.status_code == 403 and "count" not in r.json()
    audit, _, _ = _rows_since(marks)
    assert audit == []


# ── история ──────────────────────────────────────────────────────────────────

@pytest.fixture
def story(client):
    """
    Пользователь: подана → отклонена (причина A) → подана повторно →
    отклонена (причина B, проверявший затем «удалён»: reviewed_by NULL) →
    подана повторно (pending, текущая). Плюс чужая заявка другого пользователя.
    """
    sup_id, sup = _supervisor(client)
    other_sup_id, _ = _supervisor(client)
    uid, _ = _student()
    first = _submit(uid, faculty="law", ticket="T-FIRST-01")
    _reject(first, sup_id, "Причина A: номер не читается")
    second = _submit(uid, faculty="history", ticket="T-SECOND-02")
    _reject(second, other_sup_id, "Причина B: другой факультет")
    with SessionLocal() as db:            # имитация FK ON DELETE SET NULL
        db.execute(update(SVR).where(SVR.uuid == second["uuid"]).values(reviewed_by=None))
        db.commit()
    current = _submit(uid, faculty="economics", ticket="T-CURRENT-03")
    foreign = _submit(_student()[0], faculty="law", ticket="T-FOREIGN-04")
    return {"sup_id": sup_id, "sup": sup, "uid": uid, "first": first,
            "second": second, "current": current, "foreign": foreign}


def test_card_history_is_complete_chronological_and_minimal(client, story):
    marks = _marks()
    r = client.get(f"{LIST_URL}/{story['current']['uuid']}", headers=_auth(story["sup"]))
    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "no-store, private"
    card = r.json()
    history = card["history"]
    assert history["has_more"] is False and history["next_cursor"] is None
    assert _events(history) == [
        (story["current"]["uuid"], ["resubmitted"]),
        (story["second"]["uuid"], ["rejected", "resubmitted"]),
        (story["first"]["uuid"], ["rejected", "submitted"]),
    ]
    cur, second, first = history["items"]
    assert cur["is_current"] is True and not second["is_current"] and not first["is_current"]
    assert first["events"][0]["reason"] == "Причина A: номер не читается"
    assert first["events"][0]["actor"]["full_name"]
    assert second["events"][0]["reason"] == "Причина B: другой факультет"
    assert second["events"][0]["actor"] is None                # проверявший недоступен
    assert all(e["actor"]["full_name"] for e in cur["events"])   # заявитель
    assert [i["faculty"]["code"] for i in history["items"]] == ["economics", "history", "law"]

    raw = json.dumps(history, ensure_ascii=False)
    for secret in ("T-FIRST-01", "T-SECOND-02", "T-FOREIGN-04", "enc:v1:"):
        assert secret not in raw
    assert story["foreign"]["uuid"] not in r.text
    assert card["ticket_number"] == "T-CURRENT-03"

    # content_read: текущая (номер) + каждая прежняя заявка с пояснением.
    reads = _content_reads(marks)
    ids = [a.entity_id for a in reads]
    assert ids[0] == _request_id(story["current"]["uuid"])
    assert sorted(ids[1:]) == sorted([_request_id(story["first"]["uuid"]),
                                      _request_id(story["second"]["uuid"])])
    assert len(ids) == len(set(ids)) == 3
    assert all(a.user_id == story["sup_id"] and a.user_role == "supervisor"
               and a.outcome == "success" and a.log_metadata == {}
               and a.entity_type == "student_verification_request" for a in reads)


def test_card_of_decided_request_does_not_duplicate_its_own_read(client, story):
    """Текущая заявка — отклонённая: её пояснение и в карточке, и в строке
    истории, но событие одно."""
    marks = _marks()
    r = client.get(f"{LIST_URL}/{story['first']['uuid']}", headers=_auth(story["sup"]))
    assert r.status_code == 200
    body = r.json()
    assert body["rejection_reason"] == "Причина A: номер не читается"
    ids = [a.entity_id for a in _content_reads(marks)]
    assert ids.count(_request_id(story["first"]["uuid"])) == 1
    assert len(ids) == 2                       # first + second (current — pending)


def test_approved_request_shows_reviewer_without_reason(client):
    sup_id, sup = _supervisor(client)
    uid, _ = _student()
    req = _submit(uid)
    _approve(req, sup_id)
    marks = _marks()
    card = client.get(f"{LIST_URL}/{req['uuid']}", headers=_auth(sup)).json()
    (item,) = card["history"]["items"]
    assert [e["type"] for e in item["events"]] == ["approved", "submitted"]
    assert item["events"][0]["actor"]["full_name"] and item["events"][0]["reason"] is None
    assert [a.entity_id for a in _content_reads(marks)] == [_request_id(req["uuid"])]


def _many_rejected(n, sup_id):
    uid, _ = _student()
    reqs = []
    for i in range(n):
        req = _submit(uid, ticket=f"T-{i:03d}")
        _reject(req, sup_id, f"Причина {i:03d}")
        reqs.append(req)
    return uid, reqs


def test_more_history_by_cursor_is_complete_without_duplicates(client):
    sup_id, sup = _supervisor(client)
    uid, reqs = _many_rejected(12, sup_id)
    newest = reqs[-1]
    card = client.get(f"{LIST_URL}/{newest['uuid']}", headers=_auth(sup)).json()
    page1 = card["history"]
    assert len(page1["items"]) == 10 and page1["has_more"] is True
    assert page1["next_cursor"] == page1["items"][-1]["uuid"]

    # Новая подача между порциями — не сдвигает keyset-границу.
    fresh = _submit(uid, ticket="T-NEW")
    marks = _marks()
    r = client.get(f"{LIST_URL}/{newest['uuid']}/history", headers=_auth(sup),
                   params={"before": page1["next_cursor"], "size": 10})
    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "no-store, private"
    page2 = r.json()
    assert page2["has_more"] is False and page2["next_cursor"] is None
    loaded = [i["uuid"] for i in page1["items"] + page2["items"]]
    assert loaded == [q["uuid"] for q in reversed(reqs)]       # все, по порядку
    assert len(loaded) == len(set(loaded)) and fresh["uuid"] not in loaded
    # «подана» — только у самой ранней заявки, и она во второй порции.
    kinds = [e["type"] for i in page1["items"] + page2["items"] for e in i["events"]]
    assert kinds.count("submitted") == 1
    assert page2["items"][-1]["events"][-1]["type"] == "submitted"
    assert all(i["is_current"] is False for i in page2["items"])
    # Аудит порции: по событию на каждое раскрытое пояснение (2 заявки).
    ids = sorted(a.entity_id for a in _content_reads(marks))
    assert ids == sorted(_request_id(q["uuid"]) for q in reqs[:2])
    assert "T-000" not in r.text and "enc:v1:" not in r.text


def test_more_history_portion_without_reasons_is_not_audited(client):
    sup_id, sup = _supervisor(client)
    uid, _ = _student()
    req = _submit(uid)
    _approve(req, sup_id)
    marks = _marks()
    r = client.get(f"{LIST_URL}/{req['uuid']}/history", headers=_auth(sup))
    assert r.status_code == 200
    assert [i["uuid"] for i in r.json()["items"]] == [req["uuid"]]
    assert all(rows == [] for rows in _rows_since(marks))


def test_foreign_cursor_and_unknown_request_are_404(client, story):
    url = f"{LIST_URL}/{story['current']['uuid']}/history"
    marks = _marks()
    r = client.get(url, headers=_auth(story["sup"]),
                   params={"before": story["foreign"]["uuid"]})
    assert r.status_code == 404 and r.json()["code"] == "verification_not_found"
    r = client.get(url, headers=_auth(story["sup"]),
                   params={"before": str(_uuid.uuid4())})
    assert r.status_code == 404
    r = client.get(f"{LIST_URL}/{_uuid.uuid4()}/history", headers=_auth(story["sup"]))
    assert r.status_code == 404
    assert client.get(url, headers=_auth(story["sup"]),
                      params={"before": "not-a-uuid"}).status_code == 422
    assert client.get(url, headers=_auth(story["sup"]),
                      params={"size": 51}).status_code == 422
    assert all(rows == [] for rows in _rows_since(marks))


@pytest.mark.parametrize("roles", [["admin"], ["psychologist"], ["student"]])
def test_history_requires_supervisor(client, story, roles):
    token, _, _ = create_multi_role_user(client, roles)
    r = client.get(f"{LIST_URL}/{story['current']['uuid']}/history", headers=_auth(token))
    assert r.status_code == 403 and "Причина" not in r.text


def test_history_is_forbidden_in_impersonation(client, story):
    admin_token, _, _ = create_multi_role_user(client, ["admin"])
    sup_id, _ = _supervisor(client)
    imp = client.post(f"/api/admin/users/{_uuid_of(sup_id)}/impersonate",
                      headers=_auth(admin_token)).json()["session_token"]
    marks = _marks()
    r = client.get(f"{LIST_URL}/{story['current']['uuid']}/history", headers=_auth(imp))
    assert r.status_code == 403 and "Причина" not in r.text
    audit, _, _ = _rows_since(marks)
    assert audit == []


@pytest.mark.parametrize("fail_on", [1, 2, 3])
def test_card_audit_failure_reveals_neither_ticket_nor_reasons(
    client, story, monkeypatch, fail_on,
):
    real = sv_service.record_event
    calls = []

    def _flaky(**kwargs):
        calls.append(kwargs)
        if len(calls) == fail_on:
            raise AuditStorageError("audit storage failure")
        return real(**kwargs)
    monkeypatch.setattr(sv_service, "record_event", _flaky)
    r = client.get(f"{LIST_URL}/{story['current']['uuid']}", headers=_auth(story["sup"]))
    assert r.status_code == 503
    for secret in ("T-CURRENT-03", "Причина A", "Причина B", "enc:v1:"):
        assert secret not in r.text


def test_more_history_audit_failure_reveals_no_reasons(client, monkeypatch):
    sup_id, sup = _supervisor(client)
    _, reqs = _many_rejected(12, sup_id)
    card = client.get(f"{LIST_URL}/{reqs[-1]['uuid']}", headers=_auth(sup)).json()

    def _fail(**kwargs):
        raise AuditStorageError("audit storage failure")
    monkeypatch.setattr(sv_service, "record_event", _fail)
    r = client.get(f"{LIST_URL}/{reqs[-1]['uuid']}/history", headers=_auth(sup),
                   params={"before": card["history"]["next_cursor"]})
    assert r.status_code == 503 and "Причина" not in r.text
