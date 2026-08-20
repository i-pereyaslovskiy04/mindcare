"""
Integration-тесты admin CRUD allowlist почтовых доменов
(/api/admin/email-domains). Требуют dev PostgreSQL на alembic head.

Все тесты используют фикстуру reset_email_domains — восстановление seeded-набора
после теста (allowlist — общий стейт).
"""

import uuid as _uuid

import bcrypt

from app.auth import storage as auth_storage
from app.db.session import SessionLocal
from app.db.models import AllowedEmailDomain, AuditLog

PASSWORD = "SecurePass42!"
BASE = "/api/admin/email-domains/"


def _hash() -> str:
    return bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode()


def _make_user(client, role: str) -> str:
    """Совместимость со старыми тестами: возвращает только token."""
    token, _uid = _make_user_with_id(client, role)
    return token


def _make_user_with_id(client, role: str) -> tuple[str, int]:
    u = auth_storage.save_user({
        "name": f"Integ {role} {_uuid.uuid4().hex[:6]}",
        "email": f"integ_domadmin_{role}_{_uuid.uuid4().hex[:10]}@example.com",
        "hashed_password": _hash(),
        "role": role,
    })
    r = client.post(
        "/api/auth/login", json={"email": u["email"], "password": PASSWORD},
    )
    assert r.status_code == 200, r.text
    return r.json()["session_token"], int(u["id"])


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _temp_domain() -> str:
    return f"integ-{_uuid.uuid4().hex[:10]}.ru"


def _domain_row(domain: str):
    with SessionLocal() as db:
        row = (
            db.query(AllowedEmailDomain)
            .filter(AllowedEmailDomain.domain == domain)
            .first()
        )
        if row:
            db.expunge(row)
        return row


def _audit_rows(domain: str):
    # Stage 4B-2: metadata домена больше не пишется (→ {}), поэтому строки аудита
    # ищем по entity_id (id домена), а не по log_metadata["domain"].
    with SessionLocal() as db:
        dom = (
            db.query(AllowedEmailDomain)
            .filter(AllowedEmailDomain.domain == domain)
            .first()
        )
        if dom is None:
            return []
        rows = (
            db.query(AuditLog)
            .filter(
                AuditLog.entity_type == "allowed_email_domain",
                AuditLog.entity_id == dom.id,
            )
            .all()
        )
        for r in rows:
            db.expunge(r)
        return rows


# ─── Admin-only guards ────────────────────────────────────────────────────────

class TestAdminOnly:
    def test_student_forbidden(self, client, reset_email_domains):
        token = _make_user(client, "student")
        assert client.get(BASE, headers=_auth(token)).status_code == 403
        assert client.post(
            BASE, headers=_auth(token), json={"domain": _temp_domain()},
        ).status_code == 403
        assert client.patch(
            f"{BASE}1", headers=_auth(token), json={"is_active": False},
        ).status_code == 403

    def test_unauthenticated_401(self, client, reset_email_domains):
        assert client.get(BASE).status_code == 401


# ─── Add ──────────────────────────────────────────────────────────────────────

