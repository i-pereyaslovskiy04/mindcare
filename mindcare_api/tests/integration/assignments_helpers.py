"""
ADR-033 — общие помощники integration-тестов заданий (не тест-модуль).

Пользователи — через create_multi_role_user (integ_-префикс, cleanup conftest);
сопровождения — прямой insert (как в тестах контактов) или настоящие операции
supervisor-сервиса; статьи — прямой insert с integ_-заголовком, удаляются
фикстурой `articles` ПОСЛЕ заданий (FK assignments.article_id — RESTRICT).
"""
import uuid
from datetime import datetime, timezone

import pytest

from app.db.models import (
    Article, Assignment, AuditLog, AuthLog, DataChangeLog, TherapyEngagement, User,
)
from app.db.session import SessionLocal
from tests.integration.conftest import create_multi_role_user

SECRET = "Секретное-задание-про-тревогу-7f3a"
NO_STORE = "no-store, private"


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def user(client, roles):
    token, uid, _ = create_multi_role_user(client, list(roles))
    return uid, token


def uuid_of(uid):
    with SessionLocal() as db:
        return str(db.get(User, uid).uuid)


def engage(psy_id, client_id, *, status="active", ended_at=None):
    with SessionLocal() as db:
        eng = TherapyEngagement(
            psychologist_id=psy_id, client_id=client_id, status=status, ended_at=ended_at,
        )
        db.add(eng)
        db.commit()
        return eng.id


def end_engagement(eng_id, status="completed"):
    with SessionLocal() as db:
        eng = db.get(TherapyEngagement, eng_id)
        eng.status = status
        eng.ended_at = datetime.now(timezone.utc)
        db.commit()


def set_user(uid, **values):
    with SessionLocal() as db:
        db.query(User).filter(User.id == uid).update(values)
        db.commit()


def client_url(client_uid):
    return f"/api/psychologist/clients/{uuid_of(client_uid)}/assignments"


def create(client, ptoken, client_uid, text=SECRET, **extra):
    return client.post(client_url(client_uid), headers=auth(ptoken),
                       json={"text": text, **extra})


def create_ok(client, ptoken, client_uid, text=SECRET, **extra):
    r = create(client, ptoken, client_uid, text, **extra)
    assert r.status_code == 201, r.text
    return r.json()["uuid"]


def complete(client, stoken, assignment_uuid):
    return client.post(f"/api/assignments/my/{assignment_uuid}/complete", headers=auth(stoken))


def cancel(client, ptoken, assignment_uuid):
    return client.post(f"/api/psychologist/assignments/{assignment_uuid}/cancel",
                       headers=auth(ptoken))


def my(client, stoken, view="open", **params):
    return client.get("/api/assignments/my", headers=auth(stoken),
                      params={"view": view, **params})


def row(assignment_uuid):
    with SessionLocal() as db:
        r = db.query(Assignment).filter(Assignment.uuid == uuid.UUID(str(assignment_uuid))).first()
        if r is not None:
            db.expunge(r)
        return r


def marks():
    with SessionLocal() as db:
        return tuple(
            db.query(m.id).order_by(m.id.desc()).limit(1).scalar() or 0
            for m in (AuditLog, AuthLog, DataChangeLog)
        )


def rows_since(m):
    out = []
    with SessionLocal() as db:
        for model, mark in zip((AuditLog, AuthLog, DataChangeLog), m):
            rows = db.query(model).filter(model.id > mark).order_by(model.id).all()
            for r in rows:
                db.expunge(r)
            out.append(rows)
    return out


def audit_since(m):
    return rows_since(m)[0]


def blob(r):
    return " | ".join(str(getattr(r, c.name, "")) for c in r.__table__.columns)


def assert_success_row(r, event, actor_uid, role, assignment_uuid):
    target = row(assignment_uuid)
    assert r.event_type == event
    assert (r.user_id, r.user_role) == (actor_uid, role)
    assert (r.entity_type, r.entity_id) == ("assignment", target.id)
    assert r.outcome == "success" and r.failure_reason_code is None
    assert r.log_metadata == {} and r.description is None
    assert SECRET not in blob(r) and target.text_enc not in blob(r)


def assert_failure_row(r, event, actor_uid, role, code):
    assert r.event_type == event
    assert (r.user_id, r.user_role) == (actor_uid, role)
    assert r.outcome == "failure" and r.failure_reason_code == code
    assert r.entity_type is None and r.entity_id is None
    assert r.log_metadata == {} and SECRET not in blob(r)


@pytest.fixture
def articles():
    """Фабрика статей integ_; teardown удаляет задания с этими статьями, затем статьи."""
    created = []

    def make(*, published=True, deleted=False, title=None):
        with SessionLocal() as db:
            art = Article(
                title=title or f"integ_article_{uuid.uuid4().hex[:8]}",
                excerpt="Короткое описание",
                content="<p>Текст</p>",
                is_published=published,
                status="published" if published else "draft",
                published_at=datetime.now(timezone.utc) if published else None,
                deleted_at=datetime.now(timezone.utc) if deleted else None,
            )
            db.add(art)
            db.commit()
            created.append(art.id)
            return {"id": art.id, "uuid": str(art.uuid), "title": art.title}

    yield make
    if created:
        with SessionLocal() as db:
            db.query(Assignment).filter(Assignment.article_id.in_(created)).delete(
                synchronize_session=False)
            db.query(Article).filter(Article.id.in_(created)).delete(synchronize_session=False)
            db.commit()


def set_article(article_id, **values):
    # Статус модерации согласован с публичностью (CHECK ck_articles_status_published).
    if "is_published" in values and "status" not in values:
        values["status"] = "published" if values["is_published"] else "draft"
    with SessionLocal() as db:
        db.query(Article).filter(Article.id == article_id).update(values)
        db.commit()
