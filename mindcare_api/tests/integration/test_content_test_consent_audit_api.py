"""
Stage 4B-5 — gated integration: content/test/consent writers через record_event().
Запуск ТОЛЬКО через Stage 1 isolated runner; dev/prod запрещены.

Проверяет:
  - category/article/news/tag create → ровно 1 audit-строка в audit_log,
    entity_id == реальный int id, outcome=success, metadata={}, description None,
    actor=admin;
  - test create/update/duplicate/delete от admin; test create от supervisor
    (actor_role="supervisor", не 500 — registry widened);
  - duplicate target == id новой копии (не source);
  - consent accept target == ConsentRecord.id; repeat accept → вторая строка на
    тот же id, исходные accepted_at/ip/ua не изменены;
  - submit target == TestResult.id, metadata/description без ответов/score/free-text;
  - auth_log не получает новых legacy admin_*/test_* строк (before/after count);
  - invalid IP/UA не даёт 500 и не сохраняется raw.

Append-only audit-таблицы не очищаются — используются entity_id и before/after.
"""
import uuid as _uuid

from app.core.normalization import normalize_email
from app.db.session import SessionLocal
from app.db.models import (
    AuditLog, AuthLog, Article, News, Tag, Test,
    ConsentRecord, TestResult, User,
)
from tests.integration.conftest import (
    ALLOWED_TEST_DOMAIN, create_multi_role_user, create_test_user,
)

PASSWORD = "SecurePass42!"


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _audit_rows(event_type, entity_type, entity_id):
    with SessionLocal() as db:
        rows = (
            db.query(AuditLog)
            .filter(
                AuditLog.event_type == event_type,
                AuditLog.entity_type == entity_type,
                AuditLog.entity_id == entity_id,
            )
            .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
            .all()
        )
        for r in rows:
            db.expunge(r)
        return rows


def _auth_log_count(prefix):
    with SessionLocal() as db:
        return (
            db.query(AuthLog)
            .filter(AuthLog.event.like(f"{prefix}%"))
            .count()
        )


def _assert_success_contract(row, entity_type, entity_id, actor_id, actor_role):
    assert row.entity_type == entity_type
    assert row.entity_id == entity_id
    assert row.outcome == "success"
    assert row.failure_reason_code is None
    assert row.description is None
    assert (row.log_metadata or {}) == {}
    assert row.user_id == actor_id
    assert row.user_role == actor_role


# ── content: category / article / news / tag ─────────────────────────────────

def test_category_create_update_delete_writes_audit(client):
    token, admin_id, _ = create_multi_role_user(client, ["admin"])
    before = _auth_log_count("admin_create_category")
    name = f"IntegCat {_uuid.uuid4().hex[:8]}"
    r = client.post("/api/admin/categories", headers=_auth(token), json={"name": name})
    assert r.status_code == 201, r.text
    cid = r.json()["id"]

    rows = _audit_rows("category_created", "category", cid)
    assert len(rows) == 1
    _assert_success_contract(rows[0], "category", cid, admin_id, "admin")

    r = client.patch(
        f"/api/admin/categories/{cid}", headers=_auth(token),
        json={"name": name + " ред"},
    )
    assert r.status_code == 200, r.text
    urows = _audit_rows("category_updated", "category", cid)
    assert len(urows) == 1
    _assert_success_contract(urows[0], "category", cid, admin_id, "admin")

    r = client.delete(f"/api/admin/categories/{cid}", headers=_auth(token))
    assert r.status_code == 204, r.text
    drows = _audit_rows("category_deleted", "category", cid)
    assert len(drows) == 1
    _assert_success_contract(drows[0], "category", cid, admin_id, "admin")

    # legacy auth_log не пополнился (before/after, не глобальный ноль)
    assert _auth_log_count("admin_create_category") == before


