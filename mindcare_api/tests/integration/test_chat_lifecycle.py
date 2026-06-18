"""
Stage 31p — Messenger lifecycle: reactivate same-pair chat + hide empty inactive.

Покрывает:
  A. повторное назначение того же active психолога → 409, без изменений;
  B. close → повторное назначение того же психолога → реактивация той же связи
     и той же беседы (тот же conversation_uuid), без дублей;
  C. transfer X→Y, где у Y была прежняя переписка → реактивация Y, тот же uuid,
     сообщения сохранены;
  D. transfer X→Y с пустым X → пустая transferred-беседа X скрыта в списках;
  E. transfer X→Y с сообщениями в X → X виден как read-only история, запись 409;
  F. X→Y→X → возвращается прежняя беседа X, тот же uuid, без третьей беседы;
  G. rollback при сбое реактивации;
  H. list API: active-пустая видна, inactive-пустая скрыта, inactive-непустая видна.

Requires dev PostgreSQL on alembic head + DATA_ENCRYPTION_KEY.
"""

import uuid as _uuid

import bcrypt
import pytest

from app.auth import storage as auth_storage
from app.supervisor import service as sup
from app.supervisor.service import SupervisorError
from app.db.session import SessionLocal
from app.db.models import ChatConversation, ChatMessage, TherapyEngagement

PASSWORD = "SecurePass42!"


