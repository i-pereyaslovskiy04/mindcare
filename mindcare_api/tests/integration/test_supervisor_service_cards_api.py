"""
Integration tests for service cards (/services CMS): admin+supervisor CRUD
через /api/supervisor/service-cards, публичное чтение через /api/service-cards.

Coverage:
- Доступ: admin и supervisor разрешены, прочие роли — 403.
- title и description обязательны и непусты (422 при отсутствии/пустой строке).
- create/list/patch, картинка резолвится в image_url через media_files.
- benefits — JSON-массив строк, точный round-trip (порядок сохраняется).
- Явный null на NOT NULL-поле (title/description/benefits) в PATCH → 422,
  без мутации, без audit-строки (в отличие от banner_slides, где такого
  гварда нет).
- is_active выделен в отдельные audit-события activated/deactivated,
  не смешивается с service_card_updated (по аналогии с banner_slides).
- Identical PATCH — no-op: без мутации, без сдвига updated_at, без audit.
- Публичный эндпоинт отдаёт только активные карточки, отсортированные по
  display_order, без авторизации, БЕЗ служебных полей (id/uuid/display_order/
  is_active).

Requires: PostgreSQL on alembic head, DATA_ENCRYPTION_KEY, seeded roles.
"""
import uuid as _uuid

import bcrypt

from app.auth import storage as auth_storage
from app.db.session import SessionLocal
from app.db.models import AuditLog, MediaFile, ServiceCard

