"""
Integration tests for Diary backend (Stage Diary Backend + Chart Hotfix 2 + Catalog Update).

Покрывает:
  - GET /api/diary/emotions — активный справочник
  - обновлённый каталог: 12 активных состояний, tense/irritated/low/lonely,
    angry/light — деактивированы и не возвращаются API
  - GET /api/diary/today — пустая запись при отсутствии
  - PUT /api/diary/today — создание записи
  - повторный PUT /today — обновляет, не создаёт вторую
  - mood_score < 1 → 422; mood_score > 10 → 422
  - неизвестный emotion key → 422
  - неактивный emotion key → 422 (в т.ч. deprecated: angry, light)
  - GET /api/diary/entries — только свои записи
  - другой student не видит чужие записи
  - psychologist / admin / supervisor → 403
  - в БД mood_score_enc начинается с enc:v1:
  - в БД entry_text_enc начинается с enc:v1: (когда текст задан)
  - в БД emotions_enc начинается с enc:v1:
  - plaintext entry_text не лежит в БД
  - GET /api/diary/summary — fixed calendar period frame, year monthly aggregation
  - summary отклоняет неизвестный period → 422

Требования: dev PostgreSQL на alembic head (c3a7f8e2d1b9), DATA_ENCRYPTION_KEY.
"""

import json as _json
from datetime import date, timedelta

import bcrypt
import pytest

from app.auth import storage as auth_storage
from app.core.encryption import ENCRYPTION_PREFIX, encrypt_text
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


