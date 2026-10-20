"""
Integration: авторство psychologist в психодиагностике (Этап F2, ADR-016).

Покрывает:
  - psychologist создаёт тест ВСЕГДА как draft (даже если прислал status=published);
  - редактирует свой draft/needs_changes/published — 200 (Этап F2.1: published
    после правки снимается с публикации — status → draft, пишет
    test_unpublished_for_edit ПОВЕРХ test_updated); удаляет — только draft/
    needs_changes;
  - редактирует/удаляет свой in_review → 409 (TestNotEditable); удаляет
    published → 409;
  - published с результатами: правка вопросов → 409 (has_results, тест
    остаётся published), правка метаданных без вопросов → 200 (снимается);
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
from app.db.models import AuditLog, Test as TestModel, TestResult as TestResultModel
from tests.integration.conftest import create_test_user

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
        if not t:
            return
        # student_answers.option_id — ON DELETE RESTRICT, поэтому если у теста
        # уже есть результат (F2.1-тесты сабмитят его), сначала удаляем
        # TestResult (каскадно тянет student_answers), иначе ORM-каскад на
        # options упрётся в FK-нарушение.
        db.query(TestResultModel).filter(
            TestResultModel.test_id == t.id
        ).delete(synchronize_session=False)
        db.delete(t)
        db.commit()


def _set_status(test_uuid, new_status):
    with SessionLocal() as db:
        db.query(TestModel).filter(
            TestModel.uuid == _uuid.UUID(test_uuid)
        ).update({"status": new_status})
        db.commit()


def _internal_id(test_uuid: str) -> int:
    with SessionLocal() as db:
        return db.query(TestModel).filter(TestModel.uuid == _uuid.UUID(test_uuid)).first().id


def _audit_rows(event_type: str, entity_id: int):
    with SessionLocal() as db:
        return (
            db.query(AuditLog)
            .filter(AuditLog.event_type == event_type, AuditLog.entity_id == entity_id)
            .all()
        )


def _submit_result(client, email, test):
    """Студент проходит опубликованный тест психолога → у теста появляется результат."""
    create_test_user(email, PASSWORD)
    r = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    headers = {"Authorization": f"Bearer {r.json()['session_token']}"}
    client.post("/api/tests/consent/accept", headers=headers)
    q = test["questions"][0]
    r = client.post(
        f"/api/tests/{test['uuid']}/submit",
        json={"answers": [{"question_id": q["id"], "option_id": q["options"][1]["id"]}]},
        headers=headers,
    )
    assert r.status_code == 201, r.text


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


@pytest.mark.parametrize("blocked_status", ["in_review"])
def test_psychologist_edit_blocked_when_not_editable(client, blocked_status):
    # published больше НЕ в этом списке (Этап F2.1) — автор может дорабатывать
    # свой опубликованный тест, см. test_psychologist_edit_published_unpublishes_it.
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


# ── Этап F2.1: правка published снимает его с публикации ──────────────────────

def test_psychologist_edit_published_unpublishes_it(client):
    headers, _ = _staff(client, "psychologist")
    r = client.post(
        "/api/psychologist/tests",
        json=_payload(f"PSYCH {_uuid.uuid4().hex[:6]}"), headers=headers,
    )
    test = r.json()
    _set_status(test["uuid"], "published")
    try:
        r = client.patch(
            f"/api/psychologist/tests/{test['uuid']}",
            json={"title": "Доработано после публикации"}, headers=headers,
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "draft"
        assert r.json()["title"] == "Доработано после публикации"

        entity_id = _internal_id(test["uuid"])
        assert len(_audit_rows("test_updated", entity_id)) == 1
        assert len(_audit_rows("test_unpublished_for_edit", entity_id)) == 1
    finally:
        _hard_delete_test(test["uuid"])


def test_psychologist_edit_draft_does_not_write_unpublish_event(client):
    headers, _ = _staff(client, "psychologist")
    r = client.post(
        "/api/psychologist/tests",
        json=_payload(f"PSYCH {_uuid.uuid4().hex[:6]}"), headers=headers,
    )
    test = r.json()
    try:
        r = client.patch(
            f"/api/psychologist/tests/{test['uuid']}",
            json={"title": "X"}, headers=headers,
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "draft"

        entity_id = _internal_id(test["uuid"])
        assert len(_audit_rows("test_unpublished_for_edit", entity_id)) == 0
    finally:
        _hard_delete_test(test["uuid"])


def test_psychologist_edit_published_with_results_blocks_questions_but_allows_metadata(
    client, test_email,
):
    headers, _ = _staff(client, "psychologist")
    r = client.post(
        "/api/psychologist/tests",
        json=_payload(f"PSYCH {_uuid.uuid4().hex[:6]}"), headers=headers,
    )
    test = r.json()
    _set_status(test["uuid"], "published")
    try:
        _submit_result(client, test_email, test)

        # правка вопросов теста, по которому уже есть результат — 409, тест
        # остаётся published (unpublish не применился к неуспешной правке)
        bad_payload = _payload("x")
        bad_payload["questions"][0]["question_text"] = "Изменённый вопрос"
        r = client.patch(
            f"/api/psychologist/tests/{test['uuid']}",
            json={"questions": bad_payload["questions"]}, headers=headers,
        )
        assert r.status_code == 409, r.text

        r = client.get(f"/api/psychologist/tests/{test['uuid']}", headers=headers)
        assert r.json()["status"] == "published"

        # правка метаданных (без вопросов) — ok, снимается с публикации
        r = client.patch(
            f"/api/psychologist/tests/{test['uuid']}",
            json={"description": "Обновлённое описание"}, headers=headers,
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "draft"
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


# ── Этап F2.2: дублирование своего теста (любой статус источника) ─────────────

def test_psychologist_duplicates_own_draft(client):
    headers, _ = _staff(client, "psychologist")
    r = client.post(
        "/api/psychologist/tests",
        json=_payload(f"PSYCH {_uuid.uuid4().hex[:6]}"), headers=headers,
    )
    src = r.json()
    copy = None
    try:
        r = client.post(f"/api/psychologist/tests/{src['uuid']}/duplicate", headers=headers)
        assert r.status_code == 201, r.text
        copy = r.json()
        assert copy["uuid"] != src["uuid"]
        assert copy["status"] == "draft"
        assert copy["title"].startswith(src["title"])
        assert copy["questions"][0]["question_text"] == src["questions"][0]["question_text"]
    finally:
        _hard_delete_test(src["uuid"])
        if copy:
            _hard_delete_test(copy["uuid"])


@pytest.mark.parametrize("src_status", ["in_review", "published"])
def test_psychologist_duplicates_without_touching_original_status(client, src_status):
    """Ключевое отличие от update_my_test('published'): дублирование НЕ снимает
    оригинал с публикации/проверки — это read-only копирование, не мутация."""
    headers, _ = _staff(client, "psychologist")
    r = client.post(
        "/api/psychologist/tests",
        json=_payload(f"PSYCH {_uuid.uuid4().hex[:6]}"), headers=headers,
    )
    src = r.json()
    _set_status(src["uuid"], src_status)
    copy = None
    try:
        r = client.post(f"/api/psychologist/tests/{src['uuid']}/duplicate", headers=headers)
        assert r.status_code == 201, r.text
        copy = r.json()
        assert copy["status"] == "draft"

        # оригинал остался в исходном статусе
        with SessionLocal() as db:
            still = db.query(TestModel).filter(
                TestModel.uuid == _uuid.UUID(src["uuid"])
            ).first()
            assert still.status == src_status
    finally:
        _hard_delete_test(src["uuid"])
        if copy:
            _hard_delete_test(copy["uuid"])


def test_psychologist_cannot_duplicate_others_test(client):
    owner_headers, _ = _staff(client, "psychologist")
    other_headers, _ = _staff(client, "psychologist")
    r = client.post(
        "/api/psychologist/tests",
        json=_payload(f"PSYCH {_uuid.uuid4().hex[:6]}"), headers=owner_headers,
    )
    test = r.json()
    try:
        r = client.post(f"/api/psychologist/tests/{test['uuid']}/duplicate", headers=other_headers)
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
