"""
Unit-тесты валидации модуля психодиагностики (Этап A — admin CRUD).

Service-слой с замоканным storage — без БД (как test_change_password.py).
Покрывают:
  - валидацию структуры теста (вопросы/варианты/scale-config);
  - валидацию порогов интерпретации (диапазоны, пересечения);
  - нормализацию title;
  - проброс ValueError из storage (not found) в service.
"""

import pytest
from unittest.mock import patch

from app.tests import service


# ── helpers ───────────────────────────────────────────────────────────────────

def _choice_question(order=1, n_opts=2, qtype="single_choice"):
    return {
        "question_text": f"Вопрос {order}",
        "question_order": order,
        "question_type": qtype,
        "is_required": True,
        "config": {},
        "options": [
            {"option_text": f"O{i}", "option_order": i, "value_score": i}
            for i in range(n_opts)
        ],
    }


def _interp(min_s, max_s, scale=None, label="L"):
    return {
        "scale_name": scale, "min_score": min_s, "max_score": max_s,
        "label": label, "recommendation": None,
    }


def _base_test(**over):
    data = {
        "title": "Тест", "description": None, "scoring": "sum",
        "max_score": None, "time_limit_min": None, "is_active": True,
        "category_ids": [], "tag_uuids": [], "questions": [], "interpretations": [],
    }
    data.update(over)
    return data


# ── валидация вопросов ────────────────────────────────────────────────────────

def test_choice_requires_two_options():
    with pytest.raises(ValueError, match="минимум 2 варианта"):
        service._validate_questions([_choice_question(n_opts=1)])


def test_choice_two_options_ok():
    service._validate_questions([_choice_question(n_opts=2)])  # no raise


def test_duplicate_question_order_rejected():
    qs = [_choice_question(order=1), _choice_question(order=1)]
    with pytest.raises(ValueError, match="question_order"):
        service._validate_questions(qs)


def test_duplicate_option_order_rejected():
    q = _choice_question(n_opts=2)
    q["options"][1]["option_order"] = q["options"][0]["option_order"]
    with pytest.raises(ValueError, match="option_order"):
        service._validate_questions([q])


def test_scale_requires_valid_config():
    q = {
        "question_text": "S", "question_order": 1, "question_type": "scale",
        "is_required": True, "config": {"min": 5, "max": 1}, "options": [],
    }
    with pytest.raises(ValueError, match="min < max"):
        service._validate_questions([q])


def test_scale_valid_config_ok():
    q = {
        "question_text": "S", "question_order": 1, "question_type": "scale",
        "is_required": True, "config": {"min": 0, "max": 10}, "options": [],
    }
    service._validate_questions([q])  # no raise


def test_free_text_needs_no_options():
    q = {
        "question_text": "F", "question_order": 1, "question_type": "free_text",
        "is_required": False, "config": {}, "options": [],
    }
    service._validate_questions([q])  # no raise


def test_empty_questions_allowed():
    service._validate_questions([])  # черновик допустим


# ── валидация интерпретаций ───────────────────────────────────────────────────

def test_interpretation_min_gt_max_rejected():
    with pytest.raises(ValueError, match="min_score"):
        service._validate_interpretations([_interp(10, 5)])


def test_interpretation_overlap_rejected():
    items = [_interp(0, 5), _interp(5, 10)]  # 5 пересекается
    with pytest.raises(ValueError, match="ересекающиеся"):
        service._validate_interpretations(items)


def test_interpretation_adjacent_ok():
    items = [_interp(0, 5), _interp(6, 10)]
    service._validate_interpretations(items)  # no raise


def test_interpretation_overlap_isolated_per_scale():
    # одинаковые диапазоны, но разные шкалы — не пересечение
    items = [_interp(0, 5, scale="anxiety"), _interp(0, 5, scale="depression")]
    service._validate_interpretations(items)  # no raise


# ── нормализация title ────────────────────────────────────────────────────────

def test_blank_title_rejected():
    with pytest.raises(ValueError, match="не может быть пустым"):
        service._normalize(_base_test(title="   "))


def test_title_trimmed():
    out = service._normalize(_base_test(title="  Тест  "))
    assert out["title"] == "Тест"


# ── service: проброс в storage ────────────────────────────────────────────────

def test_create_test_calls_storage_after_validation():
    data = _base_test(questions=[_choice_question()], interpretations=[_interp(0, 5)])
    with patch.object(service.storage, "create_test", return_value={"uuid": "x"}) as m:
        result = service.create_test(data, created_by=1)
    assert result == {"uuid": "x"}
    m.assert_called_once()


