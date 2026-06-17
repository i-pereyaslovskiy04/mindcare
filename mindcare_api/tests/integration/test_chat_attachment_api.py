"""
Integration-тесты API вложений чата (Stage 32c).

Покрывает:
  - Upload: student / psychologist / валидация / permission matrix
  - Send message с attachment_uuids
  - Download: participant / non-participant / headers
  - Regression: text-only, edit, delete, список сообщений с attachments []

Требования: dev PostgreSQL на alembic head, DATA_ENCRYPTION_KEY в .env.
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

_SMALL_PDF = b"%PDF-1.4 test file content"   # минимальный байтовый контент
_SMALL_JPG = b"\xff\xd8\xff" + b"fake-jpeg-body"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_user(client, role: str) -> tuple[str, int]:
    user = auth_storage.save_user({
        "name":            f"ATT {role.capitalize()} {_uuid.uuid4().hex[:6]}",
        "email":           f"integ_att_{role}_{_uuid.uuid4().hex[:10]}@example.com",
        "hashed_password": bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode(),
        "role":            role,
    })
    r = client.post("/api/auth/login", json={"email": user["email"], "password": PASSWORD})
    assert r.status_code == 200
    return r.json()["session_token"], int(user["id"])


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _make_engagement(student_id: int, psychologist_id: int, status: str = "active") -> int:
    with SessionLocal() as db:
        eng = TherapyEngagement(
            client_id=student_id,
            psychologist_id=psychologist_id,
            status=status,
        )
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


def _get_conversation_uuid(eng_id: int) -> str | None:
    """Возвращает uuid беседы для engagement или None."""
    with SessionLocal() as db:
        conv = (
            db.query(ChatConversation)
            .filter(ChatConversation.engagement_id == eng_id)
            .first()
        )
        return str(conv.uuid) if conv else None


def _pair(client) -> dict:
    s_token, s_id = _make_user(client, "student")
    p_token, p_id = _make_user(client, "psychologist")
    eng_id = _make_engagement(s_id, p_id)
    return {
        "s_token": s_token, "s_id": s_id,
        "p_token": p_token, "p_id": p_id,
        "eng_id": eng_id,
    }


def _create_conversation(client, pair: dict) -> str:
    """Lazy-create беседы через student GET и вернуть conversation_uuid."""
    r = client.get("/api/chat/my-conversation", headers=_auth(pair["s_token"]))
    assert r.status_code == 200
    return r.json()["conversation"]["uuid"]


def _upload_student(client, token: str, conv_uuid: str, data: bytes, filename: str, mime: str):
    return client.post(
        f"/api/chat/student/conversations/{conv_uuid}/attachments",
        headers=_auth(token),
        files={"file": (filename, data, mime)},
    )


def _upload_psychologist(client, token: str, conv_uuid: str, data: bytes, filename: str, mime: str):
    return client.post(
        f"/api/chat/conversations/{conv_uuid}/attachments",
        headers=_auth(token),
        files={"file": (filename, data, mime)},
    )


def _send_student(client, token: str, conv_uuid: str, content: str, att_uuids=None):
    body = {"content": content}
    if att_uuids:
        body["attachment_uuids"] = att_uuids
    return client.post(
        f"/api/chat/student/conversations/{conv_uuid}/messages",
        headers=_auth(token),
        json=body,
    )


def _send_psychologist(client, token: str, conv_uuid: str, content: str, att_uuids=None):
    body = {"content": content}
    if att_uuids:
        body["attachment_uuids"] = att_uuids
    return client.post(
        f"/api/chat/conversations/{conv_uuid}/messages",
        headers=_auth(token),
        json=body,
    )


@pytest.fixture()
def att_dir(tmp_path):
    """Перенаправляет CHAT_FILE_STORAGE_DIR в tmp_path на время теста."""
    with patch.object(settings, "CHAT_FILE_STORAGE_DIR", str(tmp_path)):
        yield tmp_path


# ─── 1. Upload ────────────────────────────────────────────────────────────────

class TestUpload:
    def test_student_uploads_pdf(self, client, att_dir):
        p       = _pair(client)
        c_uuid  = _create_conversation(client, p)
        r = _upload_student(client, p["s_token"], c_uuid, _SMALL_PDF, "doc.pdf", "application/pdf")
        assert r.status_code == 201
        body = r.json()
        assert body["mime_type"] == "application/pdf"
        assert body["original_filename"] == "doc.pdf"
        assert body["is_image"] is False
        assert body["file_size"] == len(_SMALL_PDF)
        assert "uuid" in body
        assert "storage_key" not in body   # не раскрывать путь

    def test_student_uploads_jpeg(self, client, att_dir):
        p      = _pair(client)
        c_uuid = _create_conversation(client, p)
        r = _upload_student(client, p["s_token"], c_uuid, _SMALL_JPG, "photo.jpg", "image/jpeg")
        assert r.status_code == 201
        assert r.json()["is_image"] is True

    def test_psychologist_uploads_pdf(self, client, att_dir):
        p      = _pair(client)
        c_uuid = _create_conversation(client, p)
        r = _upload_psychologist(
            client, p["p_token"], c_uuid, _SMALL_PDF, "report.pdf", "application/pdf"
        )
        assert r.status_code == 201

    def test_upload_creates_db_row_with_null_message_id(self, client, att_dir):
        p      = _pair(client)
        c_uuid = _create_conversation(client, p)
        r = _upload_student(client, p["s_token"], c_uuid, _SMALL_PDF, "f.pdf", "application/pdf")
        assert r.status_code == 201
        att_uuid = r.json()["uuid"]
        with SessionLocal() as db:
            att = db.query(ChatAttachment).filter(
                ChatAttachment.uuid == att_uuid
            ).first()
            assert att is not None
            assert att.message_id is None   # orphan до send

    def test_upload_creates_physical_file(self, client, att_dir):
        p      = _pair(client)
        c_uuid = _create_conversation(client, p)
        r = _upload_student(client, p["s_token"], c_uuid, _SMALL_PDF, "f.pdf", "application/pdf")
        assert r.status_code == 201
        # Проверяем что в att_dir появился файл
        files = list(att_dir.rglob("*"))
        assert any(f.is_file() for f in files)

    def test_upload_closed_engagement_returns_409(self, client, att_dir):
        p      = _pair(client)
        c_uuid = _create_conversation(client, p)
        _close_engagement(p["eng_id"])
        r = _upload_student(client, p["s_token"], c_uuid, _SMALL_PDF, "f.pdf", "application/pdf")
        assert r.status_code == 409

    def test_student_cannot_upload_to_foreign_conversation(self, client, att_dir):
        p1     = _pair(client)
        p2     = _pair(client)
        c2_uuid = _create_conversation(client, p2)
        # студент из пары 1 пытается загрузить в беседу пары 2
        r = _upload_student(client, p1["s_token"], c2_uuid, _SMALL_PDF, "f.pdf", "application/pdf")
        assert r.status_code == 404

    def test_psychologist_cannot_upload_to_foreign_conversation(self, client, att_dir):
        p1     = _pair(client)
        p2     = _pair(client)
        c2_uuid = _create_conversation(client, p2)
        r = _upload_psychologist(client, p1["p_token"], c2_uuid, _SMALL_PDF, "f.pdf", "application/pdf")
        assert r.status_code == 404

    def test_empty_file_rejected_400(self, client, att_dir):
        p      = _pair(client)
        c_uuid = _create_conversation(client, p)
        r = _upload_student(client, p["s_token"], c_uuid, b"", "f.pdf", "application/pdf")
        assert r.status_code == 400

    def test_too_large_file_rejected_413(self, client, att_dir):
        p      = _pair(client)
        c_uuid = _create_conversation(client, p)
        big_data = b"x" * (20 * 1024 * 1024 + 1)
        r = _upload_student(client, p["s_token"], c_uuid, big_data, "big.pdf", "application/pdf")
        assert r.status_code == 413

    def test_blocked_extension_rejected_400(self, client, att_dir):
        p      = _pair(client)
        c_uuid = _create_conversation(client, p)
        r = _upload_student(
            client, p["s_token"], c_uuid, b"evil", "malware.exe", "application/pdf"
        )
        assert r.status_code == 400

    def test_disallowed_mime_rejected_400(self, client, att_dir):
        p      = _pair(client)
        c_uuid = _create_conversation(client, p)
        r = _upload_student(
            client, p["s_token"], c_uuid, b"zip", "archive.zip", "application/zip"
        )
        assert r.status_code == 400

    def test_unauthenticated_upload_rejected(self, client, att_dir):
        p      = _pair(client)
        c_uuid = _create_conversation(client, p)
        r = client.post(
            f"/api/chat/student/conversations/{c_uuid}/attachments",
            files={"file": ("f.pdf", _SMALL_PDF, "application/pdf")},
        )
        assert r.status_code in (401, 403)

    def test_admin_cannot_upload(self, client, att_dir):
        admin_token, _ = _make_user(client, "admin")
        p      = _pair(client)
        c_uuid = _create_conversation(client, p)
        r = client.post(
            f"/api/chat/student/conversations/{c_uuid}/attachments",
            headers=_auth(admin_token),
            files={"file": ("f.pdf", _SMALL_PDF, "application/pdf")},
        )
        assert r.status_code == 403


# ─── 2. Send message с attachment_uuids ──────────────────────────────────────

class TestSendWithAttachments:
    def test_send_text_and_attachment(self, client, att_dir):
        p      = _pair(client)
        c_uuid = _create_conversation(client, p)
        r_up = _upload_student(client, p["s_token"], c_uuid, _SMALL_PDF, "f.pdf", "application/pdf")
        att_uuid = r_up.json()["uuid"]
        r = _send_student(client, p["s_token"], c_uuid, "Смотри файл", [att_uuid])
        assert r.status_code == 201
        body = r.json()
        assert body["content"] == "Смотри файл"
        assert len(body["attachments"]) == 1
        assert body["attachments"][0]["uuid"] == att_uuid

    def test_send_attachment_only(self, client, att_dir):
        p      = _pair(client)
        c_uuid = _create_conversation(client, p)
        r_up = _upload_student(client, p["s_token"], c_uuid, _SMALL_PDF, "f.pdf", "application/pdf")
        att_uuid = r_up.json()["uuid"]
        r = _send_student(client, p["s_token"], c_uuid, "", [att_uuid])
        assert r.status_code == 201
        assert len(r.json()["attachments"]) == 1

    def test_send_links_message_id_in_db(self, client, att_dir):
        p      = _pair(client)
        c_uuid = _create_conversation(client, p)
        r_up   = _upload_student(client, p["s_token"], c_uuid, _SMALL_PDF, "f.pdf", "application/pdf")
        att_uuid = r_up.json()["uuid"]
        r = _send_student(client, p["s_token"], c_uuid, "hi", [att_uuid])
        msg_id = r.json()["id"]
        with SessionLocal() as db:
            att = db.query(ChatAttachment).filter(
                ChatAttachment.uuid == att_uuid
            ).first()
            assert att.message_id == msg_id

    def test_send_empty_text_no_attachments_rejected(self, client):
        p      = _pair(client)
        c_uuid = _create_conversation(client, p)
        r = _send_student(client, p["s_token"], c_uuid, "")
        assert r.status_code == 422

    def test_cannot_use_foreign_attachment(self, client, att_dir):
        p1     = _pair(client)
        p2     = _pair(client)
        c1_uuid = _create_conversation(client, p1)
        c2_uuid = _create_conversation(client, p2)
        r_up = _upload_student(client, p1["s_token"], c1_uuid, _SMALL_PDF, "f.pdf", "application/pdf")
        att_uuid = r_up.json()["uuid"]
        # студент пары 2 пытается использовать вложение пары 1
        r = _send_student(client, p2["s_token"], c2_uuid, "text", [att_uuid])
        assert r.status_code == 400

    def test_cannot_reuse_attachment(self, client, att_dir):
        p      = _pair(client)
        c_uuid = _create_conversation(client, p)
        r_up   = _upload_student(client, p["s_token"], c_uuid, _SMALL_PDF, "f.pdf", "application/pdf")
        att_uuid = r_up.json()["uuid"]
        # Первая отправка
        r1 = _send_student(client, p["s_token"], c_uuid, "first", [att_uuid])
        assert r1.status_code == 201
        # Вторая отправка с тем же attachment
        r2 = _send_student(client, p["s_token"], c_uuid, "second", [att_uuid])
        assert r2.status_code == 400

    def test_too_many_attachments_rejected(self, client, att_dir):
        p      = _pair(client)
        c_uuid = _create_conversation(client, p)
        uuids  = []
        # Загружаем 6 файлов (лимит 5)
        for i in range(6):
            r_up = _upload_student(
                client, p["s_token"], c_uuid,
                _SMALL_PDF + bytes([i]), f"f{i}.pdf", "application/pdf",
            )
            uuids.append(r_up.json()["uuid"])
        r = _send_student(client, p["s_token"], c_uuid, "too many", uuids)
        assert r.status_code == 400

    def test_list_messages_includes_attachments(self, client, att_dir):
        p      = _pair(client)
        c_uuid = _create_conversation(client, p)
        r_up   = _upload_student(client, p["s_token"], c_uuid, _SMALL_PDF, "f.pdf", "application/pdf")
        att_uuid = r_up.json()["uuid"]
        _send_student(client, p["s_token"], c_uuid, "msg", [att_uuid])
        r = client.get(
            f"/api/chat/student/conversations/{c_uuid}/messages",
            headers=_auth(p["s_token"]),
        )
        assert r.status_code == 200
        msgs = r.json()["items"]
        assert any(len(m["attachments"]) == 1 for m in msgs)

    def test_psychologist_sees_attachment_in_messages(self, client, att_dir):
        p      = _pair(client)
        c_uuid = _create_conversation(client, p)
        r_up   = _upload_student(client, p["s_token"], c_uuid, _SMALL_PDF, "f.pdf", "application/pdf")
        att_uuid = r_up.json()["uuid"]
        _send_student(client, p["s_token"], c_uuid, "msg", [att_uuid])
        r = client.get(
            f"/api/chat/conversations/{c_uuid}/messages",
            headers=_auth(p["p_token"]),
        )
        assert r.status_code == 200
        msgs = r.json()["items"]
        assert any(len(m["attachments"]) == 1 for m in msgs)

    def test_psychologist_can_send_with_attachment(self, client, att_dir):
        p      = _pair(client)
        c_uuid = _create_conversation(client, p)
        r_up   = _upload_psychologist(
            client, p["p_token"], c_uuid, _SMALL_PDF, "rep.pdf", "application/pdf"
        )
        att_uuid = r_up.json()["uuid"]
        r = _send_psychologist(client, p["p_token"], c_uuid, "см. файл", [att_uuid])
        assert r.status_code == 201
        assert len(r.json()["attachments"]) == 1


# ─── 3. Download ──────────────────────────────────────────────────────────────

class TestDownload:
    def _upload_and_send(self, client, att_dir, pair) -> tuple[str, str]:
        """Загружает файл, отправляет сообщение. Возвращает (conv_uuid, att_uuid)."""
        c_uuid = _create_conversation(client, pair)
        r_up   = _upload_student(
            client, pair["s_token"], c_uuid, _SMALL_PDF, "report.pdf", "application/pdf"
        )
        att_uuid = r_up.json()["uuid"]
        _send_student(client, pair["s_token"], c_uuid, "see file", [att_uuid])
        return c_uuid, att_uuid

    def test_sender_can_download(self, client, att_dir):
        p                = _pair(client)
        c_uuid, att_uuid = self._upload_and_send(client, att_dir, p)
        r = client.get(
            f"/api/chat/student/conversations/{c_uuid}/attachments/{att_uuid}/download",
            headers=_auth(p["s_token"]),
        )
        assert r.status_code == 200
        assert r.content == _SMALL_PDF

    def test_psychologist_can_download(self, client, att_dir):
        p                = _pair(client)
        c_uuid, att_uuid = self._upload_and_send(client, att_dir, p)
        r = client.get(
            f"/api/chat/conversations/{c_uuid}/attachments/{att_uuid}/download",
            headers=_auth(p["p_token"]),
        )
        assert r.status_code == 200
        assert r.content == _SMALL_PDF

    def test_download_headers(self, client, att_dir):
        p                = _pair(client)
        c_uuid, att_uuid = self._upload_and_send(client, att_dir, p)
        r = client.get(
            f"/api/chat/student/conversations/{c_uuid}/attachments/{att_uuid}/download",
            headers=_auth(p["s_token"]),
        )
        assert r.status_code == 200
        assert "attachment" in r.headers.get("content-disposition", "").lower()
        assert r.headers.get("cache-control", "") == "private, no-store"
        assert r.headers.get("x-content-type-options", "") == "nosniff"

    def test_download_after_closed_engagement(self, client, att_dir):
        p                = _pair(client)
        c_uuid, att_uuid = self._upload_and_send(client, att_dir, p)
        _close_engagement(p["eng_id"])
        r = client.get(
            f"/api/chat/student/conversations/{c_uuid}/attachments/{att_uuid}/download",
            headers=_auth(p["s_token"]),
        )
        assert r.status_code == 200

    def test_non_participant_cannot_download(self, client, att_dir):
        p1               = _pair(client)
        p2               = _pair(client)
        c_uuid, att_uuid = self._upload_and_send(client, att_dir, p1)
        # студент пары 2 не является участником беседы пары 1
        r = client.get(
            f"/api/chat/student/conversations/{c_uuid}/attachments/{att_uuid}/download",
            headers=_auth(p2["s_token"]),
        )
        assert r.status_code == 404

    def test_attachment_from_another_conversation_not_downloadable(self, client, att_dir):
        p1               = _pair(client)
        p2               = _pair(client)
        c1_uuid, att1_uuid = self._upload_and_send(client, att_dir, p1)
        c2_uuid = _create_conversation(client, p2)
        # студент пары 1 пытается скачать вложение через беседу пары 2
        r = client.get(
            f"/api/chat/student/conversations/{c2_uuid}/attachments/{att1_uuid}/download",
            headers=_auth(p1["s_token"]),
        )
        assert r.status_code == 404

    def test_nonexistent_attachment_returns_404(self, client, att_dir):
        p      = _pair(client)
        c_uuid = _create_conversation(client, p)
        fake   = str(_uuid.uuid4())
        r = client.get(
            f"/api/chat/student/conversations/{c_uuid}/attachments/{fake}/download",
            headers=_auth(p["s_token"]),
        )
        assert r.status_code == 404


# ─── 4. Regression: существующая функциональность не сломана ─────────────────

class TestRegression:
    def test_text_only_message_still_works(self, client):
        p      = _pair(client)
        c_uuid = _create_conversation(client, p)
        r = _send_student(client, p["s_token"], c_uuid, "plain text")
        assert r.status_code == 201
        body = r.json()
        assert body["content"] == "plain text"
        assert body["attachments"] == []

    def test_list_messages_returns_attachments_empty_list(self, client):
        p      = _pair(client)
        c_uuid = _create_conversation(client, p)
        _send_student(client, p["s_token"], c_uuid, "hello")
        r = client.get(
            f"/api/chat/student/conversations/{c_uuid}/messages",
            headers=_auth(p["s_token"]),
        )
        assert r.status_code == 200
        for msg in r.json()["items"]:
            assert "attachments" in msg
            assert isinstance(msg["attachments"], list)

    def test_edit_message_not_allowed_on_closed(self, client):
        p      = _pair(client)
        c_uuid = _create_conversation(client, p)
        r_send = _send_student(client, p["s_token"], c_uuid, "original")
        msg_uuid = r_send.json()["uuid"]
        _close_engagement(p["eng_id"])
        r = client.patch(
            f"/api/chat/student/conversations/{c_uuid}/messages/{msg_uuid}",
            headers=_auth(p["s_token"]),
            json={"content": "changed"},
        )
        assert r.status_code == 409

    def test_delete_message_hides_from_list(self, client):
        p      = _pair(client)
        c_uuid = _create_conversation(client, p)
        r_send = _send_student(client, p["s_token"], c_uuid, "to delete")
        msg_uuid = r_send.json()["uuid"]
        r_del = client.delete(
            f"/api/chat/student/conversations/{c_uuid}/messages/{msg_uuid}",
            headers=_auth(p["s_token"]),
        )
        assert r_del.status_code == 200
        r_list = client.get(
            f"/api/chat/student/conversations/{c_uuid}/messages",
            headers=_auth(p["s_token"]),
        )
        msg_ids = [m["id"] for m in r_list.json()["items"]]
        assert r_del.json()["id"] not in msg_ids

    def test_student_role_boundary_preserved(self, client):
        """Student не может обращаться к psychologist-эндпоинтам."""
        p      = _pair(client)
        c_uuid = _create_conversation(client, p)
        r = client.get(
            f"/api/chat/conversations/{c_uuid}/messages",
            headers=_auth(p["s_token"]),
        )
        assert r.status_code == 403

    def test_psychologist_role_boundary_preserved(self, client):
        """Psychologist не может обращаться к student-эндпоинтам."""
        p      = _pair(client)
        c_uuid = _create_conversation(client, p)
        r = client.get(
            f"/api/chat/student/conversations/{c_uuid}/messages",
            headers=_auth(p["p_token"]),
        )
        assert r.status_code == 403
