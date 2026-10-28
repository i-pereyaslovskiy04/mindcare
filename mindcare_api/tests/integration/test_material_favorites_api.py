"""
ADR-034 — gated integration: избранные материалы пользователя.

  * добавить / убрать / повтор — no-op, состояние сохраняется между запросами;
  * только опубликованная неудалённая статья; снятая с публикации исчезает из
    избранного, но вернётся при повторной публикации;
  * список — серверная пагинация, поиск и категория; только свои отметки;
  * предел FAVORITES_LIMIT; impersonation — 403; аудит не пишется;
  * Cache-Control: no-store.
"""
import uuid

import pytest

import app.material_favorites.storage as fav_storage
from tests.integration.assignments_helpers import (  # noqa: F401 — fixture articles
    articles, auth, marks, rows_since, set_article, user, uuid_of,
)

NO_STORE = "no-store, private"


def _ids(client, token):
    r = client.get("/api/materials/favorites/ids", headers=auth(token))
    assert r.status_code == 200 and r.headers["cache-control"] == NO_STORE
    return r.json()


def _put(client, token, art_uuid):
    return client.put(f"/api/materials/favorites/{art_uuid}", headers=auth(token))


def _delete(client, token, art_uuid):
    return client.delete(f"/api/materials/favorites/{art_uuid}", headers=auth(token))


def test_add_remove_and_repeat_are_idempotent_and_persist(client, articles):
    _, token = user(client, ["student"])
    a1, a2 = articles(), articles()
    m = marks()
    assert _put(client, token, a1["uuid"]).status_code == 204
    assert _put(client, token, a1["uuid"]).status_code == 204          # повтор — no-op
    assert _put(client, token, a2["uuid"]).status_code == 204
    body = _ids(client, token)
    assert body == {"uuids": [a2["uuid"], a1["uuid"]], "count": 2}      # новые сначала

    r = _delete(client, token, a2["uuid"])
    assert r.status_code == 204 and r.headers["cache-control"] == NO_STORE
    assert _delete(client, token, a2["uuid"]).status_code == 204       # повтор — no-op
    assert _delete(client, token, str(uuid.uuid4())).status_code == 204
    assert _ids(client, token) == {"uuids": [a1["uuid"]], "count": 1}
    assert rows_since(m) == [[], [], []]                                # аудит не пишется


@pytest.mark.parametrize("kind", ["unpublished", "deleted", "missing"])
def test_only_published_material_can_be_added(client, articles, kind):
    _, token = user(client, ["student"])
    art_uuid = (str(uuid.uuid4()) if kind == "missing"
                else articles(published=(kind != "unpublished"), deleted=(kind == "deleted"))["uuid"])
    r = _put(client, token, art_uuid)
    assert r.status_code == 404 and r.headers["cache-control"] == NO_STORE
    assert r.json()["code"] == "material_not_available"
    assert _ids(client, token)["count"] == 0


def test_unpublished_material_is_hidden_but_kept(client, articles):
    _, token = user(client, ["student"])
    art = articles(title="integ_article_fav_hidden")
    assert _put(client, token, art["uuid"]).status_code == 204
    set_article(art["id"], is_published=False)
    assert _ids(client, token)["count"] == 0
    r = client.get("/api/materials/favorites", headers=auth(token))
    assert r.json()["items"] == [] and "integ_article_fav_hidden" not in r.text
    set_article(art["id"], is_published=True)
    assert _ids(client, token)["uuids"] == [art["uuid"]]


def test_list_is_paginated_searchable_and_own_only(client, articles):
    _, token = user(client, ["student"])
    _, other = user(client, ["psychologist", "student"])
    arts = [articles(title=f"integ_article_fav_{n}_{'сон' if n % 2 else 'стресс'}") for n in range(3)]
    for a in arts:
        assert _put(client, token, a["uuid"]).status_code == 204
    r = client.get("/api/materials/favorites", headers=auth(token), params={"page": 1, "size": 2})
    assert r.status_code == 200 and r.headers["cache-control"] == NO_STORE
    body = r.json()
    assert body["total"] == 3 and len(body["items"]) == 2 and body["page"] == 1
    r = client.get("/api/materials/favorites", headers=auth(token), params={"search": "сон"})
    assert [i["uuid"] for i in r.json()["items"]] == [arts[1]["uuid"]]
    # чужие отметки не видны
    assert _ids(client, other) == {"uuids": [], "count": 0}
    assert client.get("/api/materials/favorites", headers=auth(other)).json()["total"] == 0


def test_limit_is_enforced(client, articles, monkeypatch):
    _, token = user(client, ["student"])
    monkeypatch.setattr(fav_storage, "FAVORITES_LIMIT", 1)
    a1, a2 = articles(), articles()
    assert _put(client, token, a1["uuid"]).status_code == 204
    r = _put(client, token, a2["uuid"])
    assert r.status_code == 409 and r.json()["code"] == "favorites_limit"
    assert _put(client, token, a1["uuid"]).status_code == 204          # уже в избранном — no-op


def test_impersonation_and_anonymous_are_rejected(client, articles):
    uid, token = user(client, ["student"])
    art = articles()
    _, admin_token = user(client, ["admin"])
    imp = client.post(f"/api/admin/users/{uuid_of(uid)}/impersonate",
                      headers=auth(admin_token)).json()["session_token"]
    for r in (client.get("/api/materials/favorites/ids", headers=auth(imp)),
              _put(client, imp, art["uuid"]), _delete(client, imp, art["uuid"]),
              client.get("/api/materials/favorites", headers=auth(imp))):
        assert r.status_code == 403
    assert client.get("/api/materials/favorites/ids").status_code == 401
    assert _ids(client, token)["count"] == 0


def test_bad_uuid_is_422(client):
    _, token = user(client, ["student"])
    assert _put(client, token, "not-a-uuid").status_code == 422
