"""
SQLAlchemy-слой модуля психодиагностики (Этап A — admin CRUD).

Тест хранится как дерево: tests → questions → options, плюс test_interpretations,
test_categories (M:N), test_tags (M:N). Запись/обновление дерева — в одной
транзакции (one SessionLocal + один commit).
"""

import sys
import uuid as _uuid
from datetime import datetime, timezone
from typing import Callable, Optional

from sqlalchemy import desc, func, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload

from app.core.encryption import decrypt_text, encrypt_text
from app.db.session import SessionLocal
from app.db.models import (
    Test, TestCategory, TestTag, TestInterpretation,
    Question, Option, QuestionMedia, OptionMedia, MediaFile,
    TestResult, TestResultScale, StudentAnswer,
    Category, Tag, User, Role, UserRole,
    Consent, ConsentRecord, CampaignResponseAnswer, TestCampaign,
)
from app.audit import Actor, Outcome, Target, record_event
from app.audit.request_context import build_request_context
from app.psychologist.client_scope import lock_client_scope
from app.tests import rules as test_rules


class TestStateChanged(Exception):
    """
    Состояние теста под блокировкой строки не совпало с ожидаемым вызывающей
    стороной (статус или updated_at изменились с момента, когда решение было
    принято). Мутации нет; route мапит на 409 test_state_changed. Определена
    здесь (как TestHasResults), service её ре-экспортирует.
    """

    def __init__(self, current_status: str):
        super().__init__(current_status)
        self.current_status = current_status


class TestHasResults(Exception):
    """
    Попытка заменить вопросы теста, по которому уже есть пройденные результаты.

    Определена здесь (а не в service), чтобы storage мог её поднять без
    циклического импорта; service её ре-экспортирует, routes → HTTP 409.
    """


class TestUsedByCampaigns(TestHasResults):
    """
    Удаление методики, по которой созданы тестирования по ссылке (ADR-037):
    кампании и их ответы ссылаются на неё. Подкласс TestHasResults — routes,
    уже мапящие TestHasResults на 409, обрабатывают и этот случай.
    (До ADR-037 здесь был сплошной запрет правки campaign_only-тестов —
    TestCampaignOnly; его заменили правила версий и has_results.)
    """

    def __init__(self, msg: str = (
        "Методика используется в тестировании по ссылке — удалить её нельзя."
    )):
        super().__init__(msg)


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


def _question_media_to_list(links) -> list[dict]:
    """Связки вопрос↔медиа → [{uuid, url, caption}] по display_order."""
    out = []
    for link in sorted(links, key=lambda m: m.display_order):
        mf: Optional[MediaFile] = link.media
        if mf is None:
            continue   # осиротевшая связка (файл удалён) — не отдаём
        out.append({
            "uuid":    str(mf.uuid),
            "url":     mf.file_path,
            "kind":    mf.file_type,
            "caption": link.caption,
        })
    return out


def _option_media_to_list(links) -> list[dict]:
    """Связки вариант↔медиа → [{uuid, url, caption=None}] по display_order.

    У option_media нет колонки caption (варианты декоративны) — поле включаем
    для единообразия формы, всегда None.
    """
    out = []
    for link in sorted(links, key=lambda m: m.display_order):
        mf: Optional[MediaFile] = link.media
        if mf is None:
            continue
        out.append({
            "uuid":    str(mf.uuid),
            "url":     mf.file_path,
            "kind":    mf.file_type,
            "caption": None,
        })
    return out


def _option_to_dict(o: Option) -> dict:
    return {
        "id":           o.id,
        "option_text":  o.option_text,
        "option_order": o.option_order,
        "value_score":  o.value_score,
        "media":        _option_media_to_list(o.media),
    }


