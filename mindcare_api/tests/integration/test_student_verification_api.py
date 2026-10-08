"""
ADR-029 — gated integration: подтверждение статуса студента ДонГУ на реальном
PostgreSQL (isolated runner).

Покрывает:
  * каталог — любому аутентифицированному (в т.ч. без student), без сессии 401;
  * все 12 факультетов; произвольный факультет, пустой/длинный номер → 422;
    ведущие нули сохраняются, в БД только `enc:v1:`;
  * self-service: только чистый student; staff+student и impersonation → 403 +
    точный failure-audit (при impersonation actor — admin-инициатор);
  * pending неизменяема, повторная подача → 409; после отказа — новая заявка,
    история сохраняется; одобрение финально (409 already_verified);
  * доступ supervisor: admin без supervisor / psychologist / student → 403;
    impersonation supervisor'а → 403 без расшифровки и без content_read;
    прямой admin+supervisor → 200;
  * список без номера; карточка — номер + content_read; сбой аудита → 503;
  * решения: точный audit, outbox-намерение и сообщение, no-op повтор,
    противоположное решение → 409, 404, отключённый заявитель, self-review,
    reviewer_not_allowed после ожидания блокировок;
  * failure-injection: заявка, решение и намерение откатываются вместе;
  * оба способа регистрации создают намерение и доставляют приглашение;
  * отсутствие номера/пояснения/email/факультета в журналах и логах.
"""
import json
import logging
import uuid as _uuid

import pytest

import app.student_verification.service as sv_service
import app.student_verification.storage as sv_storage
from app.audit.contracts import AuditStorageError
from app.auth import otp_service
from app.auth import service as auth_service
from app.auth import storage as auth_storage
from app.core.encryption import decrypt_text
from app.db.models import (
    AuditLog, AuthLog, ChatConversation, ChatMessage, DataChangeLog,
    OtpVerification, StudentVerificationRequest as SVR, SystemMessageIntent,
    User,
)
from app.db.session import SessionLocal
from app.notifications import service as outbox_service
from app.notifications.templates import (
    MESSAGE_TEMPLATES, STUDENT_VERIFICATION_APPROVED, STUDENT_VERIFICATION_INVITE,
    STUDENT_VERIFICATION_REJECTED,
)
from app.student_verification import errors
from app.student_verification.faculties import FACULTY_CODES
from tests.integration.conftest import (
    add_user_role, create_multi_role_user, create_test_user,
)

PASSWORD = "SecurePass42!"
TICKET = "000123"
REASON = "Номер билета не совпадает с документом — конфиденциально"
ME_URL = "/api/student-verification/me"
LIST_URL = "/api/supervisor/student-verifications"


# ── helpers ──────────────────────────────────────────────────────────────────

def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _email(tag="sv"):
    return f"integ_{tag}_{_uuid.uuid4().hex[:10]}@example.com"


def _login(client, email):
    r = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["session_token"]


def _student(client):
    """Чистый student с сессией → (user_id, token, email)."""
    email = _email("st")
    uid = int(create_test_user(email, PASSWORD)["id"])
    return uid, _login(client, email), email


def _supervisor(client, *extra):
    token, uid, _ = create_multi_role_user(client, ["supervisor", "student", *extra])
    return uid, token


def _uuid_of(user_id):
    with SessionLocal() as db:
        return str(db.get(User, user_id).uuid)


def _submit(client, token, faculty="law", ticket=TICKET):
    return client.post(ME_URL, headers=_auth(token),
                       json={"faculty_code": faculty, "ticket_number": ticket})


def _submitted(client, faculty="law", ticket=TICKET):
    uid, token, email = _student(client)
    r = _submit(client, token, faculty, ticket)
    assert r.status_code == 201, r.text
    return uid, token, email, r.json()["current"]["uuid"]


def _requests(user_id):
    with SessionLocal() as db:
        rows = db.query(SVR).filter(SVR.user_id == user_id).order_by(SVR.id).all()
        for r in rows:
            db.expunge(r)
        return rows


def _request(req_uuid):
    with SessionLocal() as db:
        row = db.query(SVR).filter(SVR.uuid == req_uuid).one()
        db.expunge(row)
        return row


