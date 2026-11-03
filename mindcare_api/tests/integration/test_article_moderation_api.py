"""
ADR-034 — gated integration: статьи психолога и модерация.

  * черновик автора не публичен; отправка → очередь проверяющего → публикация;
  * правка опубликованной снимает с публикации (article_unpublished_for_edit);
  * возврат с комментарием: комментарий зашифрован, виден автору, не попадает
    в журнал; повторная отправка его снимает;
  * чужие статьи — 404; недопустимый переход — 409; роли и impersonation;
  * админ публикует напрямую — статус согласован с is_published;
  * конкурирующие publish / return — ровно один побеждает (FOR UPDATE).
"""
import uuid

import pytest

import app.articles.moderation_storage as ms
from app.db.models import Article, AuditLog
from app.db.session import SessionLocal
from tests.integration.assignments_helpers import (
    auth, blob, marks, rows_since, user, uuid_of,
)
from tests.integration.lock_helpers import (
    Gate, assert_no_deadlock_error, run_in_thread, wait_for_lock_waiter,
)

COMMENT = "Уточните источники в третьем абзаце — коммент-7c1d"
BASE = "/api/psychologist/articles"
REVIEW = "/api/review/articles"


@pytest.fixture(autouse=True)
def _cleanup_articles():
    yield
    with SessionLocal() as db:
        db.query(Article).filter(Article.title.like("integ\\_mod\\_%", escape="\\")).delete(
            synchronize_session=False)
        db.commit()


def _title():
    return f"integ_mod_{uuid.uuid4().hex[:8]}"


def _create(client, token, **extra):
    r = client.post(BASE, headers=auth(token), json={
        "title": _title(), "excerpt": "Коротко", "content": "<p>Текст</p>", **extra,
    })
    assert r.status_code == 201, r.text
    return r.json()


def _row(art_uuid):
    with SessionLocal() as db:
        a = db.query(Article).filter(Article.uuid == uuid.UUID(art_uuid)).first()
        db.expunge(a)
        return a


def _events(m):
    # system_conversation_created — побочный эффект первого system-сообщения
    # автору (уведомление о решении), не событие модерации.
    return [(r.event_type, r.user_role) for r in rows_since(m)[0]
            if r.event_type != "system_conversation_created"]


@pytest.fixture
def actors(client):
    pid, ptoken = user(client, ["psychologist", "student"])
    sid, stoken = user(client, ["supervisor", "student"])
    return {"pid": pid, "ptoken": ptoken, "sid": sid, "stoken": stoken}


def test_full_moderation_flow(client, actors):
    a = actors
    m = marks()
    art = _create(client, a["ptoken"])
    assert art["status"] == "draft" and art["is_published"] is False
    assert _events(m) == [("article_created", "psychologist")]
    assert client.get(f"/api/articles/{art['uuid']}").status_code == 404     # не публичен

    # проверяющий черновик не видит
    assert client.get(f"{REVIEW}/{art['uuid']}", headers=auth(a["stoken"])).status_code == 404

    m = marks()
    r = client.post(f"{BASE}/{art['uuid']}/submit", headers=auth(a["ptoken"]))
    assert r.status_code == 200 and r.json()["status"] == "in_review"
    assert _events(m) == [("article_submitted_for_review", "psychologist")]
    # на проверке автор не правит
    r = client.patch(f"{BASE}/{art['uuid']}", headers=auth(a["ptoken"]), json={"title": _title()})
    assert r.status_code == 409 and r.json()["current_status"] == "in_review"

    queue = client.get(REVIEW, headers=auth(a["stoken"])).json()
    assert art["uuid"] in [i["uuid"] for i in queue["items"]]
    assert client.get(f"{REVIEW}/{art['uuid']}", headers=auth(a["stoken"])).json()["content"] == "<p>Текст</p>"

    m = marks()
    r = client.post(f"{REVIEW}/{art['uuid']}/publish", headers=auth(a["stoken"]))
    assert r.status_code == 200 and r.json()["status"] == "published"
    assert _events(m) == [("article_published", "supervisor")]
    pub = client.get(f"/api/articles/{art['uuid']}")
    assert pub.status_code == 200 and pub.json()["status"] == "published"
    assert _row(art["uuid"]).published_at is not None

    # правка опубликованной — снимает с публикации
    m = marks()
    r = client.patch(f"{BASE}/{art['uuid']}", headers=auth(a["ptoken"]), json={"excerpt": "Новое"})
    assert r.status_code == 200 and r.json()["status"] == "draft" and r.json()["is_published"] is False
    assert _events(m) == [("article_unpublished_for_edit", "psychologist"),
                          ("article_updated", "psychologist")]
    assert client.get(f"/api/articles/{art['uuid']}").status_code == 404


