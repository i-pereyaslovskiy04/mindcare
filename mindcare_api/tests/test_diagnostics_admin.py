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
