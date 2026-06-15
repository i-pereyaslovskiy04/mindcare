"""
API/integration tests for session_notes access policy B + read audit (Stage 25b).

Политика:
  psychologist — только свои заметки, с content;
  supervisor   — list metadata-only; get by id: content + audit;
  admin        — metadata-only везде, decrypt не вызывается;
  student      — 403.

Требования: dev PostgreSQL на alembic head, DATA_ENCRYPTION_KEY в .env.
"""

import json
import uuid as _uuid

import bcrypt
import pytest

from app.auth import storage as auth_storage
from app.db.session import SessionLocal
from app.db.models import AuditLog, SessionNote
from app.core.encryption import ENCRYPTION_PREFIX

PASSWORD = "SecurePass42!"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_user(client, role: str) -> tuple[str, int]:
    """Создаёт пользователя с ролью, логинится, возвращает (token, user_id)."""
    user = auth_storage.save_user({
        "name":            f"Integration {role.capitalize()}",
        "email":           f"integ_{role}_{_uuid.uuid4().hex[:10]}@example.com",
        "hashed_password": bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode(),
        "role":            role,
    })
    r = client.post("/api/auth/login", json={
        "email": user["email"], "password": PASSWORD,
    })
    assert r.status_code == 200
    return r.json()["session_token"], int(user["id"])


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _create_note(client, token: str, content: str) -> dict:
    r = client.post("/api/session-notes", headers=_auth(token), json={
        "content": content, "note_type": "general",
    })
    assert r.status_code == 201
    return r.json()


def _content_read_events(note_id: int) -> list[AuditLog]:
    with SessionLocal() as db:
        rows = (
            db.query(AuditLog)
            .filter(
                AuditLog.entity_type == "session_note",
                AuditLog.entity_id == note_id,
                AuditLog.event_type == "session_note_content_read",
            )
            .all()
        )
        for row in rows:
            db.expunge(row)
        return rows


# ─── 1. Psychologist: свои заметки с content ─────────────────────────────────

class TestPsychologistOwnNotes:
    def test_create_and_get_own_note_with_content(self, client):
        token, _ = _make_user(client, "psychologist")
        secret = f"терапевтический-секрет-{_uuid.uuid4().hex[:8]}"
        note = _create_note(client, token, secret)

        r = client.get(f"/api/session-notes/{note['id']}", headers=_auth(token))
        assert r.status_code == 200
        assert r.json()["content"] == secret

    def test_own_list_contains_content(self, client):
        token, _ = _make_user(client, "psychologist")
        secret = f"секрет-списка-{_uuid.uuid4().hex[:8]}"
        _create_note(client, token, secret)

        r = client.get("/api/session-notes", headers=_auth(token))
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 1
        assert items[0]["content"] == secret

    def test_cannot_get_foreign_note(self, client):
        token_a, _ = _make_user(client, "psychologist")
        token_b, _ = _make_user(client, "psychologist")
        note = _create_note(client, token_a, "чужая заметка")

        r = client.get(f"/api/session-notes/{note['id']}", headers=_auth(token_b))
        assert r.status_code == 404  # неотличимо от несуществующей

    def test_foreign_note_absent_from_list(self, client):
        token_a, _ = _make_user(client, "psychologist")
        token_b, _ = _make_user(client, "psychologist")
        _create_note(client, token_a, "чужая заметка для списка")

        r = client.get("/api/session-notes", headers=_auth(token_b))
        assert r.status_code == 200
        assert r.json()["total"] == 0


# ─── 2. Student: 403 ──────────────────────────────────────────────────────────

class TestStudentForbidden:
    def test_student_403_on_all_endpoints(self, client):
        token, _ = _make_user(client, "student")
        assert client.get("/api/session-notes", headers=_auth(token)).status_code == 403
        assert client.get("/api/session-notes/1", headers=_auth(token)).status_code == 403
        assert client.post(
            "/api/session-notes", headers=_auth(token), json={"content": "x"},
        ).status_code == 403


# ─── 3. Admin: metadata-only, без decrypt ────────────────────────────────────

