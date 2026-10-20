"""
Stage 4B-2/4B-3 — gated integration: supervisor-операции пишут корректные
audit_log строки через record_event. Запуск ТОЛЬКО через Stage 1 isolated
runner (disposable mindcare_test_<random>); dev/prod запрещены. Синтетические
integ_-данные.

Проверяет:
  - assign → supervisor_assign_psychologist (actor=int supervisor, entity=engagement,
    metadata {}, description NULL);
  - assign → chat_conversation_created (Stage 4B-3) на том же conv_id, actor
    совпадает с supervisor_assign_psychologist (supervisor и admin);
  - close → re-assign того же психолога → supervisor_reactivate_psychologist
    (отдельное событие, отличное от assign);
  - create_student с psychologist_id → две строки (supervisor_create_student user +
    supervisor_assign_psychologist therapy_engagement);
  - admin-инициированная операция не падает 500 (widened roles {supervisor,admin}).
"""
import uuid as _uuid

import bcrypt

from app.auth import storage as auth_storage
from app.core.normalization import normalize_email
from app.db.session import SessionLocal
from app.db.models import AuditLog, ChatConversation, User
from tests.integration.conftest import (
    ALLOWED_TEST_DOMAIN, create_multi_role_user, create_test_user,
)

PASSWORD = "SecurePass42!"


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _psychologist(email):
    pw = bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode()
    return auth_storage.save_user({
        "name": "Integ Psy", "email": email, "hashed_password": pw,
        "role": "psychologist",
    })


def _student_email():
    return f"integ_stu_{_uuid.uuid4().hex[:10]}@{ALLOWED_TEST_DOMAIN}"


def _psy_email():
    return f"integ_psy_{_uuid.uuid4().hex[:10]}@{ALLOWED_TEST_DOMAIN}"


def _user_id_by_email(email):
    with SessionLocal() as db:
        row = (
            db.query(User.id)
            .filter(User.email == normalize_email(email))
            .first()
        )
        return row.id if row else None


def _conv_id_for_engagement(eng_id):
    with SessionLocal() as db:
        row = (
            db.query(ChatConversation.id)
            .filter(ChatConversation.engagement_id == eng_id)
            .first()
        )
        return row.id if row else None


def _audit_by_entity(entity_type, entity_id, event=None):
    with SessionLocal() as db:
        q = db.query(AuditLog).filter(
            AuditLog.entity_type == entity_type,
            AuditLog.entity_id == entity_id,
        )
        if event:
            q = q.filter(AuditLog.event_type == event)
        rows = q.all()
        for r in rows:
            db.expunge(r)
        return rows


# ── assign ────────────────────────────────────────────────────────────────────

def test_assign_writes_assign_event(client):
    token, sup_id, _ = create_multi_role_user(client, ["supervisor"])
    student = create_test_user(_student_email())
    psy = _psychologist(_psy_email())

    r = client.post(
        "/api/supervisor/engagements", headers=_auth(token),
        json={"client_id": int(student["id"]), "psychologist_id": int(psy["id"])},
    )
    assert r.status_code == 201, r.text
    eng_id = r.json()["id"]

    rows = _audit_by_entity("therapy_engagement", eng_id,
                            "supervisor_assign_psychologist")
    assert len(rows) == 1
    a = rows[0]
    assert a.user_id == sup_id                  # actor = supervisor (int)
    assert a.user_role == "supervisor"
    assert a.entity_id == eng_id                # target = engagement
    assert (a.log_metadata or {}) == {}         # metadata пуста
    assert a.description is None                # description не пишется

    # Stage 4B-3: assign также создаёт беседу → chat_conversation_created на
    # том же conv_id, actor совпадает (widened roles {student,psychologist,
    # supervisor,admin} для этого события).
    conv_id = _conv_id_for_engagement(eng_id)
    assert conv_id is not None
    chat_rows = _audit_by_entity("chat_conversation", conv_id,
                                 "chat_conversation_created")
    assert len(chat_rows) == 1
    c = chat_rows[0]
    assert c.user_id == sup_id and c.user_role == "supervisor"
    assert (c.log_metadata or {}) == {}
    assert c.description is None


def test_admin_actor_assign_does_not_500(client):
    # admin (без supervisor-роли) инициирует supervisor-операцию: widened roles
    # {supervisor,admin} не дают AuditError→500.
    token, admin_id, _ = create_multi_role_user(client, ["admin"])
    student = create_test_user(_student_email())
    psy = _psychologist(_psy_email())

    r = client.post(
        "/api/supervisor/engagements", headers=_auth(token),
        json={"client_id": int(student["id"]), "psychologist_id": int(psy["id"])},
    )
    assert r.status_code == 201, r.text
    eng_id = r.json()["id"]
    rows = _audit_by_entity("therapy_engagement", eng_id,
                            "supervisor_assign_psychologist")
    assert len(rows) == 1 and rows[0].user_id == admin_id
    assert rows[0].user_role == "admin"

    # chat_conversation_created с actor role "admin" не даёт 500 (registry
    # widening Stage 4B-3: allowed_actor_roles включает admin).
    conv_id = _conv_id_for_engagement(eng_id)
    assert conv_id is not None
    chat_rows = _audit_by_entity("chat_conversation", conv_id,
                                 "chat_conversation_created")
    assert len(chat_rows) == 1
    assert chat_rows[0].user_id == admin_id and chat_rows[0].user_role == "admin"


