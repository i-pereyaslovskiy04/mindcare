"""
Integration tests: system messages для событий therapy engagement
(Stage 29d + Stage 31r lifecycle).

Stage 31r:
  - уведомления получают ОБА участника (студент и психолог);
  - тексты только «Чат с психологом/пациентом <ФИО> создан/закрыт.»;
  - первое назначение и реактивация → один текст «создан» (без «снова»);
  - transfer = старый закрыт + новый создан (для всех участников);
  - event_key уникален per-occurrence → close→reactivate→close не теряется;
  - same active psychologist → 409, без новых уведомлений;
  - encryption-at-rest сохраняется (enc:v1:).

Требования: dev PostgreSQL на alembic head, DATA_ENCRYPTION_KEY.
"""

import uuid as _uuid

import bcrypt
import pytest

from app.auth import storage as auth_storage
from app.chat.system_publisher import publish_system_message
from app.core.encryption import ENCRYPTION_PREFIX
from app.supervisor import service as supervisor_service
from app.supervisor.service import SupervisorError
from app.db.session import SessionLocal
from app.db.models import ChatConversation, ChatMessage, User

PASSWORD = "SecurePass42!"

FORBIDDEN_PHRASES = ["снова назначен", "консультационная связь", "Ваш психолог изменён"]


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_user(client, role: str) -> tuple[str, int]:
    user = auth_storage.save_user({
        "name":            f"Eng {role.capitalize()} {_uuid.uuid4().hex[:6]}",
        "email":           f"integ_engsys_{role}_{_uuid.uuid4().hex[:10]}@example.com",
        "hashed_password": bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode(),
        "role":            role,
    })
    r = client.post("/api/auth/login", json={"email": user["email"], "password": PASSWORD})
    assert r.status_code == 200
    return r.json()["session_token"], int(user["id"])


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _full_name(user_id: int) -> str:
    with SessionLocal() as db:
        return db.query(User.full_name).filter(User.id == user_id).scalar()


def _system_rows(recipient_id: int) -> list[ChatMessage]:
    with SessionLocal() as db:
        conv = (
            db.query(ChatConversation)
            .filter(
                ChatConversation.type == "system",
                ChatConversation.recipient_id == recipient_id,
            )
            .first()
        )
        if conv is None:
            return []
        return (
            db.query(ChatMessage)
            .filter(ChatMessage.conversation_id == conv.id)
            .all()
        )


def _api_texts(client, token: str) -> list[str]:
    r = client.get("/api/chat/system-conversation/messages", headers=_auth(token))
    assert r.status_code == 200
    return [m["content"] for m in r.json()["items"]]


def _assign(client):
    s_token, s_id = _make_user(client, "student")
    p_token, p_id = _make_user(client, "psychologist")
    _sv_token, sv_id = _make_user(client, "supervisor")
    eng = supervisor_service.assign_psychologist(
        client_id=s_id, psychologist_id=p_id,
        primary_concern=None, actor_id=sv_id, actor_role="supervisor",
    )
    return {
        "s_token": s_token, "s_id": s_id,
        "p_token": p_token, "p_id": p_id,
        "sv_id": sv_id, "eng_id": eng["id"],
    }


# ─── A. Assignment → both participants get "создан" ───────────────────────────

class TestAssignment:
    def test_patient_and_psychologist_get_created(self, client):
        ctx = _assign(client)
        psych_name = _full_name(ctx["p_id"])
        patient_name = _full_name(ctx["s_id"])

        assert f"Чат с психологом {psych_name} создан." in _api_texts(client, ctx["s_token"])
        assert f"Чат с пациентом {patient_name} создан." in _api_texts(client, ctx["p_token"])

    def test_assignment_encrypted_at_rest(self, client):
        ctx = _assign(client)
        psych_name = _full_name(ctx["p_id"])
        rows = _system_rows(ctx["s_id"])
        assert rows
        assert rows[0].content.startswith(ENCRYPTION_PREFIX)
        assert psych_name not in rows[0].content        # plaintext имени нет в БД
        assert rows[0].message_kind == "system"
        assert rows[0].sender_id is None


