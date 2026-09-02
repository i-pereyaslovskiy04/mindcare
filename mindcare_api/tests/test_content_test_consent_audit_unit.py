"""
Stage 4B-5 — no-DB unit-тесты переноса content/test/consent writer'ов на
record_event(): categories/articles/news/tags CRUD, test CRUD, consent accept,
test submit.

Покрывает: registry widening test_* + контракт ролей; fail-closed actor guard
всех 18 writer-функций (guard стоит до SessionLocal — DB не нужна);
actor/target/event mapping репрезентативных flow (mock SessionLocal + spy
record_event); consent new/existing семантику и sanitized context; отсутствие
чувствительных данных в submit-аудите; static-проверки удаления legacy
log_auth_event и helper-модуля. Реальная БД не используется.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError

from app.audit.contracts import AuditStorageError
from app.audit.registry import REGISTRY

import app.categories.storage as cat_storage
import app.articles.storage as art_storage
import app.news.storage as news_storage
import app.tags.storage as tag_storage
import app.tests.storage as tests_storage

ACTOR_ID = 101


def _mock_session(mock_db):
    m = MagicMock()
    m.return_value.__enter__ = MagicMock(return_value=mock_db)
    m.return_value.__exit__ = MagicMock(return_value=False)
    return m


# ══════════════════════════════════════════════════════════════════════════
# 1. Registry contract (no DB, no mocking)
# ══════════════════════════════════════════════════════════════════════════

def test_test_events_widened_to_admin_supervisor():
    # duplicate остаётся admin/supervisor-only (Этап F2: psychologist duplicate
    # не использует — не входит в scope этого блока).
    assert REGISTRY["test_duplicated"].allowed_actor_roles == frozenset(
        {"admin", "supervisor"}
    )


def test_test_crud_events_widened_to_psychologist_stage_f2():
    # Этап F2 (ADR-016): psychologist управляет своими draft/needs_changes тестами
    # через те же storage/audit-пути, что admin/supervisor.
    for name in ("test_created", "test_updated", "test_deleted"):
        assert REGISTRY[name].allowed_actor_roles == frozenset(
            {"admin", "supervisor", "psychologist"}
        ), name


def test_content_events_stay_admin_only():
    for base in ("category", "article", "news", "tag"):
        for op in ("created", "updated", "deleted"):
            name = f"{base}_{op}"
            assert REGISTRY[name].allowed_actor_roles == frozenset({"admin"}), name


def test_student_events_stay_student_only():
    for name in ("test_consent_accepted", "test_submitted"):
        assert REGISTRY[name].allowed_actor_roles == frozenset({"student"}), name


def test_registry_total_count_unchanged():
    # Актуальный счётчик registry: 7 auth + 87 audit = 94.
    assert len(REGISTRY) == 110


def test_content_test_consent_events_entity_types():
    assert REGISTRY["category_created"].entity_type == "category"
    assert REGISTRY["article_created"].entity_type == "article"
    assert REGISTRY["news_created"].entity_type == "news"
    assert REGISTRY["tag_created"].entity_type == "tag"
    assert REGISTRY["test_created"].entity_type == "test"
    assert REGISTRY["test_consent_accepted"].entity_type == "consent_record"
    assert REGISTRY["test_submitted"].entity_type == "test_result"


def test_all_18_events_have_empty_metadata_schema():
    names = [
        f"{b}_{o}" for b in ("category", "article", "news", "tag")
        for o in ("created", "updated", "deleted")
    ] + [
        "test_created", "test_updated", "test_duplicated", "test_deleted",
        "test_consent_accepted", "test_submitted",
    ]
    for name in names:
        assert dict(REGISTRY[name].metadata_schema) == {}, name


# ══════════════════════════════════════════════════════════════════════════
# 2. Fail-closed actor guards (guard стоит до SessionLocal → DB не нужна)
# ══════════════════════════════════════════════════════════════════════════

def test_category_create_requires_actor():
    with pytest.raises(RuntimeError):
        cat_storage.create_category(
            name="X", slug=None, description=None, display_order=0,
            is_active=True, actor_id=None, actor_role="admin",
        )
    with pytest.raises(RuntimeError):
        cat_storage.create_category(
            name="X", slug=None, description=None, display_order=0,
            is_active=True, actor_id=ACTOR_ID, actor_role=None,
        )


def test_category_update_delete_require_actor():
    with pytest.raises(RuntimeError):
        cat_storage.update_category(1, {"name": "X"}, actor_id=None, actor_role="admin")
    with pytest.raises(RuntimeError):
        cat_storage.deactivate_category(1, actor_id=1, actor_role=None)


def test_article_create_requires_actor():
    with pytest.raises(RuntimeError):
        art_storage.create_article(
            title="X", excerpt=None, content=None, cover_image_uuid=None,
            category_ids=[], tag_uuids=[], is_published=False, published_at=None,
            created_by=None, actor_role="admin",
        )
    with pytest.raises(RuntimeError):
        art_storage.create_article(
            title="X", excerpt=None, content=None, cover_image_uuid=None,
            category_ids=[], tag_uuids=[], is_published=False, published_at=None,
            created_by=ACTOR_ID, actor_role=None,
        )


def test_article_update_delete_require_actor():
    with pytest.raises(RuntimeError):
        art_storage.update_article("u", {}, actor_id=None, actor_role="admin")
    with pytest.raises(RuntimeError):
        art_storage.delete_article("u", actor_id=1, actor_role=None)


def test_news_create_update_delete_require_actor():
    with pytest.raises(RuntimeError):
        news_storage.create_news(
            title="X", content=None, cover_image_uuid=None, tag_uuids=[],
            is_published=False, published_at=None, created_by=None, actor_role="admin",
        )
    with pytest.raises(RuntimeError):
        news_storage.update_news("u", {}, actor_id=None, actor_role="admin")
    with pytest.raises(RuntimeError):
        news_storage.delete_news("u", actor_id=1, actor_role=None)


def test_tag_create_update_delete_require_actor():
    with pytest.raises(RuntimeError):
        tag_storage.create_tag("X", actor_id=None, actor_role="admin")
    with pytest.raises(RuntimeError):
        tag_storage.update_tag("u", "X", actor_id=1, actor_role=None)
    with pytest.raises(RuntimeError):
        tag_storage.delete_tag("u", actor_id=None, actor_role="admin")


def test_test_crud_require_actor():
    with pytest.raises(RuntimeError):
        tests_storage.create_test({"title": "X"}, created_by=None, actor_role="admin")
    with pytest.raises(RuntimeError):
        tests_storage.create_test({"title": "X"}, created_by=1, actor_role=None)
    with pytest.raises(RuntimeError):
        tests_storage.update_test("u", {}, actor_id=None, actor_role="admin")
    with pytest.raises(RuntimeError):
        tests_storage.duplicate_test("u", created_by=1, actor_role=None)
    with pytest.raises(RuntimeError):
        tests_storage.delete_test("u", actor_id=None, actor_role="admin")


def test_consent_and_submit_require_actor():
    with pytest.raises(RuntimeError):
        tests_storage.save_consent_record(1, 2, actor_role=None)
    with pytest.raises(RuntimeError):
        tests_storage.save_result(1, "u", {}, [], actor_role=None)


# ══════════════════════════════════════════════════════════════════════════
# 3. Mapping: category create (представитель content-flow)
# ══════════════════════════════════════════════════════════════════════════

def test_category_create_maps_event_actor_target(monkeypatch):
    calls = []
    monkeypatch.setattr(cat_storage, "record_event", lambda **kw: calls.append(kw))

    db = MagicMock(name="db")
    db.query.return_value.filter.return_value.scalar.return_value = None  # no slug conflict
    cat_cls = MagicMock(name="Category")   # MagicMock, чтобы Category.slug/.id в query работали
    cat_cls.return_value = SimpleNamespace(id=777)
    monkeypatch.setattr(cat_storage, "SessionLocal", _mock_session(db))
    monkeypatch.setattr(cat_storage, "Category", cat_cls)
    monkeypatch.setattr(cat_storage, "get_category_by_id", lambda cid: {"id": cid})

    cat_storage.create_category(
        name="X", slug=None, description=None, display_order=0, is_active=True,
        actor_id=ACTOR_ID, actor_role="admin", ip="203.0.113.7", user_agent="ua",
    )

    assert len(calls) == 1
    kw = calls[0]
    assert kw["event"] == "category_created"
    assert kw["actor"].user_id == ACTOR_ID and kw["actor"].role == "admin"
    assert kw["target"].entity_type == "category"
    assert kw["target"].entity_id == 777
    assert kw["metadata"] == {}
    assert kw["db"] is db
    db.commit.assert_called_once()


def test_category_create_audit_failure_prevents_commit(monkeypatch):
    def _boom(**kw):
        raise AuditStorageError("audit storage failure for category_created")
    monkeypatch.setattr(cat_storage, "record_event", _boom)

    db = MagicMock(name="db")
    db.query.return_value.filter.return_value.scalar.return_value = None
    cat_cls = MagicMock(name="Category")
    cat_cls.return_value = SimpleNamespace(id=1)
    monkeypatch.setattr(cat_storage, "SessionLocal", _mock_session(db))
    monkeypatch.setattr(cat_storage, "Category", cat_cls)
    monkeypatch.setattr(cat_storage, "get_category_by_id", lambda cid: {"id": cid})

    with pytest.raises(AuditStorageError):
        cat_storage.create_category(
            name="X", slug=None, description=None, display_order=0,
            is_active=True, actor_id=ACTOR_ID, actor_role="admin",
        )
    db.commit.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════
# 3b. IntegrityError separation: business flush → ValueError конфликт;
#     audit/commit IntegrityError НЕ преобразуется в конфликт
# ══════════════════════════════════════════════════════════════════════════

def _integrity_error() -> IntegrityError:
    return IntegrityError("stmt", "params", Exception("orig"))


def test_category_create_business_flush_integrity_becomes_valueerror(monkeypatch):
    calls = []
    monkeypatch.setattr(cat_storage, "record_event", lambda **kw: calls.append(kw))

    db = MagicMock(name="db")
    db.query.return_value.filter.return_value.scalar.return_value = None
    db.flush.side_effect = _integrity_error()   # business INSERT конфликт
    cat_cls = MagicMock(name="Category")
    cat_cls.return_value = SimpleNamespace(id=1)
    monkeypatch.setattr(cat_storage, "SessionLocal", _mock_session(db))
    monkeypatch.setattr(cat_storage, "Category", cat_cls)

    with pytest.raises(ValueError, match="уже используется"):
        cat_storage.create_category(
            name="X", slug=None, description=None, display_order=0,
            is_active=True, actor_id=ACTOR_ID, actor_role="admin",
        )
    assert calls == []                 # audit не стейджился
    db.commit.assert_not_called()


def test_category_create_audit_commit_integrity_not_mapped_to_conflict(monkeypatch):
    # flush (business) ок; commit падает IntegrityError (напр. от audit-строки) —
    # НЕ должен превратиться в ValueError конфликта slug, всплывает как есть.
    monkeypatch.setattr(cat_storage, "record_event", lambda **kw: None)

    db = MagicMock(name="db")
    db.query.return_value.filter.return_value.scalar.return_value = None
    db.commit.side_effect = _integrity_error()
    cat_cls = MagicMock(name="Category")
    cat_cls.return_value = SimpleNamespace(id=1)
    monkeypatch.setattr(cat_storage, "SessionLocal", _mock_session(db))
    monkeypatch.setattr(cat_storage, "Category", cat_cls)

    with pytest.raises(IntegrityError):
        cat_storage.create_category(
            name="X", slug=None, description=None, display_order=0,
            is_active=True, actor_id=ACTOR_ID, actor_role="admin",
        )


def test_category_update_business_flush_integrity_becomes_valueerror(monkeypatch):
    calls = []
    monkeypatch.setattr(cat_storage, "record_event", lambda **kw: calls.append(kw))

    db = MagicMock(name="db")
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(
        id=5, name="n", slug="s", description=None, display_order=0, is_active=True,
    )
    db.query.return_value.filter.return_value.scalar.return_value = None  # no slug conflict
    db.flush.side_effect = _integrity_error()
    monkeypatch.setattr(cat_storage, "SessionLocal", _mock_session(db))

    with pytest.raises(ValueError, match="Конфликт данных"):
        cat_storage.update_category(
            5, {"name": "New"}, actor_id=ACTOR_ID, actor_role="admin",
        )
    assert calls == []
    db.commit.assert_not_called()


def test_tag_create_business_flush_integrity_becomes_valueerror(monkeypatch):
    calls = []
    monkeypatch.setattr(tag_storage, "record_event", lambda **kw: calls.append(kw))

    db = MagicMock(name="db")
    db.query.return_value.filter.return_value.first.return_value = None  # no name conflict
    db.flush.side_effect = _integrity_error()
    tag_cls = MagicMock(name="Tag")
    tag_cls.return_value = SimpleNamespace(id=1)
    monkeypatch.setattr(tag_storage, "SessionLocal", _mock_session(db))
    monkeypatch.setattr(tag_storage, "Tag", tag_cls)

    with pytest.raises(ValueError, match="уже существует"):
        tag_storage.create_tag("X", actor_id=ACTOR_ID, actor_role="admin")
    assert calls == []
    db.commit.assert_not_called()


def test_tag_create_audit_commit_integrity_not_mapped_to_conflict(monkeypatch):
    monkeypatch.setattr(tag_storage, "record_event", lambda **kw: None)

    db = MagicMock(name="db")
    db.query.return_value.filter.return_value.first.return_value = None
    db.commit.side_effect = _integrity_error()
    tag_cls = MagicMock(name="Tag")
    tag_cls.return_value = SimpleNamespace(id=1)
    monkeypatch.setattr(tag_storage, "SessionLocal", _mock_session(db))
    monkeypatch.setattr(tag_storage, "Tag", tag_cls)

    with pytest.raises(IntegrityError):
        tag_storage.create_tag("X", actor_id=ACTOR_ID, actor_role="admin")


def test_tag_update_business_flush_integrity_becomes_valueerror(monkeypatch):
    calls = []
    monkeypatch.setattr(tag_storage, "record_event", lambda **kw: calls.append(kw))

    existing = SimpleNamespace(id=7, name="old")
    db = MagicMock(name="db")
    # первый .first() → сам тег; conflict-query .first() → None
    db.query.return_value.filter.return_value.first.side_effect = [existing, None]
    db.flush.side_effect = _integrity_error()
    monkeypatch.setattr(tag_storage, "SessionLocal", _mock_session(db))

    with pytest.raises(ValueError, match="уже существует"):
        tag_storage.update_tag(
            "00000000-0000-0000-0000-000000000001", "New",
            actor_id=ACTOR_ID, actor_role="admin",
        )
    assert calls == []
    db.commit.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════
# 3c. Failure-injection: test CRUD / consent / submit — record_event падает
# ══════════════════════════════════════════════════════════════════════════

def test_create_test_audit_failure_propagates_no_commit(monkeypatch):
    calls = []

    def _boom(**kw):
        calls.append(kw)
        raise AuditStorageError("audit storage failure for test_created")
    monkeypatch.setattr(tests_storage, "record_event", _boom)

    db = MagicMock(name="db")
    test_cls = MagicMock(name="Test")
    test_cls.return_value = SimpleNamespace(id=1)
    monkeypatch.setattr(tests_storage, "Test", test_cls)
    monkeypatch.setattr(tests_storage, "_sync_categories", lambda *a, **k: None)
    monkeypatch.setattr(tests_storage, "_sync_tags", lambda *a, **k: None)
    monkeypatch.setattr(tests_storage, "_replace_questions", lambda *a, **k: None)
    monkeypatch.setattr(tests_storage, "_replace_interpretations", lambda *a, **k: None)
    monkeypatch.setattr(tests_storage, "SessionLocal", _mock_session(db))

    with pytest.raises(AuditStorageError):
        tests_storage.create_test(
            {"title": "X"}, created_by=7, actor_role="admin",
        )
    assert len(calls) == 1          # ровно одна попытка, без повторной записи
    db.commit.assert_not_called()


def test_save_consent_record_audit_failure_propagates_no_commit(monkeypatch):
    calls = []

    def _boom(**kw):
        calls.append(kw)
        raise AuditStorageError("audit storage failure for test_consent_accepted")
    monkeypatch.setattr(tests_storage, "record_event", _boom)

    db = MagicMock(name="db")
    db.query.return_value.filter.return_value.first.return_value = None  # new record
    rec_cls = MagicMock(name="ConsentRecord")
    rec_cls.return_value = SimpleNamespace(id=555)
    monkeypatch.setattr(tests_storage, "ConsentRecord", rec_cls)
    monkeypatch.setattr(tests_storage, "SessionLocal", _mock_session(db))

    with pytest.raises(AuditStorageError):
        tests_storage.save_consent_record(42, 7, actor_role="student")
    assert len(calls) == 1
    db.commit.assert_not_called()


def test_save_result_audit_failure_propagates_no_commit(monkeypatch):
    calls = []

    def _boom(**kw):
        calls.append(kw)
        raise AuditStorageError("audit storage failure for test_submitted")
    monkeypatch.setattr(tests_storage, "record_event", _boom)

    db = MagicMock(name="db")
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(
        id=1, version=1,
    )
    res_cls = MagicMock(name="TestResult")
    res_cls.return_value = SimpleNamespace(id=888)
    monkeypatch.setattr(tests_storage, "TestResult", res_cls)
    monkeypatch.setattr(tests_storage, "SessionLocal", _mock_session(db))

    with pytest.raises(AuditStorageError):
        tests_storage.save_result(
            42, "00000000-0000-0000-0000-000000000000",
            {"total_score": 1, "scales": []}, [], actor_role="student",
        )
    assert len(calls) == 1
    db.commit.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════
# 4. Consent: new vs existing семантика + sanitized context
# ══════════════════════════════════════════════════════════════════════════

def test_consent_new_record_maps_and_shares_sanitized_context(monkeypatch):
    calls = []
    monkeypatch.setattr(tests_storage, "record_event", lambda **kw: calls.append(kw))

    db = MagicMock(name="db")
    db.query.return_value.filter.return_value.first.return_value = None  # new
    created = MagicMock(name="ConsentRecord")
    created.id = 555
    ctor = MagicMock(return_value=created)
    monkeypatch.setattr(tests_storage, "ConsentRecord", ctor)
    monkeypatch.setattr(tests_storage, "SessionLocal", _mock_session(db))

    rid = tests_storage.save_consent_record(
        user_id=42, consent_id=7, ip="not-an-ip", user_agent="x" * 600,
        actor_role="student",
    )

    assert rid == 555
    kw = calls[0]
    assert kw["event"] == "test_consent_accepted"
    assert kw["actor"].user_id == 42 and kw["actor"].role == "student"
    assert kw["target"].entity_type == "consent_record"
    assert kw["target"].entity_id == 555
    assert kw["metadata"] == {}
    # sanitized: invalid ip / oversized UA → None и в audit, и в ConsentRecord
    assert kw["context"].ip_address is None
    assert kw["context"].user_agent is None
    ctor_kwargs = ctor.call_args.kwargs
    assert ctor_kwargs["ip_address"] is None
    assert ctor_kwargs["user_agent"] is None


def test_consent_repeat_reuses_id_without_overwriting_original(monkeypatch):
    calls = []
    monkeypatch.setattr(tests_storage, "record_event", lambda **kw: calls.append(kw))

    existing = SimpleNamespace(
        id=999, accepted=False,
        ip_address="10.0.0.1", user_agent="orig-ua", accepted_at="t0",
    )
    db = MagicMock(name="db")
    db.query.return_value.filter.return_value.first.return_value = existing
    monkeypatch.setattr(tests_storage, "SessionLocal", _mock_session(db))

    rid = tests_storage.save_consent_record(
        user_id=42, consent_id=7, ip="203.0.113.9", user_agent="new-ua",
        actor_role="student",
    )

    assert rid == 999
    assert existing.accepted is True            # идемпотентно
    assert existing.ip_address == "10.0.0.1"    # НЕ перезаписан
    assert existing.user_agent == "orig-ua"     # НЕ перезаписан
    assert existing.accepted_at == "t0"         # НЕ перезаписан
    assert calls[0]["target"].entity_id == 999


# ══════════════════════════════════════════════════════════════════════════
# 5. Submit: target = TestResult.id, metadata пуста, нет чувствительных данных
# ══════════════════════════════════════════════════════════════════════════

def test_submit_maps_target_result_id_no_sensitive_data(monkeypatch):
    calls = []
    monkeypatch.setattr(tests_storage, "record_event", lambda **kw: calls.append(kw))

    db = MagicMock(name="db")
    fake_test = SimpleNamespace(id=1, version=3)
    db.query.return_value.filter.return_value.first.return_value = fake_test
    fake_result = MagicMock(name="TestResult")
    fake_result.id = 888
    monkeypatch.setattr(tests_storage, "TestResult", lambda **kw: fake_result)
    monkeypatch.setattr(tests_storage, "_result_to_dict", lambda r, db: {"uuid": "r"})
    monkeypatch.setattr(tests_storage, "SessionLocal", _mock_session(db))
    monkeypatch.setattr(tests_storage, "encrypt_text", lambda t: "enc:v1:x")

    computed = {
        "total_score": 27, "max_possible": 27, "scoring_used": "sum",
        "recommendations": "секретная рекомендация", "scales": [],
    }
    answers = [{"question_id": 1, "free_text_answer": "мне тревожно секрет"}]

    tests_storage.save_result(
        user_id=42, test_uuid="00000000-0000-0000-0000-000000000000",
        computed=computed, answers=answers, actor_role="student",
    )

    assert len(calls) == 1
    kw = calls[0]
    assert kw["event"] == "test_submitted"
    assert kw["actor"].user_id == 42 and kw["actor"].role == "student"
    assert kw["target"].entity_type == "test_result"
    assert kw["target"].entity_id == 888
    assert kw["metadata"] == {}
    # Детерминированная проекция ТОЛЬКО audit payload — без db (MagicMock, чей
    # repr содержит адрес памяти и случайно ловит "27" и т.п.).
    payload = {
        "event": kw["event"],
        "actor": repr(kw["actor"]),
        "target": repr(kw["target"]),
        "outcome": repr(kw["outcome"]),
        "metadata": kw["metadata"],
        "context": repr(kw["context"]),
    }
    blob = repr(payload)
    for sensitive in ("тревожно", "секрет", "рекомендаци", "27", "enc:v1:"):
        assert sensitive not in blob


# ══════════════════════════════════════════════════════════════════════════
# 6. Test duplicate: target = новая копия (не source) — через spy на реальном
#    объекте копии, минимальный мок дерева
# ══════════════════════════════════════════════════════════════════════════

def test_duplicate_target_is_new_copy(monkeypatch):
    calls = []
    monkeypatch.setattr(tests_storage, "record_event", lambda **kw: calls.append(kw))

    src = SimpleNamespace(
        id=1, title="Src", description="d", scoring="sum", max_score=6,
        time_limit_min=None, shuffle_questions=False, shuffle_options=False,
        questions=[], interpretations=[],
    )
    db = MagicMock(name="db")
    db.query.return_value.filter.return_value.first.return_value = src
    db.query.return_value.filter.return_value.all.return_value = []
    copy = MagicMock(name="copy")
    copy.id = 4242
    test_cls = MagicMock(name="Test")   # MagicMock: и Test(...), и Test.uuid в query
    test_cls.return_value = copy
    monkeypatch.setattr(tests_storage, "Test", test_cls)
    monkeypatch.setattr(tests_storage, "_test_to_dict", lambda t, db: {"uuid": "c"})
    monkeypatch.setattr(tests_storage, "SessionLocal", _mock_session(db))

    tests_storage.duplicate_test(
        "00000000-0000-0000-0000-000000000000", created_by=7, actor_role="supervisor",
    )

    assert len(calls) == 1
    kw = calls[0]
    assert kw["event"] == "test_duplicated"
    assert kw["actor"].user_id == 7 and kw["actor"].role == "supervisor"
    assert kw["target"].entity_type == "test"
    assert kw["target"].entity_id == 4242   # copy.id, НЕ src.id (1)


# ══════════════════════════════════════════════════════════════════════════
# 7. Static: legacy log_auth_event удалён из мигрированных route-файлов;
#    helper-модуль удалён
# ══════════════════════════════════════════════════════════════════════════

_APP = Path(__file__).resolve().parents[1] / "app"


def _src(rel: str) -> str:
    return (_APP / rel).read_text(encoding="utf-8")


def test_migrated_routes_have_no_log_auth_event():
    for rel in (
        "categories/routes_admin.py", "articles/routes_admin.py",
        "news/routes_admin.py", "tags/routes_admin.py",
        "tests/routes_admin.py", "tests/routes.py",
    ):
        src = _src(rel)
        assert "log_auth_event" not in src, rel
        assert "from app.auth import audit" not in src, rel
        assert "from app.auth.audit" not in src, rel


def test_no_dynamic_legacy_event_strings():
    for rel, prefixes in (
        ("categories/routes_admin.py", ("admin_create_category", "admin_update_category")),
        ("articles/routes_admin.py", ("admin_create_article",)),
        ("news/routes_admin.py", ("admin_create_news",)),
        ("tags/routes_admin.py", ("admin_create_tag",)),
        ("tests/routes_admin.py", ("admin_create_test", "admin_duplicate_test")),
        ("tests/routes.py", ("test_consent_accept", "test_submit:")),
    ):
        src = _src(rel)
        for p in prefixes:
            assert p not in src, f"{rel}:{p}"


def test_legacy_audit_helper_module_removed():
    with pytest.raises(ModuleNotFoundError):
        import app.auth.audit  # noqa: F401


def test_no_log_auth_event_anywhere_in_app():
    hits = []
    for path in _APP.rglob("*.py"):
        if "log_auth_event(" in path.read_text(encoding="utf-8"):
            hits.append(str(path))
    assert hits == []
