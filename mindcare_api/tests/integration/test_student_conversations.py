"""
Stage 31t — student conversation list / archive + uuid-based read/send/read.

Единая с психологом visibility policy: active всегда; inactive — только
с сообщениями; empty inactive скрыт; доступ строго к своим беседам; отправка
в inactive → 409; system conversation в engagement-список не попадает.

Requires dev PostgreSQL on alembic head + DATA_ENCRYPTION_KEY.
"""

import uuid as _uuid

import bcrypt
import pytest

from app.auth import storage as auth_storage
from app.supervisor import service as sup
from app.db.session import SessionLocal
from app.db.models import ChatConversation, TherapyEngagement

PASSWORD = "SecurePass42!"


def _make_user(client, role: str) -> tuple[str, int]:
    user = auth_storage.save_user({
        "name":            f"Stud {role} {_uuid.uuid4().hex[:6]}",
        "email":           f"integ_studconv_{role}_{_uuid.uuid4().hex[:10]}@example.com",
        "hashed_password": bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode(),
        "role":            role,
    })
    r = client.post("/api/auth/login", json={"email": user["email"], "password": PASSWORD})
    assert r.status_code == 200
    return r.json()["session_token"], int(user["id"])


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _assign(s_id, p_id, sup_id):
    return sup.assign_psychologist(
        client_id=s_id, psychologist_id=p_id, primary_concern=None,
        actor_id=sup_id, actor_role="supervisor",
    )


def _transfer(eng_id, new_p_id, sup_id):
    return sup.transfer_psychologist(
        engagement_id=eng_id, new_psychologist_id=new_p_id,
        transfer_reason=None, actor_id=sup_id, actor_role="supervisor",
    )


def _student_list(client, token):
    r = client.get("/api/chat/student/conversations", headers=_auth(token))
    assert r.status_code == 200
    return r.json()["items"]


def _conv_uuid(eng_id) -> str:
    with SessionLocal() as db:
        c = db.query(ChatConversation).filter_by(engagement_id=eng_id).first()
        return str(c.uuid)


def _send(client, token, uuid, text="привет"):
    return client.post(
        f"/api/chat/student/conversations/{uuid}/messages",
        headers=_auth(token), json={"content": text},
    )


# ─── A. list returns active conversation ──────────────────────────────────────

def test_list_returns_active_conversation(client):
    s_token, s_id = _make_user(client, "student")
    _p, p_id = _make_user(client, "psychologist")
    _sv, sup_id = _make_user(client, "supervisor")

    eng = _assign(s_id, p_id, sup_id)
    items = _student_list(client, s_token)
    uuids = [it["uuid"] for it in items]
    assert _conv_uuid(eng["id"]) in uuids
    item = next(it for it in items if it["uuid"] == _conv_uuid(eng["id"]))
    assert item["engagement_status"] == "active"
    assert item["partner"]["id"] == p_id


# ─── B/C. inactive-with-messages shown, inactive-empty hidden ─────────────────

def test_inactive_with_messages_shown_empty_hidden(client):
    s_token, s_id = _make_user(client, "student")
    _x, x_id = _make_user(client, "psychologist")
    _y, y_id = _make_user(client, "psychologist")
    _sv, sup_id = _make_user(client, "supervisor")

    # X с сообщением → потом transfer → X archived non-empty
    eng_x = _assign(s_id, x_id, sup_id)
    conv_x = _conv_uuid(eng_x["id"])
    assert _send(client, s_token, conv_x, "история").status_code == 201

    eng_y = _transfer(eng_x["id"], y_id, sup_id)   # X transferred (non-empty), Y active empty
    conv_y = _conv_uuid(eng_y["id"])

    uuids = [it["uuid"] for it in _student_list(client, s_token)]
    assert conv_x in uuids          # inactive non-empty → виден (архив)
    assert conv_y in uuids          # active → виден

    # отдельный пустой inactive: новый студент, assign→transfer без сообщений
    s2_token, s2_id = _make_user(client, "student")
    e1 = _assign(s2_id, x_id, sup_id)
    conv_empty = _conv_uuid(e1["id"])
    e2 = _transfer(e1["id"], y_id, sup_id)
    conv_active = _conv_uuid(e2["id"])

    uuids2 = [it["uuid"] for it in _student_list(client, s2_token)]
    assert conv_empty not in uuids2     # inactive empty → скрыт
    assert conv_active in uuids2


# ─── D. student cannot see another student's conversation ─────────────────────

def test_student_cannot_read_foreign_conversation(client):
    s1_token, s1_id = _make_user(client, "student")
    s2_token, _s2_id = _make_user(client, "student")
    _p, p_id = _make_user(client, "psychologist")
    _sv, sup_id = _make_user(client, "supervisor")

    eng = _assign(s1_id, p_id, sup_id)
    conv = _conv_uuid(eng["id"])

    # чужой студент не видит её ни в списке, ни по uuid (404)
    assert conv not in [it["uuid"] for it in _student_list(client, s2_token)]
    r = client.get(
        f"/api/chat/student/conversations/{conv}/messages", headers=_auth(s2_token),
    )
    assert r.status_code == 404


# ─── E/F/G. read archived; send to inactive → 409; send to active → 201 ───────

def test_read_archived_and_send_rules(client):
    s_token, s_id = _make_user(client, "student")
    _x, x_id = _make_user(client, "psychologist")
    _y, y_id = _make_user(client, "psychologist")
    _sv, sup_id = _make_user(client, "supervisor")

    eng_x = _assign(s_id, x_id, sup_id)
    conv_x = _conv_uuid(eng_x["id"])
    assert _send(client, s_token, conv_x, "в X до перевода").status_code == 201   # G: active

    eng_y = _transfer(eng_x["id"], y_id, sup_id)
    conv_y = _conv_uuid(eng_y["id"])

    # E: чтение архивной (X) истории по uuid
    r_read = client.get(
        f"/api/chat/student/conversations/{conv_x}/messages", headers=_auth(s_token),
    )
    assert r_read.status_code == 200
    assert any(m["content"] == "в X до перевода" for m in r_read.json()["items"])

    # F: отправка в архивную (X, transferred) → 409
    assert _send(client, s_token, conv_x, "после перевода").status_code == 409

    # G: отправка в активную (Y) → 201
    assert _send(client, s_token, conv_y, "в Y").status_code == 201


# ─── H. system conversation not in engagement list ───────────────────────────

def test_system_conversation_not_in_student_list(client):
    s_token, s_id = _make_user(client, "student")
    _p, p_id = _make_user(client, "psychologist")
    _sv, sup_id = _make_user(client, "supervisor")

    _assign(s_id, p_id, sup_id)   # публикует system-сообщение студенту (Stage 31r)

    items = _student_list(client, s_token)
    # все элементы — engagement-беседы с partner; system среди них нет
    assert all("partner" in it for it in items)
    with SessionLocal() as db:
        eng_count = (
            db.query(TherapyEngagement)
            .filter(TherapyEngagement.client_id == s_id)
            .count()
        )
    assert len(items) == eng_count


# ─── psychologist route stays psychologist-only ──────────────────────────────

def test_student_route_rejects_psychologist(client):
    p_token, _p_id = _make_user(client, "psychologist")
    r = client.get("/api/chat/student/conversations", headers=_auth(p_token))
    assert r.status_code == 403