PASSWORD = "SecurePass42!"
URL = "/api/supervisor/service-cards"
PUBLIC_URL = "/api/service-cards"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _make_user(client, role: str):
    suffix = _uuid.uuid4().hex[:10]
    email = f"integ_svccard_{role}_{suffix}@example.com"
    user = auth_storage.save_user({
        "name": f"ServiceCardTest {role.capitalize()} {_uuid.uuid4().hex[:6]}",
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


def _make_media_file() -> tuple[str, str]:
    """Создаёт активный MediaFile напрямую в БД, возвращает (uuid, file_path)."""
    with SessionLocal() as db:
        mf = MediaFile(
            file_name=f"integ_svccard_{_uuid.uuid4().hex[:6]}.webp",
            file_path=f"/media/uploads/integ_svccard_{_uuid.uuid4().hex[:6]}.webp",
            file_type="image",
            mime_type="image/webp",
            is_active=True,
        )
        db.add(mf)
        db.commit()
        db.refresh(mf)
        return str(mf.uuid), mf.file_path


def _create(client, tok, **overrides):
    body = {
        "title": f"integ_card_{_uuid.uuid4().hex[:8]}",
        "description": "Описание услуги для интеграционного теста.",
    }
    body.update(overrides)
    return client.post(URL, json=body, headers=_auth(tok))


# ═══════════════════════════════════════════════════════════════════════════
# Доступ по ролям
# ═══════════════════════════════════════════════════════════════════════════

def test_admin_can_create_and_supervisor_can_list(client):
    tok_admin, _ = _make_user(client, "admin")
    r = _create(client, tok_admin)
    assert r.status_code == 201, r.text
    card_id = r.json()["id"]

    tok_sup, _ = _make_user(client, "supervisor")
    r = client.get(f"{URL}?include_inactive=true", headers=_auth(tok_sup))
    assert r.status_code == 200
    assert any(item["id"] == card_id for item in r.json())


def test_other_roles_forbidden(client):
    for role in ("student", "psychologist"):
        tok, _ = _make_user(client, role)
        r = client.get(URL, headers=_auth(tok))
        assert r.status_code == 403, (role, r.text)
        r = client.post(URL, json={"title": "x", "description": "y"}, headers=_auth(tok))
        assert r.status_code == 403, (role, r.text)


def test_unauthenticated_forbidden(client):
    assert client.get(URL).status_code == 401


# ═══════════════════════════════════════════════════════════════════════════
# Валидация
# ═══════════════════════════════════════════════════════════════════════════

def test_create_requires_nonempty_title_and_description(client):
    tok, _ = _make_user(client, "admin")
    assert client.post(URL, json={}, headers=_auth(tok)).status_code == 422
    assert client.post(
        URL, json={"title": "", "description": "x"}, headers=_auth(tok)
    ).status_code == 422
    assert client.post(
        URL, json={"title": "x", "description": ""}, headers=_auth(tok)
    ).status_code == 422
    assert client.post(
        URL, json={"title": "x"}, headers=_auth(tok)
    ).status_code == 422


def test_patch_rejects_blank_title(client):
    tok, _ = _make_user(client, "admin")
    card_id = _create(client, tok).json()["id"]
    assert client.patch(
        f"{URL}/{card_id}", json={"title": ""}, headers=_auth(tok),
    ).status_code == 422


def test_patch_unknown_id_returns_404(client):
    tok, _ = _make_user(client, "admin")
    assert client.patch(
        f"{URL}/99999999", json={"title": "x"}, headers=_auth(tok),
    ).status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# NOT NULL guard — явный null на NOT NULL-поле в PATCH
# ═══════════════════════════════════════════════════════════════════════════

def test_patch_null_title_rejected_without_mutation_or_audit(client):
    tok, _ = _make_user(client, "admin")
    card = _create(client, tok, title="Стабильный заголовок").json()

    r = client.patch(f"{URL}/{card['id']}", json={"title": None}, headers=_auth(tok))
    assert r.status_code == 422

    with SessionLocal() as db:
        row = db.query(ServiceCard).filter(ServiceCard.id == card["id"]).first()
        assert row.title == "Стабильный заголовок"
    assert _audit_rows("service_card_updated", card["id"]) == []


def test_patch_null_description_rejected(client):
    tok, _ = _make_user(client, "admin")
    card_id = _create(client, tok).json()["id"]
    r = client.patch(f"{URL}/{card_id}", json={"description": None}, headers=_auth(tok))
    assert r.status_code == 422


def test_patch_null_benefits_rejected(client):
    tok, _ = _make_user(client, "admin")
    card_id = _create(client, tok).json()["id"]
    r = client.patch(f"{URL}/{card_id}", json={"benefits": None}, headers=_auth(tok))
    assert r.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════
# CRUD + картинка + benefits
# ═══════════════════════════════════════════════════════════════════════════

def test_create_with_optional_fields_and_image(client):
    tok, _ = _make_user(client, "admin")
    image_uuid, file_path = _make_media_file()

    r = _create(
        client, tok,
        benefits=["Пункт 1", "Пункт 2"],
        image_uuid=image_uuid,
        link_url="/services",
        display_order=3,
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["benefits"] == ["Пункт 1", "Пункт 2"]
    assert data["image_uuid"] == image_uuid
    assert data["image_url"] == file_path
    assert data["link_url"] == "/services"
    assert data["display_order"] == 3
    assert data["is_active"] is True

    arows = _audit_rows("service_card_created", data["id"])
    assert len(arows) == 1


def test_create_without_image_leaves_image_url_null(client):
    tok, _ = _make_user(client, "admin")
    r = _create(client, tok)
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["image_uuid"] is None
    assert data["image_url"] is None


def test_benefits_round_trip_preserves_order(client):
    tok, _ = _make_user(client, "admin")
    benefits = ["a", "b", "c"]
    card = _create(client, tok, benefits=benefits).json()
    assert card["benefits"] == benefits

    r = client.get(f"{URL}?include_inactive=true", headers=_auth(tok))
    fetched = next(item for item in r.json() if item["id"] == card["id"])
    assert fetched["benefits"] == benefits


def test_create_and_clear_link_url(client):
    tok, _ = _make_user(client, "admin")
    r = _create(client, tok, link_url="/services")
    assert r.status_code == 201, r.text
    card = r.json()
    assert card["link_url"] == "/services"

    r = client.patch(
        f"{URL}/{card['id']}", json={"link_url": None}, headers=_auth(tok),
    )
    assert r.status_code == 200
    assert r.json()["link_url"] is None


def test_patch_updates_fields_and_writes_updated_event(client):
    tok, _ = _make_user(client, "admin")
    card_id = _create(client, tok).json()["id"]

    r = client.patch(
        f"{URL}/{card_id}",
        json={"title": "Новый заголовок", "description": "Новое описание"},
        headers=_auth(tok),
    )
    assert r.status_code == 200, r.text
    assert r.json()["title"] == "Новый заголовок"
    assert len(_audit_rows("service_card_updated", card_id)) == 1
    assert _audit_rows("service_card_activated", card_id) == []
    assert _audit_rows("service_card_deactivated", card_id) == []


def test_patch_is_active_writes_activated_and_deactivated_not_created(client):
    tok, _ = _make_user(client, "admin")
    card_id = _create(client, tok).json()["id"]

    assert client.patch(
        f"{URL}/{card_id}", json={"is_active": False}, headers=_auth(tok),
    ).status_code == 200
    assert len(_audit_rows("service_card_deactivated", card_id)) == 1
    assert len(_audit_rows("service_card_created", card_id)) == 1  # только исходное создание

    assert client.patch(
        f"{URL}/{card_id}", json={"is_active": True}, headers=_auth(tok),
    ).status_code == 200
    assert len(_audit_rows("service_card_activated", card_id)) == 1
    # Реактивация — НЕ повторное "created".
    assert len(_audit_rows("service_card_created", card_id)) == 1


def test_combined_patch_writes_two_separate_events(client):
    tok, _ = _make_user(client, "admin")
    card_id = _create(client, tok).json()["id"]

    assert client.patch(
        f"{URL}/{card_id}",
        json={"title": "Другой заголовок", "is_active": False},
        headers=_auth(tok),
    ).status_code == 200
    assert len(_audit_rows("service_card_updated", card_id)) == 1
    assert len(_audit_rows("service_card_deactivated", card_id)) == 1


def test_identical_patch_is_noop(client):
    tok, _ = _make_user(client, "admin")
    card_id = _create(client, tok, title="Стабильный заголовок").json()["id"]

    with SessionLocal() as db:
        updated_before = db.query(ServiceCard.updated_at).filter(
            ServiceCard.id == card_id).scalar()

    updated_before_calls = len(_audit_rows("service_card_updated", card_id))
    assert client.patch(
        f"{URL}/{card_id}", json={"title": "Стабильный заголовок"},
        headers=_auth(tok),
    ).status_code == 200
    assert client.patch(
        f"{URL}/{card_id}", json={}, headers=_auth(tok),
    ).status_code == 200

    assert len(_audit_rows("service_card_updated", card_id)) == updated_before_calls
    with SessionLocal() as db:
        assert db.query(ServiceCard.updated_at).filter(
            ServiceCard.id == card_id).scalar() == updated_before


# ═══════════════════════════════════════════════════════════════════════════
# Публичный эндпоинт
# ═══════════════════════════════════════════════════════════════════════════

def test_public_endpoint_returns_only_active_ordered_no_auth(client):
    tok, _ = _make_user(client, "admin")
    prefix = _uuid.uuid4().hex[:8]

    active_first = _create(
        client, tok, title=f"integ_pub_{prefix}_first", display_order=1,
    ).json()
    active_second = _create(
        client, tok, title=f"integ_pub_{prefix}_second", display_order=2,
    ).json()
    inactive = _create(
        client, tok, title=f"integ_pub_{prefix}_inactive", display_order=0,
        is_active=False,
    ).json()

    r = client.get(PUBLIC_URL)
    assert r.status_code == 200
    titles = [item["title"] for item in r.json()]
    assert active_first["title"] in titles
    assert active_second["title"] in titles
    assert inactive["title"] not in titles
    # Порядок: display_order 1 раньше display_order 2 среди наших карточек.
    own_titles = [t for t in titles if t.startswith(f"integ_pub_{prefix}")]
    assert own_titles == [active_first["title"], active_second["title"]]

    # Публичная схема не отдаёт служебные поля (id/uuid/display_order/is_active).
    first_payload = next(
        item for item in r.json() if item["title"] == active_first["title"]
    )
    assert set(first_payload.keys()) == {
        "title", "description", "benefits", "image_url", "link_url",
    }


def test_public_endpoint_has_no_query_params(client):
    """service_cards — одна страница-получатель, в отличие от banner_slides
    здесь нет placement вообще (ни как query-параметра, ни в схеме)."""
    r = client.get(f"{PUBLIC_URL}?placement=services")
    assert r.status_code == 200  # неизвестный query-параметр молча игнорируется FastAPI


# ═══════════════════════════════════════════════════════════════════════════
# Удаление (физическое)
# ═══════════════════════════════════════════════════════════════════════════

def test_admin_can_delete_card(client):
    tok, _ = _make_user(client, "admin")
    card = _create(client, tok).json()

    r = client.delete(f"{URL}/{card['id']}", headers=_auth(tok))
    assert r.status_code == 204

    with SessionLocal() as db:
        assert db.query(ServiceCard).filter(ServiceCard.id == card["id"]).first() is None

    assert len(_audit_rows("service_card_deleted", card["id"])) == 1


def test_supervisor_can_delete_card(client):
    tok, _ = _make_user(client, "supervisor")
    card = _create(client, tok).json()
    assert client.delete(f"{URL}/{card['id']}", headers=_auth(tok)).status_code == 204


def test_other_roles_cannot_delete(client):
    tok_admin, _ = _make_user(client, "admin")
    card = _create(client, tok_admin).json()

    for role in ("student", "psychologist"):
        tok, _ = _make_user(client, role)
        r = client.delete(f"{URL}/{card['id']}", headers=_auth(tok))
        assert r.status_code == 403, (role, r.text)


def test_delete_unknown_id_returns_404(client):
    tok, _ = _make_user(client, "admin")
    assert client.delete(f"{URL}/99999999", headers=_auth(tok)).status_code == 404


def test_deleted_card_disappears_from_public_endpoint(client):
    tok, _ = _make_user(client, "admin")
    card = _create(client, tok).json()

    assert client.delete(f"{URL}/{card['id']}", headers=_auth(tok)).status_code == 204

    titles = [i["title"] for i in client.get(PUBLIC_URL).json()]
    assert card["title"] not in titles
