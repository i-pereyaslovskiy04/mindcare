"""
SQLAlchemy-слой модуля психодиагностики (Этап A — admin CRUD).

Тест хранится как дерево: tests → questions → options, плюс test_interpretations,
test_categories (M:N), test_tags (M:N). Запись/обновление дерева — в одной
транзакции (one SessionLocal + один commit).
"""

import uuid as _uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import desc, func

from app.core.encryption import encrypt_text
from app.db.session import SessionLocal
from app.db.models import (
    Test, TestCategory, TestTag, TestInterpretation,
    Question, Option, TestResult, TestResultScale, StudentAnswer,
    Category, Tag, User, Consent, ConsentRecord,
)
from app.audit import Actor, Outcome, Target, record_event
from app.audit.request_context import build_request_context


class TestHasResults(Exception):
    """
    Попытка заменить вопросы теста, по которому уже есть пройденные результаты.

    Определена здесь (а не в service), чтобы storage мог её поднять без
    циклического импорта; service её ре-экспортирует, routes → HTTP 409.
    """


# ── helpers: чтение ───────────────────────────────────────────────────────────

def _categories_of(test_id: int, db) -> list[dict]:
    rows = (
        db.query(Category)
        .join(TestCategory, TestCategory.category_id == Category.id)
        .filter(TestCategory.test_id == test_id)
        .all()
    )
    return [{"id": c.id, "name": c.name} for c in rows]


def _tags_of(test_id: int, db) -> list[dict]:
    rows = (
        db.query(Tag)
        .join(TestTag, TestTag.tag_id == Tag.id)
        .filter(TestTag.test_id == test_id)
        .all()
    )
    return [{"uuid": str(t.uuid), "name": t.name} for t in rows]


def _author_name(created_by: Optional[int], db) -> Optional[str]:
    if not created_by:
        return None
    user = db.query(User).filter(User.id == created_by).first()
    return user.full_name if user else None


def _question_to_dict(q: Question) -> dict:
    options = sorted(q.options, key=lambda o: o.option_order)
    return {
        "id":             q.id,
        "question_text":  q.question_text,
        "question_order": q.question_order,
        "question_type":  q.question_type,
        "is_required":    q.is_required,
        "config":         q.config or {},
        "options": [
            {
                "id":           o.id,
                "option_text":  o.option_text,
                "option_order": o.option_order,
                "value_score":  o.value_score,
            }
            for o in options
        ],
    }


def _interpretation_to_dict(i: TestInterpretation) -> dict:
    return {
        "id":             i.id,
        "scale_name":     i.scale_name,
        "min_score":      i.min_score,
        "max_score":      i.max_score,
        "label":          i.label,
        "recommendation": i.recommendation,
    }


def _test_to_dict(test: Test, db) -> dict:
    questions = sorted(test.questions, key=lambda q: q.question_order)
    interpretations = sorted(
        test.interpretations,
        key=lambda i: (i.scale_name or "", i.min_score),
    )
    return {
        "uuid":            str(test.uuid),
        "title":           test.title,
        "description":     test.description,
        "version":         test.version,
        "scoring":         test.scoring,
        "max_score":       test.max_score,
        "time_limit_min":  test.time_limit_min,
        "is_active":       test.is_active,
        "created_at":      test.created_at,
        "updated_at":      test.updated_at,
        "created_by_name": _author_name(test.created_by, db),
        "categories":      _categories_of(test.id, db),
        "tags":            _tags_of(test.id, db),
        "questions":       [_question_to_dict(q) for q in questions],
        "interpretations": [_interpretation_to_dict(i) for i in interpretations],
    }


# ── helpers: запись вложенных коллекций ───────────────────────────────────────

def _sync_categories(test_id: int, category_ids: list[int], db) -> None:
    db.query(TestCategory).filter(TestCategory.test_id == test_id).delete()
    for cat_id in category_ids:
        cat = db.query(Category).filter(
            Category.id == cat_id, Category.is_active.is_(True)
        ).first()
        if cat:
            db.add(TestCategory(test_id=test_id, category_id=cat.id))


