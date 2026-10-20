"""
Diary storage: SQLAlchemy queries, encrypt-on-write, decrypt-on-read.

SECURITY:
  - encrypt_text / decrypt_text вызываются ТОЛЬКО здесь.
  - Plaintext mood_score, entry_text, emotions не логируется.
  - Шифруются: mood_score (str), entry_text (str), emotions (JSON array).
  - entry_text_enc = NULL если текст не предоставлен.
"""

import json
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import desc

from app.core.encryption import decrypt_text, encrypt_text
from app.db.models.diary import DiaryEmotion, DiaryEntry
from app.db.session import SessionLocal


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _entry_to_dict(entry: DiaryEntry) -> dict:
    mood_score = int(decrypt_text(entry.mood_score_enc))
    entry_text = decrypt_text(entry.entry_text_enc) if entry.entry_text_enc else ""
    emotions   = json.loads(decrypt_text(entry.emotions_enc))
    return {
        "uuid":       str(entry.uuid),
        "entry_date": entry.entry_date,
        "mood_score": mood_score,
        "entry_text": entry_text,
        "emotions":   emotions,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
        "updated_at": entry.updated_at.isoformat() if entry.updated_at else None,
    }


def _summary_dict(entry: DiaryEntry) -> dict:
    """Minimal dict for summary: only entry_date + mood_score (no entry_text/emotions)."""
    return {
        "entry_date": entry.entry_date,
        "mood_score": int(decrypt_text(entry.mood_score_enc)),
    }


# ─── Emotions ─────────────────────────────────────────────────────────────────

def get_active_emotions() -> list[dict]:
    with SessionLocal() as db:
        rows = (
            db.query(DiaryEmotion)
            .filter(DiaryEmotion.is_active.is_(True))
            .order_by(DiaryEmotion.sort_order)
            .all()
        )
        return [{"key": r.key, "label": r.label, "sort_order": r.sort_order} for r in rows]


def get_all_emotion_keys() -> set[str]:
    with SessionLocal() as db:
        rows = db.query(DiaryEmotion.key).filter(DiaryEmotion.is_active.is_(True)).all()
        return {r.key for r in rows}


# ─── Today entry ──────────────────────────────────────────────────────────────

def get_today_entry(student_id: int, today: date) -> Optional[dict]:
    with SessionLocal() as db:
        entry = (
            db.query(DiaryEntry)
            .filter(
                DiaryEntry.student_id == student_id,
                DiaryEntry.entry_date == today,
                DiaryEntry.deleted_at.is_(None),
            )
            .first()
        )
        if not entry:
            return None
        return _entry_to_dict(entry)


def upsert_today_entry(student_id: int, today: date, data: dict) -> dict:
    mood_enc   = encrypt_text(str(data["mood_score"]))
    text_plain = data.get("entry_text") or ""
    text_enc   = encrypt_text(text_plain) if text_plain else None
    emo_enc    = encrypt_text(json.dumps(data["emotions"]))

    with SessionLocal() as db:
        entry = (
            db.query(DiaryEntry)
            .filter(
                DiaryEntry.student_id == student_id,
                DiaryEntry.entry_date == today,
                DiaryEntry.deleted_at.is_(None),
            )
            .first()
        )
        if entry:
            entry.mood_score_enc = mood_enc
            entry.entry_text_enc = text_enc
            entry.emotions_enc   = emo_enc
            entry.updated_at     = datetime.now(timezone.utc)
        else:
            entry = DiaryEntry(
                student_id     = student_id,
                entry_date     = today,
                mood_score_enc = mood_enc,
                entry_text_enc = text_enc,
                emotions_enc   = emo_enc,
            )
            db.add(entry)

        db.commit()
        db.refresh(entry)
        return _entry_to_dict(entry)


# ─── Entries list ─────────────────────────────────────────────────────────────

def get_entries(student_id: int, limit: int, offset: int) -> tuple[list[dict], int]:
    with SessionLocal() as db:
        q = db.query(DiaryEntry).filter(
            DiaryEntry.student_id == student_id,
            DiaryEntry.deleted_at.is_(None),
        )
        total   = q.count()
        entries = (
            q.order_by(desc(DiaryEntry.entry_date), desc(DiaryEntry.created_at))
            .limit(limit)
            .offset(offset)
            .all()
        )
        return [_entry_to_dict(e) for e in entries], total


# ─── Edit / Delete ────────────────────────────────────────────────────────────

def update_entry_by_uuid(student_id: int, entry_uuid: str, data: dict) -> Optional[dict]:
    """Partial update of diary entry. Returns updated dict or None if not found.
    Empty data → no-op: returns current entry without touching updated_at."""
    with SessionLocal() as db:
        entry = (
            db.query(DiaryEntry)
            .filter(
                DiaryEntry.uuid == entry_uuid,
                DiaryEntry.student_id == student_id,
                DiaryEntry.deleted_at.is_(None),
            )
            .first()
        )
        if not entry:
            return None

        if not data:
            return _entry_to_dict(entry)

        if "mood_score" in data:
            entry.mood_score_enc = encrypt_text(str(data["mood_score"]))
        if "entry_text" in data:
            t = data["entry_text"]
            entry.entry_text_enc = encrypt_text(t) if t else None
        if "emotions" in data:
            entry.emotions_enc = encrypt_text(json.dumps(data["emotions"]))

        entry.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(entry)
        return _entry_to_dict(entry)


def soft_delete_entry_by_uuid(student_id: int, entry_uuid: str) -> bool:
    """Soft-delete diary entry. Returns True if deleted, False if not found/already deleted."""
    with SessionLocal() as db:
        entry = (
            db.query(DiaryEntry)
            .filter(
                DiaryEntry.uuid == entry_uuid,
                DiaryEntry.student_id == student_id,
                DiaryEntry.deleted_at.is_(None),
            )
            .first()
        )
        if not entry:
            return False
        entry.deleted_at = datetime.now(timezone.utc)
        db.commit()
        return True


# ─── Summary ──────────────────────────────────────────────────────────────────

def get_entries_in_range(student_id: int, start: date, end: date) -> list[dict]:
    with SessionLocal() as db:
        rows = (
            db.query(DiaryEntry)
            .filter(
                DiaryEntry.student_id == student_id,
                DiaryEntry.entry_date >= start,
                DiaryEntry.entry_date <= end,
                DiaryEntry.deleted_at.is_(None),
            )
            .all()
        )
        return [_summary_dict(r) for r in rows]
