"""
Integration tests for self-profile API (GET/PATCH /api/auth/profile).

Endpoint is общий для всех ролей: каждый пользователь читает/правит ТОЛЬКО
свой профиль (user_id берётся из сессии, не из body/URL).

Editable self-fields: full_name, phone. email/role/is_active менять нельзя
(ProfileUpdate с extra='forbid' → 422).

Requires: dev PostgreSQL on alembic head, DATA_ENCRYPTION_KEY in .env.
"""

import uuid as _uuid

import bcrypt

from app.auth import storage as auth_storage
from app.db.session import SessionLocal
from app.db.models import AuditLog, AuthLog, User

PASSWORD = "SecurePass42!"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_user(client, role: str = "student"):
    """Returns (token, user_id, email)."""
    suffix = _uuid.uuid4().hex[:10]
    email = f"integ_profile_{role}_{suffix}@example.com"
    user = auth_storage.save_user({
        "name": f"Profile {role.capitalize()} {_uuid.uuid4().hex[:6]}",
        "email": email,
        "hashed_password": bcrypt.hashpw(
            PASSWORD.encode(), bcrypt.gensalt()
        ).decode(),
        "role": role,
    })
    r = client.post(
        "/api/auth/login",
        json={"email": email, "password": PASSWORD},
    )
    assert r.status_code == 200, r.text
    return r.json()["session_token"], int(user["id"]), email


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ─── Tests ──────────────────────────────────────────────────────────────────