def test_article_create_update_delete_writes_audit(client):
    token, admin_id, _ = create_multi_role_user(client, ["admin"])
    title = f"IntegArt {_uuid.uuid4().hex[:8]}"
    r = client.post("/api/admin/articles", headers=_auth(token), json={"title": title})
    assert r.status_code == 201, r.text
    art_uuid = r.json()["uuid"]
    with SessionLocal() as db:
        aid = db.query(Article.id).filter(Article.uuid == _uuid.UUID(art_uuid)).scalar()

    crows = _audit_rows("article_created", "article", aid)
    assert len(crows) == 1
    _assert_success_contract(crows[0], "article", aid, admin_id, "admin")

    r = client.patch(
        f"/api/admin/articles/{art_uuid}", headers=_auth(token),
        json={"title": title + " ред"},
    )
    assert r.status_code == 200, r.text
    urows = _audit_rows("article_updated", "article", aid)
    assert len(urows) == 1
    _assert_success_contract(urows[0], "article", aid, admin_id, "admin")

    r = client.delete(f"/api/admin/articles/{art_uuid}", headers=_auth(token))
    assert r.status_code == 204, r.text
    rows = _audit_rows("article_deleted", "article", aid)
    assert len(rows) == 1
    _assert_success_contract(rows[0], "article", aid, admin_id, "admin")


def test_news_create_update_delete_writes_audit(client):
    token, admin_id, _ = create_multi_role_user(client, ["admin"])
    title = f"IntegNews {_uuid.uuid4().hex[:8]}"
    r = client.post("/api/admin/news", headers=_auth(token), json={"title": title})
    assert r.status_code == 201, r.text
    news_uuid = r.json()["uuid"]
    with SessionLocal() as db:
        nid = db.query(News.id).filter(News.uuid == _uuid.UUID(news_uuid)).scalar()

    rows = _audit_rows("news_created", "news", nid)
    assert len(rows) == 1
    _assert_success_contract(rows[0], "news", nid, admin_id, "admin")

    r = client.patch(
        f"/api/admin/news/{news_uuid}", headers=_auth(token),
        json={"title": title + " ред"},
    )
    assert r.status_code == 200, r.text
    urows = _audit_rows("news_updated", "news", nid)
    assert len(urows) == 1
    _assert_success_contract(urows[0], "news", nid, admin_id, "admin")

    r = client.delete(f"/api/admin/news/{news_uuid}", headers=_auth(token))
    assert r.status_code == 204, r.text
    drows = _audit_rows("news_deleted", "news", nid)
    assert len(drows) == 1
    _assert_success_contract(drows[0], "news", nid, admin_id, "admin")


def test_tag_create_update_delete_writes_audit(client):
    token, admin_id, _ = create_multi_role_user(client, ["admin"])
    name = f"Integtag{_uuid.uuid4().hex[:8]}"
    r = client.post("/api/admin/tags/", headers=_auth(token), json={"name": name})
    assert r.status_code == 201, r.text
    tag_uuid = r.json()["uuid"]
    with SessionLocal() as db:
        tid = db.query(Tag.id).filter(Tag.uuid == _uuid.UUID(tag_uuid)).scalar()

    rows = _audit_rows("tag_created", "tag", tid)
    assert len(rows) == 1
    _assert_success_contract(rows[0], "tag", tid, admin_id, "admin")

    r = client.patch(
        f"/api/admin/tags/{tag_uuid}", headers=_auth(token),
        json={"name": name + "ред"},
    )
    assert r.status_code == 200, r.text
    urows = _audit_rows("tag_updated", "tag", tid)
    assert len(urows) == 1
    _assert_success_contract(urows[0], "tag", tid, admin_id, "admin")

    # HARD delete: тег физически удаляется, но audit-строка остаётся (entity_id
    # — просто int, без FK на tag).
    r = client.delete(f"/api/admin/tags/{tag_uuid}", headers=_auth(token))
    assert r.status_code == 204, r.text
    with SessionLocal() as db:
        assert db.query(Tag.id).filter(Tag.id == tid).scalar() is None  # тег удалён
    drows = _audit_rows("tag_deleted", "tag", tid)
    assert len(drows) == 1                                              # audit цел
    _assert_success_contract(drows[0], "tag", tid, admin_id, "admin")


# ── test CRUD: admin + supervisor ────────────────────────────────────────────