class TestAddDomain:
    def test_add_valid_201(self, client, reset_email_domains):
        token = _make_user(client, "admin")
        domain = _temp_domain()
        r = client.post(BASE, headers=_auth(token), json={"domain": domain})
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["domain"] == domain
        assert body["is_active"] is True
        assert body["comment"] is None
        # видно в списке
        listed = client.get(BASE, headers=_auth(token)).json()
        assert any(d["domain"] == domain for d in listed)

    def test_add_mixed_case_normalized(self, client, reset_email_domains):
        token = _make_user(client, "admin")
        suffix = _uuid.uuid4().hex[:10]
        r = client.post(
            BASE, headers=_auth(token),
            json={"domain": f"  Integ-{suffix}.RU  "},
        )
        assert r.status_code == 201, r.text
        assert r.json()["domain"] == f"integ-{suffix}.ru"

    def test_add_duplicate_seeded_409(self, client, reset_email_domains):
        token = _make_user(client, "admin")
        r = client.post(BASE, headers=_auth(token), json={"domain": "donnu.ru"})
        assert r.status_code == 409

    def test_add_duplicate_disabled_409(self, client, reset_email_domains):
        token = _make_user(client, "admin")
        domain = _temp_domain()
        created = client.post(BASE, headers=_auth(token), json={"domain": domain})
        dom_id = created.json()["id"]
        client.patch(
            f"{BASE}{dom_id}", headers=_auth(token), json={"is_active": False},
        )
        # повторный POST на отключённый домен → 409 (реактивация через PATCH)
        r = client.post(BASE, headers=_auth(token), json={"domain": domain})
        assert r.status_code == 409

    def test_add_invalid_422(self, client, reset_email_domains):
        token = _make_user(client, "admin")
        for bad in ("bad@domain.ru", "localhost", "http://x.ru", "x.ru:8080"):
            r = client.post(BASE, headers=_auth(token), json={"domain": bad})
            assert r.status_code == 422, (bad, r.status_code)

    def test_add_with_comment(self, client, reset_email_domains):
        token = _make_user(client, "admin")
        domain = _temp_domain()
        r = client.post(
            BASE, headers=_auth(token),
            json={"domain": domain, "comment": "  партнёрский вуз  "},
        )
        assert r.status_code == 201
        assert r.json()["comment"] == "партнёрский вуз"  # trim


# ─── Disable / reactivate / update ────────────────────────────────────────────

class TestPatchDomain:
    def _add(self, client, token, comment=None):
        domain = _temp_domain()
        body = {"domain": domain}
        if comment is not None:
            body["comment"] = comment
        r = client.post(BASE, headers=_auth(token), json=body)
        assert r.status_code == 201, r.text
        return r.json()

    def test_disable_then_reactivate(self, client, reset_email_domains):
        token, admin_id = _make_user_with_id(client, "admin")
        row = self._add(client, token)
        dom_id = row["id"]

        r = client.patch(
            f"{BASE}{dom_id}", headers=_auth(token), json={"is_active": False},
        )
        assert r.status_code == 200
        assert r.json()["is_active"] is False

        r = client.patch(
            f"{BASE}{dom_id}", headers=_auth(token), json={"is_active": True},
        )
        assert r.status_code == 200
        assert r.json()["is_active"] is True

        all_rows = _audit_rows(row["domain"])
        disable_rows = [a for a in all_rows if a.event_type == "email_domain_disable"]
        reactivate_rows = [
            a for a in all_rows if a.event_type == "email_domain_reactivate"
        ]
        assert len(disable_rows) == 1
        assert len(reactivate_rows) == 1
        for a in (disable_rows[0], reactivate_rows[0]):
            assert a.entity_type == "allowed_email_domain"
            assert a.entity_id == dom_id
            assert (a.log_metadata or {}) == {}
            assert a.description is None
            assert a.user_id == admin_id           # actor — текущий admin
            assert a.user_role == "admin"

    def test_comment_only_update_changes_updated_at(
        self, client, reset_email_domains,
    ):
        token, admin_id = _make_user_with_id(client, "admin")
        row = self._add(client, token)
        before = _domain_row(row["domain"]).updated_at
        r = client.patch(
            f"{BASE}{row['id']}", headers=_auth(token),
            json={"comment": "новый комментарий"},
        )
        assert r.status_code == 200
        assert r.json()["comment"] == "новый комментарий"
        after = _domain_row(row["domain"]).updated_at
        assert after > before
        # ровно одна строка email_domain_update, с корректным actor/target и
        # без комментария/description (comment может содержать ПДн).
        update_rows = [
            a for a in _audit_rows(row["domain"]) if a.event_type == "email_domain_update"
        ]
        assert len(update_rows) == 1
        a = update_rows[0]
        assert a.entity_type == "allowed_email_domain"
        assert a.entity_id == row["id"]
        assert (a.log_metadata or {}) == {}
        assert a.description is None
        assert a.user_id == admin_id
        assert a.user_role == "admin"
        assert "новый комментарий" not in str(a.log_metadata)
        assert a.description != "новый комментарий"

    def test_noop_patch_no_audit_no_updated_at(
        self, client, reset_email_domains,
    ):
        token = _make_user(client, "admin")
        row = self._add(client, token, comment="c")
        before = _domain_row(row["domain"]).updated_at
        audit_before = len(_audit_rows(row["domain"]))
        # is_active уже True, comment уже "c" → no-op
        r = client.patch(
            f"{BASE}{row['id']}", headers=_auth(token),
            json={"is_active": True, "comment": "c"},
        )
        assert r.status_code == 200
        after = _domain_row(row["domain"]).updated_at
        assert after == before                         # updated_at не тронут
        assert len(_audit_rows(row["domain"])) == audit_before  # без нового audit

    def test_empty_patch_body_422(self, client, reset_email_domains):
        token = _make_user(client, "admin")
        row = self._add(client, token)
        r = client.patch(f"{BASE}{row['id']}", headers=_auth(token), json={})
        assert r.status_code == 422

    def test_extra_field_forbidden_422(self, client, reset_email_domains):
        token = _make_user(client, "admin")
        row = self._add(client, token)
        r = client.patch(
            f"{BASE}{row['id']}", headers=_auth(token),
            json={"domain": "hacked.ru"},   # domain менять нельзя (extra=forbid)
        )
        assert r.status_code == 422

    def test_patch_not_found_404(self, client, reset_email_domains):
        token = _make_user(client, "admin")
        r = client.patch(
            f"{BASE}999999999", headers=_auth(token), json={"is_active": False},
        )
        assert r.status_code == 404

    def test_comment_explicit_null_clears(self, client, reset_email_domains):
        token = _make_user(client, "admin")
        row = self._add(client, token, comment="есть")
        r = client.patch(
            f"{BASE}{row['id']}", headers=_auth(token), json={"comment": None},
        )
        assert r.status_code == 200
        assert r.json()["comment"] is None


