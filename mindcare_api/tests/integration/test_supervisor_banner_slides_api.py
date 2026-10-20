"""
Integration tests for banner slides (Hero.jsx CMS): admin+supervisor CRUD
через /api/supervisor/banner-slides, публичное чтение через /api/banner-slides.

Coverage:
- Доступ: admin и supervisor разрешены, прочие роли — 403.
- title обязателен и непуст (422 при отсутствии/пустой строке).
- create/list/patch, картинка резолвится в image_url через media_files.
- is_active выделен в отдельные audit-события activated/deactivated,
  не смешивается с banner_slide_updated (по аналогии с meeting_types).
- Identical PATCH — no-op: без мутации, без сдвига updated_at, без audit.
- Публичный эндпоинт отдаёт только активные слайды, отсортированные по
  display_order, без авторизации.

Requires: PostgreSQL on alembic head, DATA_ENCRYPTION_KEY, seeded roles.
"""
import uuid as _uuid

import bcrypt

from app.auth import storage as auth_storage
from app.db.session import SessionLocal
from app.db.models import AuditLog, BannerSlide, MediaFile

PASSWORD = "SecurePass42!"
URL = "/api/supervisor/banner-slides"
PUBLIC_URL = "/api/banner-slides"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _make_user(client, role: str):
    suffix = _uuid.uuid4().hex[:10]
    email = f"integ_banner_{role}_{suffix}@example.com"
    user = auth_storage.save_user({
        "name": f"BannerTest {role.capitalize()} {_uuid.uuid4().hex[:6]}",
        "email": email,
        "hashed_password": bcrypt.hashpw(
            PASSWORD.encode(), bcrypt.gensalt()
        ).decode(),
        "role": role,
    })
    r = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["session_token"], int(user["id"])


def _audit_rows(event_type, entity_id):
    with SessionLocal() as db:
        rows = (
            db.query(AuditLog)
            .filter(AuditLog.event_type == event_type,
                    AuditLog.entity_id == entity_id)
            .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
            .all()
        )
        for r in rows:
            db.expunge(r)
        return rows


def _make_media_file() -> str:
    """Создаёт активный MediaFile напрямую в БД, возвращает его uuid (str)."""
    with SessionLocal() as db:
        mf = MediaFile(
            file_name=f"integ_banner_{_uuid.uuid4().hex[:6]}.webp",
            file_path=f"/media/uploads/integ_banner_{_uuid.uuid4().hex[:6]}.webp",
            file_type="image",
            mime_type="image/webp",
            is_active=True,
        )
        db.add(mf)
        db.commit()
        db.refresh(mf)
        return str(mf.uuid), mf.file_path


# ═══════════════════════════════════════════════════════════════════════════
# Доступ по ролям
# ═══════════════════════════════════════════════════════════════════════════

def test_admin_can_create_and_supervisor_can_list(client):
    tok_admin, _ = _make_user(client, "admin")
    r = client.post(
        URL, json={"title": f"integ_slide_{_uuid.uuid4().hex[:8]}"},
        headers=_auth(tok_admin),
    )
    assert r.status_code == 201, r.text
    slide_id = r.json()["id"]

    tok_sup, _ = _make_user(client, "supervisor")
    r = client.get(f"{URL}?include_inactive=true", headers=_auth(tok_sup))
    assert r.status_code == 200
    assert any(item["id"] == slide_id for item in r.json())


def test_other_roles_forbidden(client):
    for role in ("student", "psychologist"):
        tok, _ = _make_user(client, role)
        r = client.get(URL, headers=_auth(tok))
        assert r.status_code == 403, (role, r.text)
        r = client.post(URL, json={"title": "x"}, headers=_auth(tok))
        assert r.status_code == 403, (role, r.text)


def test_unauthenticated_forbidden(client):
    assert client.get(URL).status_code == 401


# ═══════════════════════════════════════════════════════════════════════════
# Валидация
# ═══════════════════════════════════════════════════════════════════════════