_TEST_BODY = {
    "title": None,  # set per-call
    "description": "d", "scoring": "sum", "max_score": 3,
    "time_limit_min": None, "is_active": True,
    "category_ids": [], "tag_uuids": [],
    "questions": [{
        "question_text": "Q1", "question_order": 1, "question_type": "single_choice",
        "is_required": True, "config": {},
        "options": [{"option_text": "нет", "option_order": 0, "value_score": 0},
                    {"option_text": "да", "option_order": 1, "value_score": 3}],
    }],
    "interpretations": [
        {"scale_name": None, "min_score": 0, "max_score": 1, "label": "L", "recommendation": "r"},
        {"scale_name": None, "min_score": 2, "max_score": 3, "label": "H", "recommendation": "r"},
    ],
}


def _create_test(client, token, title):
    body = {**_TEST_BODY, "title": title}
    return client.post("/api/admin/tests", headers=_auth(token), json=body)


def _test_id(test_uuid):
    with SessionLocal() as db:
        return db.query(Test.id).filter(Test.uuid == _uuid.UUID(test_uuid)).scalar()


def test_test_create_by_admin_writes_audit(client):
    token, admin_id, _ = create_multi_role_user(client, ["admin"])
    r = _create_test(client, token, f"IntegTest {_uuid.uuid4().hex[:8]}")
    assert r.status_code == 201, r.text
    tid = _test_id(r.json()["uuid"])
    rows = _audit_rows("test_created", "test", tid)
    assert len(rows) == 1
    _assert_success_contract(rows[0], "test", tid, admin_id, "admin")


def test_test_create_by_supervisor_not_500_actor_supervisor(client):
    # registry widened {admin,supervisor}: supervisor не даёт AuditError→500.
    token, sup_id, _ = create_multi_role_user(client, ["supervisor"])
    r = _create_test(client, token, f"IntegTestSup {_uuid.uuid4().hex[:8]}")
    assert r.status_code == 201, r.text
    tid = _test_id(r.json()["uuid"])
    rows = _audit_rows("test_created", "test", tid)
    assert len(rows) == 1
    _assert_success_contract(rows[0], "test", tid, sup_id, "supervisor")


def test_test_update_writes_audit(client):
    token, admin_id, _ = create_multi_role_user(client, ["admin"])
    r = _create_test(client, token, f"IntegUpd {_uuid.uuid4().hex[:8]}")
    assert r.status_code == 201, r.text
    test_uuid = r.json()["uuid"]
    tid = _test_id(test_uuid)

    # metadata-only правка (без questions) разрешена и без результатов.
    r = client.patch(
        f"/api/admin/tests/{test_uuid}", headers=_auth(token),
        json={"title": "IntegUpd переименован"},
    )
    assert r.status_code == 200, r.text
    rows = _audit_rows("test_updated", "test", tid)
    assert len(rows) == 1
    _assert_success_contract(rows[0], "test", tid, admin_id, "admin")


def test_test_duplicate_target_is_new_copy(client):
    token, admin_id, _ = create_multi_role_user(client, ["admin"])
    r = _create_test(client, token, f"IntegDup {_uuid.uuid4().hex[:8]}")
    assert r.status_code == 201, r.text
    src_uuid = r.json()["uuid"]
    src_id = _test_id(src_uuid)

    r = client.post(f"/api/admin/tests/{src_uuid}/duplicate", headers=_auth(token))
    assert r.status_code == 201, r.text
    copy_id = _test_id(r.json()["uuid"])
    assert copy_id != src_id

    rows = _audit_rows("test_duplicated", "test", copy_id)
    assert len(rows) == 1          # target — копия
    assert _audit_rows("test_duplicated", "test", src_id) == []  # не source
    _assert_success_contract(rows[0], "test", copy_id, admin_id, "admin")


def test_test_delete_writes_audit(client):
    token, admin_id, _ = create_multi_role_user(client, ["admin"])
    r = _create_test(client, token, f"IntegDel {_uuid.uuid4().hex[:8]}")
    test_uuid = r.json()["uuid"]
    tid = _test_id(test_uuid)
    r = client.delete(f"/api/admin/tests/{test_uuid}", headers=_auth(token))
    assert r.status_code == 204, r.text
    rows = _audit_rows("test_deleted", "test", tid)
    assert len(rows) == 1
    _assert_success_contract(rows[0], "test", tid, admin_id, "admin")


# ── student: consent + submit ────────────────────────────────────────────────

