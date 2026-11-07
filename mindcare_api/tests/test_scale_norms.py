"""
Нормы шкал (ТЗ редактора методик, этап 2, §5) — чистые функции.

ИТО норм не получает (в методичке Собчик таблиц перевода нет); механизм
проверяется на синтетических таблицах.

  - группа — первая подходящая по анкете (пол, возраст, факультет); группа без
    условий — запасная; нет группы или балл вне таблицы — None;
  - схема: пересечения строк, повтор поля условия, форма условий;
  - пробел таблицы относительно диапазона шкалы — norm_gap;
  - аналитика и xlsx кампании; шаблон методики туда-обратно.
"""
import io
from datetime import datetime, timezone

import pytest
from openpyxl import load_workbook

from app.campaigns import analytics
from app.campaigns.export import build_workbook as build_export
from app.tests import methodology_xlsx as mx
from app.tests import rules as R
from app.tests.profiles import ito_sobchik as ito

FEMALE_YOUNG = {"when": [{"field": "gender", "eq": "female"},
                         {"field": "age", "min": 17, "max": 25}],
                "table": [{"min": 0, "max": 4, "value": 3}, {"min": 5, "max": 10, "value": 7}]}
ANY = {"when": [], "table": [{"min": 0, "max": 6, "value": 4}, {"min": 7, "max": 10, "value": 8}]}


def _raw(groups=(FEMALE_YOUNG, ANY), **norms):
    return {"version": 1, "scales": [
        {"code": "A", "label": "Тревога", "main": True,
         "norms": {"kind": "sten", "groups": list(groups), **norms}},
        {"code": "B", "label": "Без норм", "main": True}]}


def test_group_selection_and_values():
    rules = R.parse(_raw())
    assert R.norm_value(rules, "A", 5, {"gender": "female", "age": 19}) == 7
    assert R.norm_value(rules, "A", 5, {"gender": "female", "age": 30}) == 4   # запасная
    assert R.norm_value(rules, "A", 5, {"gender": "male", "age": 19}) == 4
    assert R.norm_value(rules, "A", 11, {"gender": "male", "age": 19}) is None  # вне таблицы
    assert R.norm_value(rules, "B", 5, {}) is None
    no_fallback = R.parse(_raw(groups=(FEMALE_YOUNG,)))
    assert R.norm_value(no_fallback, "A", 5, {"gender": "male", "age": 19}) is None
    assert R.norms_of(rules)["A"].title == "Стены"
    assert R.parse(_raw(label="Мои баллы")).scales[0].norms.title == "Мои баллы"


def test_faculty_condition():
    rules = R.parse(_raw(groups=({"when": [{"field": "faculty_code", "eq": "law"}],
                                  "table": [{"min": 0, "max": 10, "value": 9}]}, ANY)))
    assert R.norm_value(rules, "A", 3, {"faculty_code": "law"}) == 9
    assert R.norm_value(rules, "A", 3, {"faculty_code": "math_it"}) == 4


def test_dump_compact_and_ito_unchanged():
    dumped = R.dump(R.parse(_raw()))
    assert "norms" not in dumped["scales"][1]
    assert dumped["scales"][0]["norms"]["groups"][0]["when"] == FEMALE_YOUNG["when"]
    assert "label" not in dumped["scales"][0]["norms"]
    assert all("norms" not in s for s in R.dump(R.parse(ito.scoring_rules()))["scales"])


@pytest.mark.parametrize("groups", [
    ({"when": [], "table": [{"min": 0, "max": 5, "value": 1}, {"min": 5, "max": 9, "value": 2}]},),
    ({"when": [{"field": "gender", "eq": "male"}, {"field": "gender", "eq": "female"}],
      "table": [{"min": 0, "max": 5, "value": 1}]},),
    ({"when": [{"field": "age", "eq": "18"}], "table": [{"min": 0, "max": 5, "value": 1}]},),
    ({"when": [{"field": "gender", "min": 1}], "table": [{"min": 0, "max": 5, "value": 1}]},),
    ({"when": [{"field": "age", "min": 30, "max": 20}], "table": [{"min": 0, "max": 5, "value": 1}]},),
    ({"when": [{"field": "city", "eq": "x"}], "table": [{"min": 0, "max": 5, "value": 1}]},),
    ({"when": [], "table": []},),
    (),
])
def test_invalid_norms_rejected(groups):
    with pytest.raises(R.RulesInvalid):
        R.parse(_raw(groups=groups))


