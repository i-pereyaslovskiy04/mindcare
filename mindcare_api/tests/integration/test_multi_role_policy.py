"""
API/integration tests: multi-role effective policy для session_notes
(ADR-018 — validated X-Active-Role + консервативный default).

Покрывает:
  - supervisor+psychologist: default → консервативно psychologist (own);
    X-Active-Role: supervisor → content + session_note_content_read audit;
  - невалидная/неимеющаяся X-Active-Role → 403 (не тихий fallback);
  - admin+psychologist: default → metadata-only; X-Active-Role: psychologist →
    own content;
  - supervisor content-read audit пишет effective роль (supervisor), а не
    случайную primary.

Требования: dev PostgreSQL на alembic head, DATA_ENCRYPTION_KEY в .env.
"""

import json
import uuid as _uuid

import bcrypt

from app.auth import storage as auth_storage
from app.db.session import SessionLocal
from app.db.models import AuditLog
from tests.integration.conftest import create_multi_role_user

PASSWORD = "SecurePass42!"


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _make_single_role_user(client, role: str) -> tuple[str, int]:
    user = auth_storage.save_user({
        "name":            f"Integ {role}",
        "email":           f"integ_{role}_{_uuid.uuid4().hex[:10]}@example.com",
        "hashed_password": bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode(),
        "role":            role,
    })
    r = client.post(
        "/api/auth/login", json={"email": user["email"], "password": PASSWORD},
    )
    assert r.status_code == 200
    return r.json()["session_token"], int(user["id"])


def _create_note(client, token: str, content: str) -> dict:
    r = client.post("/api/session-notes", headers=_auth(token), json={
        "content": content, "note_type": "general",
    })
    assert r.status_code == 201, r.text
    return r.json()


def _content_read_events(note_id: int) -> list:
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


# ─── 1. supervisor+psychologist ──────────────────────────────────────────────

class TestSupervisorPlusPsychologist:
    def test_default_conservative_is_psychologist_own(self, client):
        psy_token, _psy_id = _make_single_role_user(client, "psychologist")
        note = _create_note(client, psy_token, f"секрет-{_uuid.uuid4().hex[:8]}")

        token, _uid, _email = create_multi_role_user(
            client, ["psychologist", "supervisor"],
        )
        # без X-Active-Role: консервативно psychologist → чужая заметка = 404
        r = client.get(f"/api/session-notes/{note['id']}", headers=_auth(token))
        assert r.status_code == 404
        assert _content_read_events(note["id"]) == []

    def test_active_supervisor_reads_content_and_audits(self, client):
        psy_token, psy_id = _make_single_role_user(client, "psychologist")
        secret = f"супервизия-{_uuid.uuid4().hex[:8]}"
        note = _create_note(client, psy_token, secret)

        token, uid, _email = create_multi_role_user(
            client, ["psychologist", "supervisor"],
        )
        r = client.get(
            f"/api/session-notes/{note['id']}",
            headers={**_auth(token), "X-Active-Role": "supervisor"},
        )
        assert r.status_code == 200
        assert r.json()["content"] == secret

        events = _content_read_events(note["id"])
        assert len(events) == 1
        assert events[0].user_id == uid
        assert events[0].user_role == "supervisor"  # effective, не случайная primary

    def test_active_psychologist_role_stays_own_only(self, client):
        psy_token, _psy_id = _make_single_role_user(client, "psychologist")
        note = _create_note(client, psy_token, "чужая")

        token, _uid, _email = create_multi_role_user(
            client, ["psychologist", "supervisor"],
        )
        r = client.get(
            f"/api/session-notes/{note['id']}",
            headers={**_auth(token), "X-Active-Role": "psychologist"},
        )
        assert r.status_code == 404  # не автор
        assert _content_read_events(note["id"]) == []

    def test_active_role_not_in_membership_403(self, client):
        psy_token, _psy_id = _make_single_role_user(client, "psychologist")
        note = _create_note(client, psy_token, "секрет")

        token, _uid, _email = create_multi_role_user(
            client, ["psychologist", "supervisor"],
        )
        # admin не входит в membership пользователя → 403, а не тихий fallback
        r = client.get(
            f"/api/session-notes/{note['id']}",
            headers={**_auth(token), "X-Active-Role": "admin"},
        )
        assert r.status_code == 403
        assert _content_read_events(note["id"]) == []

    def test_garbage_active_role_403(self, client):
        token, _uid, _email = create_multi_role_user(
            client, ["psychologist", "supervisor"],
        )
        r = client.get(
            "/api/session-notes",
            headers={**_auth(token), "X-Active-Role": "banana"},
        )
        assert r.status_code == 403

    def test_active_supervisor_list_metadata_only(self, client):
        psy_token, _psy_id = _make_single_role_user(client, "psychologist")
        secret = f"список-{_uuid.uuid4().hex[:8]}"
        _create_note(client, psy_token, secret)

        token, _uid, _email = create_multi_role_user(
            client, ["psychologist", "supervisor"],
        )
        r = client.get(
            "/api/session-notes",
            headers={**_auth(token), "X-Active-Role": "supervisor"},
        )
        assert r.status_code == 200
        for item in r.json()["items"]:
            assert "content" not in item
        assert secret not in json.dumps(r.json(), ensure_ascii=False)


# ─── 2. admin+psychologist ───────────────────────────────────────────────────

class TestAdminPlusPsychologist:
    def test_default_conservative_is_metadata_only(self, client):
        token, _uid, _email = create_multi_role_user(
            client, ["psychologist", "admin"],
        )
        secret = f"своя-{_uuid.uuid4().hex[:8]}"
        note = _create_note(client, token, secret)   # автор — сам пользователь

        # default effective = admin (наименьшая экспозиция) → metadata-only
        r = client.get(f"/api/session-notes/{note['id']}", headers=_auth(token))
        assert r.status_code == 200
        body = r.json()
        assert "content" not in body
        assert body["content_available"] is False
        assert secret not in json.dumps(body, ensure_ascii=False)
        assert _content_read_events(note["id"]) == []

    def test_active_psychologist_reads_own_content(self, client):
        token, _uid, _email = create_multi_role_user(
            client, ["psychologist", "admin"],
        )
        secret = f"своя-контент-{_uuid.uuid4().hex[:8]}"
        note = _create_note(client, token, secret)

        r = client.get(
            f"/api/session-notes/{note['id']}",
            headers={**_auth(token), "X-Active-Role": "psychologist"},
        )
        assert r.status_code == 200
        assert r.json()["content"] == secret
        # чтение своей заметки как psychologist не пишет supervisor-audit
        assert _content_read_events(note["id"]) == []