def test_create_test_blocks_invalid_structure_before_storage():
    data = _base_test(questions=[_choice_question(n_opts=1)])
    with patch.object(service.storage, "create_test") as m:
        with pytest.raises(ValueError):
            service.create_test(data, created_by=1)
    m.assert_not_called()


def test_update_test_not_found_raises():
    with patch.object(service.storage, "update_test", return_value=None):
        with pytest.raises(ValueError, match="не найден"):
            service.update_test("missing-uuid", {"title": "X"})


def test_delete_test_not_found_raises():
    with patch.object(service.storage, "delete_test", return_value=False):
        with pytest.raises(ValueError, match="не найден"):
            service.delete_test("missing-uuid")


# ── правило «все шкалы или ни одной» (P0-2) ───────────────────────────────────
# scoring.compute_result считает тест многошкальным, если шкала есть хоть у
# одного вопроса, и молча выбрасывает из подсчёта вопросы без шкалы. Ловим это
# на сохранении.

def _scaled(order, scale):
    q = _choice_question(order=order)
    q["config"] = {"scale": scale}
    return q


def test_scale_on_all_scored_questions_ok():
    service._validate_questions([_scaled(1, "Тревога"), _scaled(2, "Депрессия")])


def test_no_scales_at_all_ok():
    service._validate_questions([_choice_question(1), _choice_question(2)])


def test_partial_scales_rejected():
    with pytest.raises(ValueError, match="Шкала указана не у всех"):
        service._validate_questions([_scaled(1, "Тревога"), _choice_question(2)])


def test_partial_scales_error_lists_questions_without_scale():
    with pytest.raises(ValueError, match=r"#2, #3"):
        service._validate_questions([
            _scaled(1, "Тревога"), _choice_question(2), _choice_question(3),
        ])


def test_blank_scale_counts_as_absent():
    q = _choice_question(1)
    q["config"] = {"scale": "   "}
    with pytest.raises(ValueError, match="Шкала указана не у всех"):
        service._validate_questions([q, _scaled(2, "Тревога")])


def test_free_text_not_required_to_have_scale():
    # free_text не участвует в подсчёте, поэтому шкала для него не обязательна
    free = {
        "question_text": "Комментарий", "question_order": 2,
        "question_type": "free_text", "is_required": False,
        "config": {}, "options": [],
    }
    service._validate_questions([_scaled(1, "Тревога"), free])


def test_scale_type_question_included_in_coverage_rule():
    scale_q = {
        "question_text": "Оцените", "question_order": 2, "question_type": "scale",
        "is_required": True, "config": {"min": 0, "max": 10}, "options": [],
    }
    with pytest.raises(ValueError, match="Шкала указана не у всех"):
        service._validate_questions([_scaled(1, "Тревога"), scale_q])


# ── запрет правки вопросов теста с результатами (P0-1) ────────────────────────

def test_update_questions_blocked_when_results_exist():
    data = {"questions": [_choice_question()]}
    with patch.object(service.storage, "test_has_results", return_value=True), \
         patch.object(service.storage, "update_test") as m:
        with pytest.raises(service.TestHasResults, match="уже есть результаты"):
            service.update_test("some-uuid", data)
    m.assert_not_called()


def test_update_questions_allowed_when_no_results():
    data = {"questions": [_choice_question()]}
    with patch.object(service.storage, "test_has_results", return_value=False), \
         patch.object(service.storage, "update_test", return_value={"uuid": "x"}) as m:
        assert service.update_test("some-uuid", data) == {"uuid": "x"}
    m.assert_called_once()


def test_update_metadata_only_allowed_when_results_exist():
    # переименование теста с результатами должно проходить: FK из
    # student_answers держит questions/options, а не заголовок
    with patch.object(service.storage, "test_has_results", return_value=True) as has, \
         patch.object(service.storage, "update_test", return_value={"uuid": "x"}) as m:
        assert service.update_test("some-uuid", {"title": "Новое имя"}) == {"uuid": "x"}
    m.assert_called_once()
    has.assert_not_called()


def test_update_interpretations_allowed_when_results_exist():
    # пороги не связаны FK с результатами, а расшифровка снапшотится при submit
    with patch.object(service.storage, "test_has_results", return_value=True), \
         patch.object(service.storage, "update_test", return_value={"uuid": "x"}) as m:
        service.update_test("some-uuid", {"interpretations": [_interp(0, 5)]})
    m.assert_called_once()