def test_create_requires_nonempty_title(client):
    tok, _ = _make_user(client, "admin")
    assert client.post(URL, json={}, headers=_auth(tok)).status_code == 422
    assert client.post(
        URL, json={"title": ""}, headers=_auth(tok)
    ).status_code == 422


def test_patch_rejects_blank_title(client):
    tok, _ = _make_user(client, "admin")
    slide_id = client.post(
        URL, json={"title": f"integ_slide_{_uuid.uuid4().hex[:8]}"},
        headers=_auth(tok),
    ).json()["id"]
    assert client.patch(
        f"{URL}/{slide_id}", json={"title": ""}, headers=_auth(tok),
    ).status_code == 422


def test_patch_unknown_id_returns_404(client):
    tok, _ = _make_user(client, "admin")
    assert client.patch(
        f"{URL}/99999999", json={"title": "x"}, headers=_auth(tok),
    ).status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# CRUD + картинка
# ═══════════════════════════════════════════════════════════════════════════

def test_create_with_optional_fields_and_image(client):
    tok, _ = _make_user(client, "admin")
    image_uuid, file_path = _make_media_file()

    r = client.post(
        URL,
        json={
            "label": "Психологическая служба",
            "title": "Забота о вашей",
            "highlight": "душевной гармонии",
            "sub": "Профессиональная поддержка.",
            "image_uuid": image_uuid,
            "display_order": 3,
        },
        headers=_auth(tok),
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["label"] == "Психологическая служба"
    assert data["highlight"] == "душевной гармонии"
    assert data["image_uuid"] == image_uuid
    assert data["image_url"] == file_path
    assert data["display_order"] == 3
    assert data["is_active"] is True

    arows = _audit_rows("banner_slide_created", data["id"])
    assert len(arows) == 1


def test_create_and_clear_link_url(client):
    tok, _ = _make_user(client, "admin")
    r = client.post(
        URL,
        json={"title": f"integ_slide_{_uuid.uuid4().hex[:8]}", "link_url": "/services"},
        headers=_auth(tok),
    )
    assert r.status_code == 201, r.text
    slide = r.json()
    assert slide["link_url"] == "/services"

    r = client.get(PUBLIC_URL)
    payload = next(item for item in r.json() if item["title"] == slide["title"])
    assert payload["link_url"] == "/services"

    # Явный null в PATCH снимает ссылку.
    r = client.patch(
        f"{URL}/{slide['id']}", json={"link_url": None}, headers=_auth(tok),
    )
    assert r.status_code == 200
    assert r.json()["link_url"] is None


def test_create_without_image_leaves_image_url_null(client):
    tok, _ = _make_user(client, "admin")
    r = client.post(
        URL, json={"title": f"integ_slide_{_uuid.uuid4().hex[:8]}"},
        headers=_auth(tok),
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["image_uuid"] is None
    assert data["image_url"] is None


def test_patch_updates_fields_and_writes_updated_event(client):
    tok, _ = _make_user(client, "admin")
    slide_id = client.post(
        URL, json={"title": f"integ_slide_{_uuid.uuid4().hex[:8]}"},
        headers=_auth(tok),
    ).json()["id"]

    r = client.patch(
        f"{URL}/{slide_id}",
        json={"title": "Новый заголовок", "sub": "Новый подзаголовок"},
        headers=_auth(tok),
    )
    assert r.status_code == 200, r.text
    assert r.json()["title"] == "Новый заголовок"
    assert len(_audit_rows("banner_slide_updated", slide_id)) == 1
    assert _audit_rows("banner_slide_activated", slide_id) == []
    assert _audit_rows("banner_slide_deactivated", slide_id) == []


def test_patch_is_active_writes_activated_and_deactivated_not_created(client):
    tok, _ = _make_user(client, "admin")
    slide_id = client.post(
        URL, json={"title": f"integ_slide_{_uuid.uuid4().hex[:8]}"},
        headers=_auth(tok),
    ).json()["id"]

    assert client.patch(
        f"{URL}/{slide_id}", json={"is_active": False}, headers=_auth(tok),
    ).status_code == 200
    assert len(_audit_rows("banner_slide_deactivated", slide_id)) == 1
    assert _audit_rows("banner_slide_created", slide_id).__len__() == 1  # только исходное создание

    assert client.patch(
        f"{URL}/{slide_id}", json={"is_active": True}, headers=_auth(tok),
    ).status_code == 200
    assert len(_audit_rows("banner_slide_activated", slide_id)) == 1
    # Реактивация — НЕ повторное "created".
    assert len(_audit_rows("banner_slide_created", slide_id)) == 1


def test_combined_patch_writes_two_separate_events(client):
    tok, _ = _make_user(client, "admin")
    slide_id = client.post(
        URL, json={"title": f"integ_slide_{_uuid.uuid4().hex[:8]}"},
        headers=_auth(tok),
    ).json()["id"]

    assert client.patch(
        f"{URL}/{slide_id}",
        json={"title": "Другой заголовок", "is_active": False},
        headers=_auth(tok),
    ).status_code == 200
    assert len(_audit_rows("banner_slide_updated", slide_id)) == 1
    assert len(_audit_rows("banner_slide_deactivated", slide_id)) == 1


def test_identical_patch_is_noop(client):
    tok, _ = _make_user(client, "admin")
    slide_id = client.post(
        URL, json={"title": "Стабильный заголовок"}, headers=_auth(tok),
    ).json()["id"]

    with SessionLocal() as db:
        updated_before = db.query(BannerSlide.updated_at).filter(
            BannerSlide.id == slide_id).scalar()

    updated_before_calls = len(_audit_rows("banner_slide_updated", slide_id))
    assert client.patch(
        f"{URL}/{slide_id}", json={"title": "Стабильный заголовок"},
        headers=_auth(tok),
    ).status_code == 200
    assert client.patch(
        f"{URL}/{slide_id}", json={}, headers=_auth(tok),
    ).status_code == 200

    assert len(_audit_rows("banner_slide_updated", slide_id)) == updated_before_calls
    with SessionLocal() as db:
        assert db.query(BannerSlide.updated_at).filter(
            BannerSlide.id == slide_id).scalar() == updated_before


# ═══════════════════════════════════════════════════════════════════════════
# Публичный эндпоинт
# ═══════════════════════════════════════════════════════════════════════════

def test_public_endpoint_returns_only_active_ordered_no_auth(client):
    tok, _ = _make_user(client, "admin")
    prefix = _uuid.uuid4().hex[:8]

    active_first = client.post(
        URL, json={"title": f"integ_pub_{prefix}_first", "display_order": 1},
        headers=_auth(tok),
    ).json()
    active_second = client.post(
        URL, json={"title": f"integ_pub_{prefix}_second", "display_order": 2},
        headers=_auth(tok),
    ).json()
    inactive = client.post(
        URL, json={
            "title": f"integ_pub_{prefix}_inactive", "display_order": 0,
            "is_active": False,
        },
        headers=_auth(tok),
    ).json()

    r = client.get(PUBLIC_URL)
    assert r.status_code == 200
    titles = [item["title"] for item in r.json()]
    assert active_first["title"] in titles
    assert active_second["title"] in titles
    assert inactive["title"] not in titles
    # Порядок: display_order 1 раньше display_order 2 среди наших слайдов.
    own_titles = [t for t in titles if t.startswith(f"integ_pub_{prefix}")]
    assert own_titles == [active_first["title"], active_second["title"]]

    # Публичная схема не отдаёт служебные поля.
    first_payload = next(
        item for item in r.json() if item["title"] == active_first["title"]
    )
    assert set(first_payload.keys()) == {"label", "title", "highlight", "sub", "image_url", "link_url"}


# ═══════════════════════════════════════════════════════════════════════════
# Placement — какая страница показывает слайд
# ═══════════════════════════════════════════════════════════════════════════

def test_placement_defaults_to_home(client):
    tok, _ = _make_user(client, "admin")
    slide = client.post(
        URL, json={"title": f"integ_slide_{_uuid.uuid4().hex[:8]}"},
        headers=_auth(tok),
    ).json()
    assert slide["placement"] == "home"


def test_placement_rejects_unknown_page(client):
    tok, _ = _make_user(client, "admin")
    r = client.post(
        URL, json={"title": "x", "placement": "unknown-page"}, headers=_auth(tok),
    )
    assert r.status_code == 422


def test_public_endpoint_filters_by_placement(client):
    tok, _ = _make_user(client, "admin")
    prefix = _uuid.uuid4().hex[:8]

    home_slide = client.post(
        URL, json={"title": f"integ_place_{prefix}_home", "placement": "home"},
        headers=_auth(tok),
    ).json()
    services_slide = client.post(
        URL,
        json={"title": f"integ_place_{prefix}_services", "placement": "services"},
        headers=_auth(tok),
    ).json()

    home_titles = [i["title"] for i in client.get(PUBLIC_URL).json()]
    services_titles = [
        i["title"] for i in client.get(f"{PUBLIC_URL}?placement=services").json()
    ]
    assert home_slide["title"] in home_titles
    assert home_slide["title"] not in services_titles
    assert services_slide["title"] in services_titles
    assert services_slide["title"] not in home_titles


def test_public_endpoint_rejects_unknown_placement(client):
    assert client.get(f"{PUBLIC_URL}?placement=unknown-page").status_code == 422


def test_supervisor_list_filters_by_placement(client):
    tok, _ = _make_user(client, "admin")
    prefix = _uuid.uuid4().hex[:8]
    services_slide = client.post(
        URL,
        json={"title": f"integ_place_{prefix}_svc", "placement": "services"},
        headers=_auth(tok),
    ).json()

    r = client.get(f"{URL}?placement=services&include_inactive=true", headers=_auth(tok))
    assert any(item["id"] == services_slide["id"] for item in r.json())
    r = client.get(f"{URL}?placement=home&include_inactive=true", headers=_auth(tok))
    assert not any(item["id"] == services_slide["id"] for item in r.json())


# ═══════════════════════════════════════════════════════════════════════════
# Удаление (физическое, с подтверждением на фронте)
# ═══════════════════════════════════════════════════════════════════════════

def test_admin_can_delete_slide(client):
    tok, _ = _make_user(client, "admin")
    slide = client.post(
        URL, json={"title": f"integ_slide_{_uuid.uuid4().hex[:8]}"},
        headers=_auth(tok),
    ).json()

    r = client.delete(f"{URL}/{slide['id']}", headers=_auth(tok))
    assert r.status_code == 204

    with SessionLocal() as db:
        assert db.query(BannerSlide).filter(BannerSlide.id == slide["id"]).first() is None

    assert len(_audit_rows("banner_slide_deleted", slide["id"])) == 1


def test_supervisor_can_delete_slide(client):
    tok, _ = _make_user(client, "supervisor")
    slide = client.post(
        URL, json={"title": f"integ_slide_{_uuid.uuid4().hex[:8]}"},
        headers=_auth(tok),
    ).json()

    assert client.delete(f"{URL}/{slide['id']}", headers=_auth(tok)).status_code == 204


def test_other_roles_cannot_delete(client):
    tok_admin, _ = _make_user(client, "admin")
    slide = client.post(
        URL, json={"title": f"integ_slide_{_uuid.uuid4().hex[:8]}"},
        headers=_auth(tok_admin),
    ).json()

    for role in ("student", "psychologist"):
        tok, _ = _make_user(client, role)
        r = client.delete(f"{URL}/{slide['id']}", headers=_auth(tok))
        assert r.status_code == 403, (role, r.text)


def test_delete_unknown_id_returns_404(client):
    tok, _ = _make_user(client, "admin")
    assert client.delete(f"{URL}/99999999", headers=_auth(tok)).status_code == 404


def test_deleted_slide_disappears_from_public_endpoint(client):
    tok, _ = _make_user(client, "admin")
    slide = client.post(
        URL, json={"title": f"integ_slide_{_uuid.uuid4().hex[:8]}"},
        headers=_auth(tok),
    ).json()

    assert client.delete(f"{URL}/{slide['id']}", headers=_auth(tok)).status_code == 204

    titles = [i["title"] for i in client.get(PUBLIC_URL).json()]
    assert slide["title"] not in titles
