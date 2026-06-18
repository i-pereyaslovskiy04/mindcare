"""
Integration tests for Diary backend (Stage Diary Backend).

Покрывает:
  - GET /api/diary/emotions — активный справочник
  - GET /api/diary/today — пустая запись при отсутствии
  - PUT /api/diary/today — создание записи
  - повторный PUT /today — обновляет, не создаёт вторую
  - mood_score < 1 → 422; mood_score > 10 → 422
  - неизвестный emotion key → 422
  - неактивный emotion key → 422
  - GET /api/diary/entries — только свои записи
  - другой student не видит чужие записи
  - psychologist / admin / supervisor → 403
  - в БД mood_score_enc начинается с enc:v1:
  - в БД entry_text_enc начинается с enc:v1: (когда текст задан)
  - в БД emotions_enc начинается с enc:v1:
  - plaintext entry_text не лежит в БД
  - GET /api/diary/summary?period=14d → точки и null для дней без записи
  - summary отклоняет неизвестный period → 422

Требования: dev PostgreSQL на alembic head (b2e4d7f1a9c3), DATA_ENCRYPTION_KEY.
"""

import bcrypt
import pytest

from app.auth import storage as auth_storage
from app.core.encryption import ENCRYPTION_PREFIX
from app.db.session import SessionLocal
from app.db.models import DiaryEntry, DiaryEmotion

PASSWORD = "SecurePass42!"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_user(client, role: str) -> tuple[str, int]:
    """(token, user_id)."""
    import uuid as _uuid
    user = auth_storage.save_user({
        "name":            f"Diary {role.capitalize()} {_uuid.uuid4().hex[:6]}",
        "email":           f"integ_diary_{role}_{_uuid.uuid4().hex[:10]}@example.com",
        "hashed_password": bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode(),
        "role":            role,
    })
    r = client.post("/api/auth/login", json={"email": user["email"], "password": PASSWORD})
    assert r.status_code == 200
    return r.json()["session_token"], int(user["id"])


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _put_today(client, token: str, payload: dict) -> "Response":
    return client.put("/api/diary/today", headers=_auth(token), json=payload)


def _create_inactive_emotion(key: str = "test_inactive_emo") -> None:
    with SessionLocal() as db:
        existing = db.query(DiaryEmotion).filter(DiaryEmotion.key == key).first()
        if not existing:
            db.add(DiaryEmotion(key=key, label="Тестовая неактивная", sort_order=99, is_active=False))
            db.commit()


def _delete_inactive_emotion(key: str = "test_inactive_emo") -> None:
    with SessionLocal() as db:
        db.query(DiaryEmotion).filter(DiaryEmotion.key == key).delete(synchronize_session=False)
        db.commit()


# ─── 1. Emotions справочник ───────────────────────────────────────────────────

class TestEmotions:
    def test_emotions_returns_active_list(self, client):
        token, _ = _make_user(client, "student")
        r = client.get("/api/diary/emotions", headers=_auth(token))
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 10
        keys = [e["key"] for e in data]
        assert "calm" in keys
        assert "focused" in keys

    def test_emotions_sorted_by_sort_order(self, client):
        token, _ = _make_user(client, "student")
        r = client.get("/api/diary/emotions", headers=_auth(token))
        data = r.json()
        orders = [e["sort_order"] for e in data]
        assert orders == sorted(orders)

    def test_emotions_has_required_fields(self, client):
        token, _ = _make_user(client, "student")
        r = client.get("/api/diary/emotions", headers=_auth(token))
        first = r.json()[0]
        assert "key" in first
        assert "label" in first
        assert "sort_order" in first


# ─── 2. GET /today ────────────────────────────────────────────────────────────