def test_return_with_encrypted_comment_and_resubmit(client, actors, capsys):
    a = actors
    art = _create(client, a["ptoken"])
    client.post(f"{BASE}/{art['uuid']}/submit", headers=auth(a["ptoken"]))
    capsys.readouterr()
    m = marks()
    r = client.post(f"{REVIEW}/{art['uuid']}/return", headers=auth(a["stoken"]),
                    json={"comment": f"  {COMMENT}  "})
    assert r.status_code == 200 and r.json()["status"] == "needs_changes"
    assert COMMENT not in r.text                                    # проверяющему не эхоится
    stored = _row(art["uuid"])
    assert stored.review_comment_enc.startswith("enc:v1:") and COMMENT not in stored.review_comment_enc
    rows = rows_since(m)[0]
    assert [(x.event_type, x.log_metadata) for x in rows
            if x.event_type != "system_conversation_created"] == [("article_returned_for_changes", {})]
    assert all(COMMENT not in blob(x) for x in rows)
    assert COMMENT not in capsys.readouterr().err

    mine = client.get(f"{BASE}/{art['uuid']}", headers=auth(a["ptoken"])).json()
    assert mine["review_comment"] == COMMENT
    listed = client.get(BASE, headers=auth(a["ptoken"]), params={"status": "needs_changes"}).json()
    assert [i["review_comment"] for i in listed["items"]] == [COMMENT]

    r = client.post(f"{BASE}/{art['uuid']}/submit", headers=auth(a["ptoken"]))
    assert r.status_code == 200 and r.json()["review_comment"] is None
    assert _row(art["uuid"]).review_comment_enc is None


def test_invalid_transitions_are_409(client, actors):
    a = actors
    art = _create(client, a["ptoken"])
    for path in (f"{REVIEW}/{art['uuid']}/publish", f"{REVIEW}/{art['uuid']}/return"):
        r = client.post(path, headers=auth(a["stoken"]), json={})
        assert r.status_code == 409 and r.json()["current_status"] == "draft"
    client.post(f"{BASE}/{art['uuid']}/submit", headers=auth(a["ptoken"]))
    assert client.post(f"{BASE}/{art['uuid']}/submit", headers=auth(a["ptoken"])).status_code == 409
    client.post(f"{REVIEW}/{art['uuid']}/publish", headers=auth(a["stoken"]))
    assert client.post(f"{REVIEW}/{art['uuid']}/publish", headers=auth(a["stoken"])).status_code == 409
    # опубликованную автор не удаляет
    r = client.delete(f"{BASE}/{art['uuid']}", headers=auth(a["ptoken"]))
    assert r.status_code == 409 and r.json()["current_status"] == "published"


def test_author_isolation_and_delete(client, actors):
    a = actors
    _, other = user(client, ["psychologist", "student"])
    art = _create(client, a["ptoken"])
    for r in (client.get(f"{BASE}/{art['uuid']}", headers=auth(other)),
              client.patch(f"{BASE}/{art['uuid']}", headers=auth(other), json={"title": _title()}),
              client.delete(f"{BASE}/{art['uuid']}", headers=auth(other)),
              client.post(f"{BASE}/{art['uuid']}/submit", headers=auth(other))):
        assert r.status_code == 404
    assert client.get(BASE, headers=auth(other)).json()["total"] == 0
    m = marks()
    assert client.delete(f"{BASE}/{art['uuid']}", headers=auth(a["ptoken"])).status_code == 204
    assert _events(m) == [("article_deleted", "psychologist")]
    assert client.get(f"{BASE}/{art['uuid']}", headers=auth(a["ptoken"])).status_code == 404