class TestSelfProfile:

    def test_01_student_reads_own_profile(self, client):
        tok, uid, email = _make_user(client, "student")
        r = client.get("/api/auth/profile", headers=_auth(tok))
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["id"] == str(uid)
        assert data["email"] == email
        assert data["role"] == "student"
        assert "full_name" in data
        assert "phone" in data  # null допустим

    def test_02_student_updates_name_and_phone(self, client):
        tok, uid, _ = _make_user(client, "student")
        r = client.patch(
            "/api/auth/profile",
            json={"full_name": "Иванов Иван Иванович",
                  "phone": "+7 (949) 123-45-67"},
            headers=_auth(tok),
        )
        assert r.status_code == 200, r.text
        assert r.json()["full_name"] == "Иванов Иван Иванович"
        assert r.json()["phone"] == "+7 (949) 123-45-67"

        # Повторный GET отдаёт обновлённые значения.
        r2 = client.get("/api/auth/profile", headers=_auth(tok))
        assert r2.json()["full_name"] == "Иванов Иван Иванович"
        assert r2.json()["phone"] == "+7 (949) 123-45-67"

        # GET /me тоже отражает новое имя (читается из БД на каждом запросе).
        r3 = client.get("/api/auth/me", headers=_auth(tok))
        assert r3.json()["name"] == "Иванов Иван Иванович"

    def test_03_full_name_is_trimmed(self, client):
        tok, _, _ = _make_user(client, "student")
        r = client.patch(
            "/api/auth/profile",
            json={"full_name": "  Пётр Петров  ", "phone": None},
            headers=_auth(tok),
        )
        assert r.status_code == 200, r.text
        assert r.json()["full_name"] == "Пётр Петров"

    def test_04_empty_phone_becomes_null(self, client):
        tok, _, _ = _make_user(client, "student")
        # Сначала задаём телефон, затем очищаем пустой строкой.
        client.patch(
            "/api/auth/profile",
            json={"full_name": "Анна Сидорова", "phone": "+7 (949) 000-11-22"},
            headers=_auth(tok),
        )
        r = client.patch(
            "/api/auth/profile",
            json={"full_name": "Анна Сидорова", "phone": "   "},
            headers=_auth(tok),
        )
        assert r.status_code == 200, r.text
        assert r.json()["phone"] is None

    def test_05_cannot_change_email_or_role_via_body(self, client):
        tok, uid, email = _make_user(client, "student")
        r = client.patch(
            "/api/auth/profile",
            json={
                "full_name": "Новое Имя",
                "phone": None,
                "email": "hacker@example.com",
                "role": "admin",
                "is_active": False,
            },
            headers=_auth(tok),
        )
        # extra='forbid' → лишние поля дают 422.
        assert r.status_code == 422, r.text

        # email и роль в БД не изменились.
        with SessionLocal() as db:
            u = db.query(User).filter(User.id == uid).first()
            assert u.email == email
            assert u.is_active is True

    def test_06_short_full_name_rejected(self, client):
        tok, _, _ = _make_user(client, "student")
        r = client.patch(
            "/api/auth/profile",
            json={"full_name": "A", "phone": None},
            headers=_auth(tok),
        )
        assert r.status_code == 422, r.text

    def test_07_unauthenticated_rejected(self, client):
        r_get = client.get("/api/auth/profile")
        assert r_get.status_code in (401, 403)
        r_patch = client.patch(
            "/api/auth/profile",
            json={"full_name": "Кто-то", "phone": None},
        )
        assert r_patch.status_code in (401, 403)

    def test_08_psychologist_reads_and_updates_own_profile(self, client):
        tok, uid, email = _make_user(client, "psychologist")
        r = client.get("/api/auth/profile", headers=_auth(tok))
        assert r.status_code == 200, r.text
        assert r.json()["role"] == "psychologist"
        assert r.json()["email"] == email

        r2 = client.patch(
            "/api/auth/profile",
            json={"full_name": "Психолог Тестовый", "phone": None},
            headers=_auth(tok),
        )
        assert r2.status_code == 200, r2.text
        assert r2.json()["full_name"] == "Психолог Тестовый"

    def test_10_theme_prefs_default_null(self, client):
        tok, _, _ = _make_user(client, "student")
        r = client.get("/api/auth/profile", headers=_auth(tok))
        assert r.status_code == 200, r.text
        # «Не задано» → тему определяет устройство (localStorage).
        assert r.json()["ui_theme_palette"] is None
        assert r.json()["ui_theme_mode"] is None

    def test_11_theme_prefs_roundtrip(self, client):
        tok, _, _ = _make_user(client, "student")
        r = client.patch(
            "/api/auth/profile",
            json={
                "full_name": "Тема Тестовая",
                "phone": None,
                "ui_theme_palette": "nature",
                "ui_theme_mode": "dark",
            },
            headers=_auth(tok),
        )
        assert r.status_code == 200, r.text
        assert r.json()["ui_theme_palette"] == "nature"
        assert r.json()["ui_theme_mode"] == "dark"

        r2 = client.get("/api/auth/profile", headers=_auth(tok))
        assert r2.json()["ui_theme_palette"] == "nature"
        assert r2.json()["ui_theme_mode"] == "dark"

    def test_12_invalid_theme_value_rejected(self, client):
        tok, _, _ = _make_user(client, "student")
        r = client.patch(
            "/api/auth/profile",
            json={"full_name": "Тема Тестовая", "phone": None,
                  "ui_theme_palette": "neon"},
            headers=_auth(tok),
        )
        assert r.status_code == 422, r.text

        r2 = client.patch(
            "/api/auth/profile",
            json={"full_name": "Тема Тестовая", "phone": None,
                  "ui_theme_mode": "sepia"},
            headers=_auth(tok),
        )
        assert r2.status_code == 422, r2.text

    def test_13_patch_without_theme_fields_keeps_them(self, client):
        tok, _, _ = _make_user(client, "student")
        client.patch(
            "/api/auth/profile",
            json={"full_name": "Тема Сохранена", "phone": None,
                  "ui_theme_palette": "classic", "ui_theme_mode": "light"},
            headers=_auth(tok),
        )
        # PATCH без полей темы не должен их обнулять (unset ≠ None).
        r = client.patch(
            "/api/auth/profile",
            json={"full_name": "Другое Имя", "phone": None},
            headers=_auth(tok),
        )
        assert r.status_code == 200, r.text
        assert r.json()["ui_theme_palette"] == "classic"
        assert r.json()["ui_theme_mode"] == "light"

    def test_14_theme_can_be_reset_to_null(self, client):
        tok, _, _ = _make_user(client, "student")
        client.patch(
            "/api/auth/profile",
            json={"full_name": "Тема Сброс", "phone": None,
                  "ui_theme_palette": "coffee", "ui_theme_mode": "system"},
            headers=_auth(tok),
        )
        # Явный null сбрасывает в «не задано».
        r = client.patch(
            "/api/auth/profile",
            json={"full_name": "Тема Сброс", "phone": None,
                  "ui_theme_palette": None, "ui_theme_mode": None},
            headers=_auth(tok),
        )
        assert r.status_code == 200, r.text
        assert r.json()["ui_theme_palette"] is None
        assert r.json()["ui_theme_mode"] is None

    def test_15_theme_only_patch_keeps_name_and_phone(self, client):
        tok, _, _ = _make_user(client, "student")
        client.patch(
            "/api/auth/profile",
            json={"full_name": "Имя Сохранено", "phone": "+7 (949) 555-00-11"},
            headers=_auth(tok),
        )
        # PATCH только темы (без ФИО/телефона) не должен их обнулять.
        r = client.patch(
            "/api/auth/profile",
            json={"ui_theme_mode": "dark"},
            headers=_auth(tok),
        )
        assert r.status_code == 200, r.text
        assert r.json()["full_name"] == "Имя Сохранено"
        assert r.json()["phone"] == "+7 (949) 555-00-11"
        assert r.json()["ui_theme_mode"] == "dark"

    def test_09_admin_updates_only_own_profile(self, client):
        tok_admin, admin_id, _ = _make_user(client, "admin")
        _, other_id, other_email = _make_user(client, "student")

        # admin правит свой профиль — затрагивается только он.
        r = client.patch(
            "/api/auth/profile",
            json={"full_name": "Админ Обновлённый", "phone": None},
            headers=_auth(tok_admin),
        )
        assert r.status_code == 200, r.text
        assert r.json()["id"] == str(admin_id)

        # Профиль другого пользователя не тронут.
        with SessionLocal() as db:
            other = db.query(User).filter(User.id == other_id).first()
            assert other.email == other_email
            assert other.full_name != "Админ Обновлённый"