def _audit(event, **filters):
    with SessionLocal() as db:
        q = db.query(AuditLog).filter(AuditLog.event_type == event)
        for key, value in filters.items():
            q = q.filter(getattr(AuditLog, key) == value)
        rows = q.order_by(AuditLog.id).all()
        for r in rows:
            db.expunge(r)
        return rows


def _intents(user_id):
    with SessionLocal() as db:
        rows = db.query(SystemMessageIntent).filter(
            SystemMessageIntent.recipient_id == user_id,
        ).order_by(SystemMessageIntent.id).all()
        for r in rows:
            db.expunge(r)
        return rows


def _messages(user_id):
    """[(event_key, plaintext)] system-беседы пользователя."""
    with SessionLocal() as db:
        rows = (
            db.query(ChatMessage.event_key, ChatMessage.content)
            .join(ChatConversation, ChatConversation.id == ChatMessage.conversation_id)
            .filter(ChatConversation.type == "system",
                    ChatConversation.recipient_id == user_id)
            .order_by(ChatMessage.id)
            .all()
        )
        return [(k, decrypt_text(c)) for k, c in rows]


def _marks():
    with SessionLocal() as db:
        return tuple(
            db.query(model.id).order_by(model.id.desc()).limit(1).scalar() or 0
            for model in (AuditLog, AuthLog, DataChangeLog)
        )


def _rows_since(marks):
    out = []
    with SessionLocal() as db:
        for model, mark in zip((AuditLog, AuthLog, DataChangeLog), marks):
            rows = db.query(model).filter(model.id > mark).all()
            for r in rows:
                db.expunge(r)
            out.append(rows)
    return out


def _blob(row):
    parts = []
    for col in row.__table__.columns:
        val = getattr(row, col.name, None)
        if isinstance(val, (dict, list)):
            val = json.dumps(val, ensure_ascii=False)
        parts.append("" if val is None else str(val))
    return " | ".join(parts)


def _assert_failure(row, *, actor_id, role, code):
    assert row.user_id == actor_id
    assert row.user_role == role
    assert row.outcome == "failure"
    assert row.failure_reason_code == code
    assert row.entity_type is None and row.entity_id is None
    assert row.log_metadata == {}
    assert row.description is None


def _assert_success(row, *, actor_id, role, request_id):
    assert row.user_id == actor_id
    assert row.user_role == role
    assert row.outcome == "success"
    assert row.failure_reason_code is None
    assert row.entity_type == "student_verification_request"
    assert row.entity_id == request_id
    assert row.log_metadata == {}
    assert row.description is None


def _approve(client, token, req_uuid):
    return client.post(f"{LIST_URL}/{req_uuid}/approve", headers=_auth(token))


def _reject(client, token, req_uuid, reason=REASON):
    return client.post(f"{LIST_URL}/{req_uuid}/reject", headers=_auth(token),
                       json={"reason": reason})


def _card(client, token, req_uuid):
    return client.get(f"{LIST_URL}/{req_uuid}", headers=_auth(token))


# ── каталог ──────────────────────────────────────────────────────────────────

def test_faculties_available_to_any_authenticated_user(client):
    token, _, _ = create_multi_role_user(client, ["psychologist"])
    r = client.get("/api/student-verification/faculties", headers=_auth(token))
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert [i["code"] for i in items] == list(FACULTY_CODES)
    assert all(i["label"] for i in items)

    _, st_token, _ = _student(client)
    assert client.get("/api/student-verification/faculties",
                      headers=_auth(st_token)).status_code == 200
    assert client.get("/api/student-verification/faculties").status_code == 401


# ── подача ───────────────────────────────────────────────────────────────────

