"""Demo seed: реальный storage/API и аудит на одноразовой PostgreSQL-БД runner'а."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

import seed_demo_materials as seed
from app.articles import storage
from app.db.models import Article, AuditLog, Category, DataChangeLog, Role, Tag, User, UserRole
from app.db.session import SessionLocal
from tests.integration.lock_helpers import Gate, run_in_thread, wait_for_lock_waiter


@pytest.fixture
def sandbox(client, monkeypatch):
    monkeypatch.setattr(seed.settings, "ENV", "test")
    titles = [item["title"] for item in seed.DEMO_MATERIALS]
    with SessionLocal() as db:
        author = User(full_name="Synthetic seed author",
                      email=f"integ_seed_{uuid.uuid4().hex}@example.com", is_active=True)
        db.add(author)
        db.flush()
        role = db.query(Role).filter(Role.name == "admin").one()
        db.add(UserRole(user_id=author.id, role_id=role.id))
        db.commit()
        author_id = author.id
    yield author_id
    with SessionLocal() as db:
        db.query(Article).filter(Article.title.in_(titles)).delete(synchronize_session=False)
        db.commit()


def articles():
    with SessionLocal() as db:
        rows = db.query(Article).filter(
            Article.title.in_([item["title"] for item in seed.DEMO_MATERIALS])
        ).all()
        db.expunge_all()
        return rows


def events():
    ids = [row.id for row in articles()]
    with SessionLocal() as db:
        rows = db.query(AuditLog).filter(
            AuditLog.entity_type == "article", AuditLog.entity_id.in_(ids)
        ).order_by(AuditLog.id).all()
        db.expunge_all()
        return rows


def create_orphan(author_id, item=None, **overrides):
    item = item or seed.DEMO_MATERIALS[-1]
    data = dict(title=item["title"], excerpt=item["excerpt"], content=item["content"],
                cover_image_uuid=None, category_ids=[], tag_uuids=[], is_published=True,
                published_at=datetime.now(timezone.utc), created_by=author_id, actor_role="admin")
    data.update(overrides)
    return storage.create_article(**data)


def test_create_repeat_public_api_and_audit(sandbox, client):
    with SessionLocal() as db:
        taxonomy = (db.query(Category).count(), db.query(Tag).count())
        dcl = db.query(DataChangeLog).count()
        category = db.query(Category).filter(Category.slug == seed.CATEGORY_SLUG,
                                              Category.is_active.is_(True)).first()
        category_id = category.id if category else None
        tag_names = {name for (name,) in db.query(Tag.name).all()}
    result = seed.run()
    expected = {seed.demo_slug(item["key"]) for item in seed.DEMO_MATERIALS}
    assert len(expected) == 12
    assert set(result.created) == expected
    assert result.author_id == sandbox
    rows = articles()
    assert len(rows) == 12 and {r.slug for r in rows} == expected
    assert all(r.is_published and r.status == "published" and r.published_at.tzinfo
               and r.published_at <= datetime.now(timezone.utc) for r in rows)
    log = events()
    assert len(log) == 24
    assert [r.event_type for r in log] == ["article_created", "article_updated"] * 12
    assert all(r.user_id == sandbox and r.user_role == "admin" and r.outcome == "success"
               and r.log_metadata == {} and r.failure_reason_code is None for r in log)
    assert all(r.ip_address is None and r.user_agent is None for r in log)

    repeat = seed.run()
    assert repeat.created == repeat.adopted == [] and set(repeat.skipped) == expected
    assert len(articles()) == 12 and len(events()) == 24
    response = client.get("/api/articles", params={"size": 100})
    assert response.status_code == 200
    public = {r["uuid"]: r for r in response.json()["items"]}
    for item, row in zip(seed.DEMO_MATERIALS, reversed(sorted(rows, key=lambda r: r.id))):
        assert row.title == item["title"]
        data = public[str(row.uuid)]
        assert data["is_published"] is True and data["status"] == "published"
        assert (data["title"], data["excerpt"]) == (item["title"], item["excerpt"])
        assert {t["name"] for t in data["tags"]} == set(item["tags"]) & tag_names
        assert [c["id"] for c in data["categories"]] == ([category_id] if category_id else [])
        detail = client.get(f"/api/articles/{row.uuid}")
        assert detail.status_code == 200 and detail.json()["content"] == item["content"]
    found = client.get("/api/articles", params={"search": seed.DEMO_MATERIALS[0]["title"]})
    assert found.status_code == 200 and found.json()["total"] == 1
    if category_id:
        filtered = client.get("/api/articles", params={"category_id": category_id, "size": 100})
        assert {str(r.uuid) for r in rows} <= {r["uuid"] for r in filtered.json()["items"]}
    with SessionLocal() as db:
        assert (db.query(Category).count(), db.query(Tag).count()) == taxonomy
        assert db.query(DataChangeLog).count() == dcl


@pytest.mark.parametrize("env", ["production", "staging", "release", "", "unknown", None,
                                  "Development", " test "])
def test_env_blocks_before_database(monkeypatch, env):
    monkeypatch.setattr(seed.settings, "ENV", env)
    def forbidden():
        pytest.fail("blocked ENV reached database")
    monkeypatch.setattr(seed, "SessionLocal", forbidden)
    for dry_run in (True, False):
        with pytest.raises(seed.SeedBlocked):
            seed.run(dry_run=dry_run)


@pytest.mark.parametrize("env", ["development", "test"])
def test_allowed_env(monkeypatch, env):
    monkeypatch.setattr(seed.settings, "ENV", env)
    seed.ensure_allowed_env()


def test_dry_run_and_cli_list_all_without_writes(sandbox, monkeypatch, capsys):
    with SessionLocal() as db:
        before = (db.query(Article).count(), db.query(AuditLog).count())
    monkeypatch.setattr(seed.sys, "argv", ["seed_demo_materials.py", "--dry-run"])
    assert seed.main() == seed.EXIT_OK
    output = capsys.readouterr().out
    assert "12" in output and "dry-run" in output
    assert all(item["title"] in output for item in seed.DEMO_MATERIALS)
    with SessionLocal() as db:
        assert (db.query(Article).count(), db.query(AuditLog).count()) == before


@pytest.mark.parametrize("dry_run", [False, True])
def test_no_author_does_not_write(sandbox, dry_run):
    with SessionLocal() as db:
        db.query(UserRole).filter(UserRole.user_id == sandbox).delete()
        db.commit()
    with pytest.raises(LookupError):
        seed.run(dry_run=dry_run)
    assert articles() == []


def test_author_activity_soft_delete_expiry_and_first_account(sandbox):
    with SessionLocal() as db:
        db.query(UserRole).filter(UserRole.user_id == sandbox).delete()
        admin = db.query(Role).filter(Role.name == "admin").one().id
        supervisor = db.query(Role).filter(Role.name == "supervisor").one().id
        for active, deleted, expires, role_id in [
            (False, None, None, admin),
            (True, datetime.now(timezone.utc), None, admin),
            (True, None, datetime.now(timezone.utc) - timedelta(days=1), admin),
            (True, None, None, supervisor),
            (True, None, None, admin),
        ]:
            user = User(full_name="Synthetic candidate",
                        email=f"integ_seed_{uuid.uuid4().hex}@example.com",
                        is_active=active, deleted_at=deleted)
            db.add(user)
            db.flush()
            db.add(UserRole(user_id=user.id, role_id=role_id, expires_at=expires))
            if role_id == supervisor:
                expected = user.id
        db.commit()
        # ORM default превращает переданный None в True; проверяем legacy NULL через UPDATE.
        db.query(User).filter(User.id == expected).update({"is_active": None})
        db.commit()
        assert seed._find_author(db) == (expected, "supervisor")
    assert seed.run().author_id == expected
    assert all(r.user_role == "supervisor" for r in events())


def test_interrupted_creation_is_adopted_even_in_dry_run(sandbox, monkeypatch):
    original = seed._set_slug
    def interrupt(*args, **kwargs):
        raise RuntimeError("synthetic interruption")
    monkeypatch.setattr(seed, "_set_slug", interrupt)
    with pytest.raises(RuntimeError):
        seed.run()
    assert len(articles()) == 1 and articles()[0].slug is None
    assert [r.event_type for r in events()] == ["article_created"]
    monkeypatch.setattr(seed, "_set_slug", original)
    dry = seed.run(dry_run=True)
    assert len(dry.created) == 11 and len(dry.adopted) == 1
    assert articles()[0].slug is None and len(events()) == 1
    result = seed.run()
    assert len(result.created) == 11 and len(result.adopted) == 1
    assert len(articles()) == 12 and all(r.slug for r in articles())
    assert len(seed.run().skipped) == 12


@pytest.mark.parametrize("collision", ["content", "author", "draft", "multiple", "slug"])
def test_title_collision_fails_before_any_seed_write(sandbox, collision):
    item = seed.DEMO_MATERIALS[0]  # проверяется последним в плане — preflight всего набора
    overrides = {"content": "Unrelated synthetic text"} if collision == "content" else {}
    if collision == "draft":
        overrides["is_published"] = False
    existing = create_orphan(sandbox, item, **overrides)
    if collision == "multiple":
        create_orphan(sandbox, item)
    with SessionLocal() as db:
        row = db.query(Article).filter(Article.uuid == uuid.UUID(existing["uuid"])).one()
        if collision == "author":
            row.created_by = None
        if collision == "slug":
            row.slug = "unrelated-material"
        db.commit()
    before = [(r.uuid, r.slug, r.content) for r in articles()]
    count = len(events())
    with pytest.raises(seed.SeedConflict):
        seed.run()
    assert [(r.uuid, r.slug, r.content) for r in articles()] == before
    assert len(events()) == count


@pytest.mark.parametrize("with_slug", [True, False])
def test_soft_deleted_material_stays_deleted(sandbox, client, with_slug):
    item = seed.DEMO_MATERIALS[-1]
    existing = create_orphan(sandbox, item)
    with SessionLocal() as db:
        row = db.query(Article).filter(Article.uuid == uuid.UUID(existing["uuid"])).one()
        row.deleted_at = datetime.now(timezone.utc)
        row.slug = seed.demo_slug(item["key"]) if with_slug else None
        db.commit()
    result = seed.run()
    assert len(result.created) == 11 and result.skipped == [seed.demo_slug(item["key"])]
    assert len(articles()) == 12
    deleted = next(r for r in articles() if str(r.uuid) == existing["uuid"])
    assert deleted.deleted_at is not None
    assert client.get(f"/api/articles/{deleted.uuid}").status_code == 404
    assert len(seed.run().skipped) == 12


def test_missing_taxonomy_does_not_create_it(sandbox, monkeypatch):
    monkeypatch.setattr(seed, "CATEGORY_SLUG", "integ-missing-demo-category")
    monkeypatch.setattr(seed, "DEMO_MATERIALS", [
        {**item, "tags": ["integ-missing-demo-tag"]} for item in seed.DEMO_MATERIALS
    ])
    with SessionLocal() as db:
        counts = (db.query(Category).count(), db.query(Tag).count())
    assert len(seed.run().created) == 12
    for row in articles():
        public = storage.get_article_by_uuid(str(row.uuid), public_only=True)
        assert public["tags"] == public["categories"] == []
    with SessionLocal() as db:
        assert (db.query(Category).count(), db.query(Tag).count()) == counts


def test_create_audit_failure_rolls_back_article(sandbox, monkeypatch):
    def fail(**kwargs):
        raise RuntimeError("synthetic audit failure")
    monkeypatch.setattr(storage, "record_event", fail)
    with pytest.raises(RuntimeError):
        seed.run()
    assert articles() == []


@pytest.mark.parametrize("failure", ["audit", "commit"])
def test_slug_failure_rolls_back_slug_and_its_audit_then_recovers(sandbox, monkeypatch, failure):
    def fail(*args, **kwargs):
        raise RuntimeError("synthetic failure with secret-content")
    with monkeypatch.context() as m:
        if failure == "audit":
            m.setattr(seed, "record_event", fail)
        else:
            def factory():
                db = SessionLocal()
                db.commit = fail
                return db
            m.setattr(seed, "SessionLocal", factory)
        with pytest.raises(RuntimeError):
            seed.run()
    assert len(articles()) == 1 and articles()[0].slug is None
    assert [r.event_type for r in events()] == ["article_created"]
    result = seed.run()
    assert len(result.adopted) == 1 and len(articles()) == 12
    assert len(events()) == 24


def test_concurrent_runs_do_not_duplicate(sandbox, monkeypatch):
    gate = Gate()
    monkeypatch.setattr(storage, "create_article", gate.wrap(storage.create_article))
    first = run_in_thread(seed.run)
    gate.wait_reached()
    second = run_in_thread(seed.run)
    try:
        wait_for_lock_waiter()
    finally:
        gate.release.set()
    a, b = first.join(), second.join()
    assert a[0] == b[0] == "ok"
    assert len(a[1].created) == 12 and len(b[1].skipped) == 12
    assert len(articles()) == 12 and len(events()) == 24


def test_cli_errors_do_not_leak_exception_text(monkeypatch, capsys):
    def fail(**kwargs):
        raise RuntimeError("synthetic-secret-database-url-and-content")
    monkeypatch.setattr(seed, "run", fail)
    monkeypatch.setattr(seed.sys, "argv", ["seed_demo_materials.py"])
    assert seed.main() == seed.EXIT_ERROR
    output = capsys.readouterr()
    assert "RuntimeError" in output.err and "synthetic-secret" not in output.err + output.out
