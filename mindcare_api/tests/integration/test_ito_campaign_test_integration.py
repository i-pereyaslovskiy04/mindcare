"""
Integration: тест ИТО как методика кампаний (ADR-036, этап 2).

Покрывает:
  - seed (ensure_ito_test): 91 вопрос, 10 шкал, пороги; повтор идемпотентен;
    расхождение структуры с ключом → ItoTestMismatch без изменений;
  - тест campaign_only НЕ виден студенту: нет в каталоге GET /api/tests,
    GET /api/tests/{uuid} и POST …/submit → 404 (хотя status=published);
  - после ответов кампании вопросы и правила не меняются, удаление методики
    с кампаниями — 409 (ADR-037; сплошного запрета правки больше нет);
  - has_results учитывает ответы кампаний (вопросы теста с ответами кампании
    не заменяются);
  - обычный опубликованный тест по-прежнему виден (регресс фильтра).
"""
import hashlib
import secrets
import uuid as _uuid

import bcrypt
import pytest

from app.auth import storage as auth_storage
from app.core.encryption import encrypt_text
from app.db.models import (
    CampaignResponse, CampaignResponseAnswer, Consent, ConsentRecord, Option,
    Question, Test as TestModel, TestCampaign, TestInterpretation,
)
from app.db.session import SessionLocal
from app.tests import storage as tests_storage
from app.tests.profiles import ito_sobchik
from app.tests.profiles.ito_seed import ItoTestMismatch, ensure_ito_test
from tests.integration.conftest import create_test_user

PASSWORD = "SecurePass42!"


# ─── helpers ──────────────────────────────────────────────────────────────────

