"""
ADR-016 (дополнение 2026-10-29) — общие помощники integration-тестов
staff-доступа к результатам и ответам (не тест-модуль).

Тест «все типы ответов» строится прямо через storage.create_test (integ_-
заголовок): single_choice с медиа вопроса и варианта, multiple_choice, scale,
free_text и необязательный вопрос, который клиент пропускает. Медиа — прямой
insert media_files (integ_-имя); фикстура `full_test` удаляет результаты, тест
и медиа после теста.
"""
import uuid
from datetime import datetime, timezone

import pytest

from app.db.models import AuditLog, MediaFile, TestResult
from app.db.models import Test as TestModel
from app.db.session import SessionLocal
from app.tests import storage as tests_storage

SECRET_TEXT = "Секретный-ответ-про-сон-91c2"
NO_STORE = "no-store, private"
Q_MEDIA_URL = "/media/integ_question_image.png"
OPT_MEDIA_URL = "/media/integ_option_image.png"
OTHER_OPT_MEDIA_URL = "/media/integ_other_option.png"


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def _media(file_path, uploader_id):
    with SessionLocal() as db:
        mf = MediaFile(
            file_name=f"integ_{uuid.uuid4().hex[:8]}.png", file_path=file_path,
            file_type="image", mime_type="image/png", uploaded_by=uploader_id,
            is_active=True,
        )
        db.add(mf)
        db.commit()
        return mf.id, str(mf.uuid)


def make_full_test(author_id):
    """Тест из пяти вопросов всех типов; возвращает dict storage.create_test + media ids."""
    q_media_id, q_media = _media(Q_MEDIA_URL, author_id)
    o_media_id, o_media = _media(OPT_MEDIA_URL, author_id)
    other_id, other_media = _media(OTHER_OPT_MEDIA_URL, author_id)
    data = {
        "title": f"integ_STAFFRES {uuid.uuid4().hex[:6]}", "description": "d",
        "scoring": "sum", "max_score": 10, "time_limit_min": None, "is_active": True,
        "category_ids": [], "tag_uuids": [],
        "questions": [
            {"question_text": "Как вы спите?", "question_order": 1,
             "question_type": "single_choice", "is_required": True, "config": {},
             "media": [{"media_uuid": q_media, "caption": "Подпись картинки"}],
             "options": [
                 {"option_text": "Плохо", "option_order": 0, "value_score": 0,
                  "media": [{"media_uuid": other_media}]},
                 {"option_text": "Хорошо", "option_order": 1, "value_score": 3,
                  "media": [{"media_uuid": o_media}]},
             ]},
            {"question_text": "Что беспокоит?", "question_order": 2,
             "question_type": "multiple_choice", "is_required": True, "config": {},
             "options": [
                 {"option_text": "Учёба", "option_order": 0, "value_score": 1},
                 {"option_text": "Семья", "option_order": 1, "value_score": 1},
                 {"option_text": "Друзья", "option_order": 2, "value_score": 1},
             ]},
            {"question_text": "Оцените тревогу", "question_order": 3,
             "question_type": "scale", "is_required": True,
             "config": {"min": 1, "max": 5, "weight": 2}, "options": []},
            {"question_text": "Опишите неделю", "question_order": 4,
             "question_type": "free_text", "is_required": True, "config": {},
             "options": []},
            {"question_text": "Необязательный вопрос", "question_order": 5,
             "question_type": "single_choice", "is_required": False, "config": {},
             "options": [
                 {"option_text": "Да", "option_order": 0, "value_score": 1},
                 {"option_text": "Нет", "option_order": 1, "value_score": 0},
             ]},
        ],
        "interpretations": [
            {"scale_name": None, "min_score": 0, "max_score": 100,
             "label": "Исходная метка", "recommendation": "Исходная рекомендация"},
        ],
    }
    test = tests_storage.create_test(data, created_by=author_id, actor_role="admin")
    test["_media_ids"] = [q_media_id, o_media_id, other_id]
    return test


def full_answers(test, free_text=SECRET_TEXT):
    q = test["questions"]
    return [
        {"question_id": q[0]["id"], "option_id": q[0]["options"][1]["id"]},
        {"question_id": q[1]["id"],
         "selected_options": [q[1]["options"][2]["id"], q[1]["options"][0]["id"]]},
        {"question_id": q[2]["id"], "scale_value": 4},
        {"question_id": q[3]["id"], "free_text_answer": free_text},
    ]


def submit(client, client_token, test, answers=None) -> str:
    client.post("/api/tests/consent/accept", headers=auth(client_token))
    r = client.post(
        f"/api/tests/{test['uuid']}/submit",
        json={"answers": answers if answers is not None else full_answers(test)},
        headers=auth(client_token),
    )
    assert r.status_code == 201, r.text
    return r.json()["uuid"]


def cleanup_test(test):
    with SessionLocal() as db:
        t = db.query(TestModel).filter(TestModel.uuid == uuid.UUID(test["uuid"])).first()
        if t is not None:
            db.query(TestResult).filter(TestResult.test_id == t.id).delete(
                synchronize_session=False)
            db.delete(t)
            db.commit()
        db.query(MediaFile).filter(MediaFile.id.in_(test.get("_media_ids") or [])).delete(
            synchronize_session=False)
        db.commit()


def result_id(result_uuid):
    with SessionLocal() as db:
        return db.query(TestResult.id).filter(
            TestResult.uuid == uuid.UUID(str(result_uuid))).scalar()


def content_reads(result_uuid):
    rid = result_id(result_uuid)
    with SessionLocal() as db:
        rows = db.query(AuditLog).filter(
            AuditLog.event_type == "test_result_content_read",
            AuditLog.entity_type == "test_result", AuditLog.entity_id == rid,
        ).order_by(AuditLog.id).all()
        for r in rows:
            db.expunge(r)
        return rows


def now():
    return datetime.now(timezone.utc)


@pytest.fixture
def full_test():
    created = []

    def make(author_id):
        test = make_full_test(author_id)
        created.append(test)
        return test

    yield make
    for test in created:
        cleanup_test(test)