def test_initial_status_is_not_submitted(client):
    _, token, _ = _student(client)
    r = client.get(ME_URL, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json() == {"status": "not_submitted", "can_submit": True, "current": None}
    assert r.headers["cache-control"] == "no-store, private"


@pytest.mark.parametrize("code", FACULTY_CODES)
def test_every_faculty_is_accepted(client, code):
    uid, _, _, req_uuid = _submitted(client, faculty=code)
    (row,) = _requests(uid)
    assert row.faculty_code == code and row.status == "pending"
    assert str(row.uuid) == req_uuid


@pytest.mark.parametrize("body", [
    {"faculty_code": "medicine", "ticket_number": TICKET},
    {"faculty_code": "Юридический факультет", "ticket_number": TICKET},
    {"faculty_code": "law", "ticket_number": ""},
    {"faculty_code": "law", "ticket_number": "    "},
    {"faculty_code": "law", "ticket_number": "1" * 51},
    {"faculty_code": "law", "ticket_number": "12\n34"},
    {"faculty_code": "law", "ticket_number": TICKET, "user_id": 1},
])
def test_invalid_submission_is_422_without_side_effects(client, body):
    uid, token, _ = _student(client)
    marks = _marks()
    r = client.post(ME_URL, headers=_auth(token), json=body)
    assert r.status_code == 422, r.text
    assert _requests(uid) == []
    assert all(rows == [] for rows in _rows_since(marks))


def test_submit_encrypts_ticket_keeps_leading_zeros_and_audits(client):
    uid, token, _ = _student(client)
    marks = _marks()
    r = _submit(client, token, ticket="  000123  ")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "pending" and body["can_submit"] is False
    assert body["current"]["faculty"] == {"code": "law", "label": "Юридический факультет"}
    assert "ticket" not in json.dumps(body)

    (row,) = _requests(uid)
    assert row.ticket_number_enc.startswith("enc:v1:")
    assert TICKET not in row.ticket_number_enc
    assert decrypt_text(row.ticket_number_enc) == TICKET
    assert row.reviewed_by is None and row.reviewed_at is None

    audit, auth, dcl = _rows_since(marks)
    assert [a.event_type for a in audit] == ["student_verification_submitted"]
    _assert_success(audit[0], actor_id=uid, role="student", request_id=row.id)
    assert auth == [] and dcl == []


def test_pending_is_immutable_and_second_submission_is_409(client):
    uid, token, _, req_uuid = _submitted(client, faculty="law", ticket=TICKET)
    for method in ("patch", "put", "delete"):
        assert getattr(client, method)(ME_URL, headers=_auth(token)).status_code == 405

    r = _submit(client, token, faculty="history", ticket="999")
    assert r.status_code == 409
    assert r.json()["code"] == "verification_pending_exists"
    (row,) = _requests(uid)
    assert (row.faculty_code, decrypt_text(row.ticket_number_enc)) == ("law", TICKET)
    (fail,) = _audit("student_verification_submit_failed", user_id=uid)
    _assert_failure(fail, actor_id=uid, role="student",
                    code="verification_pending_exists")


def test_staff_with_student_role_has_no_self_service(client):
    token, uid, _ = create_multi_role_user(client, ["psychologist", "student"])
    r = _submit(client, token)
    assert r.status_code == 403 and r.json()["code"] == "verification_not_allowed"
    assert client.get(ME_URL, headers=_auth(token)).status_code == 403
    assert _requests(uid) == []
    (fail,) = _audit("student_verification_submit_failed", user_id=uid)
    _assert_failure(fail, actor_id=uid, role="psychologist",
                    code="verification_not_allowed")


def test_impersonation_has_no_self_service_and_is_attributed_to_admin(client):
    admin_token, admin_id, _ = create_multi_role_user(client, ["admin"])
    uid, _, _ = _student(client)
    r = client.post(f"/api/admin/users/{_uuid_of(uid)}/impersonate",
                    headers=_auth(admin_token))
    assert r.status_code == 200, r.text
    imp = r.json()["session_token"]

    assert client.get(ME_URL, headers=_auth(imp)).status_code == 403
    r = _submit(client, imp)
    assert r.status_code == 403 and r.json()["code"] == "impersonation_forbidden"
    assert _requests(uid) == []
    (fail,) = _audit("student_verification_submit_failed", user_id=admin_id)
    _assert_failure(fail, actor_id=admin_id, role="admin",
                    code="impersonation_forbidden")
    assert _audit("student_verification_submit_failed", user_id=uid) == []


# ── доступ supervisor ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("roles", [["admin"], ["psychologist"], ["student"]])
def test_non_supervisors_cannot_review(client, roles):
    _, _, _, req_uuid = _submitted(client)
    token, _, _ = create_multi_role_user(client, roles)
    assert client.get(LIST_URL, headers=_auth(token)).status_code == 403
    r = _card(client, token, req_uuid)
    assert r.status_code == 403 and TICKET not in r.text
    assert _approve(client, token, req_uuid).status_code == 403
    assert _reject(client, token, req_uuid).status_code == 403
    assert _request(req_uuid).status == "pending"
    assert _audit("student_verification_content_read",
                  entity_id=_request(req_uuid).id) == []


def test_impersonated_supervisor_is_denied_everything(client):
    applicant, _, _, req_uuid = _submitted(client)
    req_id = _request(req_uuid).id
    admin_token, admin_id, _ = create_multi_role_user(client, ["admin"])
    sup_id, _ = _supervisor(client)
    r = client.post(f"/api/admin/users/{_uuid_of(sup_id)}/impersonate",
                    headers=_auth(admin_token))
    assert r.status_code == 200, r.text
    imp = r.json()["session_token"]

    responses = [
        client.get(LIST_URL, headers=_auth(imp)),
        _card(client, imp, req_uuid),
        _approve(client, imp, req_uuid),
        _reject(client, imp, req_uuid),
    ]
    assert [x.status_code for x in responses] == [403, 403, 403, 403]
    assert all(TICKET not in x.text for x in responses)
    assert _request(req_uuid).status == "pending"
    assert _audit("student_verification_content_read", entity_id=req_id) == []
    for event in ("student_verification_approved", "student_verification_rejected",
                  "student_verification_review_failed"):
        assert _audit(event, user_id=sup_id) == []
        assert _audit(event, user_id=admin_id) == []
    assert not any(i.event_key.startswith("student_verification_result:")
                   for i in _intents(applicant))


def test_direct_admin_plus_supervisor_has_access(client):
    _, _, _, req_uuid = _submitted(client)
    token, uid, _ = create_multi_role_user(client, ["admin", "supervisor"])
    assert client.get(LIST_URL, headers=_auth(token)).status_code == 200
    r = _card(client, token, req_uuid)
    assert r.status_code == 200 and r.json()["ticket_number"] == TICKET
    (read,) = _audit("student_verification_content_read",
                     entity_id=_request(req_uuid).id)
    _assert_success(read, actor_id=uid, role="supervisor",
                    request_id=_request(req_uuid).id)


def test_list_never_contains_ticket_and_is_not_audited(client):
    applicant, _, email, req_uuid = _submitted(client, ticket="000777")
    sup_id, sup = _supervisor(client)
    marks = _marks()
    r = client.get(LIST_URL, headers=_auth(sup), params={"status": "all", "size": 100})
    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "no-store, private"
    assert "000777" not in r.text and "enc:v1:" not in r.text
    item = next(i for i in r.json()["items"] if i["uuid"] == req_uuid)
    assert set(item) == {"uuid", "status", "faculty", "submitted_at", "reviewed_at",
                         "student", "reviewer"}
    assert item["student"]["uuid"] == _uuid_of(applicant)
    assert item["student"]["email"] == email
    assert all(rows == [] for rows in _rows_since(marks))


def test_pending_list_is_fifo_and_filters_by_status(client):
    _, _, _, first = _submitted(client)
    _, _, _, second = _submitted(client)
    _, sup = _supervisor(client)
    r = client.get(LIST_URL, headers=_auth(sup), params={"size": 100})
    uuids = [i["uuid"] for i in r.json()["items"]]
    assert uuids.index(first) < uuids.index(second)
    assert all(i["status"] == "pending" for i in r.json()["items"])
    assert client.get(LIST_URL, headers=_auth(sup),
                      params={"status": "bogus"}).status_code == 422


# ── карточка ─────────────────────────────────────────────────────────────────

def test_card_reveals_ticket_under_content_read_audit(client):
    applicant, _, _, req_uuid = _submitted(client)
    sup_id, sup = _supervisor(client)
    marks = _marks()
    r = _card(client, sup, req_uuid)
    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "no-store, private"
    body = r.json()
    assert body["ticket_number"] == TICKET
    assert body["can_review"] is True and body["history"] == []
    audit, auth, dcl = _rows_since(marks)
    assert [a.event_type for a in audit] == ["student_verification_content_read"]
    _assert_success(audit[0], actor_id=sup_id, role="supervisor",
                    request_id=_request(req_uuid).id)
    assert TICKET not in _blob(audit[0])
    assert auth == [] and dcl == []


def test_card_audit_failure_is_fail_closed(client, monkeypatch):
    _, _, _, req_uuid = _submitted(client)
    _, sup = _supervisor(client)

    def _fail(**kwargs):
        raise AuditStorageError("audit storage failure")
    monkeypatch.setattr(sv_service, "record_event", _fail)
    r = _card(client, sup, req_uuid)
    assert r.status_code == 503
    assert TICKET not in r.text
    assert _audit("student_verification_content_read",
                  entity_id=_request(req_uuid).id) == []


def test_card_unknown_is_404_and_malformed_is_422(client):
    _, sup = _supervisor(client)
    r = _card(client, sup, str(_uuid.uuid4()))
    assert r.status_code == 404 and r.json()["code"] == "verification_not_found"
    assert _card(client, sup, "not-a-uuid").status_code == 422


# ── решения ──────────────────────────────────────────────────────────────────

def test_approve_transitions_audits_and_notifies(client):
    applicant, token, _, req_uuid = _submitted(client)
    sup_id, sup = _supervisor(client)
    marks = _marks()
    r = _approve(client, sup, req_uuid)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved" and "ticket" not in r.text

    row = _request(req_uuid)
    assert (row.status, row.reviewed_by) == ("approved", sup_id)
    assert row.reviewed_at is not None and row.rejection_reason_enc is None

    audit, auth, dcl = _rows_since(marks)
    # system_conversation_created — техническое событие publisher'а (первая
    # system-беседа получателя), не часть решения.
    decision = [a for a in audit if a.event_type != "system_conversation_created"]
    assert [a.event_type for a in decision] == ["student_verification_approved"]
    _assert_success(decision[0], actor_id=sup_id, role="supervisor", request_id=row.id)
    assert auth == [] and dcl == []

    result_key = f"student_verification_result:{req_uuid}"
    (intent,) = [i for i in _intents(applicant) if i.event_key == result_key]
    assert intent.message_code == STUDENT_VERIFICATION_APPROVED
    assert intent.delivered_at is not None and intent.attempts == 0
    assert (result_key, MESSAGE_TEMPLATES[STUDENT_VERIFICATION_APPROVED]) in _messages(applicant)

    me = client.get(ME_URL, headers=_auth(token)).json()
    assert me["status"] == "approved" and me["can_submit"] is False

    # Одобрение финально: новая заявка отклоняется и аудируется.
    r = _submit(client, token, faculty="history", ticket="111")
    assert r.status_code == 409 and r.json()["code"] == "already_verified"
    assert len(_requests(applicant)) == 1
    (fail,) = _audit("student_verification_submit_failed", user_id=applicant)
    _assert_failure(fail, actor_id=applicant, role="student", code="already_verified")


def test_reject_requires_reason_then_allows_new_submission(client):
    applicant, token, _, req_uuid = _submitted(client)
    sup_id, sup = _supervisor(client)
    for body in ({}, {"reason": ""}, {"reason": "   "}):
        r = client.post(f"{LIST_URL}/{req_uuid}/reject", headers=_auth(sup), json=body)
        assert r.status_code == 422
    assert _request(req_uuid).status == "pending"

    r = _reject(client, sup, req_uuid)
    assert r.status_code == 200, r.text
    row = _request(req_uuid)
    assert row.status == "rejected" and row.reviewed_by == sup_id
    assert row.rejection_reason_enc.startswith("enc:v1:")
    assert decrypt_text(row.rejection_reason_enc) == REASON
    (event,) = _audit("student_verification_rejected", entity_id=row.id)
    _assert_success(event, actor_id=sup_id, role="supervisor", request_id=row.id)
    assert REASON not in _blob(event)

    key = f"student_verification_result:{req_uuid}"
    messages = dict(_messages(applicant))
    assert messages[key] == MESSAGE_TEMPLATES[STUDENT_VERIFICATION_REJECTED]
    assert REASON not in messages[key] and TICKET not in messages[key]

    me = client.get(ME_URL, headers=_auth(token)).json()
    assert me["status"] == "rejected" and me["can_submit"] is True
    assert me["current"]["rejection_reason"] == REASON

    r = _submit(client, token, faculty="history", ticket="555")
    assert r.status_code == 201, r.text
    new_uuid = r.json()["current"]["uuid"]
    assert new_uuid != req_uuid
    rows = _requests(applicant)
    assert [x.status for x in rows] == ["rejected", "pending"]

    card = _card(client, sup, new_uuid).json()
    assert card["ticket_number"] == "555"
    assert [h["uuid"] for h in card["history"]] == [req_uuid]
    assert card["history"][0]["status"] == "rejected"
    assert "rejection_reason" not in card["history"][0]


def test_repeat_of_same_decision_is_noop(client):
    applicant, _, _, req_uuid = _submitted(client)
    _, sup = _supervisor(client)
    _, other = _supervisor(client)
    assert _approve(client, sup, req_uuid).status_code == 200
    reviewed = _request(req_uuid)
    marks = _marks()
    r = _approve(client, other, req_uuid)
    assert r.status_code == 200 and r.json()["status"] == "approved"
    assert all(rows == [] for rows in _rows_since(marks))
    assert _request(req_uuid).reviewed_by == reviewed.reviewed_by
    key = f"student_verification_result:{req_uuid}"
    assert len([i for i in _intents(applicant) if i.event_key == key]) == 1
    assert len([m for m in _messages(applicant) if m[0] == key]) == 1


def test_opposite_decision_is_409_and_audited(client):
    _, _, _, req_uuid = _submitted(client)
    _, sup = _supervisor(client)
    other_id, other = _supervisor(client)
    assert _approve(client, sup, req_uuid).status_code == 200
    r = _reject(client, other, req_uuid)
    assert r.status_code == 409 and r.json()["code"] == "verification_already_decided"
    assert _request(req_uuid).status == "approved"
    (fail,) = _audit("student_verification_review_failed", user_id=other_id)
    _assert_failure(fail, actor_id=other_id, role="supervisor",
                    code="verification_already_decided")


def test_unknown_request_decision_is_404_and_audited(client):
    sup_id, sup = _supervisor(client)
    r = _approve(client, sup, str(_uuid.uuid4()))
    assert r.status_code == 404 and r.json()["code"] == "verification_not_found"
    (fail,) = _audit("student_verification_review_failed", user_id=sup_id)
    _assert_failure(fail, actor_id=sup_id, role="supervisor",
                    code="verification_not_found")
    assert _approve(client, sup, "zzz").status_code == 422


def test_disabled_applicant_cannot_be_approved_but_can_be_rejected(client):
    applicant, _, _, req_uuid = _submitted(client)
    sup_id, sup = _supervisor(client)
    admin_token, _, _ = create_multi_role_user(client, ["admin"])
    r = client.post(f"/api/admin/users/{_uuid_of(applicant)}/deactivate",
                    headers=_auth(admin_token), json={"reason": "тест"})
    assert r.status_code == 200, r.text

    r = _approve(client, sup, req_uuid)
    assert r.status_code == 409 and r.json()["code"] == "account_inactive"
    assert _request(req_uuid).status == "pending"
    (fail,) = _audit("student_verification_review_failed", user_id=sup_id)
    _assert_failure(fail, actor_id=sup_id, role="supervisor", code="account_inactive")

    assert _reject(client, sup, req_uuid).status_code == 200
    assert _request(req_uuid).status == "rejected"


def test_applicant_who_became_supervisor_cannot_review_own_request(client):
    applicant, _, email, req_uuid = _submitted(client)
    add_user_role(applicant, "supervisor")
    token = _login(client, email)
    card = _card(client, token, req_uuid)
    assert card.status_code == 200 and card.json()["can_review"] is False

    for resp in (_approve(client, token, req_uuid), _reject(client, token, req_uuid)):
        assert resp.status_code == 403
        assert resp.json()["code"] == "self_review_forbidden"
    assert _request(req_uuid).status == "pending"
    fails = _audit("student_verification_review_failed", user_id=applicant)
    assert len(fails) == 2
    for fail in fails:
        _assert_failure(fail, actor_id=applicant, role="supervisor",
                        code="self_review_forbidden")
    assert not any(i.event_key.startswith("student_verification_result:")
                   for i in _intents(applicant))


def test_reviewer_permission_is_rechecked_after_waiting_for_locks(client, monkeypatch):
    _, _, _, req_uuid = _submitted(client)
    sup_id, sup = _supervisor(client)
    real_lock = sv_storage.lock_users_in_order

    def _role_removed_while_waiting(db, ids):
        # Конкурентная транзакция сняла роль supervisor до того, как мы
        # получили блокировки (её commit — до нашего SELECT … FOR UPDATE).
        with SessionLocal() as other:
            from app.db.models import Role, UserRole
            role_id = other.query(Role.id).filter(Role.name == "supervisor").scalar()
            other.query(UserRole).filter(UserRole.user_id == sup_id,
                                         UserRole.role_id == role_id).delete()
            other.commit()
        return real_lock(db, ids)

    monkeypatch.setattr(sv_storage, "lock_users_in_order", _role_removed_while_waiting)
    r = _approve(client, sup, req_uuid)
    assert r.status_code == 403 and r.json()["code"] == "reviewer_not_allowed"
    assert _request(req_uuid).status == "pending"
    (fail,) = _audit("student_verification_review_failed", user_id=sup_id)
    _assert_failure(fail, actor_id=sup_id, role="supervisor", code="reviewer_not_allowed")


# ── failure-injection: одна транзакция ───────────────────────────────────────

def test_submit_audit_failure_rolls_back_request(client, monkeypatch):
    uid, token, _ = _student(client)

    def _fail(**kwargs):
        raise AuditStorageError("audit storage failure")
    monkeypatch.setattr(sv_storage, "record_event", _fail)
    with pytest.raises(AuditStorageError):
        sv_storage.submit_atomic(uid, faculty_code="law", ticket_number=TICKET)
    assert _requests(uid) == []


@pytest.mark.parametrize("stage", ["audit", "intent", "commit"])
def test_decision_failure_rolls_back_decision_audit_and_intent(client, monkeypatch, stage):
    applicant, _, _, req_uuid = _submitted(client)
    sup_id, _ = _supervisor(client)

    def _boom(*args, **kwargs):
        raise RuntimeError(f"inject {stage}")

    if stage == "audit":
        monkeypatch.setattr(sv_storage, "record_event", _boom)
    elif stage == "intent":
        monkeypatch.setattr(sv_storage.outbox, "enqueue_in_tx", _boom)
    else:
        monkeypatch.setattr(sv_storage, "_commit", _boom)

    with pytest.raises(RuntimeError):
        sv_storage.decide_atomic(_uuid.UUID(req_uuid), decision="approve",
                                 reviewer_id=sup_id)
    row = _request(req_uuid)
    assert (row.status, row.reviewed_by, row.reviewed_at) == ("pending", None, None)
    assert _audit("student_verification_approved", entity_id=row.id) == []
    assert not any(i.event_key == f"student_verification_result:{req_uuid}"
                   for i in _intents(applicant))


# ── приглашение после регистрации ─────────────────────────────────────────────

def _assert_invite_delivered(user_id):
    key = f"student_verification_invite:user:{user_id}"
    (intent,) = [i for i in _intents(user_id) if i.event_key == key]
    assert intent.message_code == STUDENT_VERIFICATION_INVITE
    assert intent.delivered_at is not None
    invites = [m for m in _messages(user_id) if m[0] == key]
    assert invites == [(key, MESSAGE_TEMPLATES[STUDENT_VERIFICATION_INVITE])]
    assert "/student/settings#student-verification" in invites[0][1]


def test_password_registration_creates_and_delivers_invite(client, test_email, capture_emails):
    r = client.post("/api/auth/register/init",
                    json={"name": "Тест Тестов", "email": test_email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    r = client.post("/api/auth/register/confirm",
                    json={"email": test_email, "code": capture_emails[test_email][-1]})
    assert r.status_code == 201, r.text
    with SessionLocal() as db:
        uid = db.query(User.id).filter(User.email == test_email).scalar()
    _assert_invite_delivered(uid)


def test_registration_enqueue_failure_rolls_back_account_and_keeps_otp(test_email, monkeypatch):
    code = otp_service.create_or_update_otp(test_email, "Тест Тестов", "bcrypt$x")

    def _boom(*args, **kwargs):
        raise RuntimeError("inject: intent")
    monkeypatch.setattr("app.notifications.storage.enqueue_in_tx", _boom)
    with pytest.raises(RuntimeError):
        auth_storage.register_confirm_atomic(
            email=test_email, code=code,
            required_consent_types=auth_service.REQUIRED_CONSENTS,
        )
    with SessionLocal() as db:
        assert db.query(User).filter(User.email == test_email).count() == 0
        assert db.query(OtpVerification).filter(
            OtpVerification.email == test_email).count() == 1


def test_publisher_failure_keeps_intent_until_retry_without_duplicates(
    client, test_email, monkeypatch,
):
    monkeypatch.setattr("app.chat.system_publisher.publish_system_message",
                        lambda **kw: None)
    code = otp_service.create_or_update_otp(test_email, "Тест Тестов", "bcrypt$x")
    user = auth_service.register_confirm(test_email, code)   # post-commit soft-fail
    uid = int(user["id"])
    (intent,) = [i for i in _intents(uid)
                 if i.message_code == STUDENT_VERIFICATION_INVITE]
    assert intent.delivered_at is None and intent.attempts == 1
    assert _messages(uid) == []

    monkeypatch.undo()
    outbox_service.run_pending(1000)
    _assert_invite_delivered(uid)
    outbox_service.run_pending(1000)           # повтор — без дубля
    _assert_invite_delivered(uid)


# ── отсутствие ПДн в журналах и логах ─────────────────────────────────────────

def test_full_flow_leaks_nothing_into_journals_or_logs(client, capsys, caplog):
    # Логины (auth_log с email) — до отметки: проверяется сам процесс заявки.
    applicant, token, email = _student(client)
    _, sup = _supervisor(client)
    capsys.readouterr()
    caplog.clear()
    caplog.set_level(logging.DEBUG)
    marks = _marks()
    r = _submit(client, token, faculty="economics", ticket="0042-SECRET")
    assert r.status_code == 201, r.text
    req_uuid = r.json()["current"]["uuid"]
    assert _card(client, sup, req_uuid).status_code == 200
    assert _reject(client, sup, req_uuid).status_code == 200
    assert _submit(client, token, faculty="economics", ticket="0042-SECRET").status_code == 201
    assert _submit(client, token).status_code == 409

    secrets = ("0042-SECRET", REASON, email, "economics")
    for rows in _rows_since(marks):
        for row in rows:
            blob = _blob(row)
            for secret in secrets:
                assert secret not in blob, (row.__tablename__, secret)
    _, _, dcl = _rows_since(marks)
    assert dcl == []
    captured = capsys.readouterr()
    for secret in secrets[:3]:
        assert secret not in captured.out and secret not in captured.err
        assert secret not in caplog.text


def test_list_search_by_email_and_never_by_ticket(client):
    _, _, email, req_uuid = _submitted(client, ticket="SEARCH-0099")
    _submitted(client)
    _, sup = _supervisor(client)
    r = client.get(LIST_URL, headers=_auth(sup), params={"search": email})
    assert r.status_code == 200, r.text
    assert [i["uuid"] for i in r.json()["items"]] == [req_uuid]
    r = client.get(LIST_URL, headers=_auth(sup), params={"search": "SEARCH-0099"})
    assert r.json()["items"] == [] and r.json()["total"] == 0
    assert client.get(LIST_URL, headers=_auth(sup),
                      params={"search": "x" * 201}).status_code == 422