# ─── B. Close → both participants get "закрыт" ────────────────────────────────

class TestClose:
    def test_patient_and_psychologist_get_closed(self, client):
        ctx = _assign(client)
        supervisor_service.close_engagement(
            engagement_id=ctx["eng_id"], reason="по завершении",
            actor_id=ctx["sv_id"], actor_role="supervisor",
        )
        psych_name = _full_name(ctx["p_id"])
        patient_name = _full_name(ctx["s_id"])

        s_texts = _api_texts(client, ctx["s_token"])
        p_texts = _api_texts(client, ctx["p_token"])
        assert f"Чат с психологом {psych_name} закрыт." in s_texts
        assert f"Чат с пациентом {patient_name} закрыт." in p_texts
        # reason не раскрывается
        assert all("завершении" not in t for t in s_texts + p_texts)


# ─── C. Transfer X→Y → closed X + created Y across participants ───────────────

class TestTransfer:
    def test_transfer_notifies_all_participants(self, client):
        ctx = _assign(client)                       # student↔X active
        x_name = _full_name(ctx["p_id"])
        patient_name = _full_name(ctx["s_id"])
        y_token, y_id = _make_user(client, "psychologist")
        y_name = _full_name(y_id)

        supervisor_service.transfer_psychologist(
            engagement_id=ctx["eng_id"], new_psychologist_id=y_id,
            transfer_reason=None, actor_id=ctx["sv_id"], actor_role="supervisor",
        )

        s_texts = _api_texts(client, ctx["s_token"])
        assert f"Чат с психологом {x_name} закрыт." in s_texts
        assert f"Чат с психологом {y_name} создан." in s_texts

        # старый психолог X — чат с пациентом закрыт
        assert f"Чат с пациентом {patient_name} закрыт." in _api_texts(client, ctx["p_token"])
        # новый психолог Y — чат с пациентом создан
        assert f"Чат с пациентом {patient_name} создан." in _api_texts(client, y_token)


# ─── D. Reactivation uses "создан", not "снова" ───────────────────────────────

class TestReactivation:
    def test_reactivation_uses_created_text(self, client):
        ctx = _assign(client)
        supervisor_service.close_engagement(
            engagement_id=ctx["eng_id"], reason=None,
            actor_id=ctx["sv_id"], actor_role="supervisor",
        )
        # повторное назначение того же психолога → реактивация
        again = supervisor_service.assign_psychologist(
            client_id=ctx["s_id"], psychologist_id=ctx["p_id"],
            primary_concern=None, actor_id=ctx["sv_id"], actor_role="supervisor",
        )
        assert again["id"] == ctx["eng_id"]          # та же связь реактивирована

        psych_name = _full_name(ctx["p_id"])
        patient_name = _full_name(ctx["s_id"])
        s_texts = _api_texts(client, ctx["s_token"])
        p_texts = _api_texts(client, ctx["p_token"])
        assert f"Чат с психологом {psych_name} создан." in s_texts
        assert f"Чат с пациентом {patient_name} создан." in p_texts
        for t in s_texts + p_texts:
            assert "снова" not in t


# ─── E. event_key regression: close → reactivate → close ──────────────────────

