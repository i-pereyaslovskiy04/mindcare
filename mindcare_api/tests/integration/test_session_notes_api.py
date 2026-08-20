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


def _audit_rows(note_id: int, event_type: str) -> list[AuditLog]:
    with SessionLocal() as db:
        rows = (
            db.query(AuditLog)
            .filter(
                AuditLog.entity_type == "session_note",
                AuditLog.entity_id == note_id,
                AuditLog.event_type == event_type,
            )
            .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
            .all()
        )
        for row in rows:
            db.expunge(row)
        return rows


def _content_read_events(note_id: int) -> list[AuditLog]:
    return _audit_rows(note_id, "session_note_content_read")


def _assert_success_contract(row, note_id, actor_id, actor_role):
    """Канон Stage 4B-6: metadata={}, description None, success, только note id."""
    assert row.entity_type == "session_note"
    assert row.entity_id == note_id
    assert row.outcome == "success"
    assert row.failure_reason_code is None
    assert row.description is None
    assert (row.log_metadata or {}) == {}
    assert row.user_id == actor_id
    assert row.user_role == actor_role


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
        psy_token, _ = _make_user(client, "psychologist")
        sup_token, sup_id = _make_user(client, "supervisor")
        secret = f"аудируемое-чтение-{_uuid.uuid4().hex[:8]}"
        note = _create_note(client, psy_token, secret)

        r = client.get(f"/api/session-notes/{note['id']}", headers=_auth(sup_token))
        assert r.status_code == 200

        events = _content_read_events(note["id"])
        assert len(events) == 1
        # metadata пуста (author_id больше не дублируется — он в user_id create/update)
        _assert_success_contract(events[0], note["id"], sup_id, "supervisor")
        assert events[0].ip_address is not None
        assert events[0].user_agent is not None

    def test_supervisor_repeat_read_appends_second_row(self, client):
        psy_token, _ = _make_user(client, "psychologist")
        sup_token, sup_id = _make_user(client, "supervisor")
        note = _create_note(client, psy_token, f"read-trail-{_uuid.uuid4().hex[:8]}")

        client.get(f"/api/session-notes/{note['id']}", headers=_auth(sup_token))
        client.get(f"/api/session-notes/{note['id']}", headers=_auth(sup_token))

        events = _content_read_events(note["id"])
        assert len(events) == 2   # read trail: каждая выдача content — отдельная строка
        for ev in events:
            _assert_success_contract(ev, note["id"], sup_id, "supervisor")

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


# ─── 4b. create/update audit (ATOMIC) ────────────────────────────────────────

class TestCreateUpdateAudit:
    def test_create_writes_success_contract(self, client):
        psy_token, psy_id = _make_user(client, "psychologist")
        note = _create_note(client, psy_token, f"создание-{_uuid.uuid4().hex[:8]}")

        rows = _audit_rows(note["id"], "session_note_created")
        assert len(rows) == 1
        # author_id психолога присутствует как user_id (actor), НЕ в metadata
        _assert_success_contract(rows[0], note["id"], psy_id, "psychologist")

    def test_update_writes_success_contract_same_target(self, client):
        psy_token, psy_id = _make_user(client, "psychologist")
        note = _create_note(client, psy_token, f"до-{_uuid.uuid4().hex[:8]}")

        r = client.patch(
            f"/api/session-notes/{note['id']}", headers=_auth(psy_token),
            json={"content": f"после-{_uuid.uuid4().hex[:8]}"},
        )
        assert r.status_code == 200

        rows = _audit_rows(note["id"], "session_note_updated")
        assert len(rows) == 1
        _assert_success_contract(rows[0], note["id"], psy_id, "psychologist")

    def test_audit_rows_contain_no_plaintext(self, client):
        psy_token, _ = _make_user(client, "psychologist")
        sup_token, _ = _make_user(client, "supervisor")
        secret = f"нигде-в-аудите-{_uuid.uuid4().hex[:8]}"
        note = _create_note(client, psy_token, secret)
        client.patch(
            f"/api/session-notes/{note['id']}", headers=_auth(psy_token),
            json={"content": f"{secret}-upd"},
        )
        client.get(f"/api/session-notes/{note['id']}", headers=_auth(sup_token))

        rows = (
            _audit_rows(note["id"], "session_note_created")
            + _audit_rows(note["id"], "session_note_updated")
            + _content_read_events(note["id"])
        )
        for row in rows:
            dumped = (row.description or "") + json.dumps(
                row.log_metadata or {}, ensure_ascii=False,
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


# ─── 6. Request context sanitization + decryption failure ────────────────────

class TestContextAndDecryptAudit:
    def test_malformed_ip_ua_not_500_and_null_in_audit(self, client):
        """Некорректный IP + oversized UA: операции не падают в 500, а
        соответствующие audit ip_address/user_agent сохраняются как NULL
        (санитизация в build_request_context до facade)."""
        from fastapi.testclient import TestClient
        from app.main import app

        psy_token, _ = _make_user(client, "psychologist")
        sup_token, _ = _make_user(client, "supervisor")
        bad = TestClient(app, client=("not-an-ip", 12345))
        oversized = {"User-Agent": "x" * 600}

        # create через bad client → 201, created-audit ip/ua = NULL
        rc = bad.post(
            "/api/session-notes",
            headers={"Authorization": f"Bearer {psy_token}", **oversized},
            json={"content": "плохой-контекст", "note_type": "general"},
        )
        assert rc.status_code == 201, rc.text   # не 500
        note_id = rc.json()["id"]
        crows = _audit_rows(note_id, "session_note_created")
        assert len(crows) == 1
        assert crows[0].ip_address is None
        assert crows[0].user_agent is None

        # supervisor content_read через bad client → 200, read-audit ip/ua = NULL
        rg = bad.get(
            f"/api/session-notes/{note_id}",
            headers={"Authorization": f"Bearer {sup_token}", **oversized},
        )
        assert rg.status_code == 200, rg.text   # не 500
        rrows = _content_read_events(note_id)
        assert len(rrows) == 1
        assert rrows[0].ip_address is None
        assert rrows[0].user_agent is None

    def test_supervisor_decrypt_failure_creates_no_content_read(self, client):
        """Повреждённый ciphertext: supervisor GET падает (decrypt→RuntimeError→
        500) ДО записи аудита → session_note_content_read не создаётся."""
        psy_token, _ = _make_user(client, "psychologist")
        sup_token, _ = _make_user(client, "supervisor")
        note = _create_note(client, psy_token, "будет-повреждено")

        before = len(_content_read_events(note["id"]))

        # повреждаем ciphertext напрямую в БД (prefix сохраняем, токен ломаем)
        with SessionLocal() as db:
            db.query(SessionNote).filter(SessionNote.id == note["id"]).update(
                {"content": ENCRYPTION_PREFIX + "corrupted-not-a-valid-token"}
            )
            db.commit()

        r = client.get(
            f"/api/session-notes/{note['id']}", headers=_auth(sup_token),
        )
        assert r.status_code == 500   # decrypt fail → RuntimeError → 500

        after = _content_read_events(note["id"])
        assert len(after) == before   # аудит content-read не создан для этого id
