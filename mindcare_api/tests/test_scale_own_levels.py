"""
Свои уровни у шкалы (ТЗ редактора методик, этап 2, §4.1) — чистые функции.

  - схема: уровни только у основной шкалы, без пересечений и повторов кодов;
    пустые свои уровни не пишутся в JSONB (ИТО хранится как прежде);
  - level_of / check_against_bounds берут уровни шкалы, иначе общие;
  - аналитика и xlsx кампании: подписи и счёт по своим уровням шкалы;
  - шаблон методики: колонка «Шкала» листа «Уровни» туда-обратно.
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

A_LEVELS = [{"code": "norm", "label": "Норма", "min": 0, "max": 7},
            {"code": "sub", "label": "Субклиническая", "min": 8, "max": 10},
            {"code": "clin", "label": "Клиническая", "min": 11, "max": 21}]
COMMON = [{"code": "low", "label": "Низкий", "min": 0, "max": 10},
          {"code": "high", "label": "Высокий", "min": 11, "max": 21}]


def _raw(**over):
    raw = {"version": 1,
           "scales": [{"code": "A", "label": "Тревога", "main": True, "levels": A_LEVELS},
                      {"code": "D", "label": "Депрессия", "main": True},
                      {"code": "L", "label": "Ложь", "main": False}],
           "levels": COMMON,
           "validity": {"scales": [{"code": "L", "max_valid": 3}]}}
    raw.update(over)
    return raw


def test_level_of_uses_own_then_common():
    rules = R.parse(_raw())
    assert R.level_of(rules, 9, "A") == "sub"
    assert R.level_of(rules, 9, "D") == "low"        # общие
    assert R.level_of(rules, 9) == "low"             # без шкалы — общие
    assert R.has_levels(rules)
    assert R.has_levels(R.parse(_raw(levels=[])))     # только свои


def test_dump_omits_empty_own_levels():
    dumped = R.dump(R.parse(_raw()))
    assert "levels" in dumped["scales"][0]
    assert "levels" not in dumped["scales"][1]
    ito_raw = ito.scoring_rules()
    assert R.dump(R.parse(ito_raw)) == R.dump(R.parse(R.dump(R.parse(ito_raw))))
    assert all("levels" not in s for s in R.dump(R.parse(ito_raw))["scales"])


@pytest.mark.parametrize("scales", [
    # свои уровни у не основной шкалы
    [{"code": "A", "label": "A", "main": False, "levels": A_LEVELS}],
    # пересечение
    [{"code": "A", "label": "A", "main": True,
      "levels": [{"code": "a", "label": "a", "min": 0, "max": 5},
                 {"code": "b", "label": "b", "min": 5, "max": 9}]}],
    # повтор кода
    [{"code": "A", "label": "A", "main": True,
      "levels": [{"code": "a", "label": "a", "min": 0, "max": 4},
                 {"code": "a", "label": "b", "min": 5, "max": 9}]}],
])
def test_invalid_own_levels_rejected(scales):
    with pytest.raises(R.RulesInvalid):
        R.parse({"version": 1, "scales": scales})


def test_gap_checked_per_scale():
    rules = R.parse(_raw(levels=[{"code": "x", "label": "x", "min": 0, "max": 5}]))
    bounds = [{"scale_name": "A", "min_score": 0, "max_score": 21},
              {"scale_name": "D", "min_score": 0, "max_score": 21},
              {"scale_name": "L", "min_score": 0, "max_score": 5}]
    issues = R.check_against_bounds(rules, bounds)
    assert issues == [{"kind": "level_gap", "scale_name": "D",
                       "min_score": 6, "max_score": 21}]


def _row(name, **scores):
    return {"uuid": name, "full_name": name, "faculty_code": "law", "gender": "male",
            "age": 19, "specialty": "x",
            "submitted_at": datetime(2026, 11, 7, tzinfo=timezone.utc),
            "scores": scores, "answers": {}}


ROWS = [_row("p1", A=9, D=12, L=1), _row("p2", A=15, D=2, L=5)]


def test_analytics_and_api_shapes():
    rules = R.parse(_raw())
    rows = [analytics.enrich_row(r, rules) for r in ROWS]
    assert rows[0]["levels"] == {"A": "sub", "D": "high", "L": "valid"}
    assert rows[1]["levels"] == {"A": "clin", "D": "low", "L": "invalid"}
    summary = analytics.summarize(rows, rules)
    by = {s["scale"]: s["levels"] for s in summary["scales"]}
    assert by["A"] == {"norm": 0, "sub": 1, "clin": 1}
    assert by["D"] == {"low": 1, "high": 1}
    own = analytics.scale_levels(rules)
    assert list(own) == ["A"]
    assert [lv["tone"] for lv in own["A"]] == ["low", "norm", "maladaptive"]


def test_export_uses_scale_labels():
    rules = R.parse(_raw())
    wb = load_workbook(io.BytesIO(build_export(rules=rules, rows=ROWS,
                                                question_numbers=[1])))
    levels = [list(r) for r in wb["Уровни"].iter_rows(min_row=2, values_only=True)]
    assert levels[0][-3:] == ["Субклиническая", "Высокий", "Достоверно"]
    summary = [c for r in wb["Сводка"].iter_rows(values_only=True) for c in r if c]
    assert "Субклиническая: 1" in summary
    assert "Уровни (шкалы A)" in summary and "Уровни (шкалы D)" in summary


def test_template_roundtrip_with_own_levels():
    rules = _raw()
    test = {"title": "T", "description": None, "scoring": "sum", "campaign_only": True,
            "interpretations": [], "scoring_rules": R.dump(R.parse(rules)),
            "questions": [
                {"question_order": i, "question_text": f"q{i}", "question_type": "single_choice",
                 "config": {"scale": s}, "media": [],
                 "options": [{"option_order": 0, "option_text": "да", "value_score": 1},
                             {"option_order": 1, "option_text": "нет", "value_score": 0}]}
                for i, s in enumerate(["A", "D", "L"], start=1)]}
    data, errors = mx.parse_workbook(mx.build_workbook(test))
    assert errors == []
    assert R.dump(R.parse(data["scoring_rules"]))["scales"] == test["scoring_rules"]["scales"]
    assert data["scoring_rules"]["levels"] == COMMON


def test_template_own_level_errors():
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = mx.SHEET_META
    ws.append(["Поле", "Значение"])
    ws.append(["Название", "T"])
    for name, rows in ((mx.SHEET_OPTIONS, [[1, "да"], [2, "нет"]]),
                       (mx.SHEET_QUESTIONS, [[1, "q"]]),
                       (mx.SHEET_KEY, [["A", 1, 1, 1]]),
                       (mx.SHEET_SCALES, [["A", "A", "да"], ["L", "L", "нет", 3]]),
                       (mx.SHEET_LEVELS, [["n", "N", 0, 1, "Z"], ["n", "N", 0, 1, "L"]])):
        sheet = wb.create_sheet(name)
        sheet.append(mx.HEADERS[name])
        for r in rows:
            sheet.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    _, errors = mx.parse_workbook(buf.getvalue())
    assert {"sheet": mx.SHEET_LEVELS, "row": 2, "column": "E",
            "message": "нет такой шкалы на листе «Шкалы»"} in errors
    assert {"sheet": mx.SHEET_LEVELS, "row": 3, "column": "E",
            "message": "свои уровни — только у основной шкалы"} in errors