def _question_to_dict(q: Question) -> dict:
    options = sorted(q.options, key=lambda o: o.option_order)
    return {
        "id":             q.id,
        "question_text":  q.question_text,
        "question_order": q.question_order,
        "question_type":  q.question_type,
        "is_required":    q.is_required,
        "config":         q.config or {},
        "media":          _question_media_to_list(q.media),
        "options":        [_option_to_dict(o) for o in options],
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


def _usage(test_id: int, db) -> dict:
    """Где используется методика (для подсказок интерфейса): есть ли ответы
    (тогда вопросы, баллы и правила меняются только новой версией) и в скольких
    кампаниях она выбрана."""
    return {
        "has_results": has_results(test_id, db),
        "campaigns_count": db.query(func.count(TestCampaign.id))
        .filter(TestCampaign.test_id == test_id).scalar() or 0,
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
        "status":          test.status,
        "shuffle_questions": test.shuffle_questions,
        "shuffle_options":   test.shuffle_options,
        "scoring_rules":   test.scoring_rules,          # ADR-037
        "campaign_only":   bool(test.campaign_only),
        "lineage_uuid":    str(test.lineage_uuid) if test.lineage_uuid else None,
        "superseded_at":   test.superseded_at,
        "created_at":      test.created_at,
        "updated_at":      test.updated_at,
        "created_by":      test.created_by,
        "created_by_name": _author_name(test.created_by, db),
        "categories":      _categories_of(test.id, db),
        "tags":            _tags_of(test.id, db),
        "questions":       [_question_to_dict(q) for q in questions],
        "interpretations": [_interpretation_to_dict(i) for i in interpretations],
        **_usage(test.id, db),
    }


# ── helpers: медиа ────────────────────────────────────────────────────────────

def resolve_media(uuid_str: str, db) -> Optional[int]:
    """media_files.id по UUID или None (в т.ч. для is_active=false / битого UUID)."""
    try:
        uuid_obj = _uuid.UUID(uuid_str)
    except (ValueError, TypeError, AttributeError):
        return None
    row = (
        db.query(MediaFile.id)
        .filter(MediaFile.uuid == uuid_obj, MediaFile.is_active.is_(True))
        .first()
    )
    return row.id if row else None


def media_exists(uuid_str: str) -> bool:
    """Активный медиафайл с таким UUID существует. Для валидации в service."""
    with SessionLocal() as db:
        return resolve_media(uuid_str, db) is not None


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
        for mi, m in enumerate(q.get("media", []) or []):
            media_id = resolve_media(m["media_uuid"], db)
            if media_id is None:
                continue   # уже отвергнуто валидацией service; страховка
            db.add(QuestionMedia(
                question_id=question.id,
                media_id=media_id,
                media_role="main",
                display_order=mi + 1,
                caption=m.get("caption"),
            ))
        for o in q.get("options", []):
            option = Option(
                question_id=question.id,
                option_text=o["option_text"],
                option_order=o["option_order"],
                value_score=o["value_score"],
            )
            db.add(option)
            option_media = o.get("media", []) or []
            if option_media:
                db.flush()   # нужен option.id для связки
                for mi, m in enumerate(option_media):
                    media_id = resolve_media(m["media_uuid"], db)
                    if media_id is None:
                        continue
                    db.add(OptionMedia(
                        option_id=option.id,
                        media_id=media_id,
                        media_role="icon",
                        display_order=mi + 1,
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
    status: Optional[str] = None,
) -> tuple[list[dict], int]:
    """Admin-список. status=None (по умолчанию) — ВСЕ статусы: иначе тесты,
    переведённые data-миграцией в draft, пропали бы из вида админа."""
    with SessionLocal() as db:
        q = db.query(Test).filter(Test.deleted_at.is_(None))
        if is_active is not None:
            q = q.filter(Test.is_active.is_(is_active))
        if status is not None:
            q = q.filter(Test.status == status)
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
                "status":          t.status,
                "question_count":  qcount or 0,
                "categories":      _categories_of(t.id, db),
                "tags":            _tags_of(t.id, db),
                "created_at":      t.created_at,
                "created_by_name": _author_name(t.created_by, db),
                "updated_at":      t.updated_at,
                "superseded_at":   t.superseded_at,     # ADR-037
                **_usage(t.id, db),
                "campaign_only":   bool(t.campaign_only),
            })
    return items, total


