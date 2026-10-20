"""
Diary service: бизнес-логика.

Политика доступа:
  student — только свои записи (scope по student_id из current_user).
  Другие роли → 403 на уровне роутера (require_role("student")).

Date policy (MVP):
  entry_date определяется на backend как date.today() (серверная дата).
  Timezone-aware логика — отдельный этап. При деплое убедиться, что сервер
  настроен на часовой пояс ДГУ (Europe/Moscow / UTC+3).

Summary contract:
  14d   — последние 14 фактических календарных дней (today-13 … today); всегда 14 points.
  month — от 1-го числа текущего месяца до today; количество points = today.day.
  year  — monthly aggregated, Jan 1 текущего года … current month; ≤ 12 points.
  Дни/месяцы без записей возвращаются с mood_score=None.
  При отсутствии записей backend возвращает полный period frame (все null);
  empty state определяется на фронте по тому, что все mood_score равны null.

Не логировать: entry_text, mood_score (расшифрованные), emotions.
"""

from collections import defaultdict
from datetime import date, timedelta
from typing import Optional

from app.diary import storage
from app.diary.schemas import DiaryEntryWrite, DiaryEntryRead


_WEEKDAY_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
_MONTH_SHORT_RU = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн",
                   "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"]
_VALID_PERIODS = {"14d", "month", "year"}


class InvalidEmotionKey(Exception):
    pass


class InvalidPeriod(Exception):
    pass


class EntryNotFound(Exception):
    pass


def get_emotions() -> list[dict]:
    return storage.get_active_emotions()


def get_today(student_id: int) -> dict:
    today = date.today()
    entry = storage.get_today_entry(student_id, today)
    if entry:
        return entry
    return {
        "entry_date": today,
        "mood_score": None,
        "entry_text": "",
        "emotions":   [],
    }


def upsert_today(student_id: int, data: DiaryEntryWrite) -> dict:
    _validate_emotion_keys(data.emotions)
    today = date.today()
    return storage.upsert_today_entry(student_id, today, data.model_dump())


def get_entries(student_id: int, limit: int, offset: int) -> tuple[list[dict], int]:
    return storage.get_entries(student_id, limit, offset)


def update_entry(student_id: int, entry_uuid: str, data: dict) -> dict:
    """Partial update. data keys: mood_score, entry_text, emotions (any subset)."""
    if "emotions" in data:
        _validate_emotion_keys(data["emotions"])
    result = storage.update_entry_by_uuid(student_id, entry_uuid, data)
    if result is None:
        raise EntryNotFound()
    return result


def delete_entry(student_id: int, entry_uuid: str) -> None:
    deleted = storage.soft_delete_entry_by_uuid(student_id, entry_uuid)
    if not deleted:
        raise EntryNotFound()


def get_summary(student_id: int, period: str) -> dict:
    if period not in _VALID_PERIODS:
        raise InvalidPeriod(f"Unknown period: {period!r}")

    today = date.today()
    period_start = _period_start(period, today)

    rows = storage.get_entries_in_range(student_id, period_start, today)
    score_by_date = {r["entry_date"]: r["mood_score"] for r in rows}

    if period == "year":
        points = _build_monthly_points(score_by_date, period_start, today)
    elif period == "month":
        points = _build_daily_points(score_by_date, period_start, today, use_day_number=True)
    else:  # 14d
        points = _build_daily_points(score_by_date, period_start, today, use_day_number=False)

    return {
        "period":        period,
        "entries_count": len(score_by_date),
        "points":        points,
    }


# ─── Private helpers ──────────────────────────────────────────────────────────

def _validate_emotion_keys(keys: list[str]) -> None:
    if not keys:
        return
    active_keys = storage.get_all_emotion_keys()
    for key in keys:
        if key not in active_keys:
            raise InvalidEmotionKey(f"Неизвестная или неактивная эмоция: {key!r}")


def _period_start(period: str, today: date) -> date:
    if period == "14d":
        return today - timedelta(days=13)
    if period == "month":
        return today.replace(day=1)
    # year: с 1 января текущего года
    return today.replace(month=1, day=1)


def _build_daily_points(
    score_by_date: dict,
    period_start: date,
    today: date,
    use_day_number: bool = False,
) -> list[dict]:
    """Full calendar frame from period_start to today — null gaps, no entry clamp.

    Labels: today = "Сегодня"; month period = day number; 14d = weekday abbreviation.
    """
    points = []
    current = period_start
    while current <= today:
        if current == today:
            label = "Сегодня"
        elif use_day_number:
            label = str(current.day)
        else:
            label = _WEEKDAY_RU[current.weekday()]
        points.append({
            "date":       current,
            "label":      label,
            "mood_score": score_by_date.get(current),
        })
        current += timedelta(days=1)
    return points


def _build_monthly_points(score_by_date: dict, period_start: date, today: date) -> list[dict]:
    """Monthly aggregated points: Jan 1 → Dec 1 of current year (all 12 months).

    Future months (after today) are included with mood_score=None.
    mood_score per month = average of daily entries, round(avg, 1).
    Months without entries → mood_score=None.
    """
    start_month = period_start.replace(day=1)
    end_month = date(today.year, 12, 1)

    scores_by_month: dict[date, list[int]] = defaultdict(list)
    for entry_date, mood_score in score_by_date.items():
        scores_by_month[entry_date.replace(day=1)].append(mood_score)

    points = []
    current = start_month
    while current <= end_month:
        scores = scores_by_month.get(current)
        if scores:
            avg = round(sum(scores) / len(scores), 1)
            mood_score: Optional[float] = int(avg) if avg == int(avg) else avg
        else:
            mood_score = None

        points.append({
            "date":       current,
            "label":      _MONTH_SHORT_RU[current.month - 1],
            "mood_score": mood_score,
        })

        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)

    return points