# ── дублирование методики (P0-1, штатный путь правки) ─────────────────────────

def test_duplicate_test_not_found_raises():
    with patch.object(service.storage, "duplicate_test", return_value=None):
        with pytest.raises(ValueError, match="не найден"):
            service.duplicate_test("missing-uuid", created_by=1)


def test_duplicate_test_returns_copy():
    with patch.object(service.storage, "duplicate_test", return_value={"uuid": "copy"}) as m:
        assert service.duplicate_test("src-uuid", created_by=7) == {"uuid": "copy"}
    m.assert_called_once_with("src-uuid", created_by=7)


# ── анализ покрытия порогов интерпретации ─────────────────────────────────────
# Пороги валидируются на пересечения, но НЕ на покрытие: балл, не попавший ни в
# один диапазон, молча даёт recommendations=null. analyze_test это показывает.

def _q_scores(scores, order=1, scale=None):
    q = _choice_question(order=order, n_opts=len(scores))
    q["options"] = [
        {"option_text": str(s), "option_order": i, "value_score": s}
        for i, s in enumerate(scores)
    ]
    if scale:
        q["config"] = {"scale": scale}
    return q


def test_analyze_reports_gap_between_thresholds():
    test = {
        "scoring": "sum",
        "questions": [_q_scores([0, 3], 1), _q_scores([0, 3], 2)],   # 0..6
        "interpretations": [_interp(0, 2, label="Низкий"), _interp(5, 6, label="Высокий")],
    }
    result = service.analyze_test(test)
    assert result["score_bounds"] == [{"scale_name": None, "min_score": 0, "max_score": 6}]
    assert result["issues"] == [
        {"scale_name": None, "min_score": 3, "max_score": 4, "kind": "gap", "label": None},
    ]


def test_analyze_reports_tail_gap():
    test = {
        "scoring": "sum",
        "questions": [_q_scores([0, 3], 1)],                          # 0..3
        "interpretations": [_interp(0, 1)],
    }
    kinds = [(i["kind"], i["min_score"], i["max_score"]) for i in service.analyze_test(test)["issues"]]
    assert kinds == [("gap", 2, 3)]


def test_analyze_full_coverage_has_no_issues():
    test = {
        "scoring": "sum",
        "questions": [_q_scores([0, 3], 1)],
        "interpretations": [_interp(0, 1), _interp(2, 3)],
    }
    assert service.analyze_test(test)["issues"] == []


def test_analyze_reports_unreachable_threshold():
    test = {
        "scoring": "sum",
        "questions": [_q_scores([0, 3], 1)],
        "interpretations": [_interp(0, 3), _interp(50, 60, label="Мимо")],
    }
    issues = service.analyze_test(test)["issues"]
    assert [i["kind"] for i in issues] == ["out_of_range"]
    assert issues[0]["label"] == "Мимо"


def test_analyze_reports_threshold_for_unknown_scale():
    test = {
        "scoring": "sum",
        "questions": [_q_scores([0, 3], 1, scale="Тревога")],
        "interpretations": [_interp(0, 3, scale="Тревога"), _interp(0, 1, scale="Опечатка")],
    }
    issues = service.analyze_test(test)["issues"]
    assert [i["kind"] for i in issues] == ["unknown_scale"]
    assert issues[0]["scale_name"] == "Опечатка"


def test_analyze_without_interpretations_is_not_a_gap():
    # черновик без порогов — это не ошибка, а незаконченная работа
    test = {"scoring": "sum", "questions": [_q_scores([0, 3], 1)], "interpretations": []}
    result = service.analyze_test(test)
    assert result["score_bounds"] and result["issues"] == []


def test_analyze_draft_without_questions_is_empty():
    test = {"scoring": "sum", "questions": [], "interpretations": [_interp(0, 5)]}
    assert service.analyze_test(test) == {"score_bounds": [], "issues": []}


def test_analyze_multi_scale_gaps_are_per_scale():
    test = {
        "scoring": "sum",
        "questions": [_q_scores([0, 3], 1, scale="A"), _q_scores([0, 3], 2, scale="B")],
        "interpretations": [_interp(0, 3, scale="A"), _interp(0, 1, scale="B")],
    }
    issues = service.analyze_test(test)["issues"]
    assert issues == [
        {"scale_name": "B", "min_score": 2, "max_score": 3, "kind": "gap", "label": None},
    ]