def test_author_cannot_publish_or_set_publication_fields(client, actors):
    a = actors
    r = client.post(BASE, headers=auth(a["ptoken"]), json={"title": _title(), "is_published": True})
    assert r.status_code == 422
    art = _create(client, a["ptoken"])
    r = client.patch(f"{BASE}/{art['uuid']}", headers=auth(a["ptoken"]), json={"is_published": True})
    assert r.status_code == 422
    assert _row(art["uuid"]).is_published is False


def test_roles_and_impersonation(client, actors):
    a = actors
    art = _create(client, a["ptoken"])
    client.post(f"{BASE}/{art['uuid']}/submit", headers=auth(a["ptoken"]))
    _, student = user(client, ["student"])
    assert client.get(BASE, headers=auth(student)).status_code == 403
    assert client.get(REVIEW, headers=auth(a["ptoken"])).status_code == 403     # психолог не модерирует
    _, admin_token = user(client, ["admin"])
    assert client.get(REVIEW, headers=auth(admin_token)).status_code == 200    # админ модерирует
    imp = client.post(f"/api/admin/users/{uuid_of(a['pid'])}/impersonate",
                      headers=auth(admin_token)).json()["session_token"]
    assert client.get(BASE, headers=auth(imp)).status_code == 403
    assert client.post(BASE, headers=auth(imp), json={"title": _title()}).status_code == 403


def test_admin_direct_publication_keeps_status_consistent(client, actors):
    a = actors
    _, admin_token = user(client, ["admin"])
    r = client.post("/api/admin/articles", headers=auth(admin_token),
                    json={"title": _title(), "is_published": True})
    assert r.status_code == 201 and r.json()["status"] == "published"
    admin_art = r.json()["uuid"]
    r = client.patch(f"/api/admin/articles/{admin_art}", headers=auth(admin_token),
                     json={"is_published": False})
    assert r.json()["status"] == "draft"

    # статья психолога на проверке: админ публикует напрямую через свою форму
    art = _create(client, a["ptoken"])
    client.post(f"{BASE}/{art['uuid']}/submit", headers=auth(a["ptoken"]))
    r = client.patch(f"/api/admin/articles/{art['uuid']}", headers=auth(admin_token),
                     json={"is_published": True})
    assert r.json()["status"] == "published"
    assert client.get(f"/api/articles/{art['uuid']}").status_code == 200


def test_concurrent_publish_and_return_one_wins(client, actors, monkeypatch):
    a = actors
    art = _create(client, a["ptoken"])
    client.post(f"{BASE}/{art['uuid']}/submit", headers=auth(a["ptoken"]))
    gate = Gate()
    monkeypatch.setattr(ms, "_event", gate.wrap(ms._event))
    publisher = run_in_thread(lambda: ms.publish(a["sid"], "supervisor", art["uuid"]))
    gate.wait_reached()                         # статус уже published, commit не сделан
    returner = run_in_thread(lambda: ms.return_for_changes(a["sid"], "supervisor", art["uuid"], None))
    wait_for_lock_waiter()                      # возврат ждёт FOR UPDATE строки статьи
    gate.release.set()
    p, r = publisher.join(), returner.join()
    assert_no_deadlock_error(p, r)
    assert p[0] == "ok" and p[1]["status"] == "published"
    assert r[0] == "error" and isinstance(r[1], ms.ArticleStateConflict)
    assert r[1].current_status == "published"
    assert _row(art["uuid"]).status == "published"
    with SessionLocal() as db:
        kinds = [x.event_type for x in db.query(AuditLog).filter(
            AuditLog.entity_type == "article", AuditLog.entity_id == _row(art["uuid"]).id,
            AuditLog.event_type.in_(("article_published", "article_returned_for_changes")),
        )]
    assert kinds == ["article_published"]