def _make_user(client, role: str) -> tuple[str, int]:
    user = auth_storage.save_user({
        "name":            f"Life {role} {_uuid.uuid4().hex[:6]}",
        "email":           f"integ_life_{role}_{_uuid.uuid4().hex[:10]}@example.com",
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


def _conv_uuid_for_engagement(eng_id) -> str:
    with SessionLocal() as db:
        c = (
            db.query(ChatConversation)
            .filter(ChatConversation.engagement_id == eng_id)
            .first()
        )
        return str(c.uuid) if c else None


def _pair_conversation_count(client_id, psych_id) -> int:
    with SessionLocal() as db:
        return (
            db.query(ChatConversation)
            .join(TherapyEngagement,
                  TherapyEngagement.id == ChatConversation.engagement_id)
            .filter(TherapyEngagement.client_id == client_id,
                    TherapyEngagement.psychologist_id == psych_id)
            .count()
        )


def _engagement_count(client_id) -> int:
    with SessionLocal() as db:
        return (
            db.query(TherapyEngagement)
            .filter(TherapyEngagement.client_id == client_id)
            .count()
        )


def _student_send(client, s_token, text="привет"):
    r = client.post("/api/chat/my-conversation/messages",
                    headers=_auth(s_token), json={"content": text})
    assert r.status_code == 201


def _psy_list_uuids(client, p_token) -> list[str]:
    r = client.get("/api/chat/conversations", headers=_auth(p_token))
    assert r.status_code == 200
    return [it["uuid"] for it in r.json()["items"]]


# ─── A. Same active psychologist rejected ─────────────────────────────────────

def test_same_active_psychologist_rejected(client):
    _s, s_id = _make_user(client, "student")
    _p, p_id = _make_user(client, "psychologist")
    _sv, sup_id = _make_user(client, "supervisor")

    first = _assign(s_id, p_id, sup_id)

    with pytest.raises(SupervisorError) as ei:
        _assign(s_id, p_id, sup_id)
    assert ei.value.status_code == 409

    with pytest.raises(SupervisorError) as ei2:
        _transfer(first["id"], p_id, sup_id)
    assert ei2.value.status_code == 409

    # ничего не создано/не изменено
    assert _engagement_count(s_id) == 1
    assert _pair_conversation_count(s_id, p_id) == 1
    with SessionLocal() as db:
        eng = db.query(TherapyEngagement).filter_by(id=first["id"]).first()
        assert eng.status == "active"


# ─── B. Close then reassign same psychologist → reactivate ────────────────────

def test_close_then_reassign_same_psychologist_reactivates(client):
    _s, s_id = _make_user(client, "student")
    _p, p_id = _make_user(client, "psychologist")
    _sv, sup_id = _make_user(client, "supervisor")

    first = _assign(s_id, p_id, sup_id)
    eng_id = first["id"]
    conv_uuid = _conv_uuid_for_engagement(eng_id)

    sup.close_engagement(engagement_id=eng_id, reason=None,
                         actor_id=sup_id, actor_role="supervisor")

    again = _assign(s_id, p_id, sup_id)

    assert again["id"] == eng_id                       # та же связь
    assert again["status"] == "active"
    assert _conv_uuid_for_engagement(eng_id) == conv_uuid  # тот же чат
    assert _engagement_count(s_id) == 1                # без новой связи
    assert _pair_conversation_count(s_id, p_id) == 1   # без дубля беседы


# ─── C. Transfer X→Y where Y had previous history → reactivate Y ──────────────

def test_transfer_to_previous_psychologist_reactivates_with_history(client):
    s_token, s_id = _make_user(client, "student")
    _x, x_id = _make_user(client, "psychologist")
    _y, y_id = _make_user(client, "psychologist")
    _sv, sup_id = _make_user(client, "supervisor")

    # сначала Y с сообщением
    eng_y = _assign(s_id, y_id, sup_id)
    eng_y_id = eng_y["id"]
    conv_y_uuid = _conv_uuid_for_engagement(eng_y_id)
    _student_send(client, s_token, "история с Y")

    # перевод Y→X (теперь active = X)
    eng_x = _transfer(eng_y_id, x_id, sup_id)

    # перевод X→Y → реактивация прежней связи Y
    back = _transfer(eng_x["id"], y_id, sup_id)
    assert back["id"] == eng_y_id
    assert back["status"] == "active"
    assert _conv_uuid_for_engagement(eng_y_id) == conv_y_uuid   # тот же чат
    assert _pair_conversation_count(s_id, y_id) == 1            # без дубля

    # сообщения сохранены и беседа видна новому/вернувшемуся психологу Y
    with SessionLocal() as db:
        conv = db.query(ChatConversation).filter_by(engagement_id=eng_y_id).first()
        msg_count = (
            db.query(ChatMessage)
            .filter(ChatMessage.conversation_id == conv.id,
                    ChatMessage.deleted_at.is_(None))
            .count()
        )
    assert msg_count >= 1


# ─── D. Transfer X→Y with empty X → empty X hidden ────────────────────────────

def test_transfer_empty_x_hidden_in_lists(client):
    _s, s_id = _make_user(client, "student")
    x_token, x_id = _make_user(client, "psychologist")
    y_token, y_id = _make_user(client, "psychologist")
    _sv, sup_id = _make_user(client, "supervisor")

    eng_x = _assign(s_id, x_id, sup_id)
    conv_x_uuid = _conv_uuid_for_engagement(eng_x["id"])

    eng_y = _transfer(eng_x["id"], y_id, sup_id)
    conv_y_uuid = _conv_uuid_for_engagement(eng_y["id"])

    # пустая transferred-беседа X скрыта в списке психолога X
    assert conv_x_uuid not in _psy_list_uuids(client, x_token)
    # активная беседа Y видна психологу Y
    assert conv_y_uuid in _psy_list_uuids(client, y_token)


# ─── E. Transfer X→Y with messages in X → X read-only history, write 409 ──────

def test_transfer_nonempty_x_visible_readonly(client):
    s_token, s_id = _make_user(client, "student")
    x_token, x_id = _make_user(client, "psychologist")
    y_token, y_id = _make_user(client, "psychologist")
    _sv, sup_id = _make_user(client, "supervisor")

    eng_x = _assign(s_id, x_id, sup_id)
    conv_x_uuid = _conv_uuid_for_engagement(eng_x["id"])
    _student_send(client, s_token, "сообщение в X")

    eng_y = _transfer(eng_x["id"], y_id, sup_id)
    conv_y_uuid = _conv_uuid_for_engagement(eng_y["id"])

    # X с сообщением остаётся видимым психологу X (история)
    assert conv_x_uuid in _psy_list_uuids(client, x_token)
    # но запись в transferred-беседу запрещена → 409
    w = client.post(f"/api/chat/conversations/{conv_x_uuid}/messages",
                    headers=_auth(x_token), json={"content": "после перевода"})
    assert w.status_code == 409
    # активная Y видна психологу Y
    assert conv_y_uuid in _psy_list_uuids(client, y_token)


# ─── F. X→Y→X returns the original X conversation ─────────────────────────────

def test_x_y_x_returns_original_conversation(client):
    s_token, s_id = _make_user(client, "student")
    x_token, x_id = _make_user(client, "psychologist")
    _y, y_id = _make_user(client, "psychologist")
    _sv, sup_id = _make_user(client, "supervisor")

    eng_x = _assign(s_id, x_id, sup_id)
    eng_x_id = eng_x["id"]
    conv_x_uuid = _conv_uuid_for_engagement(eng_x_id)
    _student_send(client, s_token, "в X")

    eng_y = _transfer(eng_x_id, y_id, sup_id)
    back = _transfer(eng_y["id"], x_id, sup_id)

    assert back["id"] == eng_x_id                          # та же связь X
    assert _conv_uuid_for_engagement(eng_x_id) == conv_x_uuid
    assert _pair_conversation_count(s_id, x_id) == 1       # без третьей беседы
    assert conv_x_uuid in _psy_list_uuids(client, x_token)


# ─── G. Rollback safety during reactivation ───────────────────────────────────

def test_reactivation_rollback_on_conversation_failure(client, monkeypatch):
    _s, s_id = _make_user(client, "student")
    _p, p_id = _make_user(client, "psychologist")
    _sv, sup_id = _make_user(client, "supervisor")

    first = _assign(s_id, p_id, sup_id)
    sup.close_engagement(engagement_id=first["id"], reason=None,
                         actor_id=sup_id, actor_role="supervisor")

    def boom(db, engagement_id):
        raise RuntimeError("inject: reactivate conversation failed")

    monkeypatch.setattr("app.chat.storage.ensure_engagement_conversation", boom)

    with pytest.raises(RuntimeError, match="inject: reactivate"):
        _assign(s_id, p_id, sup_id)

    # реактивация откатилась: связь всё ещё completed, активной нет
    with SessionLocal() as db:
        eng = db.query(TherapyEngagement).filter_by(id=first["id"]).first()
        assert eng.status == "completed"
        active = (
            db.query(TherapyEngagement)
            .filter(TherapyEngagement.client_id == s_id,
                    TherapyEngagement.status == "active",
                    TherapyEngagement.ended_at.is_(None))
            .count()
        )
        assert active == 0


# ─── H. List visibility matrix ────────────────────────────────────────────────

def test_list_hides_empty_inactive_keeps_active_and_nonempty(client):
    # Один психолог P и три студента — матрица видимости в списке P:
    #   A: active empty            → видна
    #   B: inactive empty          → скрыта
    #   C: inactive non-empty      → видна
    p_token, p_id = _make_user(client, "psychologist")
    q_token, q_id = _make_user(client, "psychologist")   # «другой» психолог
    _sv, sup_id = _make_user(client, "supervisor")

    # A — активная пустая
    _a_token, a_id = _make_user(client, "student")
    eng_a = _assign(a_id, p_id, sup_id)
    conv_a = _conv_uuid_for_engagement(eng_a["id"])

    # B — пустую связь с P переводим к Q → inactive empty у P
    _b_token, b_id = _make_user(client, "student")
    eng_b = _assign(b_id, p_id, sup_id)
    conv_b = _conv_uuid_for_engagement(eng_b["id"])
    _transfer(eng_b["id"], q_id, sup_id)

    # C — связь с P получает сообщение, затем перевод к Q → inactive non-empty у P
    c_token, c_id = _make_user(client, "student")
    eng_c = _assign(c_id, p_id, sup_id)
    conv_c = _conv_uuid_for_engagement(eng_c["id"])
    _student_send(client, c_token, "сообщение C")
    _transfer(eng_c["id"], q_id, sup_id)

    uuids = _psy_list_uuids(client, p_token)
    assert conv_a in uuids        # active empty → видна
    assert conv_b not in uuids    # inactive empty → скрыта
    assert conv_c in uuids        # inactive non-empty → видна