# ── reactivate (assign vs reactivate — разные события) ────────────────────────

def test_reassign_same_psychologist_writes_reactivate(client):
    token, _, _ = create_multi_role_user(client, ["supervisor"])
    student = create_test_user(_student_email())
    psy = _psychologist(_psy_email())
    cid, pid = int(student["id"]), int(psy["id"])

    r = client.post("/api/supervisor/engagements", headers=_auth(token),
                    json={"client_id": cid, "psychologist_id": pid})
    assert r.status_code == 201, r.text
    eng_id = r.json()["id"]

    r = client.patch(f"/api/supervisor/engagements/{eng_id}/close",
                     headers=_auth(token), json={"reason": "done"})
    assert r.status_code == 200, r.text

    # повторное назначение того же психолога → реактивация прежней связи
    r = client.post("/api/supervisor/engagements", headers=_auth(token),
                    json={"client_id": cid, "psychologist_id": pid})
    assert r.status_code == 201, r.text
    reeng_id = r.json()["id"]

    react = _audit_by_entity("therapy_engagement", reeng_id,
                             "supervisor_reactivate_psychologist")
    assert len(react) == 1
    assert react[0].description is None and (react[0].log_metadata or {}) == {}
    # close-событие тоже записано (на исходный engagement)
    assert _audit_by_entity("therapy_engagement", eng_id,
                            "supervisor_close_engagement")


# ── transfer ──────────────────────────────────────────────────────────────────

def test_transfer_writes_transfer_event_on_original_engagement(client):
    token, sup_id, _ = create_multi_role_user(client, ["supervisor"])
    student = create_test_user(_student_email())
    psy_a = _psychologist(_psy_email())
    psy_b = _psychologist(_psy_email())
    cid, pid_a, pid_b = int(student["id"]), int(psy_a["id"]), int(psy_b["id"])

    r = client.post("/api/supervisor/engagements", headers=_auth(token),
                    json={"client_id": cid, "psychologist_id": pid_a})
    assert r.status_code == 201, r.text
    original_eng_id = r.json()["id"]

    secret_reason = "синтетическая причина переназначения (ПДн-подобный текст)"
    r = client.patch(
        f"/api/supervisor/engagements/{original_eng_id}/transfer",
        headers=_auth(token),
        json={"new_psychologist_id": pid_b, "transfer_reason": secret_reason},
    )
    assert r.status_code == 200, r.text
    new_eng_id = r.json()["id"]
    assert new_eng_id != original_eng_id

    rows = _audit_by_entity("therapy_engagement", original_eng_id,
                            "supervisor_transfer_psychologist")
    assert len(rows) == 1
    a = rows[0]
    # target — ИСХОДНАЯ (переносимая) связь, не новая active-связь с psy_b.
    assert a.entity_type == "therapy_engagement"
    assert a.entity_id == original_eng_id
    assert a.user_id == sup_id                  # actor
    assert a.user_role == "supervisor"
    assert (a.log_metadata or {}) == {}          # metadata пуста
    assert a.description is None                 # description не пишется
    # transfer_reason НЕ скопирован в audit (остаётся только в самой связи)
    assert secret_reason not in str(a.log_metadata)
    assert a.description != secret_reason

    # На новой active-связи с psy_b transfer-событие не пишется.
    assert _audit_by_entity("therapy_engagement", new_eng_id,
                            "supervisor_transfer_psychologist") == []


# ── create_student → две audit-строки ─────────────────────────────────────────

def test_create_student_with_psychologist_two_rows(client):
    token, sup_id, _ = create_multi_role_user(client, ["supervisor"])
    psy = _psychologist(_psy_email())
    email = f"integ_newstu_{_uuid.uuid4().hex[:10]}@{ALLOWED_TEST_DOMAIN}"

    r = client.post(
        "/api/supervisor/students", headers=_auth(token),
        json={
            "full_name": "Иван Иванов", "email": email,
            "personal_data_consent": True, "psychologist_id": int(psy["id"]),
        },
    )
    assert r.status_code == 201, r.text
    eng_id = r.json()["engagement"]["id"]
    new_uid = _user_id_by_email(email)
    assert new_uid is not None

    urows = _audit_by_entity("user", new_uid, "supervisor_create_student")
    assert len(urows) == 1
    assert urows[0].user_id == sup_id and urows[0].entity_id == new_uid
    assert urows[0].description is None and (urows[0].log_metadata or {}) == {}

    erows = _audit_by_entity("therapy_engagement", eng_id,
                             "supervisor_assign_psychologist")
    assert len(erows) == 1
    assert erows[0].user_id == sup_id and erows[0].entity_id == eng_id