def _insert_entry_direct(student_id: int, entry_date: date, mood_score: int) -> None:
    """Insert a historical diary entry directly via SQLAlchemy (bypasses today-only API)."""
    with SessionLocal() as db:
        db.add(DiaryEntry(
            student_id     = student_id,
            entry_date     = entry_date,
            mood_score_enc = encrypt_text(str(mood_score)),
            entry_text_enc = None,
            emotions_enc   = encrypt_text(_json.dumps([])),
        ))
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
    # ── No entries → full period frame with all null ───────────────────────────

    def test_summary_14d_no_entries_returns_14_null_points(self, client):
        token, _ = _make_user(client, "student")
        r = client.get("/api/diary/summary?period=14d", headers=_auth(token))
        assert r.status_code == 200
        data = r.json()
        assert data["period"] == "14d"
        assert data["entries_count"] == 0
        assert len(data["points"]) == 14
        assert all(p["mood_score"] is None for p in data["points"])

    def test_summary_month_no_entries_returns_full_frame_null_points(self, client):
        token, _ = _make_user(client, "student")
        r = client.get("/api/diary/summary?period=month", headers=_auth(token))
        assert r.status_code == 200
        data = r.json()
        assert data["entries_count"] == 0
        assert len(data["points"]) == date.today().day
        assert all(p["mood_score"] is None for p in data["points"])

    def test_summary_year_no_entries_returns_full_frame_null_points(self, client):
        token, _ = _make_user(client, "student")
        r = client.get("/api/diary/summary?period=year", headers=_auth(token))
        assert r.status_code == 200
        data = r.json()
        assert data["entries_count"] == 0
        assert len(data["points"]) == 12
        assert all(p["mood_score"] is None for p in data["points"])

    # ── Unknown period ────────────────────────────────────────────────────────

    def test_summary_unknown_period_returns_422(self, client):
        token, _ = _make_user(client, "student")
        r = client.get("/api/diary/summary?period=unknown", headers=_auth(token))
        assert r.status_code == 422

    # ── 14d: fixed 14-slot calendar frame ─────────────────────────────────────

    def test_summary_14d_always_14_points(self, client):
        token, _ = _make_user(client, "student")
        r = client.get("/api/diary/summary?period=14d", headers=_auth(token))
        data = r.json()
        assert len(data["points"]) == 14

    def test_summary_14d_start_is_today_minus_13(self, client):
        token, _ = _make_user(client, "student")
        r = client.get("/api/diary/summary?period=14d", headers=_auth(token))
        data = r.json()
        expected_start = (date.today() - timedelta(days=13)).isoformat()
        assert data["points"][0]["date"] == expected_start

    def test_summary_14d_end_is_today(self, client):
        token, _ = _make_user(client, "student")
        r = client.get("/api/diary/summary?period=14d", headers=_auth(token))
        data = r.json()
        assert data["points"][-1]["date"] == date.today().isoformat()

    def test_summary_14d_today_label_is_segodnya(self, client):
        token, _ = _make_user(client, "student")
        r = client.get("/api/diary/summary?period=14d", headers=_auth(token))
        data = r.json()
        assert data["points"][-1]["label"] == "Сегодня"

    def test_summary_14d_other_labels_are_weekdays(self, client):
        token, _ = _make_user(client, "student")
        r = client.get("/api/diary/summary?period=14d", headers=_auth(token))
        data = r.json()
        valid_labels = {"Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"}
        for point in data["points"][:-1]:  # все кроме последнего (today = "Сегодня")
            assert point["label"] in valid_labels

    def test_summary_14d_null_for_days_without_entry(self, client):
        token, _ = _make_user(client, "student")
        r = client.get("/api/diary/summary?period=14d", headers=_auth(token))
        data = r.json()
        assert all(p["mood_score"] is None for p in data["points"])

    def test_summary_14d_reflects_entry_mood_score(self, client):
        token, _ = _make_user(client, "student")
        _put_today(client, token, {"mood_score": 7, "emotions": ["calm"]})
        r = client.get("/api/diary/summary?period=14d", headers=_auth(token))
        data = r.json()
        today_str = date.today().isoformat()
        today_point = next((p for p in data["points"] if p["date"] == today_str), None)
        assert today_point is not None
        assert today_point["mood_score"] == 7

    def test_summary_14d_entries_count(self, client):
        token, _ = _make_user(client, "student")
        _put_today(client, token, {"mood_score": 5, "emotions": []})
        r = client.get("/api/diary/summary?period=14d", headers=_auth(token))
        data = r.json()
        assert data["entries_count"] == 1

    # ── month: fixed calendar frame from 1st to today ─────────────────────────

    def test_summary_month_starts_from_first_of_month(self, client):
        token, _ = _make_user(client, "student")
        r = client.get("/api/diary/summary?period=month", headers=_auth(token))
        data = r.json()
        first_of_month = date.today().replace(day=1).isoformat()
        assert data["points"][0]["date"] == first_of_month

    def test_summary_month_ends_today(self, client):
        token, _ = _make_user(client, "student")
        r = client.get("/api/diary/summary?period=month", headers=_auth(token))
        data = r.json()
        assert data["points"][-1]["date"] == date.today().isoformat()

    def test_summary_month_no_future_dates(self, client):
        token, _ = _make_user(client, "student")
        r = client.get("/api/diary/summary?period=month", headers=_auth(token))
        data = r.json()
        today_str = date.today().isoformat()
        for p in data["points"]:
            assert p["date"] <= today_str

    def test_summary_month_null_for_days_without_entry(self, client):
        token, _ = _make_user(client, "student")
        r = client.get("/api/diary/summary?period=month", headers=_auth(token))
        data = r.json()
        assert all(p["mood_score"] is None for p in data["points"])

    def test_summary_month_entries_count(self, client):
        token, _ = _make_user(client, "student")
        _put_today(client, token, {"mood_score": 5, "emotions": []})
        r = client.get("/api/diary/summary?period=month", headers=_auth(token))
        data = r.json()
        assert data["entries_count"] == 1

    # ── year: monthly aggregation from January ─────────────────────────────────

    def test_summary_year_always_12_points(self, client):
        token, _ = _make_user(client, "student")
        r = client.get("/api/diary/summary?period=year", headers=_auth(token))
        data = r.json()
        assert data["period"] == "year"
        assert len(data["points"]) == 12

    def test_summary_year_starts_from_january(self, client):
        token, _ = _make_user(client, "student")
        r = client.get("/api/diary/summary?period=year", headers=_auth(token))
        data = r.json()
        jan = date(date.today().year, 1, 1).isoformat()
        assert data["points"][0]["date"] == jan

    def test_summary_year_ends_at_december(self, client):
        token, _ = _make_user(client, "student")
        r = client.get("/api/diary/summary?period=year", headers=_auth(token))
        data = r.json()
        dec = date(date.today().year, 12, 1).isoformat()
        assert data["points"][-1]["date"] == dec

    def test_summary_year_future_months_are_null(self, client):
        # All 12 months returned; months after current month have null mood_score.
        token, _ = _make_user(client, "student")
        _put_today(client, token, {"mood_score": 7, "emotions": []})
        r = client.get("/api/diary/summary?period=year", headers=_auth(token))
        data = r.json()
        today = date.today()
        for p in data["points"]:
            point_date = date.fromisoformat(p["date"])
            if point_date > today.replace(day=1):
                assert p["mood_score"] is None, (
                    f"Future month {p['date']} must have null mood_score"
                )

    def test_summary_year_entries_count_excludes_future_null_months(self, client):
        # entries_count reflects only real diary entries, not 12-month frame size.
        token, _ = _make_user(client, "student")
        _put_today(client, token, {"mood_score": 5, "emotions": []})
        r = client.get("/api/diary/summary?period=year", headers=_auth(token))
        data = r.json()
        assert data["entries_count"] == 1  # one real entry, not 12

    def test_summary_year_month_without_entries_is_null(self, client):
        token, _ = _make_user(client, "student")
        r = client.get("/api/diary/summary?period=year", headers=_auth(token))
        data = r.json()
        # Fresh user → all months null
        assert all(p["mood_score"] is None for p in data["points"])

    def test_summary_year_average_mood_score_single_entry(self, client):
        token, _ = _make_user(client, "student")
        _put_today(client, token, {"mood_score": 8, "emotions": []})
        r = client.get("/api/diary/summary?period=year", headers=_auth(token))
        data = r.json()
        current_month = date.today().replace(day=1).isoformat()
        point = next((p for p in data["points"] if p["date"] == current_month), None)
        assert point is not None
        assert point["mood_score"] == 8

    def test_summary_year_average_mood_score_float(self, client):
        # Two entries in same month → float average
        token, uid = _make_user(client, "student")
        yesterday = date.today() - timedelta(days=1)
        if yesterday.month == date.today().month:
            _insert_entry_direct(uid, yesterday, 7)
            _put_today(client, token, {"mood_score": 8, "emotions": []})
            r = client.get("/api/diary/summary?period=year", headers=_auth(token))
            data = r.json()
            current_month = date.today().replace(day=1).isoformat()
            point = next((p for p in data["points"] if p["date"] == current_month), None)
            assert point is not None
            assert point["mood_score"] == 7.5  # avg(7, 8)
        else:
            pytest.skip("yesterday is in a different month")

    def test_summary_year_gap_month_is_null(self, client):
        # Entry 2 months ago + today → intermediate month has null
        token, uid = _make_user(client, "student")
        today = date.today()
        if today.month >= 3:
            two_months_ago = today.replace(day=1, month=today.month - 2)
            _insert_entry_direct(uid, two_months_ago, 8)
            _put_today(client, token, {"mood_score": 6, "emotions": []})

            r = client.get("/api/diary/summary?period=year", headers=_auth(token))
            data = r.json()
            # Month between two_months_ago and today must have null mood_score
            gap_month = two_months_ago.replace(month=two_months_ago.month + 1).isoformat()
            gap_point = next((p for p in data["points"] if p["date"] == gap_month), None)
            assert gap_point is not None
            assert gap_point["mood_score"] is None
        else:
            pytest.skip("month < 3 — can't create 2-month-ago entry in year window")

    def test_summary_year_month_labels_are_russian(self, client):
        valid_labels = {"Янв", "Фев", "Мар", "Апр", "Май", "Июн",
                        "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"}
        token, _ = _make_user(client, "student")
        r = client.get("/api/diary/summary?period=year", headers=_auth(token))
        data = r.json()
        for point in data["points"]:
            assert point["label"] in valid_labels

    # ── Cross-student isolation ────────────────────────────────────────────────

    def test_summary_cross_student_isolation(self, client):
        token1, _ = _make_user(client, "student")
        token2, _ = _make_user(client, "student")
        _put_today(client, token2, {"mood_score": 9, "emotions": []})
        r = client.get("/api/diary/summary?period=14d", headers=_auth(token1))
        data = r.json()
        # student1 sees no entries (full frame with all null)
        assert data["entries_count"] == 0
        assert len(data["points"]) == 14
        assert all(p["mood_score"] is None for p in data["points"])