# ─── Last active domain guard ─────────────────────────────────────────────────

class TestLastActiveGuard:
    def test_cannot_disable_last_active(self, client, reset_email_domains):
        token = _make_user(client, "admin")
        # Прямо в БД оставляем ровно один активный домен (donnu.ru), остальные
        # отключаем. Затем через API пытаемся отключить последний → 409.
        with SessionLocal() as db:
            db.query(AllowedEmailDomain).filter(
                AllowedEmailDomain.domain != "donnu.ru",
            ).update({"is_active": False}, synchronize_session=False)
            db.commit()
            last_id = (
                db.query(AllowedEmailDomain.id)
                .filter(AllowedEmailDomain.domain == "donnu.ru")
                .scalar()
            )
        r = client.patch(
            f"{BASE}{last_id}", headers=_auth(token), json={"is_active": False},
        )
        assert r.status_code == 409


# ─── Audit не содержит сырой comment / domain / description (Stage 4B-2) ───────

class TestAuditNoRawComment:
    def test_audit_metadata_shape(self, client, reset_email_domains):
        token, admin_id = _make_user_with_id(client, "admin")
        secret_comment = "ФИО Иванов +79001234567"
        domain = _temp_domain()
        created = client.post(
            BASE, headers=_auth(token),
            json={"domain": domain, "comment": secret_comment},
        )
        assert created.status_code == 201, created.text
        dom_id = created.json()["id"]

        rows = _audit_rows(domain)
        assert rows, "должно быть audit-событие email_domain_add"
        for a in rows:
            # metadata пуста, description не пишется (facade); subject — ТОЛЬКО
            # entity_type/entity_id (не domain/comment в metadata/description).
            assert (a.log_metadata or {}) == {}
            assert a.description is None
            assert a.event_type == "email_domain_add"
            assert a.entity_type == "allowed_email_domain"
            assert a.entity_id == dom_id
            assert a.user_id == admin_id
            # сырой комментарий (ПДн) и сам domain в audit не пишутся нигде
            assert secret_comment not in str(a.log_metadata)
            assert secret_comment != a.description
            assert domain not in str(a.log_metadata)