# ─── Stage 4B-4 — profile_updated audit (gated, requires PostgreSQL) ──────────

def _profile_updated_rows(uid):
    with SessionLocal() as db:
        rows = (
            db.query(AuditLog)
            .filter(
                AuditLog.event_type == "profile_updated",
                AuditLog.entity_type == "user",
                AuditLog.entity_id == uid,
            )
            # Детерминированный порядок — created_at может совпадать до
            # микросекунды на быстрых последовательных PATCH; id — надёжный
            # tie-breaker (append-only BigInteger PK, растёт монотонно).
            .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
            .all()
        )
        for r in rows:
            db.expunge(r)
        return rows


def _auth_log_rows_for_user(uid, event_prefix):
    with SessionLocal() as db:
        rows = (
            db.query(AuthLog)
            .filter(AuthLog.user_id == uid, AuthLog.event.like(f"{event_prefix}%"))
            .all()
        )
        for r in rows:
            db.expunge(r)
        return rows


class TestSelfProfileAudit:

    def test_full_name_and_phone_change_writes_exact_fields(self, client):
        tok, uid, _ = _make_user(client, "student")
        r = client.patch(
            "/api/auth/profile",
            json={"full_name": "Иванов Иван Иванович",
                  "phone": "+7 (949) 123-45-67"},
            headers=_auth(tok),
        )
        assert r.status_code == 200, r.text

        rows = _profile_updated_rows(uid)
        assert len(rows) == 1
        row = rows[0]
        assert row.user_id == uid                 # self-action: actor == target
        assert row.entity_id == uid
        assert set(row.log_metadata["fields"]) == {"full_name", "phone"}
        # Stage 4B-4 corrective pass: точный контракт success-события.
        assert row.outcome == "success"
        assert row.failure_reason_code is None
        assert row.description is None
        blob = str(row.log_metadata)
        assert "Иванов Иван Иванович" not in blob
        assert "+7 (949) 123-45-67" not in blob

        # Legacy auth_log event="profile_update" не пишется вообще (Stage 4B-4
        # перенёс это событие в audit_log как profile_updated).
        assert _auth_log_rows_for_user(uid, "profile_update") == []

    def test_repeat_same_value_patch_after_real_change_writes_only_changed_field(self, client):
        tok, uid, _ = _make_user(client, "student")
        client.patch(
            "/api/auth/profile",
            json={"full_name": "Имя Первое", "phone": "+70001112233"},
            headers=_auth(tok),
        )
        # Второй PATCH: phone тот же самый, full_name — новый.
        r = client.patch(
            "/api/auth/profile",
            json={"full_name": "Имя Второе", "phone": "+70001112233"},
            headers=_auth(tok),
        )
        assert r.status_code == 200, r.text

        rows = _profile_updated_rows(uid)   # детерминированный порядок (id asc)
        assert len(rows) == 2   # одна строка на каждый PATCH с реальным изменением
        assert set(rows[-1].log_metadata["fields"]) == {"full_name"}

    def test_theme_only_change_does_not_write_profile_updated(self, client):
        tok, uid, _ = _make_user(client, "student")
        with SessionLocal() as db:
            before = db.query(User.updated_at).filter(User.id == uid).scalar()

        r = client.patch(
            "/api/auth/profile",
            json={"ui_theme_mode": "dark"},
            headers=_auth(tok),
        )
        assert r.status_code == 200, r.text

        # Реальное изменение темы сдвигает updated_at (мутация применяется),
        # но НЕ пишет compliance-audit profile_updated.
        with SessionLocal() as db:
            after = db.query(User.updated_at).filter(User.id == uid).scalar()
        assert after != before
        assert _profile_updated_rows(uid) == []

        r2 = client.get("/api/auth/profile", headers=_auth(tok))
        assert r2.json()["ui_theme_mode"] == "dark"

    def test_identical_value_patch_is_true_no_op(self, client):
        tok, uid, _ = _make_user(client, "student")

        # Первый PATCH — реальное изменение (новый пользователь начинает без
        # этого имени) → должен создать ровно одну profile_updated строку.
        r1 = client.patch(
            "/api/auth/profile",
            json={"full_name": "Имя Стабильное", "phone": None},
            headers=_auth(tok),
        )
        assert r1.status_code == 200, r1.text
        rows_after_first = _profile_updated_rows(uid)
        assert len(rows_after_first) == 1
        count_before = len(rows_after_first)

        with SessionLocal() as db:
            before = db.query(User.updated_at).filter(User.id == uid).scalar()

        # Второй PATCH — идентичные значения (настоящий no-op).
        r2 = client.patch(
            "/api/auth/profile",
            json={"full_name": "Имя Стабильное", "phone": None},
            headers=_auth(tok),
        )
        assert r2.status_code == 200, r2.text

        # Append-only таблица — не очищаем; сравниваем количество ДО/ПОСЛЕ,
        # не абсолютную пустоту исторической выборки.
        rows_after_second = _profile_updated_rows(uid)
        assert len(rows_after_second) == count_before

        with SessionLocal() as db:
            after = db.query(User.updated_at).filter(User.id == uid).scalar()
        assert before == after   # updated_at НЕ сдвинулся на настоящем no-op

    def test_empty_patch_writes_nothing(self, client):
        tok, uid, _ = _make_user(client, "student")
        rows_before = len(_profile_updated_rows(uid))

        r = client.patch("/api/auth/profile", json={}, headers=_auth(tok))
        assert r.status_code == 200, r.text

        assert len(_profile_updated_rows(uid)) == rows_before