def _student(client):
    email = f"integ_ctc_stu_{_uuid.uuid4().hex[:10]}@{ALLOWED_TEST_DOMAIN}"
    create_test_user(email)
    r = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        uid = db.query(User.id).filter(User.email == normalize_email(email)).scalar()
    return r.json()["session_token"], uid


def _consent_records(uid):
    with SessionLocal() as db:
        rows = (
            db.query(ConsentRecord)
            .filter(ConsentRecord.user_id == uid)
            .order_by(ConsentRecord.id.asc())
            .all()
        )
        for r in rows:
            db.expunge(r)
        return rows


def test_consent_accept_target_and_repeat_semantics(client):
    tok, uid = _student(client)
    r = client.post("/api/tests/consent/accept", headers=_auth(tok))
    assert r.status_code == 200, r.text

    recs = _consent_records(uid)
    assert len(recs) == 1
    rec = recs[0]
    rows = _audit_rows("test_consent_accepted", "consent_record", rec.id)
    assert len(rows) == 1
    _assert_success_contract(rows[0], "consent_record", rec.id, uid, "student")
    orig_accepted_at, orig_ip, orig_ua = rec.accepted_at, rec.ip_address, rec.user_agent

    # повторный accept → вторая audit-строка на тот же id; исходная запись цела
    r2 = client.post("/api/tests/consent/accept", headers=_auth(tok))
    assert r2.status_code == 200, r2.text
    recs2 = _consent_records(uid)
    assert len(recs2) == 1                       # новая ConsentRecord не создаётся
    assert recs2[0].accepted_at == orig_accepted_at
    assert recs2[0].ip_address == orig_ip
    assert recs2[0].user_agent == orig_ua

    # обе строки (упорядоченные) — полный success-контракт, тот же
    # ConsentRecord.id и actor student.
    both = _audit_rows("test_consent_accepted", "consent_record", rec.id)
    assert len(both) == 2
    for row in both:
        _assert_success_contract(row, "consent_record", rec.id, uid, "student")


def test_submit_target_is_result_no_sensitive_data(client):
    admin_tok, _, _ = create_multi_role_user(client, ["admin"])
    r = _create_test(client, admin_tok, f"IntegSubmit {_uuid.uuid4().hex[:8]}")
    test_uuid = r.json()["uuid"]
    q = r.json()["questions"][0]

    legacy_before = _auth_log_count("test_submit")
    tok, uid = _student(client)
    client.post("/api/tests/consent/accept", headers=_auth(tok))
    r = client.post(
        f"/api/tests/{test_uuid}/submit", headers=_auth(tok),
        json={"answers": [{"question_id": q["id"], "option_id": q["options"][1]["id"]}]},
    )
    assert r.status_code == 201, r.text
    with SessionLocal() as db:
        rid = db.query(TestResult.id).filter(
            TestResult.uuid == _uuid.UUID(r.json()["uuid"])
        ).scalar()

    rows = _audit_rows("test_submitted", "test_result", rid)
    assert len(rows) == 1
    row = rows[0]
    _assert_success_contract(row, "test_result", rid, uid, "student")
    # sensitive data (ответы/score/free-text) не попадают: metadata пуста,
    # description None (гарантировано контрактом выше) — блоб детерминирован.
    assert f"{row.log_metadata} {row.description}" == "{} None"
    assert _auth_log_count("test_submit") == legacy_before   # no new legacy row


# ── malformed IP/UA не даёт 500 и не сохраняется raw ─────────────────────────

def test_malformed_ip_ua_content_create_not_500(client):
    from fastapi.testclient import TestClient
    from app.main import app

    token, _, _ = create_multi_role_user(client, ["admin"])
    bad = TestClient(app, client=("not-an-ip", 12345))
    name = f"IntegBadCtx {_uuid.uuid4().hex[:8]}"
    r = bad.post(
        "/api/admin/categories",
        headers={"Authorization": f"Bearer {token}", "User-Agent": "x" * 600},
        json={"name": name},
    )
    assert r.status_code == 201, r.text   # не 500
    cid = r.json()["id"]
    rows = _audit_rows("category_created", "category", cid)
    assert len(rows) == 1
    assert rows[0].ip_address is None
    assert rows[0].user_agent is None