class TestGetToday:
    def test_empty_today_when_no_entry(self, client):
        token, _ = _make_user(client, "student")
        r = client.get("/api/diary/today", headers=_auth(token))
        assert r.status_code == 200
        data = r.json()
        assert data["mood_score"] is None
        assert data["entry_text"] == ""
        assert data["emotions"] == []
        assert "entry_date" in data

    def test_today_returns_entry_after_put(self, client):
        token, _ = _make_user(client, "student")
        _put_today(client, token, {"mood_score": 7, "entry_text": "Норм", "emotions": ["calm"]})
        r = client.get("/api/diary/today", headers=_auth(token))
        assert r.status_code == 200
        data = r.json()
        assert data["mood_score"] == 7
        assert data["entry_text"] == "Норм"
        assert "calm" in data["emotions"]


# ─── 3. PUT /today ────────────────────────────────────────────────────────────

class TestPutToday:
    def test_create_entry(self, client):
        token, _ = _make_user(client, "student")
        r = _put_today(client, token, {
            "mood_score": 8,
            "entry_text": "Хороший день",
            "emotions":   ["joyful", "focused"],
        })
        assert r.status_code == 200
        data = r.json()
        assert data["mood_score"] == 8
        assert data["entry_text"] == "Хороший день"
        assert set(data["emotions"]) == {"joyful", "focused"}

    def test_update_does_not_create_second_entry(self, client):
        token, uid = _make_user(client, "student")
        _put_today(client, token, {"mood_score": 5, "emotions": []})
        _put_today(client, token, {"mood_score": 6, "emotions": []})

        with SessionLocal() as db:
            from datetime import date
            count = (
                db.query(DiaryEntry)
                .filter(
                    DiaryEntry.student_id == uid,
                    DiaryEntry.entry_date == date.today(),
                    DiaryEntry.deleted_at.is_(None),
                )
                .count()
            )
        assert count == 1

    def test_update_changes_mood_score(self, client):
        token, _ = _make_user(client, "student")
        _put_today(client, token, {"mood_score": 3, "emotions": []})
        _put_today(client, token, {"mood_score": 9, "emotions": []})
        r = client.get("/api/diary/today", headers=_auth(token))
        assert r.json()["mood_score"] == 9

    def test_mood_score_below_1_returns_422(self, client):
        token, _ = _make_user(client, "student")
        r = _put_today(client, token, {"mood_score": 0, "emotions": []})
        assert r.status_code == 422

    def test_mood_score_above_10_returns_422(self, client):
        token, _ = _make_user(client, "student")
        r = _put_today(client, token, {"mood_score": 11, "emotions": []})
        assert r.status_code == 422

    def test_unknown_emotion_key_returns_422(self, client):
        token, _ = _make_user(client, "student")
        r = _put_today(client, token, {"mood_score": 5, "emotions": ["nonexistent_xyz"]})
        assert r.status_code == 422

    def test_inactive_emotion_key_returns_422(self, client):
        _create_inactive_emotion("test_inactive_emo")
        try:
            token, _ = _make_user(client, "student")
            r = _put_today(client, token, {"mood_score": 5, "emotions": ["test_inactive_emo"]})
            assert r.status_code == 422
        finally:
            _delete_inactive_emotion("test_inactive_emo")

    def test_duplicate_emotions_are_deduplicated(self, client):
        token, _ = _make_user(client, "student")
        r = _put_today(client, token, {
            "mood_score": 5,
            "emotions":   ["calm", "calm", "tired"],
        })
        assert r.status_code == 200
        emotions = r.json()["emotions"]
        assert emotions.count("calm") == 1

    def test_empty_emotions_accepted(self, client):
        token, _ = _make_user(client, "student")
        r = _put_today(client, token, {"mood_score": 5, "emotions": []})
        assert r.status_code == 200
        assert r.json()["emotions"] == []


# ─── 4. Encryption at-rest ────────────────────────────────────────────────────

