"""
Профиль ИТО Собчик (ADR-036) — unit, без БД.

Ключ (с исправлением опечатки методички: 49 в II, 40 только в VIII), подсчёт
общим движком app/tests/scoring.compute_result по вопросам из профиля, уровни,
достоверность (L/F > 5), типы (все шкалы ≥ 8, пометка «(недостоверно)»),
порядок колонок выгрузки.
"""
import pytest

from app.tests import scoring
from app.tests.profiles import ito_sobchik as ito
from app.tests.profiles.ito_sobchik_items import ITEMS


# ─── helpers ──────────────────────────────────────────────────────────────────

def _engine_test() -> dict:
    """Тест в формате compute_result: id вопроса = номер, id варианта = n*10+порядок."""
    questions = []
    for q in ito.questions():
        n = q["question_order"]
        questions.append({
            "id": n,
            "question_type": q["question_type"],
            "config": q["config"],
            "options": [
                {"id": n * 10 + o["option_order"], "value_score": o["value_score"]}
                for o in q["options"]
            ],
        })
    return {"scoring": "sum", "questions": questions,
            "interpretations": ito.interpretations()}


def _answers(yes: set[int]) -> list[dict]:
    """«Да» на номера из yes, «Нет» на остальные."""
    return [
        {"question_id": n, "option_id": n * 10 + (1 if n in yes else 2)}
        for n in range(1, ito.QUESTION_COUNT + 1)
    ]


def _scores(yes: set[int]) -> dict[str, int]:
    res = scoring.compute_result(_engine_test(), _answers(yes))
    return {s["scale_name"]: s["score"] for s in res["scales"]}


def _keyed_yes(scale: str) -> set[int]:
    """Набор ответов «Да», дающий шкале максимум (значимые «Да», без «Нет»)."""
    return set(ito.KEY[scale][0])


# ─── ключ ─────────────────────────────────────────────────────────────────────

def test_key_self_check_passes():
    ito.validate_key()


def test_items_count_and_clean_text():
    assert len(ITEMS) == 91
    for text in ITEMS:
        assert text == " ".join(text.split())
        assert all(ord(c) >= 32 for c in text)


def test_typo_fix_49_in_spontaneity_and_40_only_in_lability():
    assert ito.scale_for_item(49) == ("II", "yes")
    assert ito.scale_for_item(40) == ("VIII", "yes")
    assert 40 not in ito.KEY["II"][0]


@pytest.mark.parametrize("n", [1, 91])
def test_service_items_outside_scales(n):
    assert ito.scale_for_item(n) is None


def test_every_item_2_to_90_in_exactly_one_scale():
    owners = {n: [s for s, (y, no) in ito.KEY.items() if n in y or n in no]
              for n in range(2, 91)}
    assert all(len(v) == 1 for v in owners.values())


def test_max_scores():
    assert ito.max_score("L") == 9
    assert ito.max_score("F") == 8
    for s in ("I", "II", "III", "IV", "V", "VI", "VII", "VIII"):
        assert ito.max_score(s) == 9


# ─── подсчёт общим движком ────────────────────────────────────────────────────

def test_engine_produces_ten_scales_with_max():
    res = scoring.compute_result(_engine_test(), _answers(set()))
    assert res["total_score"] is None
    assert {s["scale_name"] for s in res["scales"]} == set(ito.KEY)
    for s in res["scales"]:
        assert s["max_score"] == ito.max_score(s["scale_name"])


def test_all_no_scores_only_reverse_keyed_items():
    scores = _scores(set())
    for scale, (_, no) in ito.KEY.items():
        assert scores[scale] == len(no)


@pytest.mark.parametrize("scale", list(ito.KEY))
def test_scale_maximum(scale):
    yes = _keyed_yes(scale)
    assert _scores(yes)[scale] == len(yes) + len(ito.KEY[scale][1])