def _staff_headers(client, role: str):
    user = auth_storage.save_user({
        "name": f"ITO {role} {_uuid.uuid4().hex[:6]}",
        "email": f"integ_ito_{role}_{_uuid.uuid4().hex[:10]}@example.com",
        "hashed_password": bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode(),
        "role": role,
    })
    r = client.post("/api/auth/login", json={"email": user["email"], "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['session_token']}"}, int(user["id"])


def _student_headers(client):
    email = f"integ_ito_student_{_uuid.uuid4().hex[:10]}@example.com"
    create_test_user(email, PASSWORD)
    r = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    headers = {"Authorization": f"Bearer {r.json()['session_token']}"}
    assert client.post("/api/tests/consent/accept", headers=headers).status_code == 200
    return headers


def _delete_test(test_id: int) -> None:
    with SessionLocal() as db:
        campaigns = [c.id for c in db.query(TestCampaign.id)
                     .filter(TestCampaign.test_id == test_id).all()]
        consent_ids = [r.consent_record_id for r in db.query(CampaignResponse)
                       .filter(CampaignResponse.campaign_id.in_(campaigns)).all()]
        if campaigns:
            db.query(TestCampaign).filter(TestCampaign.id.in_(campaigns)) \
                .delete(synchronize_session=False)
        if consent_ids:
            db.query(ConsentRecord).filter(ConsentRecord.id.in_(consent_ids)) \
                .delete(synchronize_session=False)
        db.query(TestModel).filter(TestModel.id == test_id) \
            .delete(synchronize_session=False)
        db.commit()


@pytest.fixture()
def ito_test(client):
    """Тест ИТО через seed-функцию; удаляется после теста, если создан здесь."""
    with SessionLocal() as db:
        test, created = ensure_ito_test(db)
        db.commit()
        info = {"id": test.id, "uuid": str(test.uuid)}
    yield info
    if created:
        _delete_test(info["id"])


def _add_campaign_answer(test_id: int) -> None:
    with SessionLocal() as db:
        raw = secrets.token_urlsafe(32)
        campaign = TestCampaign(
            test_id=test_id, title="integ_ito_campaign",
            link_token_hash=hashlib.sha256(raw.encode()).hexdigest(),
            link_token_enc=encrypt_text(raw),
        )
        db.add(campaign)
        db.flush()
        consent = db.query(Consent).filter(Consent.policy_type == "test_consent").first()
        rec = ConsentRecord(user_id=None, consent_id=consent.id, accepted=True)
        db.add(rec)
        db.flush()
        resp = CampaignResponse(
            campaign_id=campaign.id, submission_key=_uuid.uuid4(), test_version=1,
            full_name_enc=encrypt_text("integ ФИО"), faculty_code="law",
            specialty="Юриспруденция", age=19, gender="male",
            consent_record_id=rec.id,
        )
        db.add(resp)
        db.flush()
        q = db.query(Question).filter(Question.test_id == test_id) \
            .order_by(Question.question_order).first()
        opt = db.query(Option).filter(Option.question_id == q.id).first()
        db.add(CampaignResponseAnswer(response_id=resp.id, question_id=q.id,
                                      option_id=opt.id))
        db.commit()


# ─── seed ─────────────────────────────────────────────────────────────────────

def test_seed_creates_full_structure(ito_test):
    with SessionLocal() as db:
        test = db.get(TestModel, ito_test["id"])
        assert test.campaign_only is True
        assert test.scoring_profile == "ito_sobchik"
        qs = db.query(Question).filter(Question.test_id == test.id) \
            .order_by(Question.question_order).all()
        assert len(qs) == 91
        assert qs[48].question_order == 49 and qs[48].config == {"scale": "II"}
        assert qs[39].config == {"scale": "VIII"}
        assert qs[0].config == {} and qs[90].config == {}
        scales = {r.scale_name for r in db.query(TestInterpretation)
                  .filter(TestInterpretation.test_id == test.id).all()}
        assert scales == set(ito_sobchik.KEY)


def test_seed_is_idempotent(ito_test):
    with SessionLocal() as db:
        again, created = ensure_ito_test(db)
        db.rollback()
        assert created is False and again.id == ito_test["id"]
        assert db.query(TestModel).filter(
            TestModel.scoring_profile == "ito_sobchik",
            TestModel.deleted_at.is_(None),
        ).count() == 1


def test_seed_detects_structure_mismatch(ito_test):
    with SessionLocal() as db:
        q = db.query(Question).filter(Question.test_id == ito_test["id"],
                                      Question.question_order == 49).one()
        q.config = {"scale": "VIII"}
        db.commit()
    try:
        with SessionLocal() as db:
            with pytest.raises(ItoTestMismatch):
                ensure_ito_test(db)
            db.rollback()
    finally:
        with SessionLocal() as db:
            q = db.query(Question).filter(Question.test_id == ito_test["id"],
                                          Question.question_order == 49).one()
            q.config = {"scale": "II"}
            db.commit()


# ─── скрыт от студента ────────────────────────────────────────────────────────

def test_hidden_from_student_catalog_and_take(client, ito_test):
    headers = _student_headers(client)

    r = client.get("/api/tests", params={"size": 100}, headers=headers)
    assert r.status_code == 200
    assert ito_test["uuid"] not in {t["uuid"] for t in r.json()["items"]}

    assert client.get(f"/api/tests/{ito_test['uuid']}", headers=headers) \
        .status_code == 404
    r = client.post(f"/api/tests/{ito_test['uuid']}/submit", headers=headers,
                    json={"answers": []})
    assert r.status_code == 404


def test_regular_published_test_still_visible(client):
    admin_headers, admin_id = _staff_headers(client, "admin")
    data = {
        "title": f"integ ITO regress {_uuid.uuid4().hex[:6]}", "description": "d",
        "scoring": "sum", "time_limit_min": None, "is_active": True,
        "status": "published", "category_ids": [], "tag_uuids": [],
        "questions": [{
            "question_text": "Q1", "question_order": 1,
            "question_type": "single_choice", "is_required": True, "config": {},
            "options": [{"option_text": "нет", "option_order": 0, "value_score": 0},
                        {"option_text": "да", "option_order": 1, "value_score": 1}],
        }],
        "interpretations": [],
    }
    test = tests_storage.create_test(data, created_by=admin_id, actor_role="admin")
    try:
        headers = _student_headers(client)
        assert client.get(f"/api/tests/{test['uuid']}", headers=headers) \
            .status_code == 200
    finally:
        with SessionLocal() as db:
            db.query(TestModel).filter(TestModel.uuid == _uuid.UUID(test["uuid"])) \
                .delete(synchronize_session=False)
            db.commit()


# ─── конструктор ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("role", ["admin", "supervisor"])
def test_constructor_guards_after_campaign_answers(client, ito_test, role):
    """ADR-037: сплошного запрета правки нет — после ответов кампании нельзя
    менять вопросы и правила обработки, а удалить методику с кампаниями нельзя."""
    headers, _ = _staff_headers(client, role)
    _add_campaign_answer(ito_test["id"])
    url = f"/api/admin/tests/{ito_test['uuid']}"
    current = client.get(url, headers=headers).json()
    assert current["scoring_rules"]["types"]["threshold"] == 8

    changed = {**current["scoring_rules"], "instruction": "Другая инструкция"}
    assert client.patch(url, headers=headers,
                        json={"scoring_rules": changed}).status_code == 409
    questions = [{k: q[k] for k in ("question_text", "question_order", "question_type",
                                    "is_required", "config")}
                 | {"options": [{k: o[k] for k in ("option_text", "option_order",
                                                    "value_score")} for o in q["options"]]}
                 for q in current["questions"]]
    assert client.patch(url, headers=headers,
                        json={"questions": questions}).status_code == 409
    r = client.delete(url, headers=headers)
    assert r.status_code == 409, r.text
    assert "тестировании по ссылке" in r.json()["detail"]

    with SessionLocal() as db:
        test = db.get(TestModel, ito_test["id"])
        assert test.deleted_at is None
        assert test.scoring_rules["instruction"] != "Другая инструкция"


# ─── has_results ──────────────────────────────────────────────────────────────

def test_has_results_counts_campaign_answers(ito_test):
    assert tests_storage.test_has_results(ito_test["uuid"]) is False
    _add_campaign_answer(ito_test["id"])
    assert tests_storage.test_has_results(ito_test["uuid"]) is True