def test_norm_gap_issue():
    rules = R.parse(_raw(groups=({"when": [], "table": [{"min": 0, "max": 6, "value": 4}]},)))
    issues = R.check_against_bounds(rules, [{"scale_name": "A", "min_score": 0, "max_score": 10},
                                            {"scale_name": "B", "min_score": 0, "max_score": 10}])
    assert issues == [{"kind": "norm_gap", "scale_name": "A", "min_score": 7, "max_score": 10}]
    assert "таблица норм" in R.describe(issues[0])


def _row(name, gender, age, a):
    return {"uuid": name, "full_name": name, "faculty_code": "law", "gender": gender,
            "age": age, "specialty": "x",
            "submitted_at": datetime(2026, 11, 7, tzinfo=timezone.utc),
            "scores": {"A": a, "B": 1}, "answers": {}}


def test_analytics_and_export():
    rules = R.parse(_raw())
    rows = [_row("p1", "female", 19, 5), _row("p2", "male", 40, 8)]
    enriched = [analytics.enrich_row(r, rules) for r in rows]
    assert [e["norms"] for e in enriched] == [{"A": 7}, {"A": 8}]
    wb = load_workbook(io.BytesIO(build_export(rules=rules, rows=rows, question_numbers=[1])))
    header = [c for c in next(wb["Результаты"].iter_rows(values_only=True))]
    col = header.index("Тревога (Стены)")
    assert [r[col] for r in wb["Результаты"].iter_rows(min_row=2, values_only=True)] == [7, 8]


def test_template_roundtrip_with_norms():
    rules = R.dump(R.parse(_raw(label="Стены (студенты)")))
    test = {"title": "T", "description": None, "scoring": "sum", "campaign_only": True,
            "interpretations": [], "scoring_rules": rules,
            "questions": [
                {"question_order": i, "question_text": f"q{i}", "question_type": "single_choice",
                 "config": {"scale": s}, "media": [],
                 "options": [{"option_order": 0, "option_text": "да", "value_score": 10},
                             {"option_order": 1, "option_text": "нет", "value_score": 0}]}
                for i, s in enumerate(["A", "B"], start=1)]}
    data, errors = mx.parse_workbook(mx.build_workbook(test))
    assert errors == []
    assert R.dump(R.parse(data["scoring_rules"])) == rules


def test_template_norm_errors():
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = mx.SHEET_META
    ws.append(["Поле", "Значение"])
    ws.append(["Название", "T"])
    for name, rows in ((mx.SHEET_OPTIONS, [[1, "да"], [2, "нет"]]),
                       (mx.SHEET_QUESTIONS, [[1, "q"]]),
                       (mx.SHEET_KEY, [["A", 1, 1, 1]]),
                       (mx.SHEET_SCALES, [["A", "A", "да", None, "sten"],
                                          ["C", "C", "да", None, "t"]]),
                       (mx.SHEET_NORMS, [["Z", None, None, None, None, 0, 1, 1],
                                         ["A", "оно", None, None, None, 0, 1, 1],
                                         ["A", None, "x", None, None, 0, 1, 1],
                                         ["A", None, None, None, "nofac", 0, 1, 1],
                                         ["A", None, None, None, None, 0, None, 1]])):
        sheet = wb.create_sheet(name)
        sheet.append(mx.HEADERS[name])
        for r in rows:
            sheet.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    _, errors = mx.parse_workbook(buf.getvalue())
    got = {(e["sheet"], e["row"], e["column"]) for e in errors}
    assert {(mx.SHEET_NORMS, 2, "A"), (mx.SHEET_NORMS, 3, "B"), (mx.SHEET_NORMS, 4, "C"),
            (mx.SHEET_NORMS, 5, "E"), (mx.SHEET_NORMS, 6, "G"),
            (mx.SHEET_SCALES, 3, "E")} <= got
