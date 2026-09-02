"""
Integration: авторство psychologist в психодиагностике (Этап F2, ADR-016).

Покрывает:
  - psychologist создаёт тест ВСЕГДА как draft (даже если прислал status=published);
  - редактирует/удаляет свой draft/needs_changes — 200/204;
  - редактирует/удаляет свой in_review/published → 409 (TestNotEditable);
  - редактирует/удаляет чужой тест → 404 (не 403 — чужого не отличить от
    несуществующего, как session_notes);
  - список — только свои тесты, все статусы;
  - media upload (image + av) psychologist → 201 (было 403 до Этапа F2);
  - analyze/preview-score psychologist → 200 (stateless, без ownership).

Требует dev/disposable PostgreSQL (Stage 1 isolated runner).
"""
import io
import uuid as _uuid

import bcrypt
import pytest
from PIL import Image

from app.auth import storage as auth_storage
from app.db.session import SessionLocal
from app.db.models import Test as TestModel

PASSWORD = "SecurePass42!"


def _staff(client, role: str):
    user = auth_storage.save_user({
        "name": f"PsychTests {role} {_uuid.uuid4().hex[:6]}",
        "email": f"integ_psychtests_{role}_{_uuid.uuid4().hex[:10]}@example.com",
        "hashed_password": bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode(),
        "role": role,
    })
    r = client.post("/api/auth/login", json={"email": user["email"], "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['session_token']}"}, int(user["id"])


def _payload(title, status="published"):
    return {
        "title": title, "description": "d", "scoring": "sum",
        "time_limit_min": None, "is_active": True, "status": status,
        "category_ids": [], "tag_uuids": [],
        "questions": [
            {"question_text": "Q1", "question_order": 1, "question_type": "single_choice",
             "is_required": True, "config": {},
             "options": [{"option_text": "нет", "option_order": 0, "value_score": 0},
                         {"option_text": "да", "option_order": 1, "value_score": 3}]},
        ],
        "interpretations": [],
    }


def _hard_delete_test(test_uuid):
    with SessionLocal() as db:
        t = db.query(TestModel).filter(TestModel.uuid == _uuid.UUID(test_uuid)).first()
        if t:
            db.delete(t)
            db.commit()


def _set_status(test_uuid, new_status):
    with SessionLocal() as db:
        db.query(TestModel).filter(
            TestModel.uuid == _uuid.UUID(test_uuid)
        ).update({"status": new_status})
        db.commit()


# ── create: всегда draft ────────────────────────────────────────────────────

def test_psychologist_create_forces_draft_even_if_published_requested(client):
    headers, _ = _staff(client, "psychologist")
    r = client.post(
        "/api/psychologist/tests",
        json=_payload(f"PSYCH {_uuid.uuid4().hex[:6]}", status="published"),
        headers=headers,
    )
    assert r.status_code == 201, r.text
    test = r.json()
    try:
        assert test["status"] == "draft"
    finally:
        _hard_delete_test(test["uuid"])


# ── edit/delete: только draft/needs_changes ─────────────────────────────────

def test_psychologist_edits_own_draft(client):
    headers, _ = _staff(client, "psychologist")
    r = client.post(
        "/api/psychologist/tests",
        json=_payload(f"PSYCH {_uuid.uuid4().hex[:6]}"), headers=headers,
    )
    test = r.json()
    try:
        r = client.patch(
            f"/api/psychologist/tests/{test['uuid']}",
            json={"title": "Изменённое название"}, headers=headers,
        )
        assert r.status_code == 200, r.text
        assert r.json()["title"] == "Изменённое название"
    finally:
        _hard_delete_test(test["uuid"])


@pytest.mark.parametrize("blocked_status", ["in_review", "published"])
def test_psychologist_edit_blocked_when_not_editable(client, blocked_status):
    headers, _ = _staff(client, "psychologist")
    r = client.post(
        "/api/psychologist/tests",
        json=_payload(f"PSYCH {_uuid.uuid4().hex[:6]}"), headers=headers,
    )
    test = r.json()
    _set_status(test["uuid"], blocked_status)
    try:
        r = client.patch(
            f"/api/psychologist/tests/{test['uuid']}",
            json={"title": "X"}, headers=headers,
        )
        assert r.status_code == 409, r.text
    finally:
        _hard_delete_test(test["uuid"])


def test_psychologist_cannot_edit_others_test(client):
    owner_headers, _ = _staff(client, "psychologist")
    other_headers, _ = _staff(client, "psychologist")
    r = client.post(
        "/api/psychologist/tests",
        json=_payload(f"PSYCH {_uuid.uuid4().hex[:6]}"), headers=owner_headers,
    )
    test = r.json()
    try:
        r = client.patch(
            f"/api/psychologist/tests/{test['uuid']}",
            json={"title": "X"}, headers=other_headers,
        )
        assert r.status_code == 404, r.text
    finally:
        _hard_delete_test(test["uuid"])


def test_psychologist_deletes_own_draft(client):
    headers, _ = _staff(client, "psychologist")
    r = client.post(
        "/api/psychologist/tests",
        json=_payload(f"PSYCH {_uuid.uuid4().hex[:6]}"), headers=headers,
    )
    test = r.json()
    r = client.delete(f"/api/psychologist/tests/{test['uuid']}", headers=headers)
    assert r.status_code == 204, r.text
    r = client.get(f"/api/psychologist/tests/{test['uuid']}", headers=headers)
    assert r.status_code == 404, r.text


def test_psychologist_delete_blocked_when_published(client):
    headers, _ = _staff(client, "psychologist")
    r = client.post(
        "/api/psychologist/tests",
        json=_payload(f"PSYCH {_uuid.uuid4().hex[:6]}"), headers=headers,
    )
    test = r.json()
    _set_status(test["uuid"], "published")
    try:
        r = client.delete(f"/api/psychologist/tests/{test['uuid']}", headers=headers)
        assert r.status_code == 409, r.text
    finally:
        _hard_delete_test(test["uuid"])


def test_psychologist_cannot_delete_others_test(client):
    owner_headers, _ = _staff(client, "psychologist")
    other_headers, _ = _staff(client, "psychologist")
    r = client.post(
        "/api/psychologist/tests",
        json=_payload(f"PSYCH {_uuid.uuid4().hex[:6]}"), headers=owner_headers,
    )
    test = r.json()
    try:
        r = client.delete(f"/api/psychologist/tests/{test['uuid']}", headers=other_headers)
        assert r.status_code == 404, r.text
    finally:
        _hard_delete_test(test["uuid"])


# ── список: только свои, все статусы ────────────────────────────────────────

def test_list_shows_only_own_tests_all_statuses(client):
    mine_headers, _ = _staff(client, "psychologist")
    other_headers, _ = _staff(client, "psychologist")

    r1 = client.post(
        "/api/psychologist/tests",
        json=_payload(f"MINE {_uuid.uuid4().hex[:6]}"), headers=mine_headers,
    )
    mine = r1.json()
    _set_status(mine["uuid"], "in_review")

    r2 = client.post(
        "/api/psychologist/tests",
        json=_payload(f"OTHER {_uuid.uuid4().hex[:6]}"), headers=other_headers,
    )
    other = r2.json()
    try:
        r = client.get("/api/psychologist/tests?page=1&size=50", headers=mine_headers)
        assert r.status_code == 200, r.text
        uuids = {it["uuid"] for it in r.json()["items"]}
        assert mine["uuid"] in uuids
        assert other["uuid"] not in uuids
        # свой тест виден со своим текущим статусом
        mine_item = next(it for it in r.json()["items"] if it["uuid"] == mine["uuid"])
        assert mine_item["status"] == "in_review"
    finally:
        _hard_delete_test(mine["uuid"])
        _hard_delete_test(other["uuid"])


# ── media upload: расширено на psychologist ─────────────────────────────────

def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), (1, 2, 3)).save(buf, format="PNG")
    return buf.getvalue()