# ─── Stage 5A-2: profile_update_failed (durable best-effort failure) ──────────

def _profile_failed_rows(uid):
    with SessionLocal() as db:
        rows = (
            db.query(AuditLog)
            .filter(
                AuditLog.event_type == "profile_update_failed",
                AuditLog.user_id == uid,
                AuditLog.outcome == "failure",
            )
            .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
            .all()
        )
        for r in rows:
            db.expunge(r)
        return rows


def test_profile_full_name_too_short_writes_profile_update_failed(client):
    tok, uid, _ = _make_user(client, "student")
    before = len(_profile_failed_rows(uid))

    r = client.patch(
        "/api/auth/profile", json={"full_name": "X"}, headers=_auth(tok),
    )
    assert r.status_code == 422, r.text

    rows = _profile_failed_rows(uid)
    assert len(rows) == before + 1
    row = rows[-1]
    assert row.outcome == "failure"
    assert row.failure_reason_code == "invalid_request"
    assert row.user_id == uid and row.user_role == "student"   # actor = сам subject
    assert row.entity_type is None and row.entity_id is None    # target FORBIDDEN
    assert (row.log_metadata or {}) == {}
    assert row.description is None
    # profile_updated (success) НЕ пишется на этом отказе
    assert _profile_updated_rows(uid) == []
