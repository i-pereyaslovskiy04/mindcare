"""
Первичная обработка результатов кампании (app/campaigns/analytics.py) — unit.

Уровни по шкалам, достоверность, фильтры (факультет, пол, достоверность, тип,
«без типа»), сводка: средние, распределение уровней, частоты типов с долей
недостоверных, разбивки по факультетам и полу. Лист «Сводка» в xlsx строится
из тех же функций.
"""
import io
from datetime import datetime, timezone

from openpyxl import load_workbook

from app.campaigns import analytics
from app.campaigns.export import build_workbook
from app.tests.profiles import ito_sobchik as ito

P = ito.PROFILE


def _row(name, faculty="law", gender="male", **scores):
    base = {s: 4 for s in ito.KEY}
    base.update({"L": 2, "F": 2})
    base.update(scores)
    return {"uuid": name, "full_name": name, "faculty_code": faculty,
            "gender": gender, "age": 18, "specialty": "x",
            "submitted_at": datetime(2026, 11, 4, tzinfo=timezone.utc),
            "scores": base, "answers": {}}


ROWS = [
    _row("norm"),
    _row("unbalanced", VIII=8, III=9),                       # тип, достоверно
    _row("unbalanced_invalid", faculty="math_it", gender="female",
         VIII=9, III=8, L=7),                                # тип, недостоверно
    _row("low", faculty="math_it", gender="female", I=0, II=1),
]


def _enriched():
    return [analytics.enrich_row(r, P) for r in ROWS]


def test_level_codes():
    assert [analytics.level_code(v) for v in (0, 2, 3, 4, 5, 7, 8, 9)] == [
        "low", "low", "norm", "norm", "accent", "accent", "maladaptive", "maladaptive"]
    assert analytics.level_code(None) is None


def test_enrich_row_levels_validity_types():
    r = analytics.enrich_row(ROWS[2], P)
    assert r["levels"]["VIII"] == "maladaptive"
    assert r["levels"]["L"] == "invalid" and r["levels"]["F"] == "valid"
    assert r["is_valid"] is False
    assert r["types"] == ["Неуравновешенный (недостоверно)"]


def test_enrich_without_profile_has_no_levels():
    r = analytics.enrich_row(ROWS[0], None)
    assert r["levels"] == {} and r["is_valid"] is None and r["types"] == []


def test_filters():
    rows = _enriched()
    names = lambda rs: [r["full_name"] for r in rs]  # noqa: E731
    assert names(analytics.filter_rows(rows, faculty_code="math_it")) == [
        "unbalanced_invalid", "low"]
    assert names(analytics.filter_rows(rows, gender="male")) == ["norm", "unbalanced"]
    assert names(analytics.filter_rows(rows, validity="invalid")) == ["unbalanced_invalid"]
    # тип ищется без пометки «(недостоверно)»
    assert names(analytics.filter_rows(rows, type_name="Неуравновешенный")) == [
        "unbalanced", "unbalanced_invalid"]
    assert names(analytics.filter_rows(rows, type_name="__none__")) == ["norm", "low"]
    assert analytics.filter_rows(rows, faculty_code="law", validity="invalid") == []


def test_summary_totals_scales_types_groups():
    s = analytics.summarize(_enriched(), P)
    assert (s["total"], s["valid"], s["invalid"], s["with_type"]) == (4, 3, 1, 2)

    by_scale = {i["scale"]: i for i in s["scales"]}
    assert [i["scale"] for i in s["scales"]] == list(ito.EXPORT_SCALE_ORDER)
    assert by_scale["VIII"]["levels"] == {"low": 0, "norm": 2, "accent": 0,
                                          "maladaptive": 2}
    assert by_scale["VIII"]["mean"] == 6.25
    assert (by_scale["VIII"]["min"], by_scale["VIII"]["max"]) == (4, 9)
    assert by_scale["I"]["levels"]["low"] == 1
    assert by_scale["L"]["levels"] == {"valid": 3, "invalid": 1}

    types = {t["name"]: t for t in s["types"]}
    assert len(types) == 6
    assert types["Неуравновешенный"] == {"name": "Неуравновешенный", "count": 2,
                                         "invalid": 1}
    assert types["Социально активный, ранимый"]["count"] == 0

    faculties = {g["code"]: g for g in s["by_faculty"]}
    assert faculties["law"]["count"] == 2 and faculties["law"]["valid"] == 2
    assert faculties["math_it"]["with_type"] == 1
    assert faculties["law"]["label"] == "Юридический факультет"
    genders = {g["code"]: g for g in s["by_gender"]}
    assert genders["female"]["label"] == "Жен" and genders["female"]["count"] == 2


def test_summary_empty():
    s = analytics.summarize([], P)
    assert s["total"] == 0 and s["by_faculty"] == []
    assert all(i["mean"] is None for i in s["scales"])


def test_workbook_has_levels_and_summary_sheets_with_fills():
    data = build_workbook(profile=P, rows=ROWS, question_numbers=range(1, 92))
    wb = load_workbook(io.BytesIO(data))
    assert wb.sheetnames == ["Результаты", "Уровни", "Сводка", "Ответы"]
    res = wb["Результаты"]
    header = [c.value for c in res[1]]
    viii = header.index("VIII Лабильность") + 1
    assert res.cell(3, viii).value == 8
    assert res.cell(3, viii).fill.fgColor.rgb.endswith("F8CBAD")   # дезадаптация
    levels = wb["Уровни"]
    assert levels.cell(3, header.index("VIII Лабильность") + 1).value == \
        "Дезадаптирующие свойства"
    summary = [[c for c in row if c is not None]
               for row in wb["Сводка"].iter_rows(values_only=True)]
    assert ["Участников", 4] in summary
    assert ["Недостоверных (L или F > 5)", 1] in summary
    assert ["Неуравновешенный", 2, 1] in summary