def test_yes_on_49_counts_only_in_spontaneity():
    base = _scores(set())
    with49 = _scores({49})
    diff = {s: with49[s] - base[s] for s in base if with49[s] != base[s]}
    assert diff == {"II": 1}


def test_yes_on_40_counts_only_in_lability():
    base = _scores(set())
    with40 = _scores({40})
    diff = {s: with40[s] - base[s] for s in base if with40[s] != base[s]}
    assert diff == {"VIII": 1}


def test_service_items_do_not_change_scores():
    assert _scores({1, 91}) == _scores(set())


def test_engine_interpretation_labels():
    res = scoring.compute_result(_engine_test(), _answers(_keyed_yes("VII")))
    vii = next(s for s in res["scales"] if s["scale_name"] == "VII")
    assert vii["score"] == 9 and vii["label"] == "Дезадаптирующие свойства"


# ─── уровни, достоверность, типы ──────────────────────────────────────────────

@pytest.mark.parametrize("score,label", [
    (0, "Гипоэмотивность, плохое самопонимание или неоткровенность"),
    (2, "Гипоэмотивность, плохое самопонимание или неоткровенность"),
    (3, "Норма"), (4, "Норма"),
    (5, "Акцентуированные черты"), (7, "Акцентуированные черты"),
    (8, "Дезадаптирующие свойства"), (9, "Дезадаптирующие свойства"),
])
def test_levels(score, label):
    assert ito.level_of(score) == label


@pytest.mark.parametrize("l_score,f_score,valid", [
    (5, 5, True), (6, 0, False), (0, 6, False), (9, 8, False),
])
def test_validity(l_score, f_score, valid):
    assert ito.is_valid({"L": l_score, "F": f_score}) is valid


def _base(**overrides) -> dict:
    scores = {s: 4 for s in ito.KEY}
    scores.update({"L": 2, "F": 2})
    scores.update(overrides)
    return scores


def test_no_types_in_norm():
    assert ito.types_of(_base()) == []
    assert ito.summarize(_base())["types"] == ""


def test_type_requires_all_scales_at_threshold():
    assert ito.types_of(_base(VIII=8, III=7)) == []
    assert ito.types_of(_base(VIII=8, III=8)) == ["Неуравновешенный"]


def test_several_types_joined():
    scores = _base(I=8, VI=8, VIII=9, III=8)
    assert ito.types_of(scores) == ["Социально активный, ранимый", "Неуравновешенный"]
    assert ito.summarize(scores)["types"] == (
        "Социально активный, ранимый; Неуравновешенный"
    )


def test_invalid_result_types_marked():
    scores = _base(L=6, VIII=8, III=8)
    assert ito.types_of(scores) == ["Неуравновешенный (недостоверно)"]
    summary = ito.summarize(scores)
    assert summary["is_valid"] is False
    assert summary["validity_label"] == "недостоверно"


def test_aggravation_type_assigned_with_invalid_mark():
    """Тип с F ≥ 8 возможен только при F > 5 — выводится с пометкой."""
    scores = _base(VII=8, V=8, F=8)
    assert ito.types_of(scores) == [
        "Дезадаптивно-интровертированный, суицидальный риск (недостоверно)"
    ]


def test_export_order_matches_customer_sample():
    assert [ito.SCALE_LABELS[s] for s in ito.EXPORT_SCALE_ORDER] == [
        "L Ложь", "F Аггравация", "IV Ригидность", "II Спонтанность",
        "VI Сензитивность", "VII Тревожность", "VIII Лабильность",
        "I Экстраверсия", "III Агрессивность", "V Интроверсия",
    ]


def test_interpretations_cover_full_range_without_overlap():
    rows = ito.interpretations()
    for scale in ito.KEY:
        ranges = sorted((r["min_score"], r["max_score"])
                        for r in rows if r["scale_name"] == scale)
        assert ranges[0][0] == 0 and ranges[-1][1] == ito.max_score(scale)
        for (_, hi), (lo, _) in zip(ranges, ranges[1:]):
            assert lo == hi + 1
