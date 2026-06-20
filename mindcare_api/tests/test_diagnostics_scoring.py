"""
Unit-тесты подсчёта результата (Этап B) — чистые функции, без БД.

Покрывают:
  - score_question по 4 типам вопросов;
  - агрегацию sum / average;
  - одношкальный итог + интерпретация по порогам;
  - многошкальный тест (config["scale"]) → total None, шкалы отдельно;
  - изоляцию value_score в проекции для прохождения (_strip_take);
  - валидацию ответов submit (_validate_answers).
"""

import pytest

from app.tests import scoring, service


# ── фабрики ───────────────────────────────────────────────────────────────────

def _opt(id_, score, order=0):
    return {"id": id_, "option_text": f"o{id_}", "option_order": order, "value_score": score}


def _q(id_, qtype, options=None, config=None, order=1, required=True):
    return {
        "id": id_, "question_text": f"q{id_}", "question_order": order,
        "question_type": qtype, "is_required": required,
        "config": config or {}, "options": options or [],
    }


def _test(questions, scoring_method="sum", interpretations=None):
    return {
        "uuid": "u", "title": "t", "description": None, "time_limit_min": None,
        "scoring": scoring_method, "questions": questions,
        "interpretations": interpretations or [],
    }


# ── score_question ────────────────────────────────────────────────────────────

def test_single_choice_score():
    q = _q(1, "single_choice", [_opt(10, 0), _opt(11, 3)])
    assert scoring.score_question(q, {"option_id": 11}) == 3
    assert scoring.score_question(q, {"option_id": 99}) == 0


def test_multiple_choice_score_sums_selected():
    q = _q(1, "multiple_choice", [_opt(10, 1), _opt(11, 2), _opt(12, 4)])
    assert scoring.score_question(q, {"selected_options": [10, 12]}) == 5


def test_scale_score():
    q = _q(1, "scale", config={"min": 0, "max": 10})
    assert scoring.score_question(q, {"scale_value": 7}) == 7


def test_free_text_not_scored():
    q = _q(1, "free_text")
    assert scoring.score_question(q, {"free_text_answer": "hi"}) is None


# ── агрегация и интерпретация (одношкальный) ──────────────────────────────────

def test_sum_total_and_interpretation():
    qs = [
        _q(1, "single_choice", [_opt(1, 0), _opt(2, 3)], order=1),
        _q(2, "single_choice", [_opt(3, 0), _opt(4, 2)], order=2),
    ]
    interp = [
        {"scale_name": None, "min_score": 0, "max_score": 2, "label": "Низкий", "recommendation": "ok"},
        {"scale_name": None, "min_score": 3, "max_score": 5, "label": "Высокий", "recommendation": "к врачу"},
    ]
    res = scoring.compute_result(_test(qs, "sum", interp), [
        {"question_id": 1, "option_id": 2},   # 3
        {"question_id": 2, "option_id": 4},   # 2
    ])
    assert res["total_score"] == 5
    assert res["max_possible"] == 5
    assert res["scales"] == []
    assert res["recommendations"] == "Высокий: к врачу"


def test_average_aggregation():
    qs = [
        _q(1, "scale", config={"min": 0, "max": 10}, order=1),
        _q(2, "scale", config={"min": 0, "max": 10}, order=2),
    ]
    res = scoring.compute_result(_test(qs, "average"), [
        {"question_id": 1, "scale_value": 4},
        {"question_id": 2, "scale_value": 6},
    ])
    assert res["total_score"] == 5      # avg(4,6)
    assert res["max_possible"] == 10    # avg(10,10)


def test_no_interpretation_when_out_of_range():
    qs = [_q(1, "single_choice", [_opt(1, 0), _opt(2, 1)])]
    interp = [{"scale_name": None, "min_score": 5, "max_score": 9, "label": "X", "recommendation": "y"}]
    res = scoring.compute_result(_test(qs, "sum", interp), [{"question_id": 1, "option_id": 2}])
    assert res["total_score"] == 1
    assert res["recommendations"] is None


# ── многошкальный ─────────────────────────────────────────────────────────────

def test_multi_scale_produces_scales_and_null_total():
    qs = [
        _q(1, "scale", config={"min": 0, "max": 3, "scale": "anxiety"}, order=1),
        _q(2, "scale", config={"min": 0, "max": 3, "scale": "anxiety"}, order=2),
        _q(3, "scale", config={"min": 0, "max": 3, "scale": "depression"}, order=3),
    ]
    interp = [
        {"scale_name": "anxiety", "min_score": 0, "max_score": 3, "label": "A-норма", "recommendation": "ok"},
        {"scale_name": "anxiety", "min_score": 4, "max_score": 6, "label": "A-высокий", "recommendation": "помощь"},
    ]
    res = scoring.compute_result(_test(qs, "sum", interp), [
        {"question_id": 1, "scale_value": 3},
        {"question_id": 2, "scale_value": 2},   # anxiety total 5
        {"question_id": 3, "scale_value": 1},   # depression total 1
    ])
    assert res["total_score"] is None
    by_name = {s["scale_name"]: s for s in res["scales"]}
    assert by_name["anxiety"]["score"] == 5
    assert by_name["anxiety"]["max_score"] == 6
    assert by_name["anxiety"]["label"] == "A-высокий"
    assert by_name["anxiety"]["interpretation"] == "помощь"
    assert by_name["depression"]["score"] == 1


# ── изоляция ключа теста ──────────────────────────────────────────────────────

def test_strip_take_hides_value_score_and_interpretations():
    full = _test(
        [_q(1, "single_choice", [_opt(1, 0), _opt(2, 9)])],
        "sum",
        [{"scale_name": None, "min_score": 0, "max_score": 9, "label": "L", "recommendation": "r"}],
    )
    stripped = service._strip_take(full)
    assert "interpretations" not in stripped
    opt = stripped["questions"][0]["options"][0]
    assert "value_score" not in opt
    assert set(opt.keys()) == {"id", "option_text", "option_order"}


# ── валидация ответов submit ──────────────────────────────────────────────────

def test_validate_requires_required_question():
    t = _test([_q(1, "single_choice", [_opt(1, 0), _opt(2, 1)], required=True)])
    with pytest.raises(ValueError, match="обязател"):
        service._validate_answers(t, [])


def test_validate_single_choice_bad_option():
    t = _test([_q(1, "single_choice", [_opt(1, 0), _opt(2, 1)])])
    with pytest.raises(ValueError, match="single_choice"):
        service._validate_answers(t, [{"question_id": 1, "option_id": 999}])


def test_validate_scale_out_of_range():
    t = _test([_q(1, "scale", config={"min": 0, "max": 5})])
    with pytest.raises(ValueError, match="диапазон"):
        service._validate_answers(t, [{"question_id": 1, "scale_value": 9}])


def test_validate_multiple_choice_subset():
    t = _test([_q(1, "multiple_choice", [_opt(1, 1), _opt(2, 1)])])
    with pytest.raises(ValueError, match="multiple_choice"):
        service._validate_answers(t, [{"question_id": 1, "selected_options": [1, 77]}])


def test_validate_answer_from_foreign_question():
    t = _test([_q(1, "single_choice", [_opt(1, 0), _opt(2, 1)], required=False)])
    with pytest.raises(ValueError, match="не из этого теста"):
        service._validate_answers(t, [{"question_id": 555, "option_id": 1}])