class TestEventKeyRegression:
    def test_close_reactivate_close_both_closes_delivered(self, client):
        ctx = _assign(client)
        sv_id = ctx["sv_id"]

        supervisor_service.close_engagement(
            engagement_id=ctx["eng_id"], reason=None,
            actor_id=sv_id, actor_role="supervisor",
        )
        supervisor_service.assign_psychologist(
            client_id=ctx["s_id"], psychologist_id=ctx["p_id"],
            primary_concern=None, actor_id=sv_id, actor_role="supervisor",
        )
        supervisor_service.close_engagement(
            engagement_id=ctx["eng_id"], reason=None,
            actor_id=sv_id, actor_role="supervisor",
        )

        psych_name = _full_name(ctx["p_id"])
        patient_name = _full_name(ctx["s_id"])
        # ДВА разных закрытия должны быть доставлены (не схлопнуты event_key)
        s_closed = [t for t in _api_texts(client, ctx["s_token"])
                    if t == f"Чат с психологом {psych_name} закрыт."]
        p_closed = [t for t in _api_texts(client, ctx["p_token"])
                    if t == f"Чат с пациентом {patient_name} закрыт."]
        assert len(s_closed) == 2
        assert len(p_closed) == 2


# ─── F. Same active psychologist → 409, no new system messages ────────────────

class TestSameActiveNoNotification:
    def test_assign_same_active_409_no_messages(self, client):
        ctx = _assign(client)
        s_before = len(_system_rows(ctx["s_id"]))
        p_before = len(_system_rows(ctx["p_id"]))

        with pytest.raises(SupervisorError) as ei:
            supervisor_service.assign_psychologist(
                client_id=ctx["s_id"], psychologist_id=ctx["p_id"],
                primary_concern=None, actor_id=ctx["sv_id"], actor_role="supervisor",
            )
        assert ei.value.status_code == 409

        with pytest.raises(SupervisorError) as ei2:
            supervisor_service.transfer_psychologist(
                engagement_id=ctx["eng_id"], new_psychologist_id=ctx["p_id"],
                transfer_reason=None, actor_id=ctx["sv_id"], actor_role="supervisor",
            )
        assert ei2.value.status_code == 409

        assert len(_system_rows(ctx["s_id"])) == s_before
        assert len(_system_rows(ctx["p_id"])) == p_before


# ─── G. No forbidden phrases anywhere across a full lifecycle ─────────────────

class TestTextRegression:
    def test_no_forbidden_phrases(self, client):
        # Полный цикл: assign X → transfer X→Y → close Y.
        ctx = _assign(client)
        y_token, y_id = _make_user(client, "psychologist")
        transferred = supervisor_service.transfer_psychologist(
            engagement_id=ctx["eng_id"], new_psychologist_id=y_id,
            transfer_reason=None, actor_id=ctx["sv_id"], actor_role="supervisor",
        )
        supervisor_service.close_engagement(
            engagement_id=transferred["id"], reason=None,
            actor_id=ctx["sv_id"], actor_role="supervisor",
        )

        all_texts = (
            _api_texts(client, ctx["s_token"])
            + _api_texts(client, ctx["p_token"])
            + _api_texts(client, y_token)
        )
        assert all_texts  # что-то опубликовано
        for t in all_texts:
            for phrase in FORBIDDEN_PHRASES:
                assert phrase not in t


# ─── Access / privacy (сохранено) ─────────────────────────────────────────────

class TestAccessPrivacy:
    def test_other_student_does_not_see_assignment(self, client):
        ctx = _assign(client)
        other_token, _other_id = _make_user(client, "student")
        r = client.get("/api/chat/system-conversation", headers=_auth(other_token))
        assert r.json()["conversation"] is None
        assert _api_texts(client, other_token) == []

    def test_publisher_idempotent_on_same_event_key(self, client):
        ctx = _assign(client)
        before = len(_system_rows(ctx["s_id"]))
        # повторный publish с тем же event_key (ретрай одной операции) — без дубля
        res = publish_system_message(
            ctx["s_id"], event_key="dup_key_test:engagement:1", text="первый",
        )
        assert res["created"] is True
        res2 = publish_system_message(
            ctx["s_id"], event_key="dup_key_test:engagement:1", text="дубль",
        )
        assert res2["created"] is False
        assert len(_system_rows(ctx["s_id"])) == before + 1
