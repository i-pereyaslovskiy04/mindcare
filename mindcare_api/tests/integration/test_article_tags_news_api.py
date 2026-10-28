"""
Дополнение 2026-10-28 к ADR-034 — gated integration:

  * фильтр «Тема» библиотеки: /api/articles?tag_uuid=… и
    /api/materials/favorites?tag_uuid=… отдают только статьи с темой;
    /api/articles/tags — только темы опубликованных статей; битый uuid — 422;
  * новости ведёт и supervisor (как admin): CRUD /api/admin/news с ролью
    supervisor в журнале; psychologist и student — 403.
"""
import uuid

import pytest

from app.db.models import Article, News, Tag
from app.db.session import SessionLocal
from tests.integration.assignments_helpers import auth, rows_since, marks, user


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    with SessionLocal() as db:
        db.query(Article).filter(Article.title.like("integ\\_tag\\_%", escape="\\")).delete(
            synchronize_session=False)
        db.query(News).filter(News.title.like("integ\\_news\\_%", escape="\\")).delete(
            synchronize_session=False)
        db.query(Tag).filter(Tag.name.like("integ\\_tag\\_%", escape="\\")).delete(
            synchronize_session=False)
        db.commit()


def _tag(client, admin):
    r = client.post("/api/admin/tags/", headers=auth(admin),
                    json={"name": f"integ_tag_{uuid.uuid4().hex[:8]}"})
    assert r.status_code == 201, r.text
    return r.json()


def _article(client, admin, tag_uuids, *, published=True):
    r = client.post("/api/admin/articles", headers=auth(admin), json={
        "title": f"integ_tag_{uuid.uuid4().hex[:8]}", "content": "<p>x</p>",
        "tag_uuids": tag_uuids, "is_published": published,
    })
    assert r.status_code == 201, r.text
    return r.json()


def test_tag_filter_and_tag_options(client):
    _, admin = user(client, ["admin"])
    sleep, stress, draft_only = _tag(client, admin), _tag(client, admin), _tag(client, admin)
    a_sleep = _article(client, admin, [sleep["uuid"]])
    a_both = _article(client, admin, [sleep["uuid"], stress["uuid"]])
    a_stress = _article(client, admin, [stress["uuid"]])
    _article(client, admin, [draft_only["uuid"]], published=False)

    r = client.get("/api/articles", params={"tag_uuid": sleep["uuid"], "size": 100})
    assert r.status_code == 200
    assert {i["uuid"] for i in r.json()["items"]} == {a_sleep["uuid"], a_both["uuid"]}
    assert r.json()["total"] == 2
    r = client.get("/api/articles", params={"tag_uuid": stress["uuid"], "size": 100})
    assert {i["uuid"] for i in r.json()["items"]} == {a_both["uuid"], a_stress["uuid"]}
    # тема только у черновика — пустая выдача
    r = client.get("/api/articles", params={"tag_uuid": draft_only["uuid"]})
    assert r.json()["items"] == [] and r.json()["total"] == 0
    assert client.get("/api/articles", params={"tag_uuid": "not-a-uuid"}).status_code == 422

    names = {t["uuid"]: t["name"] for t in client.get("/api/articles/tags").json()}
    assert names[sleep["uuid"]] == sleep["name"] and stress["uuid"] in names
    assert draft_only["uuid"] not in names


def test_favorites_tag_filter(client):
    _, admin = user(client, ["admin"])
    _, student = user(client, ["student"])
    sleep, stress = _tag(client, admin), _tag(client, admin)
    a_sleep = _article(client, admin, [sleep["uuid"]])
    a_stress = _article(client, admin, [stress["uuid"]])
    for a in (a_sleep, a_stress):
        assert client.put(f"/api/materials/favorites/{a['uuid']}",
                          headers=auth(student)).status_code == 204
    r = client.get("/api/materials/favorites", headers=auth(student),
                   params={"tag_uuid": sleep["uuid"]})
    assert r.status_code == 200
    assert [i["uuid"] for i in r.json()["items"]] == [a_sleep["uuid"]]


def test_supervisor_manages_news_like_admin(client):
    sid, supervisor = user(client, ["supervisor", "student"])
    title = f"integ_news_{uuid.uuid4().hex[:8]}"

    m = marks()
    r = client.post("/api/admin/news", headers=auth(supervisor),
                    json={"title": title, "content": "<p>n</p>", "is_published": True})
    assert r.status_code == 201, r.text
    news_uuid = r.json()["uuid"]
    assert client.get(f"/api/news/{news_uuid}").status_code == 200

    assert client.get("/api/admin/news", headers=auth(supervisor)).status_code == 200
    assert client.get(f"/api/admin/news/{news_uuid}", headers=auth(supervisor)).status_code == 200
    r = client.patch(f"/api/admin/news/{news_uuid}", headers=auth(supervisor),
                     json={"is_published": False})
    assert r.status_code == 200 and r.json()["is_published"] is False
    assert client.get(f"/api/news/{news_uuid}").status_code == 404
    assert client.delete(f"/api/admin/news/{news_uuid}", headers=auth(supervisor)).status_code == 204

    events = [(x.event_type, x.user_id, x.user_role) for x in rows_since(m)[0]
              if x.event_type.startswith("news_")]
    assert events == [("news_created", sid, "supervisor"), ("news_updated", sid, "supervisor"),
                      ("news_deleted", sid, "supervisor")]


@pytest.mark.parametrize("roles", [["psychologist", "student"], ["student"]])
def test_news_admin_api_closed_for_other_roles(client, roles):
    _, token = user(client, roles)
    assert client.get("/api/admin/news", headers=auth(token)).status_code == 403
    assert client.post("/api/admin/news", headers=auth(token),
                       json={"title": "integ_news_x"}).status_code == 403
