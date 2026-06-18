"""
Stage 32g — Редактирование сообщений с удалением вложений (PATCH + remove_attachment_uuids).

Политика: удалять вложения может только владелец сообщения в активной беседе;
soft-delete атомарен с content update; удалённые вложения не скачиваются (404).

Requires dev PostgreSQL on alembic head + DATA_ENCRYPTION_KEY.
"""

import uuid as _uuid
from pathlib import Path
from unittest.mock import patch

import bcrypt
import pytest

from app.auth import storage as auth_storage
from app.core.config import settings
from app.db.session import SessionLocal
from app.db.models import ChatAttachment, ChatConversation, TherapyEngagement

PASSWORD = "SecurePass42!"

_SMALL_PDF = b"%PDF-1.4 small"
_SMALL_JPG = b"\xff\xd8\xff" + b"fake-jpg"


# ─── Fixtures / Helpers ────────────────────────────────────────────────────────

@pytest.fixture()
def att_dir(tmp_path):
    with patch.object(settings, "CHAT_FILE_STORAGE_DIR", str(tmp_path)):
        yield tmp_path


def _make_user(client, role: str) -> tuple[str, int]:
    user = auth_storage.save_user({
        "name":            f"AE {role.capitalize()} {_uuid.uuid4().hex[:6]}",
        "email":           f"integ_ae_{role}_{_uuid.uuid4().hex[:10]}@example.com",
        "hashed_password": bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode(),
        "role":            role,
    })
    r = client.post("/api/auth/login", json={"email": user["email"], "password": PASSWORD})
    assert r.status_code == 200
    return r.json()["session_token"], int(user["id"])


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _make_engagement(s_id: int, p_id: int, status: str = "active") -> int:
    with SessionLocal() as db:
        eng = TherapyEngagement(client_id=s_id, psychologist_id=p_id, status=status)
        db.add(eng)
        db.commit()
        db.refresh(eng)
        return eng.id


def _close_engagement(eng_id: int) -> None:
    with SessionLocal() as db:
        db.query(TherapyEngagement).filter(TherapyEngagement.id == eng_id).update(
            {"status": "completed"}, synchronize_session=False,
        )
        db.commit()


def _pair(client):
    s_token, s_id = _make_user(client, "student")
    p_token, p_id = _make_user(client, "psychologist")
    eng_id = _make_engagement(s_id, p_id)
    return {"s_token": s_token, "s_id": s_id, "p_token": p_token, "p_id": p_id, "eng_id": eng_id}


def _create_conv(client, pair) -> str:
    r = client.get("/api/chat/my-conversation", headers=_auth(pair["s_token"]))
    assert r.status_code == 200
    return r.json()["conversation"]["uuid"]


def _upload_student(client, token, conv_uuid, data=_SMALL_PDF, filename="doc.pdf", mime="application/pdf"):
    return client.post(
        f"/api/chat/student/conversations/{conv_uuid}/attachments",
        headers=_auth(token),
        files={"file": (filename, data, mime)},
    )


def _upload_psychologist(client, token, conv_uuid, data=_SMALL_PDF, filename="doc.pdf", mime="application/pdf"):
    return client.post(
        f"/api/chat/conversations/{conv_uuid}/attachments",
        headers=_auth(token),
        files={"file": (filename, data, mime)},
    )


def _send_student(client, token, conv_uuid, content, att_uuids=None):
    body = {"content": content}
    if att_uuids:
        body["attachment_uuids"] = att_uuids
    r = client.post(
        f"/api/chat/student/conversations/{conv_uuid}/messages",
        headers=_auth(token), json=body,
    )
    assert r.status_code == 201, r.text
    return r.json()


def _send_psychologist(client, token, conv_uuid, content, att_uuids=None):
    body = {"content": content}
    if att_uuids:
        body["attachment_uuids"] = att_uuids
    r = client.post(
        f"/api/chat/conversations/{conv_uuid}/messages",
        headers=_auth(token), json=body,
    )
    assert r.status_code == 201, r.text
    return r.json()


def _edit_student(client, token, conv_uuid, msg_uuid, content, remove_att_uuids=None):
    body = {"content": content}
    if remove_att_uuids is not None:
        body["remove_attachment_uuids"] = remove_att_uuids
    return client.patch(
        f"/api/chat/student/conversations/{conv_uuid}/messages/{msg_uuid}",
        headers=_auth(token), json=body,
    )