class TestEncryptionAtRest:
    def test_mood_score_enc_starts_with_prefix(self, client):
        token, uid = _make_user(client, "student")
        _put_today(client, token, {"mood_score": 4, "entry_text": "Проверка", "emotions": ["sad"]})
        with SessionLocal() as db:
            from datetime import date
            entry = db.query(DiaryEntry).filter(
                DiaryEntry.student_id == uid,
                DiaryEntry.entry_date == date.today(),
                DiaryEntry.deleted_at.is_(None),
            ).first()
            assert entry is not None
            assert entry.mood_score_enc.startswith(ENCRYPTION_PREFIX)

    def test_entry_text_enc_starts_with_prefix(self, client):
        token, uid = _make_user(client, "student")
        _put_today(client, token, {"mood_score": 6, "entry_text": "Секретный текст", "emotions": []})
        with SessionLocal() as db:
            from datetime import date
            entry = db.query(DiaryEntry).filter(
                DiaryEntry.student_id == uid,
                DiaryEntry.entry_date == date.today(),
                DiaryEntry.deleted_at.is_(None),
            ).first()
            assert entry.entry_text_enc is not None
            assert entry.entry_text_enc.startswith(ENCRYPTION_PREFIX)

    def test_emotions_enc_starts_with_prefix(self, client):
        token, uid = _make_user(client, "student")
        _put_today(client, token, {"mood_score": 5, "emotions": ["calm"]})
        with SessionLocal() as db:
            from datetime import date
            entry = db.query(DiaryEntry).filter(
                DiaryEntry.student_id == uid,
                DiaryEntry.entry_date == date.today(),
                DiaryEntry.deleted_at.is_(None),
            ).first()
            assert entry.emotions_enc.startswith(ENCRYPTION_PREFIX)

    def test_plaintext_entry_text_not_in_db(self, client):
        token, uid = _make_user(client, "student")
        plaintext = "Уникальный текст дневника 12345 xyz"
        _put_today(client, token, {"mood_score": 5, "entry_text": plaintext, "emotions": []})
        with SessionLocal() as db:
            from datetime import date
            entry = db.query(DiaryEntry).filter(
                DiaryEntry.student_id == uid,
                DiaryEntry.entry_date == date.today(),
                DiaryEntry.deleted_at.is_(None),
            ).first()
            assert entry.entry_text_enc != plaintext
            assert plaintext not in (entry.entry_text_enc or "")

    def test_entry_text_enc_null_when_no_text(self, client):
        token, uid = _make_user(client, "student")
        _put_today(client, token, {"mood_score": 5, "emotions": []})
        with SessionLocal() as db:
            from datetime import date
            entry = db.query(DiaryEntry).filter(
                DiaryEntry.student_id == uid,
                DiaryEntry.entry_date == date.today(),
                DiaryEntry.deleted_at.is_(None),
            ).first()
            assert entry.entry_text_enc is None


# ─── 5. Entries list ──────────────────────────────────────────────────────────

class TestEntries:
    def test_entries_returns_own_records(self, client):
        token, _ = _make_user(client, "student")
        _put_today(client, token, {"mood_score": 7, "emotions": ["calm"]})
        r = client.get("/api/diary/entries", headers=_auth(token))
        assert r.status_code == 200
        data = r.json()
        assert data["total"] >= 1
        assert len(data["items"]) >= 1

    def test_student_cannot_see_other_student_entries(self, client):
        token1, _ = _make_user(client, "student")
        token2, _ = _make_user(client, "student")

        _put_today(client, token1, {"mood_score": 5, "emotions": []})
        r = client.get("/api/diary/entries", headers=_auth(token2))
        assert r.status_code == 200
        # student2 видит только свои (0 записей, т.к. только student1 писал)
        data = r.json()
        assert data["total"] == 0

    def test_entries_pagination_limit_offset(self, client):
        token, _ = _make_user(client, "student")
        _put_today(client, token, {"mood_score": 5, "emotions": []})
        r = client.get("/api/diary/entries?limit=1&offset=0", headers=_auth(token))
        assert r.status_code == 200
        data = r.json()
        assert data["limit"] == 1
        assert data["offset"] == 0
        assert len(data["items"]) <= 1


# ─── 6. Access control ────────────────────────────────────────────────────────