def test_psychologist_can_upload_image(client):
    headers, _ = _staff(client, "psychologist")
    r = client.post(
        "/api/media/upload",
        files={"file": ("q.png", _png_bytes(), "image/png")},
        headers=headers,
    )
    assert r.status_code == 201, r.text   # был бы 403 до Этапа F2


def test_psychologist_can_upload_av(client):
    headers, _ = _staff(client, "psychologist")
    r = client.post(
        "/api/media/upload/av",
        files={"file": ("clip.mp3", b"binary-bytes", "audio/mpeg")},
        headers=headers,
    )
    assert r.status_code == 201, r.text


# ── analyze/preview-score: stateless, доступны psychologist ────────────────

def test_psychologist_analyze_endpoint(client):
    headers, _ = _staff(client, "psychologist")
    body = {
        "scoring": "sum",
        "questions": [
            {"question_text": "Q1", "question_order": 1, "question_type": "single_choice",
             "is_required": True, "config": {},
             "options": [{"option_text": "нет", "option_order": 0, "value_score": 0},
                         {"option_text": "да", "option_order": 1, "value_score": 3}]},
        ],
        "interpretations": [],
    }
    r = client.post("/api/psychologist/tests/analyze", json=body, headers=headers)
    assert r.status_code == 200, r.text


def test_psychologist_preview_score_endpoint(client):
    headers, _ = _staff(client, "psychologist")
    body = {
        "scoring": "sum",
        "questions": [
            {"question_text": "Q1", "question_order": 0, "question_type": "single_choice",
             "is_required": True, "config": {},
             "options": [{"option_text": "нет", "option_order": 0, "value_score": 0},
                         {"option_text": "да", "option_order": 1, "value_score": 3}]},
        ],
        "interpretations": [],
        "answers": [{"question_order": 0, "option_order": 1}],
    }
    r = client.post("/api/psychologist/tests/preview-score", json=body, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["total_score"] == 3
