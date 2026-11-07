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


def test_charts_sheet_has_native_charts():
    """Лист «Графики»: по дням, уровни (общие и свои у шкалы), распределения
    баллов — нативные диаграммы Excel, ссылающиеся на таблицы листа."""
    import zipfile
    rules = R.parse({"version": 1, "scales": [
        {"code": "A", "label": "Тревога", "main": True,
         "levels": [{"code": "n", "label": "Норма", "min": 0, "max": 4},
                    {"code": "h", "label": "Высокая", "min": 5, "max": 9}]},
        {"code": "B", "label": "Бодрость", "main": True}],
        "levels": [{"code": "lo", "label": "Низкая", "min": 0, "max": 4},
                   {"code": "hi", "label": "Высокая", "min": 5, "max": 9}]})
    raw = [{"uuid": f"u{i}", "full_name": "Участник", "faculty_code": "law", "gender": "male",
            "age": 19, "specialty": "x",
            "submitted_at": datetime(2026, 11, 7, 9, tzinfo=timezone.utc),
            "scores": {"A": i, "B": 9 - i}, "answers": {}} for i in range(6)]
    content = build_workbook(rules=rules, rows=raw, question_numbers=[])
    wb = load_workbook(io.BytesIO(content))
    ws = wb["Графики"]
    texts = [c for r in ws.iter_rows(values_only=True) for c in r if isinstance(c, str)]
    assert {"Дата", "Шкала", "Балл", "Норма", "Низкая"} <= set(texts)
    charts = [n for n in zipfile.ZipFile(io.BytesIO(content)).namelist()
              if n.startswith("xl/charts/chart")]
    # по дням + уровни общие (B) + свои уровни (A) + 2 распределения
    assert len(charts) == 5
    xml = zipfile.ZipFile(io.BytesIO(content)).read(charts[1]).decode()
    assert "Графики" in xml or "'Графики'" in xml      # ссылки на ячейки листа