# ─── Helpers for edit/delete tests ───────────────────────────────────────────

def _insert_entry_and_get_uuid(
    student_id: int,
    entry_date: date,
    mood_score: int,
    entry_text: str = "",
    emotions: list | None = None,
) -> str:
    """Insert a diary entry and return its UUID string."""
    if emotions is None:
        emotions = []
    with SessionLocal() as db:
        entry = DiaryEntry(
            student_id     = student_id,
            entry_date     = entry_date,
            mood_score_enc = encrypt_text(str(mood_score)),
            entry_text_enc = encrypt_text(entry_text) if entry_text else None,
            emotions_enc   = encrypt_text(_json.dumps(emotions)),
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return str(entry.uuid)


def _get_uuid_from_entries(client, token: str) -> str:
    """Get UUID of the first entry from GET /api/diary/entries."""
    r = client.get("/api/diary/entries", headers=_auth(token))
    assert r.status_code == 200
    items = r.json()["items"]
    assert items, "No entries found"
    return items[0]["uuid"]


def _patch_entry(client, token: str, entry_uuid: str, payload: dict):
    return client.patch(
        f"/api/diary/entries/{entry_uuid}",
        headers=_auth(token),
        json=payload,
    )


def _delete_entry(client, token: str, entry_uuid: str):
    return client.delete(
        f"/api/diary/entries/{entry_uuid}",
        headers=_auth(token),
    )


# ─── 8. Edit entry (PATCH) ────────────────────────────────────────────────────

class TestEditEntry:
    def test_student_can_patch_own_past_entry(self, client):
        token, uid = _make_user(client, "student")
        yesterday = date.today() - timedelta(days=1)
        entry_uuid = _insert_entry_and_get_uuid(uid, yesterday, 5)
        r = _patch_entry(client, token, entry_uuid, {"mood_score": 8})
        assert r.status_code == 200
        assert r.json()["mood_score"] == 8

    def test_patch_updates_entry_text(self, client):
        token, uid = _make_user(client, "student")
        entry_uuid = _insert_entry_and_get_uuid(uid, date.today() - timedelta(days=1), 5)
        r = _patch_entry(client, token, entry_uuid, {"entry_text": "новый текст"})
        assert r.status_code == 200
        assert r.json()["entry_text"] == "новый текст"

    def test_patch_updates_emotions(self, client):
        token, uid = _make_user(client, "student")
        entry_uuid = _insert_entry_and_get_uuid(uid, date.today() - timedelta(days=1), 5)
        r = _patch_entry(client, token, entry_uuid, {"emotions": ["calm", "focused"]})
        assert r.status_code == 200
        assert set(r.json()["emotions"]) == {"calm", "focused"}

    def test_patch_supports_empty_text(self, client):
        token, uid = _make_user(client, "student")
        entry_uuid = _insert_entry_and_get_uuid(uid, date.today() - timedelta(days=1), 5, "старый текст")
        r = _patch_entry(client, token, entry_uuid, {"entry_text": ""})
        assert r.status_code == 200
        assert r.json()["entry_text"] == ""

    def test_patch_supports_empty_emotions(self, client):
        token, uid = _make_user(client, "student")
        entry_uuid = _insert_entry_and_get_uuid(uid, date.today() - timedelta(days=1), 5, "", ["calm"])
        r = _patch_entry(client, token, entry_uuid, {"emotions": []})
        assert r.status_code == 200
        assert r.json()["emotions"] == []

    def test_patch_partial_does_not_wipe_other_fields(self, client):
        token, uid = _make_user(client, "student")
        entry_uuid = _insert_entry_and_get_uuid(
            uid, date.today() - timedelta(days=1), 5, "сохранить текст", ["calm"]
        )
        r = _patch_entry(client, token, entry_uuid, {"mood_score": 9})
        assert r.status_code == 200
        data = r.json()
        assert data["mood_score"] == 9
        assert data["entry_text"] == "сохранить текст"
        assert "calm" in data["emotions"]

    def test_patch_can_update_today_entry_by_uuid(self, client):
        token, uid = _make_user(client, "student")
        _put_today(client, token, {"mood_score": 5, "emotions": []})
        entry_uuid = _get_uuid_from_entries(client, token)
        r = _patch_entry(client, token, entry_uuid, {"mood_score": 8})
        assert r.status_code == 200
        assert r.json()["mood_score"] == 8

    def test_patch_invalid_mood_score_returns_422(self, client):
        token, uid = _make_user(client, "student")
        entry_uuid = _insert_entry_and_get_uuid(uid, date.today() - timedelta(days=1), 5)
        r = _patch_entry(client, token, entry_uuid, {"mood_score": 0})
        assert r.status_code == 422

    def test_patch_invalid_emotion_key_returns_422(self, client):
        token, uid = _make_user(client, "student")
        entry_uuid = _insert_entry_and_get_uuid(uid, date.today() - timedelta(days=1), 5)
        r = _patch_entry(client, token, entry_uuid, {"emotions": ["nonexistent_xyz"]})
        assert r.status_code == 422

    def test_patch_other_student_entry_returns_404(self, client):
        token1, uid1 = _make_user(client, "student")
        token2, _ = _make_user(client, "student")
        entry_uuid = _insert_entry_and_get_uuid(uid1, date.today() - timedelta(days=1), 5)
        r = _patch_entry(client, token2, entry_uuid, {"mood_score": 8})
        assert r.status_code == 404

    def test_patch_deleted_entry_returns_404(self, client):
        token, uid = _make_user(client, "student")
        entry_uuid = _insert_entry_and_get_uuid(uid, date.today() - timedelta(days=1), 5)
        _delete_entry(client, token, entry_uuid)
        r = _patch_entry(client, token, entry_uuid, {"mood_score": 8})
        assert r.status_code == 404

    @pytest.mark.parametrize("role", ["psychologist", "admin", "supervisor"])
    def test_non_student_gets_403_on_patch(self, client, role):
        token, _ = _make_user(client, role)
        r = _patch_entry(client, token, "any-uuid", {"mood_score": 5})
        assert r.status_code == 403

    def test_encryption_preserved_after_patch(self, client):
        token, uid = _make_user(client, "student")
        entry_uuid = _insert_entry_and_get_uuid(uid, date.today() - timedelta(days=1), 5)
        _patch_entry(client, token, entry_uuid, {"mood_score": 8, "entry_text": "шифрованный", "emotions": ["calm"]})
        with SessionLocal() as db:
            entry = db.query(DiaryEntry).filter(DiaryEntry.uuid == entry_uuid).first()
            assert entry is not None
            assert entry.mood_score_enc.startswith(ENCRYPTION_PREFIX)
            assert entry.entry_text_enc is not None
            assert entry.entry_text_enc.startswith(ENCRYPTION_PREFIX)
            assert entry.emotions_enc.startswith(ENCRYPTION_PREFIX)

    def test_patch_malformed_uuid_returns_422(self, client):
        token, _ = _make_user(client, "student")
        r = _patch_entry(client, token, "notauuid", {"mood_score": 5})
        assert r.status_code == 422

    def test_patch_malformed_uuid_with_special_chars_returns_422(self, client):
        token, _ = _make_user(client, "student")
        r = _patch_entry(client, token, "not-a-valid-uuid-12345!", {"mood_score": 5})
        assert r.status_code == 422


# ─── 9. Delete entry (DELETE) ─────────────────────────────────────────────────

class TestDeleteEntry:
    def test_student_can_delete_own_entry(self, client):
        token, uid = _make_user(client, "student")
        entry_uuid = _insert_entry_and_get_uuid(uid, date.today() - timedelta(days=1), 5)
        r = _delete_entry(client, token, entry_uuid)
        assert r.status_code == 204

    def test_deleted_entry_disappears_from_entries_list(self, client):
        token, uid = _make_user(client, "student")
        entry_uuid = _insert_entry_and_get_uuid(uid, date.today() - timedelta(days=1), 5)
        _delete_entry(client, token, entry_uuid)
        r = client.get("/api/diary/entries", headers=_auth(token))
        uuids = [e["uuid"] for e in r.json()["items"]]
        assert entry_uuid not in uuids

    def test_deleted_today_entry_disappears_from_today(self, client):
        token, uid = _make_user(client, "student")
        _put_today(client, token, {"mood_score": 7, "emotions": []})
        entry_uuid = _get_uuid_from_entries(client, token)
        _delete_entry(client, token, entry_uuid)
        r = client.get("/api/diary/today", headers=_auth(token))
        assert r.status_code == 200
        assert r.json()["mood_score"] is None

    def test_deleted_entry_excluded_from_summary(self, client):
        token, uid = _make_user(client, "student")
        _put_today(client, token, {"mood_score": 7, "emotions": []})
        r = client.get("/api/diary/summary?period=14d", headers=_auth(token))
        assert r.json()["entries_count"] == 1

        entry_uuid = _get_uuid_from_entries(client, token)
        _delete_entry(client, token, entry_uuid)

        r = client.get("/api/diary/summary?period=14d", headers=_auth(token))
        assert r.json()["entries_count"] == 0

    def test_repeated_delete_returns_404(self, client):
        token, uid = _make_user(client, "student")
        entry_uuid = _insert_entry_and_get_uuid(uid, date.today() - timedelta(days=1), 5)
        _delete_entry(client, token, entry_uuid)
        r = _delete_entry(client, token, entry_uuid)
        assert r.status_code == 404

    def test_delete_other_student_entry_returns_404(self, client):
        token1, uid1 = _make_user(client, "student")
        token2, _ = _make_user(client, "student")
        entry_uuid = _insert_entry_and_get_uuid(uid1, date.today() - timedelta(days=1), 5)
        r = _delete_entry(client, token2, entry_uuid)
        assert r.status_code == 404

    @pytest.mark.parametrize("role", ["psychologist", "admin", "supervisor"])
    def test_non_student_gets_403_on_delete(self, client, role):
        token, _ = _make_user(client, role)
        r = _delete_entry(client, token, "any-uuid")
        assert r.status_code == 403

    def test_soft_delete_sets_deleted_at(self, client):
        token, uid = _make_user(client, "student")
        entry_uuid = _insert_entry_and_get_uuid(uid, date.today() - timedelta(days=1), 5)
        _delete_entry(client, token, entry_uuid)
        with SessionLocal() as db:
            entry = db.query(DiaryEntry).filter(DiaryEntry.uuid == entry_uuid).first()
            assert entry is not None
            assert entry.deleted_at is not None

    def test_after_soft_delete_can_create_new_entry_same_date(self, client):
        token, uid = _make_user(client, "student")
        _put_today(client, token, {"mood_score": 5, "emotions": []})
        entry_uuid = _get_uuid_from_entries(client, token)
        _delete_entry(client, token, entry_uuid)
        r = _put_today(client, token, {"mood_score": 8, "emotions": ["calm"]})
        assert r.status_code == 200
        assert r.json()["mood_score"] == 8

    def test_delete_malformed_uuid_returns_422(self, client):
        token, _ = _make_user(client, "student")
        r = _delete_entry(client, token, "notauuid")
        assert r.status_code == 422


# ─── 10. Empty PATCH (no-op) ─────────────────────────────────────────────────

class TestEmptyPatch:
    def test_patch_empty_body_returns_200(self, client):
        token, uid = _make_user(client, "student")
        entry_uuid = _insert_entry_and_get_uuid(uid, date.today() - timedelta(days=1), 5)
        r = _patch_entry(client, token, entry_uuid, {})
        assert r.status_code == 200

    def test_patch_empty_body_does_not_change_content(self, client):
        token, uid = _make_user(client, "student")
        entry_uuid = _insert_entry_and_get_uuid(
            uid, date.today() - timedelta(days=1), 5, "original text", ["calm"]
        )
        r = _patch_entry(client, token, entry_uuid, {})
        assert r.status_code == 200
        data = r.json()
        assert data["mood_score"] == 5
        assert data["entry_text"] == "original text"
        assert "calm" in data["emotions"]

    def test_patch_empty_body_does_not_update_updated_at(self, client):
        token, uid = _make_user(client, "student")
        entry_uuid = _insert_entry_and_get_uuid(uid, date.today() - timedelta(days=1), 5)
        # Get initial updated_at from entries list
        r1 = client.get("/api/diary/entries", headers=_auth(token))
        initial_updated_at = next(
            e for e in r1.json()["items"] if e["uuid"] == entry_uuid
        )["updated_at"]
        # Empty patch must not touch updated_at
        r2 = _patch_entry(client, token, entry_uuid, {})
        assert r2.json()["updated_at"] == initial_updated_at

    def test_patch_empty_body_on_missing_entry_returns_404(self, client):
        import uuid as _uuid_mod
        token, _ = _make_user(client, "student")
        r = _patch_entry(client, token, str(_uuid_mod.uuid4()), {})
        assert r.status_code == 404


# ─── 11. Updated emotions catalog (c3a7f8e2d1b9) ─────────────────────────────

class TestUpdatedCatalog:
    """Проверяет состояние каталога после миграции c3a7f8e2d1b9.

    После миграции:
      - 12 активных состояний (tense, irritated, low, lonely добавлены;
        angry, light деактивированы)
      - GET /api/diary/emotions возвращает ровно 12 записей
      - Новые ключи принимаются API; deprecated ключи отвергаются (is_active=False)
    """

    def test_active_emotions_count_is_12(self, client):
        token, _ = _make_user(client, "student")
        r = client.get("/api/diary/emotions", headers=_auth(token))
        assert r.status_code == 200
        assert len(r.json()) == 12

    def test_new_keys_present_in_catalog(self, client):
        token, _ = _make_user(client, "student")
        r = client.get("/api/diary/emotions", headers=_auth(token))
        keys = {e["key"] for e in r.json()}
        assert "tense"    in keys
        assert "irritated" in keys
        assert "low"       in keys
        assert "lonely"    in keys

    def test_deprecated_angry_not_in_active_catalog(self, client):
        token, _ = _make_user(client, "student")
        r = client.get("/api/diary/emotions", headers=_auth(token))
        keys = [e["key"] for e in r.json()]
        assert "angry" not in keys

    def test_deprecated_light_not_in_active_catalog(self, client):
        token, _ = _make_user(client, "student")
        r = client.get("/api/diary/emotions", headers=_auth(token))
        keys = [e["key"] for e in r.json()]
        assert "light" not in keys

    def test_catalog_sorted_by_new_order(self, client):
        """Первые 5 активных: calm, joyful, inspired, focused, anxious."""
        token, _ = _make_user(client, "student")
        r = client.get("/api/diary/emotions", headers=_auth(token))
        keys = [e["key"] for e in r.json()]
        assert keys[:5] == ["calm", "joyful", "inspired", "focused", "anxious"]

    def test_new_key_tense_accepted_in_put(self, client):
        token, _ = _make_user(client, "student")
        r = _put_today(client, token, {"mood_score": 5, "emotions": ["tense"]})
        assert r.status_code == 200
        assert "tense" in r.json()["emotions"]

    def test_new_key_irritated_accepted_in_put(self, client):
        token, _ = _make_user(client, "student")
        r = _put_today(client, token, {"mood_score": 4, "emotions": ["irritated"]})
        assert r.status_code == 200
        assert "irritated" in r.json()["emotions"]

    def test_new_key_low_accepted_in_put(self, client):
        token, _ = _make_user(client, "student")
        r = _put_today(client, token, {"mood_score": 3, "emotions": ["low"]})
        assert r.status_code == 200
        assert "low" in r.json()["emotions"]

    def test_new_key_lonely_accepted_in_put(self, client):
        token, _ = _make_user(client, "student")
        r = _put_today(client, token, {"mood_score": 4, "emotions": ["lonely"]})
        assert r.status_code == 200
        assert "lonely" in r.json()["emotions"]

    def test_deprecated_angry_rejected_in_put(self, client):
        token, _ = _make_user(client, "student")
        r = _put_today(client, token, {"mood_score": 5, "emotions": ["angry"]})
        assert r.status_code == 422

    def test_deprecated_light_rejected_in_put(self, client):
        token, _ = _make_user(client, "student")
        r = _put_today(client, token, {"mood_score": 5, "emotions": ["light"]})
        assert r.status_code == 422