def _sync_tags(test_id: int, tag_uuids: list[str], db) -> None:
    db.query(TestTag).filter(TestTag.test_id == test_id).delete()
    for uuid_str in tag_uuids:
        try:
            uuid_obj = _uuid.UUID(uuid_str)
        except ValueError:
            continue
        tag = db.query(Tag).filter(Tag.uuid == uuid_obj).first()
        if tag:
            db.add(TestTag(test_id=test_id, tag_id=tag.id))


def _replace_questions(test_id: int, questions: list[dict], db) -> None:
    """Полная замена вопросов/вариантов теста (cascade удаляет старые)."""
    db.query(Question).filter(Question.test_id == test_id).delete()
    db.flush()
    for q in questions:
        question = Question(
            test_id=test_id,
            question_text=q["question_text"],
            question_order=q["question_order"],
            question_type=q["question_type"],
            is_required=q["is_required"],
            config=q.get("config") or {},
        )
        db.add(question)
        db.flush()
        for o in q.get("options", []):
            db.add(Option(
                question_id=question.id,
                option_text=o["option_text"],
                option_order=o["option_order"],
                value_score=o["value_score"],
            ))


def _replace_interpretations(test_id: int, interpretations: list[dict], db) -> None:
    db.query(TestInterpretation).filter(
        TestInterpretation.test_id == test_id
    ).delete()
    for i in interpretations:
        db.add(TestInterpretation(
            test_id=test_id,
            scale_name=i.get("scale_name"),
            min_score=i["min_score"],
            max_score=i["max_score"],
            label=i["label"],
            recommendation=i.get("recommendation"),
        ))


# ── public API ────────────────────────────────────────────────────────────────

