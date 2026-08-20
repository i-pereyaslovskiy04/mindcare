"""
Stage 4B-3 — gated integration: chat_attachment_uploaded/downloaded через
record_event(). Требует dev/disposable PostgreSQL (Stage 1 isolated runner) —
НЕ запускается против live PostgreSQL в рамках этого этапа.

Покрывает:
  - upload → ровно 1 строка chat_attachment_uploaded, entity_id == реальный
    ChatAttachment.id, metadata == {"file_size":..., "mime_type":...},
    description is None, actor == uploader;
  - download → ровно 1 строка chat_attachment_downloaded, тот же entity_id,
    metadata == {}, description is None;
  - отсутствие original_filename/storage_key/checksum/UUID в audit.
"""
import uuid as _uuid
from unittest.mock import patch

import bcrypt
import pytest

from app.auth import storage as auth_storage
from app.core.config import settings
from app.db.session import SessionLocal
from app.db.models import AuditLog, ChatAttachment, TherapyEngagement

PASSWORD = "SecurePass42!"
_SMALL_PDF = b"%PDF-1.4 test file content"


def _make_user(client, role: str) -> tuple[str, int]:
    user = auth_storage.save_user({
        "name":            f"AttAudit {role.capitalize()} {_uuid.uuid4().hex[:6]}",
        "email":           f"integ_attaudit_{role}_{_uuid.uuid4().hex[:10]}@example.com",
        "hashed_password": bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode(),
        "role":            role,
    })
    r = client.post("/api/auth/login", json={"email": user["email"], "password": PASSWORD})
    assert r.status_code == 200
    return r.json()["session_token"], int(user["id"])


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _pair(client) -> dict:
    s_token, s_id = _make_user(client, "student")
    p_token, p_id = _make_user(client, "psychologist")
    with SessionLocal() as db:
        eng = TherapyEngagement(client_id=s_id, psychologist_id=p_id, status="active")
        db.add(eng)
        db.commit()
        db.refresh(eng)
        eng_id = eng.id
    return {"s_token": s_token, "s_id": s_id, "p_token": p_token, "p_id": p_id, "eng_id": eng_id}


def _create_conversation(client, pair: dict) -> str:
    r = client.get("/api/chat/my-conversation", headers=_auth(pair["s_token"]))
    assert r.status_code == 200
    return r.json()["conversation"]["uuid"]


@pytest.fixture()
def att_dir(tmp_path):
    with patch.object(settings, "CHAT_FILE_STORAGE_DIR", str(tmp_path)):
        yield tmp_path


def _audit_rows(event_type: str, entity_id: int):
    with SessionLocal() as db:
        rows = (
            db.query(AuditLog)
            .filter(AuditLog.event_type == event_type, AuditLog.entity_id == entity_id)
            .all()
        )
        for r in rows:
            db.expunge(r)
        return rows


def test_upload_writes_single_row_with_real_internal_id(client, att_dir):
    p = _pair(client)
    c_uuid = _create_conversation(client, p)
    r = client.post(
        f"/api/chat/student/conversations/{c_uuid}/attachments",
        headers=_auth(p["s_token"]),
        files={"file": ("secret_name.pdf", _SMALL_PDF, "application/pdf")},
    )
    assert r.status_code == 201, r.text
    att_uuid = r.json()["uuid"]

    with SessionLocal() as db:
        att = db.query(ChatAttachment).filter(ChatAttachment.uuid == att_uuid).first()
        assert att is not None
        internal_id = att.id

    rows = _audit_rows("chat_attachment_uploaded", internal_id)
    assert len(rows) == 1
    row = rows[0]
    assert row.user_id == p["s_id"]
    assert row.user_role == "student"
    assert row.entity_type == "chat_attachment"
    assert row.log_metadata == {
        "file_size": len(_SMALL_PDF), "mime_type": "application/pdf",
    }
    assert row.description is None
    # чувствительные/внутренние значения не попадают в audit
    blob = f"{row.description} {row.log_metadata}"
    assert "secret_name.pdf" not in blob
    assert att_uuid not in blob
    assert "storage_key" not in blob


def test_download_writes_single_row_same_entity_id(client, att_dir):
    p = _pair(client)
    c_uuid = _create_conversation(client, p)
    upload = client.post(
        f"/api/chat/student/conversations/{c_uuid}/attachments",
        headers=_auth(p["s_token"]),
        files={"file": ("doc.pdf", _SMALL_PDF, "application/pdf")},
    )
    assert upload.status_code == 201, upload.text
    att_uuid = upload.json()["uuid"]

    with SessionLocal() as db:
        att = db.query(ChatAttachment).filter(ChatAttachment.uuid == att_uuid).first()
        internal_id = att.id

    r = client.get(
        f"/api/chat/student/conversations/{c_uuid}/attachments/{att_uuid}/download",
        headers=_auth(p["s_token"]),
    )
    assert r.status_code == 200

    rows = _audit_rows("chat_attachment_downloaded", internal_id)
    assert len(rows) == 1
    row = rows[0]
    assert row.user_id == p["s_id"]
    assert row.user_role == "student"
    assert row.entity_type == "chat_attachment"
    assert (row.log_metadata or {}) == {}
    assert row.description is None
    blob = f"{row.description} {row.log_metadata}"
    assert "doc.pdf" not in blob
    assert att_uuid not in blob


def test_psychologist_upload_and_download_actor_mapping(client, att_dir):
    p = _pair(client)
    c_uuid = _create_conversation(client, p)
    upload = client.post(
        f"/api/chat/conversations/{c_uuid}/attachments",
        headers=_auth(p["p_token"]),
        files={"file": ("report.pdf", _SMALL_PDF, "application/pdf")},
    )
    assert upload.status_code == 201, upload.text
    att_uuid = upload.json()["uuid"]

    with SessionLocal() as db:
        internal_id = (
            db.query(ChatAttachment).filter(ChatAttachment.uuid == att_uuid).first().id
        )

    up_rows = _audit_rows("chat_attachment_uploaded", internal_id)
    assert len(up_rows) == 1 and up_rows[0].user_id == p["p_id"]
    assert up_rows[0].user_role == "psychologist"

    r = client.get(
        f"/api/chat/conversations/{c_uuid}/attachments/{att_uuid}/download",
        headers=_auth(p["p_token"]),
    )
    assert r.status_code == 200
    down_rows = _audit_rows("chat_attachment_downloaded", internal_id)
    assert len(down_rows) == 1 and down_rows[0].user_id == p["p_id"]
