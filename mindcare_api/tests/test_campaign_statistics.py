"""
Статистика кампании (ТЗ редактора методик, этап 2, §7) — чистые функции.

  - по дням — московские даты;
  - по вопросам — число и доля выбравших каждый вариант;
  - распределение баллов шкал — сплошной диапазон значений;
  - меньше MIN_GROUP участников — только total и by_day;
  - лист «Статистика по вопросам» в xlsx кампании.
"""
import io
from datetime import datetime, timezone

from openpyxl import load_workbook

from app.campaigns import analytics
from app.campaigns.export import build_workbook
from app.tests import rules as R

RULES = R.parse({"version": 1, "scales": [{"code": "A", "label": "Тревога", "main": True}]})
QUESTIONS = [{"number": 1, "text": "Первый", "options": ["Да", "Нет"]},
             {"number": 2, "text": "Второй", "options": ["мало", "средне", "много"]}]


def _row(i, a, q1, q2, when):
    return {"uuid": f"u{i}", "full_name": None, "faculty_code": "law", "gender": "male",
            "age": 19, "specialty": "x", "submitted_at": when,
            "scores": {"A": a}, "answers": {1: q1, 2: q2}}


def _rows(n):
    late = datetime(2026, 11, 7, 22, 30, tzinfo=timezone.utc)     # 8 ноября по Москве
    early = datetime(2026, 11, 7, 9, 0, tzinfo=timezone.utc)
    data = [(3, "Да", "мало"), (5, "Нет", "много"), (5, "Да", "много"),
            (2, "Да", None), (7, "Нет", "средне"), (5, "Да", "мало")]
    return [analytics.enrich_row(_row(i, *data[i], late if i == 0 else early), RULES)
            for i in range(n)]


def test_statistics_full():
    st = analytics.statistics(_rows(6), RULES, QUESTIONS)
    assert st["too_few"] is False and st["total"] == 6
    assert st["by_day"] == [{"date": "2026-11-07", "count": 5},
                            {"date": "2026-11-08", "count": 1}]
    q1, q2 = st["questions"]
    assert q1["answered"] == 6
    assert q1["options"] == [{"text": "Да", "count": 4, "percent": 66.7},
                             {"text": "Нет", "count": 2, "percent": 33.3}]
    assert q2["answered"] == 5
    assert [o["count"] for o in q2["options"]] == [2, 1, 2]
    (hist,) = st["scales"]
    assert hist["label"] == "Тревога"
    assert hist["bins"] == [{"score": 2, "count": 1}, {"score": 3, "count": 1},
                            {"score": 4, "count": 0}, {"score": 5, "count": 3},
                            {"score": 6, "count": 0}, {"score": 7, "count": 1}]


def test_small_group_hides_distributions():
    st = analytics.statistics(_rows(4), RULES, QUESTIONS)
    assert st["too_few"] is True and st["min_group"] == analytics.MIN_GROUP == 5
    assert st["questions"] == [] and st["scales"] == []
    assert sum(d["count"] for d in st["by_day"]) == 4


def test_export_has_question_stats_sheet():
    raw = [{k: v for k, v in r.items() if k not in ("levels", "is_valid", "types")}
           for r in _rows(6)]
    for r in raw:
        r["full_name"] = "Участник"
    wb = load_workbook(io.BytesIO(build_workbook(rules=RULES, rows=raw, question_numbers=[1, 2],
                                                 questions=QUESTIONS)))
    ws = wb["Статистика по вопросам"]
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    assert rows[0] == ["№", "Вопрос", "Ответили", "Вариант", "Выбрали", "%"]
    assert rows[1] == [1, "Первый", 6, "Да", 4, 66.7]
    assert rows[2][3:] == ["Нет", 2, 33.3]
    assert "Статистика по вопросам" not in load_workbook(io.BytesIO(
        build_workbook(rules=RULES, rows=raw, question_numbers=[1, 2]))).sheetnames