class TestAdminMetadataOnly:
    def test_admin_get_has_no_content(self, client):
        psy_token, _ = _make_user(client, "psychologist")
        admin_token, _ = _make_user(client, "admin")
        secret = f"скрыто-от-админа-{_uuid.uuid4().hex[:8]}"
        note = _create_note(client, psy_token, secret)

        r = client.get(f"/api/session-notes/{note['id']}", headers=_auth(admin_token))
        assert r.status_code == 200
        body = r.json()
        assert "content" not in body
        assert body["content_available"] is False
        assert secret not in json.dumps(body, ensure_ascii=False)

    def test_admin_list_metadata_only(self, client):
        psy_token, _ = _make_user(client, "psychologist")
        admin_token, _ = _make_user(client, "admin")
        secret = f"скрыто-в-списке-{_uuid.uuid4().hex[:8]}"
        _create_note(client, psy_token, secret)

        r = client.get("/api/session-notes", headers=_auth(admin_token))
        assert r.status_code == 200
        body = r.json()
        assert body["total"] >= 1
        for item in body["items"]:
            assert "content" not in item
            assert item["content_available"] is False
        assert secret not in json.dumps(body, ensure_ascii=False)

    def test_admin_path_never_calls_decrypt(self, client, monkeypatch):
        """Metadata-путь не вызывает decrypt_text вообще."""
        psy_token, _ = _make_user(client, "psychologist")
        admin_token, _ = _make_user(client, "admin")
        note = _create_note(client, psy_token, "не расшифровывать")

        def _boom(*a, **kw):
            raise AssertionError("decrypt_text must not be called on admin path")

        monkeypatch.setattr("app.session_notes.storage.decrypt_text", _boom)

        assert client.get(
            f"/api/session-notes/{note['id']}", headers=_auth(admin_token),
        ).status_code == 200
        assert client.get(
            "/api/session-notes", headers=_auth(admin_token),
        ).status_code == 200

    def test_admin_get_creates_no_content_read_audit(self, client):
        psy_token, _ = _make_user(client, "psychologist")
        admin_token, _ = _make_user(client, "admin")
        note = _create_note(client, psy_token, "metadata-read не аудируется")

        client.get(f"/api/session-notes/{note['id']}", headers=_auth(admin_token))
        assert _content_read_events(note["id"]) == []


# ─── 4. Supervisor: list metadata, get content + audit ───────────────────────

class TestSupervisorPolicy:
    def test_supervisor_list_metadata_only(self, client):
        psy_token, _ = _make_user(client, "psychologist")
        sup_token, _ = _make_user(client, "supervisor")
        secret = f"скрыто-в-списке-супервизора-{_uuid.uuid4().hex[:8]}"
        _create_note(client, psy_token, secret)

        r = client.get("/api/session-notes", headers=_auth(sup_token))
        assert r.status_code == 200
        for item in r.json()["items"]:
            assert "content" not in item
        assert secret not in json.dumps(r.json(), ensure_ascii=False)

    def test_supervisor_list_creates_no_audit(self, client):
        psy_token, _ = _make_user(client, "psychologist")
        sup_token, _ = _make_user(client, "supervisor")
        note = _create_note(client, psy_token, "список без аудита")

        client.get("/api/session-notes", headers=_auth(sup_token))
        assert _content_read_events(note["id"]) == []

    def test_supervisor_get_returns_content(self, client):
        psy_token, _ = _make_user(client, "psychologist")
        sup_token, _ = _make_user(client, "supervisor")
        secret = f"супервизия-{_uuid.uuid4().hex[:8]}"
        note = _create_note(client, psy_token, secret)

        r = client.get(f"/api/session-notes/{note['id']}", headers=_auth(sup_token))
        assert r.status_code == 200
        assert r.json()["content"] == secret

    def test_supervisor_content_read_audited(self, client):
        psy_token, psy_id = _make_user(client, "psychologist")
        sup_token, sup_id = _make_user(client, "supervisor")
        secret = f"аудируемое-чтение-{_uuid.uuid4().hex[:8]}"
        note = _create_note(client, psy_token, secret)

        r = client.get(f"/api/session-notes/{note['id']}", headers=_auth(sup_token))
        assert r.status_code == 200

        events = _content_read_events(note["id"])
        assert len(events) == 1
        event = events[0]
        assert event.user_id == sup_id
        assert event.user_role == "supervisor"
        assert event.entity_type == "session_note"
        assert event.entity_id == note["id"]
        assert event.log_metadata["author_id"] == psy_id
        assert event.ip_address is not None
        assert event.user_agent is not None

    def test_audit_event_contains_no_plaintext(self, client):
        psy_token, _ = _make_user(client, "psychologist")
        sup_token, _ = _make_user(client, "supervisor")
        secret = f"никогда-в-аудите-{_uuid.uuid4().hex[:8]}"
        note = _create_note(client, psy_token, secret)

        client.get(f"/api/session-notes/{note['id']}", headers=_auth(sup_token))

        event = _content_read_events(note["id"])[0]
        dumped = (event.description or "") + json.dumps(
            event.log_metadata or {}, ensure_ascii=False,
        )
        assert secret not in dumped


# ─── 5. Encrypted-at-rest не сломан ──────────────────────────────────────────

class TestEncryptionAtRest:
    def test_db_stores_ciphertext_only(self, client):
        token, _ = _make_user(client, "psychologist")
        secret = f"plaintext-не-в-БД-{_uuid.uuid4().hex[:8]}"
        note = _create_note(client, token, secret)

        with SessionLocal() as db:
            stored = db.query(SessionNote.content).filter(
                SessionNote.id == note["id"]
            ).scalar()

        assert stored.startswith(ENCRYPTION_PREFIX)
        assert secret not in stored
