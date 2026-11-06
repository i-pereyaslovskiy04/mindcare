"""ADR-037: правила обработки как данные (app/tests/rules.py).

Главное — эквивалентность прежнему коду ИТО (ito_sobchik.py) на всех
сочетаниях баллов, которые влияют на уровни, достоверность и типы.
"""
import itertools
import random

import pytest

from app.tests import rules
from app.tests.profiles import ito_sobchik as ito

ITO = rules.parse(ito.scoring_rules())


def _random_scores(rng: random.Random) -> dict:
    return {s: rng.randint(0, ito.max_score(s)) for s in ito.KEY}


def test_ito_rules_valid_and_ordered():
    assert rules.scale_order(ITO) == list(ito.EXPORT_SCALE_ORDER)
    assert rules.main_scales(ITO) == [s for s in ito.EXPORT_SCALE_ORDER
                                      if s not in ito.VALIDITY_SCALES]
    assert rules.scale_label(ITO, "VII") == "VII Тревожность"
    assert rules.scale_label(ITO, "нет") == "нет"
    assert rules.validity_scales(ITO) == {"L": 5, "F": 5}
    assert rules.dump(ITO) == rules.dump(rules.parse(rules.dump(ITO)))


@pytest.mark.parametrize("score", range(-1, 11))
def test_ito_level_equivalence(score):
    expected = None
    for code, (lo, hi, _) in zip(ito.LEVEL_CODES, ito.LEVELS):
        if lo <= score <= hi:
            expected = code
    assert rules.level_of(ITO, score) == expected


def test_ito_validity_and_types_equivalence():
    rng = random.Random(20261106)
    samples = [_random_scores(rng) for _ in range(3000)]
    # Крайние значения: все шкалы на пороге и около него.
    for value in (0, 5, 6, 7, 8, 9):
        samples.append({s: min(value, ito.max_score(s)) for s in ito.KEY})
    for scores in samples:
        assert rules.is_valid(ITO, scores) == ito.is_valid(scores)
        assert rules.types_of(ITO, scores) == ito.types_of(scores)
        assert rules.summarize(ITO, scores) == {
            "is_valid": ito.is_valid(scores), "types": ito.types_of(scores)}


def test_type_base_strips_mark():
    assert rules.type_base(ITO, "Неуравновешенный (недостоверно)") == "Неуравновешенный"
    assert rules.type_base(ITO, "Неуравновешенный") == "Неуравновешенный"


def test_no_rules():
    assert rules.parse(None) is None
    assert rules.scale_order(None, {"b": 1, "a": 2}) == ["a", "b"]
    assert rules.level_of(None, 3) is None
    assert rules.is_valid(None, {"L": 9}) is None
    assert rules.types_of(None, {"I": 9}) == []
    assert rules.summarize(None, {}) is None


def test_scales_only_rules_summary_none():
    r = rules.parse({"version": 1, "scales": [{"code": "A", "label": "A"}]})
    assert rules.summarize(r, {"A": 3}) is None
    assert rules.is_valid(r, {"A": 3}) is None


def _base(**over):
    data = {"version": 1, "scales": [{"code": "A", "label": "Шкала А", "main": True},
                                     {"code": "B", "label": "Шкала Б"}]}
    data.update(over)
    return data


@pytest.mark.parametrize("bad", [
    _base(scales=[]),
    _base(scales=[{"code": "A", "label": "x"}, {"code": "A", "label": "y"}]),
    _base(scales=[{"code": "A B", "label": "x"}]),
    _base(scales=[{"code": "A", "label": "x\x00"}]),
    _base(levels=[{"code": "lo", "label": "x", "min": 3, "max": 1}]),
    _base(levels=[{"code": "lo", "label": "x", "min": 0, "max": 3},
                  {"code": "hi", "label": "y", "min": 3, "max": 5}]),
    _base(levels=[{"code": "Lo", "label": "x", "min": 0, "max": 3}]),
    _base(levels=[{"code": "invalid", "label": "x", "min": 0, "max": 3}]),
    _base(validity={"scales": [{"code": "Z", "max_valid": 5}]}),
    _base(validity={"scales": []}),
    _base(types={"threshold": 8, "items": [{"name": "Т", "scales": ["Z"]}]}),
    _base(types={"threshold": 8, "items": [{"name": "Т", "scales": ["A"]},
                                           {"name": "Т", "scales": ["B"]}]}),
    _base(version=2),
    _base(extra=1),
    _base(instruction="x" * 2001),
])
def test_invalid_rules_rejected(bad):
    with pytest.raises(rules.RulesInvalid):
        rules.parse(bad)


def test_text_normalization():
    r = rules.parse(_base(scales=[{"code": "A", "label": "  Шкала   А "}],
                          instruction="  Строка 1\nСтрока 2  "))
    assert r.scales[0].label == "Шкала А"
    assert r.instruction == "Строка 1\nСтрока 2"
    assert rules.parse(_base(instruction="   ")).instruction is None


def test_custom_likert_rules():
    r = rules.parse({
        "version": 1,
        "scales": [{"code": "S", "label": "Стресс", "main": True},
                   {"code": "K", "label": "Контроль"}],
        "levels": [{"code": "low", "label": "Низкий", "min": 0, "max": 10},
                   {"code": "high", "label": "Высокий", "min": 11, "max": 40}],
        "validity": {"scales": [{"code": "K", "max_valid": 2}], "invalid_mark": "сомнительно"},
        "types": {"threshold": 11, "items": [{"name": "Перегрузка", "scales": ["S"]}]},
    })
    assert rules.level_of(r, 11) == "high"
    assert rules.types_of(r, {"S": 20, "K": 3}) == ["Перегрузка (сомнительно)"]
    assert rules.types_of(r, {"S": 20, "K": 1}) == ["Перегрузка"]
    for s, k in itertools.product((0, 11), (0, 3)):
        assert rules.summarize(r, {"S": s, "K": k})["is_valid"] is (k <= 2)