class TestAccessControl:
    @pytest.mark.parametrize("role", ["psychologist", "admin", "supervisor"])
    def test_non_student_gets_403_on_today(self, client, role):
        token, _ = _make_user(client, role)
        r = client.get("/api/diary/today", headers=_auth(token))
        assert r.status_code == 403

    @pytest.mark.parametrize("role", ["psychologist", "admin", "supervisor"])
    def test_non_student_gets_403_on_put_today(self, client, role):
        token, _ = _make_user(client, role)
        r = _put_today(client, token, {"mood_score": 5, "emotions": []})
        assert r.status_code == 403

    @pytest.mark.parametrize("role", ["psychologist", "admin", "supervisor"])
    def test_non_student_gets_403_on_entries(self, client, role):
        token, _ = _make_user(client, role)
        r = client.get("/api/diary/entries", headers=_auth(token))
        assert r.status_code == 403

    @pytest.mark.parametrize("role", ["psychologist", "admin", "supervisor"])
    def test_non_student_gets_403_on_emotions(self, client, role):
        token, _ = _make_user(client, role)
        r = client.get("/api/diary/emotions", headers=_auth(token))
        assert r.status_code == 403

    @pytest.mark.parametrize("role", ["psychologist", "admin", "supervisor"])
    def test_non_student_gets_403_on_summary(self, client, role):
        token, _ = _make_user(client, role)
        r = client.get("/api/diary/summary?period=14d", headers=_auth(token))
        assert r.status_code == 403

    def test_unauthenticated_gets_401(self, client):
        r = client.get("/api/diary/today")
        assert r.status_code == 401


# ─── 7. Summary ───────────────────────────────────────────────────────────────

class TestSummary:
    def test_summary_14d_has_14_points(self, client):
        token, _ = _make_user(client, "student")
        r = client.get("/api/diary/summary?period=14d", headers=_auth(token))
        assert r.status_code == 200
        data = r.json()
        assert data["period"] == "14d"
        assert len(data["points"]) == 14

    def test_summary_null_for_days_without_entry(self, client):
        token, _ = _make_user(client, "student")
        r = client.get("/api/diary/summary?period=14d", headers=_auth(token))
        data = r.json()
        null_points = [p for p in data["points"] if p["mood_score"] is None]
        assert len(null_points) > 0

    def test_summary_reflects_created_entry(self, client):
        token, _ = _make_user(client, "student")
        _put_today(client, token, {"mood_score": 7, "emotions": ["calm"]})
        r = client.get("/api/diary/summary?period=14d", headers=_auth(token))
        data = r.json()
        today_str = str(__import__("datetime").date.today())
        today_point = next((p for p in data["points"] if p["date"] == today_str), None)
        assert today_point is not None
        assert today_point["mood_score"] == 7

    def test_summary_entries_count(self, client):
        token, _ = _make_user(client, "student")
        _put_today(client, token, {"mood_score": 5, "emotions": []})
        r = client.get("/api/diary/summary?period=14d", headers=_auth(token))
        data = r.json()
        assert data["entries_count"] >= 1

    def test_summary_points_have_label(self, client):
        token, _ = _make_user(client, "student")
        r = client.get("/api/diary/summary?period=14d", headers=_auth(token))
        data = r.json()
        valid_labels = {"Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"}
        for point in data["points"]:
            assert point["label"] in valid_labels

    def test_summary_unknown_period_returns_422(self, client):
        token, _ = _make_user(client, "student")
        r = client.get("/api/diary/summary?period=unknown", headers=_auth(token))
        assert r.status_code == 422

    def test_summary_month_period(self, client):
        token, _ = _make_user(client, "student")
        r = client.get("/api/diary/summary?period=month", headers=_auth(token))
        assert r.status_code == 200
        data = r.json()
        assert data["period"] == "month"
        assert len(data["points"]) >= 1

    def test_summary_year_period(self, client):
        token, _ = _make_user(client, "student")
        r = client.get("/api/diary/summary?period=year", headers=_auth(token))
        assert r.status_code == 200
        data = r.json()
        assert data["period"] == "year"
        assert len(data["points"]) >= 1
