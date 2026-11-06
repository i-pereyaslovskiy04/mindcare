"""ADR-037: эталон ИТО. Переход на правила-данные не меняет ни одной цифры.

tests/fixtures/ito_campaign_golden.json снят прежним кодом (профиль
ito_sobchik в коде) на 60 синтетических участниках: уровни, достоверность,
типы, сводка, фильтры и ВСЕ ячейки xlsx. Новый код обязан совпасть точно.
"""
import io
import json
from datetime import datetime
from pathlib import Path

import pytest
from openpyxl import load_workbook

from app.campaigns import analytics, export
from app.tests import rules as R
from app.tests.profiles import ito_sobchik as ito

GOLDEN = json.loads((Path(__file__).parent / "fixtures" / "ito_campaign_golden.json")
                    .read_text(encoding="utf-8"))
RULES = R.parse(ito.scoring_rules())


def _rows():
    return [{**r, "submitted_at": datetime.fromisoformat(r["submitted_at"]),
             "answers": {int(k): v for k, v in r["answers"].items()}}
            for r in GOLDEN["rows"]]


def _jsonable(value):
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def test_enrich_matches_golden():
    enriched = [analytics.enrich_row(r, RULES) for r in _rows()]
    got = [{k: e[k] for k in ("levels", "is_valid", "types")} for e in enriched]
    assert _jsonable(got) == GOLDEN["enriched"]


def test_summary_and_filters_match_golden():
    enriched = [analytics.enrich_row(r, RULES) for r in _rows()]
    assert _jsonable(analytics.summarize(enriched, RULES)) == GOLDEN["summary"]
    assert {
        "invalid": len(analytics.filter_rows(enriched, rules=RULES, validity="invalid")),
        "type": len(analytics.filter_rows(enriched, rules=RULES, type_name=ito.TYPES[0][0])),
        "none": len(analytics.filter_rows(enriched, rules=RULES, type_name="__none__")),
    } == GOLDEN["filtered"]


@pytest.mark.parametrize("sheet", ["Результаты", "Уровни", "Сводка", "Ответы"])
def test_xlsx_cells_match_golden(sheet):
    wb = load_workbook(io.BytesIO(export.build_workbook(
        rules=RULES, rows=_rows(), question_numbers=range(1, 92))))
    got = [[c.isoformat() if hasattr(c, "isoformat") else c for c in row]
           for row in wb[sheet].iter_rows(values_only=True)]
    assert _jsonable(got) == GOLDEN["xlsx"][sheet]


def test_level_fills_unchanged():
    """Оттенки уровней ИТО — прежние коды заливки."""
    assert analytics.level_tones(RULES) == {
        "low": "low", "norm": "norm", "accent": "accent", "maladaptive": "maladaptive"}