def find_tests(
    page: int = 1,
    size: int = 20,
    search: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> tuple[list[dict], int]:
    with SessionLocal() as db:
        q = db.query(Test).filter(Test.deleted_at.is_(None))
        if is_active is not None:
            q = q.filter(Test.is_active.is_(is_active))
        if search:
            q = q.filter(Test.title.ilike(f"%{search.strip()}%"))

        total = q.count()
        tests = (
            q.order_by(desc(Test.created_at))
            .offset((page - 1) * size)
            .limit(size)
            .all()
        )
        items = []
        for t in tests:
            qcount = (
                db.query(func.count(Question.id))
                .filter(Question.test_id == t.id)
                .scalar()
            )
            items.append({
                "uuid":            str(t.uuid),
                "title":           t.title,
                "scoring":         t.scoring,
                "version":         t.version,
                "is_active":       t.is_active,
                "question_count":  qcount or 0,
                "categories":      _categories_of(t.id, db),
                "tags":            _tags_of(t.id, db),
                "created_at":      t.created_at,
                "created_by_name": _author_name(t.created_by, db),
            })
    return items, total


def get_test_by_uuid(uuid_str: str) -> Optional[dict]:
    try:
        uuid_obj = _uuid.UUID(uuid_str)
    except ValueError:
        return None
    with SessionLocal() as db:
        test = db.query(Test).filter(
            Test.uuid == uuid_obj, Test.deleted_at.is_(None)
        ).first()
        if not test:
            return None
        return _test_to_dict(test, db)


def create_test(
    data: dict,
    created_by: int,
    *,
    actor_role: Optional[str] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    # created_by — единственный actor id (не вводим второй actor_id).
    if created_by is None or actor_role is None:
        raise RuntimeError(
            "test create requires authenticated actor context "
            "(created_by and actor_role)"
        )
    safe_ctx = build_request_context(ip=ip, user_agent=user_agent)

    with SessionLocal() as db:
        test = Test(
            title=data["title"],
            description=data.get("description"),
            scoring=data.get("scoring", "sum"),
            max_score=data.get("max_score"),
            time_limit_min=data.get("time_limit_min"),
            is_active=data.get("is_active", True),
            version=1,
            created_by=created_by,
        )
        db.add(test)
        db.flush()
        _sync_categories(test.id, data.get("category_ids", []), db)
        _sync_tags(test.id, data.get("tag_uuids", []), db)
        _replace_questions(test.id, data.get("questions", []), db)
        _replace_interpretations(test.id, data.get("interpretations", []), db)
        record_event(
            event="test_created",
            actor=Actor.user(created_by, actor_role),
            target=Target("test", test.id),
            outcome=Outcome.SUCCESS,
            metadata={},
            context=safe_ctx,
            db=db,
        )
        db.commit()
        db.refresh(test)
        return _test_to_dict(test, db)


def has_results(test_id: int, db) -> bool:
    return db.query(
        db.query(TestResult.id).filter(TestResult.test_id == test_id).exists()
    ).scalar()


def test_has_results(uuid_str: str) -> bool:
    """Есть ли хоть один результат по тесту. Несуществующий тест → False."""
    try:
        uuid_obj = _uuid.UUID(uuid_str)
    except ValueError:
        return False
    with SessionLocal() as db:
        test = db.query(Test.id).filter(
            Test.uuid == uuid_obj, Test.deleted_at.is_(None)
        ).first()
        if not test:
            return False
        return has_results(test.id, db)


def duplicate_test(
    uuid_str: str,
    created_by: int,
    *,
    actor_role: Optional[str] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> Optional[dict]:
    """
    Копия методики: вопросы/варианты/пороги/категории/темы переносятся,
    результаты — нет. Копия создаётся как черновик (is_active=False, version=1),
    чтобы её можно было доработать до публикации.
    """
    # created_by — единственный actor id (не вводим второй actor_id).
    if created_by is None or actor_role is None:
        raise RuntimeError(
            "test duplicate requires authenticated actor context "
            "(created_by and actor_role)"
        )
    safe_ctx = build_request_context(ip=ip, user_agent=user_agent)

    try:
        uuid_obj = _uuid.UUID(uuid_str)
    except ValueError:
        return None

    with SessionLocal() as db:
        src = db.query(Test).filter(
            Test.uuid == uuid_obj, Test.deleted_at.is_(None)
        ).first()
        if not src:
            return None

        copy = Test(
            title=f"{src.title} (копия)"[:255],
            description=src.description,
            scoring=src.scoring,
            max_score=src.max_score,
            time_limit_min=src.time_limit_min,
            is_active=False,
            version=1,
            created_by=created_by,
        )
        db.add(copy)
        db.flush()

        for row in db.query(TestCategory).filter(TestCategory.test_id == src.id).all():
            db.add(TestCategory(test_id=copy.id, category_id=row.category_id))
        for row in db.query(TestTag).filter(TestTag.test_id == src.id).all():
            db.add(TestTag(test_id=copy.id, tag_id=row.tag_id))

        for q in sorted(src.questions, key=lambda x: x.question_order):
            question = Question(
                test_id=copy.id,
                question_text=q.question_text,
                question_order=q.question_order,
                question_type=q.question_type,
                is_required=q.is_required,
                config=dict(q.config or {}),
            )
            db.add(question)
            db.flush()
            for o in sorted(q.options, key=lambda x: x.option_order):
                db.add(Option(
                    question_id=question.id,
                    option_text=o.option_text,
                    option_order=o.option_order,
                    value_score=o.value_score,
                ))

        for i in src.interpretations:
            db.add(TestInterpretation(
                test_id=copy.id,
                scale_name=i.scale_name,
                min_score=i.min_score,
                max_score=i.max_score,
                label=i.label,
                recommendation=i.recommendation,
            ))

        # target — НОВАЯ копия (copy.id после flush), не source.
        record_event(
            event="test_duplicated",
            actor=Actor.user(created_by, actor_role),
            target=Target("test", copy.id),
            outcome=Outcome.SUCCESS,
            metadata={},
            context=safe_ctx,
            db=db,
        )
        db.commit()
        db.refresh(copy)
        return _test_to_dict(copy, db)


def update_test(
    uuid_str: str,
    data: dict,
    *,
    actor_id: Optional[int] = None,
    actor_role: Optional[str] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> Optional[dict]:
    """
    Частичное обновление. Скалярные поля — по наличию ключа.
    Вложенные коллекции (questions/interpretations/category_ids/tag_uuids)
    заменяются целиком только если ключ присутствует в data.

    Вопросы теста, по которому уже есть результаты, менять НЕЛЬЗЯ:
    student_answers ссылается на questions/options через ON DELETE RESTRICT,
    поэтому замена дерева физически невозможна — нужна копия методики
    (`duplicate_test`). Метаданные и пороги интерпретации менять можно:
    на них FK из результатов нет, а расшифровка снапшотится в момент submit.
    """
    if actor_id is None or actor_role is None:
        raise RuntimeError(
            "test update requires authenticated actor context "
            "(actor_id and actor_role)"
        )
    safe_ctx = build_request_context(ip=ip, user_agent=user_agent)

    try:
        uuid_obj = _uuid.UUID(uuid_str)
    except ValueError:
        return None

    with SessionLocal() as db:
        test = db.query(Test).filter(
            Test.uuid == uuid_obj, Test.deleted_at.is_(None)
        ).first()
        if not test:
            return None

        for field in ("title", "description", "scoring", "max_score",
                      "time_limit_min", "is_active"):
            if field in data and data[field] is not None:
                setattr(test, field, data[field])

        if "category_ids" in data and data["category_ids"] is not None:
            _sync_categories(test.id, data["category_ids"], db)
        if "tag_uuids" in data and data["tag_uuids"] is not None:
            _sync_tags(test.id, data["tag_uuids"], db)

        if "questions" in data and data["questions"] is not None:
            if has_results(test.id, db):
                raise TestHasResults(
                    "По этому тесту уже есть результаты — его вопросы изменить "
                    "нельзя. Создайте копию методики и правьте её."
                )
            _replace_questions(test.id, data["questions"], db)
        if "interpretations" in data and data["interpretations"] is not None:
            _replace_interpretations(test.id, data["interpretations"], db)

        test.updated_at = datetime.now(timezone.utc)
        record_event(
            event="test_updated",
            actor=Actor.user(actor_id, actor_role),
            target=Target("test", test.id),
            outcome=Outcome.SUCCESS,
            metadata={},
            context=safe_ctx,
            db=db,
        )
        db.commit()
        db.refresh(test)
        return _test_to_dict(test, db)


def delete_test(
    uuid_str: str,
    *,
    actor_id: Optional[int] = None,
    actor_role: Optional[str] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> bool:
    if actor_id is None or actor_role is None:
        raise RuntimeError(
            "test delete requires authenticated actor context "
            "(actor_id and actor_role)"
        )
    safe_ctx = build_request_context(ip=ip, user_agent=user_agent)

    try:
        uuid_obj = _uuid.UUID(uuid_str)
    except ValueError:
        return False
    with SessionLocal() as db:
        test = db.query(Test).filter(
            Test.uuid == uuid_obj, Test.deleted_at.is_(None)
        ).first()
        if not test:
            return False
        test.deleted_at = datetime.now(timezone.utc)
        test.is_active = False
        record_event(
            event="test_deleted",
            actor=Actor.user(actor_id, actor_role),
            target=Target("test", test.id),
            outcome=Outcome.SUCCESS,
            metadata={},
            context=safe_ctx,
            db=db,
        )
        db.commit()
    return True


# ══════════════════════════════════════════════════════════════════════════════
# Student-facing: прохождение, submit, результаты, consent (Этап B)
# ══════════════════════════════════════════════════════════════════════════════

def find_active_tests(
    page: int = 1, size: int = 20, search: Optional[str] = None,
) -> tuple[list[dict], int]:
    """Список активных тестов для студента (без вопросов и баллов)."""
    with SessionLocal() as db:
        q = db.query(Test).filter(
            Test.deleted_at.is_(None), Test.is_active.is_(True)
        )
        if search:
            q = q.filter(Test.title.ilike(f"%{search.strip()}%"))
        total = q.count()
        tests = (
            q.order_by(desc(Test.created_at))
            .offset((page - 1) * size).limit(size).all()
        )
        items = []
        for t in tests:
            qcount = (
                db.query(func.count(Question.id))
                .filter(Question.test_id == t.id).scalar()
            )
            items.append({
                "uuid": str(t.uuid),
                "title": t.title,
                "description": t.description,
                "time_limit_min": t.time_limit_min,
                "question_count": qcount or 0,
                "categories": _categories_of(t.id, db),
                "tags": _tags_of(t.id, db),
            })
    return items, total


def get_active_test_full(uuid_str: str) -> Optional[dict]:
    """Активный тест целиком (включая баллы/пороги) — для скоринга на сервере."""
    try:
        uuid_obj = _uuid.UUID(uuid_str)
    except ValueError:
        return None
    with SessionLocal() as db:
        test = db.query(Test).filter(
            Test.uuid == uuid_obj,
            Test.deleted_at.is_(None),
            Test.is_active.is_(True),
        ).first()
        if not test:
            return None
        data = _test_to_dict(test, db)
        data["id"] = test.id
        data["version"] = test.version
        return data


def save_result(
    user_id: int, test_uuid: str, computed: dict, answers: list[dict],
    *,
    actor_role: Optional[str] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> Optional[dict]:
    """
    Атомарно сохраняет результат прохождения: test_results + test_result_scales
    + student_answers в одной транзакции (один commit). user_id — единственный
    actor id (self-action). test_submitted пишется до commit; metadata пуста —
    score/answers/free_text/recommendations в audit НЕ попадают.
    """
    if actor_role is None:
        raise RuntimeError(
            "test submit requires authenticated actor context (actor_role)"
        )
    safe_ctx = build_request_context(ip=ip, user_agent=user_agent)

    try:
        uuid_obj = _uuid.UUID(test_uuid)
    except ValueError:
        return None

    with SessionLocal() as db:
        test = db.query(Test).filter(
            Test.uuid == uuid_obj,
            Test.deleted_at.is_(None),
            Test.is_active.is_(True),
        ).first()
        if not test:
            return None

        result = TestResult(
            user_id=user_id,
            test_id=test.id,
            test_version=test.version,
            total_score=computed.get("total_score"),
            max_possible=computed.get("max_possible"),
            scoring_used=computed.get("scoring_used"),
            recommendations=computed.get("recommendations"),
        )
        db.add(result)
        db.flush()

        for s in computed.get("scales", []):
            db.add(TestResultScale(
                test_result_id=result.id,
                scale_name=s["scale_name"],
                score=s["score"],
                max_score=s.get("max_score"),
                interpretation=s.get("interpretation"),
                scale_metadata={"label": s.get("label")} if s.get("label") else {},
            ))

        for a in answers:
            free_text = (a.get("free_text_answer") or "").strip()
            db.add(StudentAnswer(
                test_result_id=result.id,
                question_id=a["question_id"],
                option_id=a.get("option_id"),
                free_text_answer_enc=encrypt_text(free_text) if free_text else None,
                scale_value=a.get("scale_value"),
                selected_options=a.get("selected_options"),
                time_spent_sec=a.get("time_spent_sec"),
            ))

        record_event(
            event="test_submitted",
            actor=Actor.user(user_id, actor_role),
            target=Target("test_result", result.id),
            outcome=Outcome.SUCCESS,
            metadata={},
            context=safe_ctx,
            db=db,
        )
        db.commit()
        db.refresh(result)
        return _result_to_dict(result, db)


def _result_to_dict(result: TestResult, db) -> dict:
    test = db.query(Test).filter(Test.id == result.test_id).first()
    scales = (
        db.query(TestResultScale)
        .filter(TestResultScale.test_result_id == result.id)
        .all()
    )
    return {
        "uuid": str(result.uuid),
        "test_uuid": str(test.uuid) if test else None,
        "test_title": test.title if test else None,
        "total_score": result.total_score,
        "max_possible": result.max_possible,
        "scoring_used": result.scoring_used,
        "recommendations": result.recommendations,
        "submitted_at": result.submitted_at,
        "scales": [
            {
                "scale_name": s.scale_name,
                "score": s.score,
                "max_score": s.max_score,
                "interpretation": s.interpretation,
                "label": (s.scale_metadata or {}).get("label"),
            }
            for s in scales
        ],
    }


def find_user_results(user_id: int, page: int = 1, size: int = 20) -> tuple[list[dict], int]:
    with SessionLocal() as db:
        q = db.query(TestResult).filter(TestResult.user_id == user_id)
        total = q.count()
        rows = (
            q.order_by(desc(TestResult.submitted_at))
            .offset((page - 1) * size).limit(size).all()
        )
        items = [_result_to_dict(r, db) for r in rows]
    return items, total


def get_user_result(user_id: int, result_uuid: str) -> Optional[dict]:
    try:
        uuid_obj = _uuid.UUID(result_uuid)
    except ValueError:
        return None
    with SessionLocal() as db:
        result = db.query(TestResult).filter(
            TestResult.uuid == uuid_obj,
            TestResult.user_id == user_id,
        ).first()
        if not result:
            return None
        return _result_to_dict(result, db)


# ── consent (ФЗ-152) ──────────────────────────────────────────────────────────

def get_active_test_consent() -> Optional[dict]:
    """Последняя версия политики `test_consent`."""
    with SessionLocal() as db:
        c = (
            db.query(Consent)
            .filter(Consent.policy_type == "test_consent")
            .order_by(Consent.version.desc())
            .first()
        )
        if not c:
            return None
        return {
            "id": c.id, "policy_type": c.policy_type, "version": c.version,
            "title": c.title, "content": c.content,
        }


def has_accepted_consent(user_id: int, consent_id: int) -> bool:
    with SessionLocal() as db:
        rec = (
            db.query(ConsentRecord)
            .filter(
                ConsentRecord.user_id == user_id,
                ConsentRecord.consent_id == consent_id,
                ConsentRecord.accepted.is_(True),
                ConsentRecord.revoked_at.is_(None),
            )
            .first()
        )
        return rec is not None


def save_consent_record(
    user_id: int, consent_id: int,
    ip: Optional[str] = None, user_agent: Optional[str] = None,
    *,
    actor_role: Optional[str] = None,
) -> int:
    """
    Фиксирует согласие субъекта на тестирование. user_id — единственный actor id
    (self-action). Возвращает id ConsentRecord (Target аудита).

    accepted-command: каждый успешный accept пишет test_consent_accepted (даже
    повторный — на тот же существующий record.id). Повторный accept НЕ
    перезаписывает исходные accepted_at/ip_address/user_agent — первая запись
    остаётся историческим доказательством первого принятия. Sanitized context
    (build_request_context) общий для ConsentRecord (new) и audit.
    """
    if actor_role is None:
        raise RuntimeError(
            "consent accept requires authenticated actor context (actor_role)"
        )
    safe_ctx = build_request_context(ip=ip, user_agent=user_agent)

    with SessionLocal() as db:
        existing = (
            db.query(ConsentRecord)
            .filter(
                ConsentRecord.user_id == user_id,
                ConsentRecord.consent_id == consent_id,
                ConsentRecord.revoked_at.is_(None),
            )
            .first()
        )
        if existing:
            existing.accepted = True   # идемпотентно; ip/ua/accepted_at не трогаем
            record_id = existing.id
        else:
            record = ConsentRecord(
                user_id=user_id,
                consent_id=consent_id,
                accepted=True,
                ip_address=safe_ctx.ip_address,   # sanitized, не raw
                user_agent=safe_ctx.user_agent,    # sanitized, не raw
            )
            db.add(record)
            db.flush()   # id до commit — нужен Target
            record_id = record.id

        record_event(
            event="test_consent_accepted",
            actor=Actor.user(user_id, actor_role),
            target=Target("consent_record", record_id),
            outcome=Outcome.SUCCESS,
            metadata={},
            context=safe_ctx,
            db=db,
        )
        db.commit()
        return record_id