def _edit_psychologist(client, token, conv_uuid, msg_uuid, content, remove_att_uuids=None):
    body = {"content": content}
    if remove_att_uuids is not None:
        body["remove_attachment_uuids"] = remove_att_uuids
    return client.patch(
        f"/api/chat/conversations/{conv_uuid}/messages/{msg_uuid}",
        headers=_auth(token), json=body,
    )


def _download_student(client, token, conv_uuid, att_uuid):
    return client.get(
        f"/api/chat/student/conversations/{conv_uuid}/attachments/{att_uuid}/download",
        headers=_auth(token),
    )


# ─── Tests ────────────────────────────────────────────────────────────────────

class TestEditWithAttachmentRemoval:

    # 1. Редактирование текста + удаление одного из двух вложений → 200, одно вложение в ответе.
    def test_edit_text_remove_one_attachment(self, client, att_dir):
        p = _pair(client)
        conv = _create_conv(client, p)

        r1 = _upload_student(client, p["s_token"], conv)
        r2 = _upload_student(client, p["s_token"], conv, filename="doc2.pdf")
        att1_uuid = r1.json()["uuid"]
        att2_uuid = r2.json()["uuid"]

        msg = _send_student(client, p["s_token"], conv, "текст", [att1_uuid, att2_uuid])

        r = _edit_student(
            client, p["s_token"], conv, msg["uuid"],
            "обновлённый текст", remove_att_uuids=[att1_uuid],
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["content"] == "обновлённый текст"
        assert body["edited_at"] is not None
        remaining = [a["uuid"] for a in body["attachments"]]
        assert att2_uuid in remaining
        assert att1_uuid not in remaining

    # 2. Редактирование текста + удаление всех вложений → 200, пустой список вложений.
    def test_edit_text_remove_all_attachments(self, client, att_dir):
        p = _pair(client)
        conv = _create_conv(client, p)
        att_uuid = _upload_student(client, p["s_token"], conv).json()["uuid"]
        msg = _send_student(client, p["s_token"], conv, "с вложением", [att_uuid])

        r = _edit_student(
            client, p["s_token"], conv, msg["uuid"],
            "только текст", remove_att_uuids=[att_uuid],
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["content"] == "только текст"
        assert body["attachments"] == []

    # 3. Смена только текста без изменения вложений → 200, вложения в ответе.
    def test_edit_text_only_attachments_unchanged(self, client, att_dir):
        p = _pair(client)
        conv = _create_conv(client, p)
        att_uuid = _upload_student(client, p["s_token"], conv).json()["uuid"]
        msg = _send_student(client, p["s_token"], conv, "оригинал", [att_uuid])

        r = _edit_student(client, p["s_token"], conv, msg["uuid"], "изменён", remove_att_uuids=[])
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["content"] == "изменён"
        assert len(body["attachments"]) == 1
        assert body["attachments"][0]["uuid"] == att_uuid

    # 4. Удаление вложения без изменения текста (текст = тот же).
    def test_remove_attachment_text_unchanged(self, client, att_dir):
        p = _pair(client)
        conv = _create_conv(client, p)
        att_uuid = _upload_student(client, p["s_token"], conv).json()["uuid"]
        msg = _send_student(client, p["s_token"], conv, "текст сохраняется", [att_uuid])

        r = _edit_student(
            client, p["s_token"], conv, msg["uuid"],
            "текст сохраняется", remove_att_uuids=[att_uuid],
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["content"] == "текст сохраняется"
        assert body["attachments"] == []

    # 5. UUID вложения, не принадлежащего этому сообщению → 404.
    def test_remove_foreign_attachment_uuid_returns_404(self, client, att_dir):
        p = _pair(client)
        conv = _create_conv(client, p)
        att_uuid = _upload_student(client, p["s_token"], conv).json()["uuid"]
        msg = _send_student(client, p["s_token"], conv, "с вложением", [att_uuid])

        # Загружаем другое вложение и НЕ привязываем к этому сообщению.
        orphan_uuid = _upload_student(client, p["s_token"], conv, filename="other.pdf").json()["uuid"]

        r = _edit_student(
            client, p["s_token"], conv, msg["uuid"],
            "текст", remove_att_uuids=[orphan_uuid],
        )
        assert r.status_code == 404

    # 6. Несуществующий UUID вложения → 404.
    def test_remove_nonexistent_attachment_uuid_returns_404(self, client, att_dir):
        p = _pair(client)
        conv = _create_conv(client, p)
        msg = _send_student(client, p["s_token"], conv, "без вложений")

        r = _edit_student(
            client, p["s_token"], conv, msg["uuid"],
            "текст", remove_att_uuids=[str(_uuid.uuid4())],
        )
        assert r.status_code == 404

    # 7. Попытка удалить уже удалённое вложение → 404.
    def test_remove_already_deleted_attachment_returns_404(self, client, att_dir):
        p = _pair(client)
        conv = _create_conv(client, p)
        att_uuid = _upload_student(client, p["s_token"], conv).json()["uuid"]
        msg = _send_student(client, p["s_token"], conv, "текст", [att_uuid])

        # Первое удаление.
        r = _edit_student(
            client, p["s_token"], conv, msg["uuid"],
            "обновлено", remove_att_uuids=[att_uuid],
        )
        assert r.status_code == 200

        # Повторная попытка удалить уже удалённое.
        r2 = _edit_student(
            client, p["s_token"], conv, msg["uuid"],
            "ещё раз", remove_att_uuids=[att_uuid],
        )
        assert r2.status_code == 404

    # 8. Пустой текст + удаление всех вложений → 400 (would_be_empty).
    def test_empty_text_remove_all_attachments_returns_400(self, client, att_dir):
        p = _pair(client)
        conv = _create_conv(client, p)
        att_uuid = _upload_student(client, p["s_token"], conv).json()["uuid"]
        msg = _send_student(client, p["s_token"], conv, "текст", [att_uuid])

        r = _edit_student(
            client, p["s_token"], conv, msg["uuid"],
            "", remove_att_uuids=[att_uuid],
        )
        assert r.status_code == 400
        assert "пустое" in r.json().get("detail", "").lower()

    # 9. После soft-delete вложения повторное скачивание → 404.
    def test_deleted_attachment_download_returns_404(self, client, att_dir):
        p = _pair(client)
        conv = _create_conv(client, p)
        att_uuid = _upload_student(client, p["s_token"], conv).json()["uuid"]
        msg = _send_student(client, p["s_token"], conv, "файл", [att_uuid])

        r = _edit_student(
            client, p["s_token"], conv, msg["uuid"],
            "файл удалён", remove_att_uuids=[att_uuid],
        )
        assert r.status_code == 200

        # Скачивание удалённого вложения.
        dl = _download_student(client, p["s_token"], conv, att_uuid)
        assert dl.status_code == 404

    # 10. Психолог удаляет своё вложение → 200.
    def test_psychologist_can_remove_own_attachment(self, client, att_dir):
        p = _pair(client)
        conv = _create_conv(client, p)
        # Психолог загружает и отправляет вложение.
        att_uuid = _upload_psychologist(client, p["p_token"], conv).json()["uuid"]
        msg = _send_psychologist(client, p["p_token"], conv, "от психолога", [att_uuid])

        r = _edit_psychologist(
            client, p["p_token"], conv, msg["uuid"],
            "обновлено", remove_att_uuids=[att_uuid],
        )
        assert r.status_code == 200, r.text
        assert r.json()["attachments"] == []

    # 11. Студент не может удалить вложение из чужого сообщения → 404.
    def test_student_cannot_remove_psychologist_attachment(self, client, att_dir):
        p = _pair(client)
        conv = _create_conv(client, p)
        att_uuid = _upload_psychologist(client, p["p_token"], conv).json()["uuid"]
        msg = _send_psychologist(client, p["p_token"], conv, "сообщение психолога", [att_uuid])

        r = _edit_student(
            client, p["s_token"], conv, msg["uuid"],
            "взлом", remove_att_uuids=[att_uuid],
        )
        assert r.status_code == 404

    # 12. Попытка удалить вложение в закрытом engagement → 409.
    def test_cannot_remove_attachment_in_closed_engagement(self, client, att_dir):
        p = _pair(client)
        conv = _create_conv(client, p)
        att_uuid = _upload_student(client, p["s_token"], conv).json()["uuid"]
        msg = _send_student(client, p["s_token"], conv, "до закрытия", [att_uuid])

        _close_engagement(p["eng_id"])

        r = _edit_student(
            client, p["s_token"], conv, msg["uuid"],
            "после закрытия", remove_att_uuids=[att_uuid],
        )
        assert r.status_code == 409

    # 13. Удаление вложения из другой беседы (через UUID из другой беседы) → 404.
    def test_cannot_remove_attachment_from_other_conversation(self, client, att_dir):
        p1 = _pair(client)
        p2 = _pair(client)
        conv1 = _create_conv(client, p1)
        conv2 = _create_conv(client, p2)

        # Загружаем вложение в беседу 2.
        att_uuid_conv2 = _upload_student(client, p2["s_token"], conv2).json()["uuid"]
        _send_student(client, p2["s_token"], conv2, "в другой беседе", [att_uuid_conv2])

        # Сообщение в беседе 1 без вложений.
        msg = _send_student(client, p1["s_token"], conv1, "моё сообщение")

        # Попытка указать UUID вложения из беседы 2 при редактировании в беседе 1.
        r = _edit_student(
            client, p1["s_token"], conv1, msg["uuid"],
            "текст", remove_att_uuids=[att_uuid_conv2],
        )
        assert r.status_code == 404

    # 14. Пустой список remove_attachment_uuids = [] эквивалентен его отсутствию.
    def test_empty_remove_list_is_noop(self, client, att_dir):
        p = _pair(client)
        conv = _create_conv(client, p)
        att_uuid = _upload_student(client, p["s_token"], conv).json()["uuid"]
        msg = _send_student(client, p["s_token"], conv, "оригинал", [att_uuid])

        r = _edit_student(client, p["s_token"], conv, msg["uuid"], "обновлено", remove_att_uuids=[])
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["content"] == "обновлено"
        assert len(body["attachments"]) == 1
        assert body["attachments"][0]["uuid"] == att_uuid

    # 15. Непустой текст + удаление всех вложений → 200 (content достаточен).
    def test_text_only_after_removing_all_attachments(self, client, att_dir):
        p = _pair(client)
        conv = _create_conv(client, p)
        att_uuid = _upload_student(client, p["s_token"], conv).json()["uuid"]
        msg = _send_student(client, p["s_token"], conv, "текст + вложение", [att_uuid])

        r = _edit_student(
            client, p["s_token"], conv, msg["uuid"],
            "текст без вложения", remove_att_uuids=[att_uuid],
        )
        assert r.status_code == 200
        body = r.json()
        assert body["content"] == "текст без вложения"
        assert body["attachments"] == []

    # 16. Soft-delete в БД проставлен корректно после API-вызова.
    def test_soft_delete_stored_in_db(self, client, att_dir):
        p = _pair(client)
        conv = _create_conv(client, p)
        att_uuid = _upload_student(client, p["s_token"], conv).json()["uuid"]
        msg = _send_student(client, p["s_token"], conv, "текст", [att_uuid])

        r = _edit_student(
            client, p["s_token"], conv, msg["uuid"],
            "обновлено", remove_att_uuids=[att_uuid],
        )
        assert r.status_code == 200

        with SessionLocal() as db:
            att = db.query(ChatAttachment).filter(ChatAttachment.uuid == att_uuid).one()
            assert att.deleted_at is not None

    # 17. Редактирование без remove_attachment_uuids → вложения не затронуты и в ответе.
    def test_edit_without_remove_field_keeps_attachments(self, client, att_dir):
        p = _pair(client)
        conv = _create_conv(client, p)
        att_uuid = _upload_student(client, p["s_token"], conv).json()["uuid"]
        msg = _send_student(client, p["s_token"], conv, "исходник", [att_uuid])

        # Тело без поля remove_attachment_uuids.
        r = client.patch(
            f"/api/chat/student/conversations/{conv}/messages/{msg['uuid']}",
            headers=_auth(p["s_token"]),
            json={"content": "без remove_field"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["content"] == "без remove_field"
        assert len(body["attachments"]) == 1
        assert body["attachments"][0]["uuid"] == att_uuid

    # 18. Ответ PATCH включает is_deleted=False после редактирования.
    def test_edit_response_includes_is_deleted_false(self, client, att_dir):
        p = _pair(client)
        conv = _create_conv(client, p)
        att_uuid = _upload_student(client, p["s_token"], conv).json()["uuid"]
        msg = _send_student(client, p["s_token"], conv, "тест", [att_uuid])

        r = _edit_student(
            client, p["s_token"], conv, msg["uuid"],
            "обновлено", remove_att_uuids=[],
        )
        assert r.status_code == 200
        body = r.json()
        assert body["is_deleted"] is False
        assert "attachments" in body
