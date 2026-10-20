"""
Integration: загрузка в общую медиатеку (POST /api/media/upload).

Покрывает:
  - доступ admin И supervisor (закрытие разрыва: раньше supervisor → 403);
  - student → 403;
  - audit-событие media_uploaded: ровно 1 строка, entity_id == MediaFile.id,
    metadata == {file_type, mime_type, file_size}, без имени файла (ПДн).

Требует dev/disposable PostgreSQL (Stage 1 isolated runner).
"""
import io
import uuid as _uuid

import bcrypt
import pytest
from PIL import Image

from app.auth import storage as auth_storage
from app.db.session import SessionLocal
from app.db.models import AuditLog, MediaFile

PASSWORD = "SecurePass42!"


def _make_user(client, role: str) -> tuple[dict, int]:
    user = auth_storage.save_user({
        "name": f"MediaUp {role} {_uuid.uuid4().hex[:6]}",
        "email": f"integ_mediaup_{role}_{_uuid.uuid4().hex[:10]}@example.com",
        "hashed_password": bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode(),
        "role": role,
    })
    r = client.post("/api/auth/login", json={"email": user["email"], "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['session_token']}"}, int(user["id"])


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), (10, 20, 30)).save(buf, format="PNG")
    return buf.getvalue()


def _upload(client, headers):
    return client.post(
        "/api/media/upload",
        files={"file": ("secret_name.png", _png_bytes(), "image/png")},
        headers=headers,
    )


def _media_id(uuid_str: str) -> int:
    with SessionLocal() as db:
        return db.query(MediaFile).filter(MediaFile.uuid == _uuid.UUID(uuid_str)).first().id


def _audit_rows(entity_id: int):
    with SessionLocal() as db:
        return (
            db.query(AuditLog)
            .filter(AuditLog.event_type == "media_uploaded",
                    AuditLog.entity_id == entity_id)
            .all()
        )


def test_supervisor_can_upload_media(client):
    headers, _ = _make_user(client, "supervisor")
    r = _upload(client, headers)
    assert r.status_code == 201, r.text        # был бы 403 до расширения guard
    body = r.json()
    assert body["uuid"] and body["url"].startswith("/media/uploads/")


def test_admin_can_upload_media(client):
    headers, _ = _make_user(client, "admin")
    r = _upload(client, headers)
    assert r.status_code == 201, r.text


def test_student_cannot_upload_media(client):
    from tests.integration.conftest import create_test_user
    email = f"integ_mediaup_student_{_uuid.uuid4().hex[:8]}@example.com"
    create_test_user(email, PASSWORD)
    r = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    headers = {"Authorization": f"Bearer {r.json()['session_token']}"}
    assert _upload(client, headers).status_code == 403


def _upload_av(client, headers, filename, mime):
    return client.post(
        "/api/media/upload/av",
        files={"file": (filename, b"binary-av-bytes", mime)},
        headers=headers,
    )


def test_av_upload_accepts_video(client):
    headers, _ = _make_user(client, "supervisor")
    r = _upload_av(client, headers, "clip.mp4", "video/mp4")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["file_type"] == "video"
    assert body["url"].endswith(".mp4")


def test_av_upload_accepts_audio(client):
    headers, _ = _make_user(client, "admin")
    r = _upload_av(client, headers, "sound.mp3", "audio/mpeg")
    assert r.status_code == 201, r.text
    assert r.json()["file_type"] == "audio"


def test_av_upload_rejects_image(client):
    headers, _ = _make_user(client, "supervisor")
    r = _upload_av(client, headers, "x.png", "image/png")
    assert r.status_code == 415, r.text


def test_image_upload_rejects_video(client):
    headers, _ = _make_user(client, "admin")
    r = client.post(
        "/api/media/upload",
        files={"file": ("clip.mp4", b"binary", "video/mp4")},
        headers=headers,
    )
    assert r.status_code == 415, r.text


def test_av_upload_writes_audit_with_video_kind(client):
    headers, uid = _make_user(client, "supervisor")
    r = _upload_av(client, headers, "clip.mp4", "video/mp4")
    assert r.status_code == 201, r.text
    rows = _audit_rows(_media_id(r.json()["uuid"]))
    assert len(rows) == 1
    assert rows[0].log_metadata["file_type"] == "video"
    assert rows[0].log_metadata["mime_type"] == "video/mp4"


def test_media_upload_writes_audit_without_filename(client):
    headers, uid = _make_user(client, "supervisor")
    r = _upload(client, headers)
    assert r.status_code == 201, r.text
    mid = _media_id(r.json()["uuid"])

    rows = _audit_rows(mid)
    assert len(rows) == 1
    row = rows[0]
    assert row.entity_type == "media_file"
    assert row.user_id == uid
    assert row.user_role == "supervisor"
    # metadata — только нечувствительное; изображение всегда пересохраняется в webp
    assert row.log_metadata == {
        "file_type": "image",
        "mime_type": "image/webp",
        "file_size": row.log_metadata["file_size"],
    }
    # имя файла (ПДн-риск) нигде не утекает
    blob = f"{row.description} {row.log_metadata}"
    assert "secret_name" not in blob
