"""
Доработка 2026-10-13 — gated integration: галочка «Показать отключённых» в
/admin/users собирается из СУЩЕСТВУЮЩИХ параметров GET /api/admin/users/:

  * галочка выключена → is_active=true: только активные
    (deleted_at IS NULL И is_active IS NOT FALSE; исторический NULL — активен);
  * галочка включена → include_deleted=true без is_active: активные и
    отключённые, в т.ч. ранее удалённые (deleted_at) с любым is_active.

Матрица из пяти аккаунтов под общим префиксом поиска; total и страницы
(size=2) согласованы. Смысл include_deleted для прочих потребителей не
меняется (is_active=false по-прежнему сам включает удалённых).
"""
import uuid as _uuid
from datetime import datetime, timezone

import pytest

from app.core.encryption import encrypt_text
from app.db.models import User
from app.db.session import SessionLocal
from tests.integration.conftest import create_multi_role_user, create_test_user

URL = "/api/admin/users/"


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def matrix(client):
    token, _, _ = create_multi_role_user(client, ["admin"])
    prefix = f"integ_vis_{_uuid.uuid4().hex[:8]}"
    states = {}
    for state in ("active", "null", "disabled", "deleted_off", "deleted_on"):
        uid = int(create_test_user(f"{prefix}_{state}@example.com")["id"])
        with SessionLocal() as db:
            u = db.get(User, uid)
            now = datetime.now(timezone.utc)
            if state == "null":
                u.is_active = None
            elif state == "disabled":
                u.is_active = False
                u.deactivated_at = now
                u.deactivation_source = "admin"
                u.deactivation_reason_enc = encrypt_text("Причина")
            elif state == "deleted_off":
                u.deleted_at = now
                u.is_active = False
            elif state == "deleted_on":          # исторически удалённый, is_active=true
                u.deleted_at = now
                u.is_active = True
            db.commit()
            states[state] = str(u.uuid)
    return {"token": token, "prefix": prefix, "states": states}


def _list(client, matrix, **params):
    params = {"search": matrix["prefix"], "size": 100, **params}
    r = client.get(URL, headers=_auth(matrix["token"]), params=params)
    assert r.status_code == 200, r.text
    return r.json()


def _names(matrix, body):
    by_uuid = {v: k for k, v in matrix["states"].items()}
    return sorted(by_uuid[i["uuid"]] for i in body["items"])


def test_checkbox_off_shows_only_active_including_null(client, matrix):
    body = _list(client, matrix, is_active="true")
    assert _names(matrix, body) == ["active", "null"]
    assert body["total"] == 2
    assert all(i["is_active"] is True and i["deleted_at"] is None for i in body["items"])


def test_checkbox_on_shows_active_disabled_and_previously_deleted(client, matrix):
    body = _list(client, matrix, include_deleted="true")
    assert _names(matrix, body) == sorted(matrix["states"])
    assert body["total"] == 5


def test_include_deleted_meaning_for_other_consumers_is_unchanged(client, matrix):
    # Без параметров удалённые скрыты (прежний смысл умолчания).
    assert _names(matrix, _list(client, matrix)) == ["active", "disabled", "null"]
    # is_active=false сам включает удалённых (ADR-028), с include_deleted — то же.
    expected = ["deleted_off", "deleted_on", "disabled"]
    assert _names(matrix, _list(client, matrix, is_active="false")) == expected
    assert _names(matrix, _list(
        client, matrix, is_active="false", include_deleted="true")) == expected


@pytest.mark.parametrize("params,total", [
    ({"is_active": "true"}, 2),
    ({"include_deleted": "true"}, 5),
])
def test_total_and_pages_are_consistent(client, matrix, params, total):
    seen = []
    pages = -(-total // 2)
    for page in range(1, pages + 2):
        body = _list(client, matrix, size=2, page=page, **params)
        assert body["total"] == total
        if page <= pages:
            assert len(body["items"]) == min(2, total - 2 * (page - 1))
        else:
            assert body["items"] == []          # за последней страницей — пусто
        seen += [i["uuid"] for i in body["items"]]
    assert len(seen) == len(set(seen)) == total