def find_my_tests(
    author_id: int,
    page: int = 1,
    size: int = 20,
    search: Optional[str] = None,
    status: Optional[str] = None,
) -> tuple[list[dict], int]:
    """Psychologist-scoped список (Этап F2): только свои тесты. status=None
    (по умолчанию) — ВСЕ статусы, автор должен видеть, где сейчас каждый его
    draft/in_review/needs_changes/published."""
    with SessionLocal() as db:
        q = db.query(Test).filter(
            Test.deleted_at.is_(None), Test.created_by == author_id,
        )
        if status is not None:
            q = q.filter(Test.status == status)
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
                "uuid":           str(t.uuid),
                "title":          t.title,
                "scoring":        t.scoring,
                "version":        t.version,
                "is_active":      t.is_active,
                "status":         t.status,
                "question_count": qcount or 0,
                "categories":     _categories_of(t.id, db),
                "tags":           _tags_of(t.id, db),
                "created_at":     t.created_at,
                "created_by_name": _author_name(t.created_by, db),
                "updated_at":      t.updated_at,
                "superseded_at":   t.superseded_at,     # ADR-037
                **_usage(t.id, db),
                "campaign_only":   bool(t.campaign_only),
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
    event: str = "test_created",   # ADR-037: импорт из xlsx — test_imported
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
            status=data.get("status", "published"),
            shuffle_questions=data.get("shuffle_questions", False),
            shuffle_options=data.get("shuffle_options", False),
            scoring_rules=data.get("scoring_rules"),          # ADR-037
            campaign_only=bool(data.get("campaign_only", False)),
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
            event=event,
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
    """Есть ли ответы, ссылающиеся на вопросы теста: результаты студентов
    или ответы кампаний (ADR-036; оба держат questions/options через RESTRICT)."""
    if db.query(
        db.query(TestResult.id).filter(TestResult.test_id == test_id).exists()
    ).scalar():
        return True
    return db.query(
        db.query(CampaignResponseAnswer.id)
        .join(Question, Question.id == CampaignResponseAnswer.question_id)
        .filter(Question.test_id == test_id)
        .exists()
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


def _clone_tree(db, src: Test, copy: Test) -> None:
    """Категории, темы, вопросы с вариантами и медиа, пороги — из src в copy
    (copy уже flush-нут). Общий для «Дублировать» и «Новой версии»."""
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
        # медиа вопроса: тот же media_id (физический файл общий)
        for qm in q.media:
            db.add(QuestionMedia(
                question_id=question.id,
                media_id=qm.media_id,
                media_role=qm.media_role,
                display_order=qm.display_order,
                caption=qm.caption,
            ))
        for o in sorted(q.options, key=lambda x: x.option_order):
            option = Option(
                question_id=question.id,
                option_text=o.option_text,
                option_order=o.option_order,
                value_score=o.value_score,
            )
            db.add(option)
            if o.media:
                db.flush()   # нужен option.id
                for om in o.media:
                    db.add(OptionMedia(
                        option_id=option.id,
                        media_id=om.media_id,
                        media_role=om.media_role,
                        display_order=om.display_order,
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
    результаты — нет. Копия создаётся как черновик (is_active=False,
    status='draft', version=1), чтобы её можно было доработать до публикации.
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
            shuffle_questions=src.shuffle_questions,
            shuffle_options=src.shuffle_options,
            # ADR-037: правила обработки — часть методики; копия — новая
            # методика (свой lineage_uuid), не версия исходной.
            scoring_rules=src.scoring_rules,
            campaign_only=src.campaign_only,
            is_active=False,
            status="draft",
            version=1,
            created_by=created_by,
        )
        db.add(copy)
        db.flush()

        _clone_tree(db, src, copy)

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


class DraftVersionExists(Exception):
    """У методики уже есть неопубликованная версия (draft/in_review/
    needs_changes) — вторую не создаём (ADR-037) → 409."""

    def __init__(self, draft_uuid: str):
        super().__init__("У методики уже есть черновик новой версии — продолжите его.")
        self.draft_uuid = draft_uuid


def create_new_version(
    uuid_str: str,
    *,
    actor_id: int,
    actor_role: str,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> Optional[dict]:
    """
    ADR-037: новая версия методики — копия с тем же lineage_uuid, version =
    max по линии + 1, статус draft. Прежние версии, их результаты и кампании не
    меняются; при публикации новой версии предыдущие получают superseded_at
    (transition_atomic). Все строки линии берутся FOR UPDATE в порядке id —
    две параллельные «новые версии» не создадут два черновика.
    """
    safe_ctx = build_request_context(ip=ip, user_agent=user_agent)
    uuid_obj = _parse_uuid(uuid_str)
    if uuid_obj is None:
        return None
    with SessionLocal() as db:
        src = db.query(Test).filter(Test.uuid == uuid_obj, Test.deleted_at.is_(None)).first()
        if src is None:
            return None
        line = (db.query(Test)
                .filter(Test.lineage_uuid == src.lineage_uuid, Test.deleted_at.is_(None))
                .order_by(Test.id).with_for_update().populate_existing().all())
        pending = [t for t in line if t.status != "published"]
        if pending:
            raise DraftVersionExists(str(pending[0].uuid))
        copy = Test(
            title=src.title,
            description=src.description,
            scoring=src.scoring,
            max_score=src.max_score,
            time_limit_min=src.time_limit_min,
            shuffle_questions=src.shuffle_questions,
            shuffle_options=src.shuffle_options,
            scoring_rules=src.scoring_rules,
            campaign_only=src.campaign_only,
            lineage_uuid=src.lineage_uuid,
            version=max((t.version or 1) for t in line) + 1,
            is_active=src.is_active,
            status="draft",
            created_by=actor_id,
        )
        db.add(copy)
        db.flush()
        _clone_tree(db, src, copy)
        record_event(
            event="test_version_created",
            actor=Actor.user(actor_id, actor_role),
            target=Target("test", copy.id),
            outcome=Outcome.SUCCESS,
            metadata={},
            context=safe_ctx,
            db=db,
        )
        db.commit()
        db.refresh(copy)
        return _test_to_dict(copy, db)


class TextsStructureChanged(ValueError):
    """Исправление текстов прислало другой состав вопросов/вариантов → 422."""


def correct_texts(
    uuid_str: str,
    data: dict,
    *,
    actor_id: int,
    actor_role: str,
    expected_updated_at: datetime,
    expected_status: Optional[str] = None,
    unpublish_event: Optional[str] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> Optional[dict]:
    """
    ADR-037: опечатки — без новой версии и при наличии ответов. Меняются ТОЛЬКО
    question_text, option_text и rules.instruction. Под FOR UPDATE: состояние
    (updated_at, при необходимости статус) — как видел автор; набор номеров
    вопросов и вариантов — точно как в БД (иначе TextsStructureChanged).
    Баллы, шкалы, порядок, типы вопросов и прочие правила не трогаются.
    Ничего не изменилось — без события и без updated_at.
    """
    safe_ctx = build_request_context(ip=ip, user_agent=user_agent)
    uuid_obj = _parse_uuid(uuid_str)
    if uuid_obj is None:
        return None
    with SessionLocal() as db:
        test = _lock_test(db, uuid_obj)
        if not test:
            return None
        if test.updated_at != expected_updated_at or (
                expected_status is not None and test.status != expected_status):
            raise TestStateChanged(test.status)
        questions = {q.question_order: q for q in test.questions}
        incoming = {q["question_order"]: q for q in data.get("questions") or []}
        if set(incoming) != set(questions) or len(incoming) != len(data.get("questions") or []):
            raise TextsStructureChanged("Состав вопросов изменился — обновите страницу")
        changed = False
        for order, q in questions.items():
            new_q = incoming[order]
            options = {o.option_order: o for o in q.options}
            new_opts = {o["option_order"]: o for o in new_q.get("options") or []}
            if set(new_opts) != set(options) or len(new_opts) != len(new_q.get("options") or []):
                raise TextsStructureChanged(
                    f"Варианты вопроса {order} изменились — обновите страницу")
            if q.question_text != new_q["question_text"]:
                q.question_text = new_q["question_text"]
                changed = True
            for o_order, o in options.items():
                if o.option_text != new_opts[o_order]["option_text"]:
                    o.option_text = new_opts[o_order]["option_text"]
                    changed = True
        if "instruction" in data:
            rules = test_rules.parse(test.scoring_rules)
            if rules is None:
                if data["instruction"]:
                    raise TextsStructureChanged("У методики нет правил обработки для инструкции")
            else:
                new_rules = test_rules.dump(rules.model_copy(update={"instruction": None}))
                new_rules["instruction"] = data["instruction"]
                new_rules = test_rules.dump(test_rules.parse(new_rules))
                if new_rules != test_rules.dump(rules):
                    test.scoring_rules = new_rules
                    changed = True
        if not changed:
            return _test_to_dict(test, db)
        if unpublish_event is not None:
            test.status = "draft"
            record_event(
                event=unpublish_event, actor=Actor.user(actor_id, actor_role),
                target=Target("test", test.id), outcome=Outcome.SUCCESS,
                metadata={}, context=safe_ctx, db=db,
            )
        test.updated_at = datetime.now(timezone.utc)
        record_event(
            event="test_texts_corrected", actor=Actor.user(actor_id, actor_role),
            target=Target("test", test.id), outcome=Outcome.SUCCESS,
            metadata={}, context=safe_ctx, db=db,
        )
        db.commit()
        db.refresh(test)
        return _test_to_dict(test, db)


def update_test(
    uuid_str: str,
    data: dict,
    *,
    actor_id: Optional[int] = None,
    actor_role: Optional[str] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
    unpublish_event: Optional[str] = None,
    expected_status: Optional[str] = None,
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

    unpublish_event (Этап F2.1) — если задан, тест атомарно снимается с
    публикации (status → "draft") этим же вызовом, и пишется дополнительное
    audit-событие с этим именем поверх обычного test_updated (одна транзакция,
    один commit). Применяется ПОСЛЕ проверки has_results на вопросах — неуспешная
    правка (TestHasResults) не должна снимать тест с публикации попутно.

    Строка теста берётся FOR UPDATE: правка сериализуется с решениями модерации.
    expected_status — статус, по которому service принял решение (гейт автора,
    выбор unpublish_event); если под блокировкой он другой → TestStateChanged
    без мутации (иначе правка легла бы на только что опубликованный/отправленный
    на проверку тест).
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
        test = _lock_test(db, uuid_obj)
        if not test:
            return None
        if expected_status is not None and test.status != expected_status:
            raise TestStateChanged(test.status)
        for field in ("title", "description", "scoring", "max_score",
                      "time_limit_min", "is_active",
                      "shuffle_questions", "shuffle_options", "campaign_only"):
            if field in data and data[field] is not None:
                setattr(test, field, data[field])

        # ADR-037: правила обработки. Ключ передан — заменить (null — убрать).
        # Как и вопросы, после первых ответов не меняются: по ним считаются
        # результаты кампаний этой версии методики.
        if "scoring_rules" in data and data["scoring_rules"] != test.scoring_rules:
            if has_results(test.id, db):
                raise TestHasResults(
                    "По этой методике уже есть результаты — правила обработки "
                    "изменить нельзя. Создайте новую версию методики."
                )
            test.scoring_rules = data["scoring_rules"]

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

        if unpublish_event is not None:
            test.status = "draft"
            record_event(
                event=unpublish_event,
                actor=Actor.user(actor_id, actor_role),
                target=Target("test", test.id),
                outcome=Outcome.SUCCESS,
                metadata={},
                context=safe_ctx,
                db=db,
            )

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
    expected_status: Optional[str] = None,
) -> bool:
    """Мягкое удаление под FOR UPDATE; expected_status — как в update_test."""
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
        test = _lock_test(db, uuid_obj)
        if not test:
            return False
        if expected_status is not None and test.status != expected_status:
            raise TestStateChanged(test.status)
        if db.query(db.query(TestCampaign.id)
                    .filter(TestCampaign.test_id == test.id).exists()).scalar():
            raise TestUsedByCampaigns()
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
# Moderation workflow (Этап F, ADR-016)
# ══════════════════════════════════════════════════════════════════════════════

def get_status_and_author(uuid_str: str) -> Optional[dict]:
    """{"status": str, "created_by": Optional[int]} теста или None (не
    найден/удалён). created_by может быть NULL — автор аккаунта удалён
    (FK ON DELETE SET NULL); service трактует это как «нет автора» (is_author
    всегда False), но admin/supervisor по-прежнему могут publish напрямую."""
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
        return {"status": test.status, "created_by": test.created_by}


def pending_review_count() -> int:
    """Число тестов на модерации (in_review) — бейдж меню проверяющего, без аудита."""
    with SessionLocal() as db:
        return db.query(Test).filter(
            Test.deleted_at.is_(None), Test.status == "in_review",
        ).count()


def _lock_test(db, uuid_obj) -> Optional[Test]:
    """Строка неудалённого теста под FOR UPDATE (свежая версия после ожидания)."""
    return (
        db.query(Test)
        .filter(Test.uuid == uuid_obj, Test.deleted_at.is_(None))
        .populate_existing()
        .with_for_update()
        .first()
    )


def transition_atomic(
    uuid_str: str,
    new_status: str,
    *,
    decide: Callable[[str, Optional[int]], str],
    ready_check: Optional[Callable[[dict], None]] = None,
    expected_status: Optional[str] = None,
    expected_updated_at: Optional[datetime] = None,
    actor_id: int,
    actor_role: str,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> Optional[tuple[dict, str]]:
    """
    Переход статуса модерации в ОДНОЙ транзакции (ADR-016, дополнение
    2026-11-02): строка теста FOR UPDATE → сверка ожидаемого состояния →
    decide(текущий статус, created_by) — легальность и права (service), уже под
    блокировкой → смена status/updated_at → audit-событие, которое вернул decide
    (test_submitted_for_review / test_published / test_returned_for_changes),
    ATOMIC → один commit.

    expected_status / expected_updated_at — состояние, по которому принято
    решение (строка очереди или формы). Несовпадение → TestStateChanged без
    мутации и без события: решение по устаревшему экрану не применяется,
    а второе из двух конкурирующих решений не проходит как «новая» прямая
    публикация. Возвращает (test_dict, previous_status) или None (не найден).
    """
    safe_ctx = build_request_context(ip=ip, user_agent=user_agent)
    try:
        uuid_obj = _uuid.UUID(uuid_str)
    except ValueError:
        return None
    with SessionLocal() as db:
        test = _lock_test(db, uuid_obj)
        if not test:
            return None
        previous = test.status
        if expected_status is not None and previous != expected_status:
            raise TestStateChanged(previous)
        if expected_updated_at is not None and test.updated_at != expected_updated_at:
            raise TestStateChanged(previous)
        event = decide(previous, test.created_by)
        if ready_check is not None and new_status in ("in_review", "published"):
            # ADR-037: правила согласованы с вопросами — под той же блокировкой.
            ready_check(_test_to_dict(test, db))
        test.status = new_status
        test.updated_at = datetime.now(timezone.utc)
        if new_status == "published":
            # ADR-037: прежние опубликованные версии этой методики заменены —
            # их нет в каталоге и в выборе методики кампании; результаты и
            # действующие кампании остаются на своих версиях.
            (db.query(Test)
             .filter(Test.lineage_uuid == test.lineage_uuid, Test.id != test.id,
                     Test.status == "published", Test.superseded_at.is_(None),
                     Test.version < test.version)
             .update({Test.superseded_at: test.updated_at}, synchronize_session=False))
        record_event(
            event=event,
            actor=Actor.user(actor_id, actor_role),
            target=Target("test", test.id),
            outcome=Outcome.SUCCESS,
            metadata={},
            context=safe_ctx,
            db=db,
        )
        db.commit()
        db.refresh(test)
        return _test_to_dict(test, db), previous


# ══════════════════════════════════════════════════════════════════════════════
# Student-facing: прохождение, submit, результаты, consent (Этап B)
# ══════════════════════════════════════════════════════════════════════════════

def find_active_tests(
    page: int = 1, size: int = 20, search: Optional[str] = None,
) -> tuple[list[dict], int]:
    """Список тестов для студента (без вопросов и баллов). Видимость (Этап F,
    ADR-016): status='published' И is_active=True — публично виден только
    опубликованный и включённый тест. Тесты кампаний (campaign_only, ADR-036)
    в каталог не попадают."""
    with SessionLocal() as db:
        q = db.query(Test).filter(
            Test.deleted_at.is_(None), Test.is_active.is_(True),
            Test.status == "published", Test.campaign_only.is_(False),
            Test.superseded_at.is_(None),    # ADR-037: только последняя версия
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
    """Опубликованный тест целиком (включая баллы/пороги) — для скоринга на
    сервере. Используется и для отдачи студенту (get_test_for_take), и при submit
    (save_result грузит тест повторно тем же путём) — оба места защищены
    status='published' И is_active=True."""
    try:
        uuid_obj = _uuid.UUID(uuid_str)
    except ValueError:
        return None
    with SessionLocal() as db:
        test = db.query(Test).filter(
            Test.uuid == uuid_obj,
            Test.deleted_at.is_(None),
            Test.is_active.is_(True),
            Test.status == "published",
            Test.campaign_only.is_(False),   # ADR-036: только по ссылке кампании
            Test.superseded_at.is_(None),    # ADR-037: только последняя версия
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
        # Отдельный запрос от get_active_test_full (не переиспользует его сессию) —
        # тот же гейт видимости: status='published' И is_active=True, иначе submit
        # мог бы сохраниться после того, как тест сняли с публикации/увели в модерацию.
        test = db.query(Test).filter(
            Test.uuid == uuid_obj,
            Test.deleted_at.is_(None),
            Test.is_active.is_(True),
            Test.status == "published",
            Test.campaign_only.is_(False),   # ADR-036: только по ссылке кампании
            Test.superseded_at.is_(None),    # ADR-037: только последняя версия
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
            # ADR-037: снимок достоверности и типов по правилам этой версии
            # методики; студенту не отдаётся (только staff, Этап E).
            rule_summary=test_rules.summarize(
                test_rules.parse(test.scoring_rules),
                {s["scale_name"]: s["score"] for s in computed.get("scales", [])},
            ),
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


def _result_to_dict(result: TestResult, db, *, staff: bool = False) -> dict:
    """staff=True — для Этапа E: добавляет rule_summary и подписи шкал из
    правил (ADR-037). Студенту ни то, ни другое не отдаётся."""
    test = db.query(Test).filter(Test.id == result.test_id).first()
    scales = (
        db.query(TestResultScale)
        .filter(TestResultScale.test_result_id == result.id)
        .order_by(TestResultScale.id)
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
        **(_staff_extras(result, test) if staff else {}),
    }


def _staff_extras(result: TestResult, test: Optional[Test]) -> dict:
    rules = test_rules.parse(test.scoring_rules) if test else None
    return {
        "rule_summary": result.rule_summary,
        "scale_labels": {s.code: s.label for s in rules.scales} if rules else {},
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


# ══════════════════════════════════════════════════════════════════════════════
# Staff-доступ к результатам (Этап E, ADR-016; дополнение 2026-10-29)
# ══════════════════════════════════════════════════════════════════════════════
#
# Одна и та же проверка владельца результата и области доступа для списка,
# детали и ответов — ДО чтения баллов/ответов и в той же транзакции, что и
# чтение:
#   * psychologist — строгое активное сопровождение с активным клиентом
#     (app.psychologist.client_scope.lock_client_scope: FOR SHARE строки
#     сопровождения и строки клиента; клиент может иметь staff-роли);
#   * supervisor — владелец обязан быть «чистым» активным студентом (тот же
#     предикат, что у списка: staff не читает самотесты другого staff).
# Нет области / результата → None (route: единый отказ). Баллы, шкалы и ответы
# читаются только после проверки; free_text расшифровывается только в пути
# ответов. Блокировки снимаются при закрытии сессии — до записи content_read.
#
# Исторический контракт: test_title — АКТУАЛЬНОЕ название теста (snapshot нет);
# баллы, recommendations, test_result_scales и student_answers — сохранённые
# при submit значения, без пересчёта. Тексты вопросов/вариантов и связи медиа —
# текущие строки, неизменные при наличии результатов (TestHasResults + FK
# RESTRICT); удалённый файл медиатеки не показывается (правило хелперов медиа).
#
# Санитизация: неожиданная SQLAlchemyError / сбой расшифровки → rollback,
# в stderr — операция/фаза/класс, наружу StaffResultsStorageError (вне except,
# from None): SQL, параметры, ответы и шифртекст не попадают в traceback.

class StaffResultsStorageError(Exception):
    """Технический сбой staff-чтения результатов (без деталей и значений)."""


class _Undecryptable(Exception):
    pass


def _diag(operation: str, phase: str, error_class: str) -> None:
    print(
        f"[STAFF_RESULTS] op={operation} phase={phase} error={error_class}",
        file=sys.stderr,
    )


def _parse_uuid(value) -> Optional[_uuid.UUID]:
    if isinstance(value, _uuid.UUID):
        return value
    try:
        return _uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


def _pure_active_student_id(db, *, user_id: Optional[int] = None,
                            user_uuid: Optional[_uuid.UUID] = None) -> Optional[int]:
    """
    users.id, ТОЛЬКО если это реальный активный студент: активная роль student и
    НИ ОДНОЙ активной не-student роли. Роль student неявно выдана всем staff
    (ADR-024), поэтому staff-аккаунты исключаем — иначе supervisor читал бы
    результаты самотестирования другого staff. Предикат совпадает с
    supervisor.storage.get_students.
    """
    now = datetime.now(timezone.utc)
    q = db.query(User.id).filter(User.is_active.is_(True), User.deleted_at.is_(None))
    q = q.filter(User.id == int(user_id)) if user_id is not None else q.filter(User.uuid == user_uuid)
    uid = q.scalar()
    if uid is None:
        return None

    def _has_role(is_student: bool) -> bool:
        sub = (
            db.query(UserRole.id)
            .join(Role, Role.id == UserRole.role_id)
            .filter(
                UserRole.user_id == uid,
                (Role.name == "student") if is_student else (Role.name != "student"),
                or_(UserRole.expires_at.is_(None), UserRole.expires_at > now),
            )
        )
        return db.query(sub.exists()).scalar()

    return uid if (_has_role(True) and not _has_role(False)) else None


def resolve_student_id(student_uuid) -> Optional[int]:
    """users.id «чистого» активного студента по uuid (см. _pure_active_student_id)."""
    uuid_obj = _parse_uuid(student_uuid)
    if uuid_obj is None:
        return None
    with SessionLocal() as db:
        return _pure_active_student_id(db, user_uuid=uuid_obj)


def _results_page(db, user_id: int, page: int, size: int) -> tuple[list[dict], int]:
    """Metadata-страница: uuid/test_title/submitted_at БЕЗ баллов.
    Устойчивая сортировка (submitted_at DESC, id DESC); название — актуальное.
    Фильтров по публикации/статусу/удалению теста нет: история доступна всегда."""
    total = db.query(func.count(TestResult.id)).filter(TestResult.user_id == user_id).scalar() or 0
    rows = (
        db.query(TestResult.uuid, TestResult.submitted_at, Test.title)
        .join(Test, Test.id == TestResult.test_id)
        .filter(TestResult.user_id == user_id)
        .order_by(TestResult.submitted_at.desc(), TestResult.id.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )
    items = [
        {"uuid": str(r.uuid), "test_title": r.title, "submitted_at": r.submitted_at}
        for r in rows
    ]
    return items, int(total)


def _guarded(operation: str, fn):
    """Выполняет fn(db) в одной сессии с санитизацией технических сбоев."""
    with SessionLocal() as db:
        error_class = None
        phase = "read"
        out = None
        try:
            out = fn(db)
        except _Undecryptable:
            error_class, phase = "Undecryptable", "decrypt"
        except SQLAlchemyError as exc:
            error_class = type(exc).__name__
        if error_class is not None:
            try:
                db.rollback()
            except Exception as exc:   # noqa: BLE001 — rollback best-effort
                _diag(operation, "rollback", type(exc).__name__)
            _diag(operation, phase, error_class)
            raise StaffResultsStorageError() from None
    return out


def list_results_for_psychologist(
    psychologist_id: int, student_uuid, page: int, size: int,
) -> Optional[tuple[list[dict], int]]:
    """Список результатов клиента психолога; нет области → None."""
    uuid_obj = _parse_uuid(student_uuid)
    if uuid_obj is None:
        return None

    def _read(db):
        scope = lock_client_scope(db, psychologist_id, client_uuid=uuid_obj)
        if scope is None:
            return None
        return _results_page(db, scope[1], page, size)

    return _guarded("list_psychologist", _read)


def list_results_for_supervisor(
    student_uuid, page: int, size: int,
) -> Optional[tuple[list[dict], int]]:
    """Список результатов «чистого» активного студента; иначе None."""
    uuid_obj = _parse_uuid(student_uuid)
    if uuid_obj is None:
        return None

    def _read(db):
        student_id = _pure_active_student_id(db, user_uuid=uuid_obj)
        if student_id is None:
            return None
        return _results_page(db, student_id, page, size)

    return _guarded("list_supervisor", _read)


def _decrypt_answer(enc: str) -> str:
    text = None
    failed = False
    try:
        text = decrypt_text(enc)
    except Exception:   # noqa: BLE001 — класс и значения не раскрываем
        failed = True
    if failed:
        raise _Undecryptable()   # вне except: без __context__ со значениями
    return text


def _int_or_none(value) -> Optional[int]:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _answers_to_dict(result: TestResult, db) -> dict:
    """
    Ответы прохождения для психолога: ВСЕ вопросы теста в порядке теста
    (question_order, id) + сохранённые ответы. Порядок показа клиенту при
    перемешивании не сохраняется — поэтому order="test_order". Неотвеченный
    вопрос → answered=False. Варианты — только выбранные, по option_order,
    с текстом и медиа; value_score, config, id и ciphertext не отдаются.
    """
    test = db.query(Test.title).filter(Test.id == result.test_id).first()
    questions = (
        db.query(Question)
        .options(
            selectinload(Question.media).selectinload(QuestionMedia.media),
            selectinload(Question.options)
            .selectinload(Option.media).selectinload(OptionMedia.media),
        )
        .filter(Question.test_id == result.test_id)
        .order_by(Question.question_order, Question.id)
        .all()
    )
    answers = (
        db.query(StudentAnswer)
        .filter(StudentAnswer.test_result_id == result.id)
        .order_by(StudentAnswer.id)
        .all()
    )
    by_question: dict[int, StudentAnswer] = {}
    for a in answers:
        by_question.setdefault(a.question_id, a)

    items = []
    for position, q in enumerate(questions, start=1):
        a = by_question.get(q.id)
        chosen_ids: set[int] = set()
        scale_value = None
        free_text = None
        if a is not None:
            if a.option_id is not None:
                chosen_ids.add(a.option_id)
            chosen_ids.update(a.selected_options or [])
            scale_value = a.scale_value
            if a.free_text_answer_enc:
                free_text = _decrypt_answer(a.free_text_answer_enc) or None
        chosen = [
            {"option_text": o.option_text, "media": _option_media_to_list(o.media)}
            for o in sorted(q.options, key=lambda o: (o.option_order, o.id))
            if o.id in chosen_ids
        ]
        cfg = q.config or {}
        is_scale = q.question_type == "scale"
        items.append({
            "position":      position,
            "question_text": q.question_text,
            "question_type": q.question_type or "single_choice",
            "answered":      bool(chosen) or scale_value is not None or bool(free_text),
            "media":         _question_media_to_list(q.media),
            "options":       chosen,
            "scale_value":   scale_value,
            "scale_min":     _int_or_none(cfg.get("min")) if is_scale else None,
            "scale_max":     _int_or_none(cfg.get("max")) if is_scale else None,
            "free_text":     free_text,
        })
    return {
        "result_uuid":  str(result.uuid),
        "test_title":   test.title if test else None,
        "submitted_at": result.submitted_at,
        "order":        "test_order",
        "items":        items,
    }


def read_result_for_staff(
    *, role: str, actor_id: int, result_uuid, with_answers: bool = False,
) -> Optional[dict]:
    """
    {"result_id", "data"} — полный результат (with_answers=False) или ответы
    (with_answers=True, только psychologist) после проверки области; иначе None.

    Проверка — по проекции (id, user_id) результата, БЕЗ чтения баллов; затем
    область роли; только потом чтение содержимого в той же транзакции.
    """
    uuid_obj = _parse_uuid(result_uuid)
    if uuid_obj is None:
        return None
    if with_answers and role != "psychologist":
        raise ValueError("answers are available to psychologist only")

    def _read(db):
        owner = (
            db.query(TestResult.id, TestResult.user_id)
            .filter(TestResult.uuid == uuid_obj)
            .first()
        )
        if owner is None:
            return None
        result_id, owner_id = int(owner.id), int(owner.user_id)
        if role == "psychologist":
            if lock_client_scope(db, actor_id, client_id=owner_id) is None:
                return None
        elif _pure_active_student_id(db, user_id=owner_id) is None:
            return None
        result = db.get(TestResult, result_id)
        data = (_answers_to_dict(result, db) if with_answers
                else _result_to_dict(result, db, staff=True))
        return {"result_id": result_id, "data": data}

    return _guarded("answers" if with_answers else "detail", _read)


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
