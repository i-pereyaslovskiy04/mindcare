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
        assert service.duplicate_test(
            "src-uuid", created_by=7, actor_role="admin",
        ) == {"uuid": "copy"}
    # Stage 4B-5: service пробрасывает actor context в storage.
    m.assert_called_once_with(
        "src-uuid", created_by=7, actor_role="admin", ip=None, user_agent=None,
    )


# ── медиа в вопросах/вариантах (изображения) ──────────────────────────────────
# Явно прикреплённое изображение обязано существовать: в отличие от категорий/
# тегов НЕ пропускаем молча, иначе автор сохранит и потеряет картинку.

def test_question_media_valid_uuid_ok():
    q = _choice_question()
    q["media"] = [{"media_uuid": "abc", "caption": "подпись"}]
    with patch.object(service.storage, "media_exists", return_value=True) as m:
        service._validate_questions([q])   # no raise
    m.assert_called_with("abc")


def test_question_media_missing_uuid_rejected():
    q = _choice_question()
    q["media"] = [{"media_uuid": "gone", "caption": None}]
    with patch.object(service.storage, "media_exists", return_value=False):
        with pytest.raises(ValueError, match="изображение не найдено"):
            service._validate_questions([q])


def test_option_media_missing_uuid_rejected():
    q = _choice_question()
    q["options"][0]["media"] = [{"media_uuid": "gone"}]
    with patch.object(service.storage, "media_exists", return_value=False):
        with pytest.raises(ValueError, match=r"вариант #1.*изображение не найдено"):
            service._validate_questions([q])


def test_no_media_does_not_call_resolver():
    # обычный тест без картинок не должен трогать медиатеку
    with patch.object(service.storage, "media_exists") as m:
        service._validate_questions([_choice_question()])
    m.assert_not_called()


# ── staff-доступ к результатам: резолв acting-роли (Этап E) ───────────────────

def test_staff_result_role_single_supervisor():
    assert service._resolve_staff_result_role(["supervisor", "student"], None) == "supervisor"


def test_staff_result_role_single_psychologist():
    assert service._resolve_staff_result_role(["psychologist", "student"], None) == "psychologist"


def test_staff_result_role_multi_defaults_conservative():
    # без X-Active-Role при обеих ролях — консервативно psychologist (scoped)
    assert service._resolve_staff_result_role(
        ["supervisor", "psychologist"], None,
    ) == "psychologist"


def test_staff_result_role_honours_valid_active_role():
    assert service._resolve_staff_result_role(
        ["supervisor", "psychologist"], "supervisor",
    ) == "supervisor"


def test_staff_result_role_rejects_active_role_outside_holder():
    with pytest.raises(service.ResultAccessError):
        service._resolve_staff_result_role(["psychologist"], "supervisor")


def test_staff_result_role_rejects_no_holder():
    # admin вне ролей результатов (ADR-016) — доступа нет
    with pytest.raises(service.ResultAccessError):
        service._resolve_staff_result_role(["admin", "student"], None)


# ── случайный порядок (shuffle) в проекции для прохождения ────────────────────

def _take_tree(shuffle_q=False, shuffle_o=False):
    def _opt(i, order):
        return {"id": i, "option_text": f"o{i}", "option_order": order,
                "value_score": order, "media": []}
    def _q(i, order):
        return {"id": i, "question_text": f"q{i}", "question_order": order,
                "question_type": "single_choice", "is_required": True,
                "config": {}, "media": [],
                "options": [_opt(i * 10 + 1, 0), _opt(i * 10 + 2, 1)]}
    return {
        "uuid": "u", "title": "t", "description": None, "time_limit_min": None,
        "shuffle_questions": shuffle_q, "shuffle_options": shuffle_o,
        "questions": [_q(1, 1), _q(2, 2)],
    }


def test_strip_take_no_shuffle_preserves_order():
    out = service._strip_take(_take_tree())
    assert [q["id"] for q in out["questions"]] == [1, 2]
    assert [o["id"] for o in out["questions"][0]["options"]] == [11, 12]


def test_strip_take_shuffle_questions(monkeypatch):
    monkeypatch.setattr(service._random, "shuffle", lambda lst: lst.reverse())
    out = service._strip_take(_take_tree(shuffle_q=True))
    assert [q["id"] for q in out["questions"]] == [2, 1]         # порядок вопросов перевёрнут
    assert [o["id"] for o in out["questions"][0]["options"]] == [21, 22]  # варианты не тронуты


def test_strip_take_shuffle_options(monkeypatch):
    monkeypatch.setattr(service._random, "shuffle", lambda lst: lst.reverse())
    out = service._strip_take(_take_tree(shuffle_o=True))
    assert [q["id"] for q in out["questions"]] == [1, 2]         # вопросы не тронуты
    assert [o["id"] for o in out["questions"][0]["options"]] == [12, 11]  # варианты перевёрнуты


def test_strip_take_shuffle_never_leaks_value_score():
    out = service._strip_take(_take_tree(shuffle_q=True, shuffle_o=True))
    ids = {q["id"] for q in out["questions"]}
    assert ids == {1, 2}                                          # состав сохранён
    for q in out["questions"]:
        for o in q["options"]:
            assert "value_score" not in o


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


# ── moderation workflow: _validate_transition (Этап F, ADR-016) ───────────────
# Легальные переходы: draft/needs_changes → in_review (только автор);
# draft/in_review/needs_changes → published (только staff);
# in_review → needs_changes (только staff). published не имеет исходящих
# переходов (снятие с публикации — существующий is_active toggle).

@pytest.mark.parametrize("current", ["draft", "needs_changes"])
def test_transition_to_in_review_by_author_ok(current):
    event = service._validate_transition(current, "in_review", "psychologist", True)
    assert event == "test_submitted_for_review"


@pytest.mark.parametrize("current", ["draft", "needs_changes"])
def test_transition_to_in_review_by_non_author_forbidden(current):
    with pytest.raises(service.TestTransitionForbidden):
        service._validate_transition(current, "in_review", "psychologist", False)


@pytest.mark.parametrize("current", ["draft", "in_review", "needs_changes"])
@pytest.mark.parametrize("role", ["admin", "supervisor"])
def test_transition_to_published_by_staff_ok(current, role):
    event = service._validate_transition(current, "published", role, False)
    assert event == "test_published"


@pytest.mark.parametrize("current", ["draft", "in_review", "needs_changes"])
def test_transition_to_published_by_non_staff_forbidden(current):
    # даже автор-психолог не может публиковать напрямую — только admin/supervisor
    with pytest.raises(service.TestTransitionForbidden):
        service._validate_transition(current, "published", "psychologist", True)


@pytest.mark.parametrize("role", ["admin", "supervisor"])
def test_transition_in_review_to_needs_changes_by_staff_ok(role):
    event = service._validate_transition("in_review", "needs_changes", role, False)
    assert event == "test_returned_for_changes"


def test_transition_in_review_to_needs_changes_by_non_staff_forbidden():
    with pytest.raises(service.TestTransitionForbidden):
        service._validate_transition("in_review", "needs_changes", "psychologist", False)


@pytest.mark.parametrize("current,target", [
    ("draft", "needs_changes"),        # нет прямого пути, минуя review
    ("draft", "draft"),                # no-op не определён
    ("published", "draft"),            # unpublish — не через status
    ("published", "in_review"),
    ("published", "needs_changes"),
    ("in_review", "draft"),
    ("needs_changes", "needs_changes"),
])
def test_illegal_transitions_rejected_regardless_of_role(current, target):
    # роль/авторство не спасают нелегальный переход — 409, не 403
    with pytest.raises(service.TestTransitionError):
        service._validate_transition(current, target, "admin", True)


# ── авторство psychologist: create_my_test / _own_editable_test (Этап F2) ─────

def test_create_my_test_forces_draft_even_if_client_sends_published():
    data = _base_test(status="published")
    with patch.object(service.storage, "create_test", return_value={"uuid": "x"}) as m:
        service.create_my_test(data, created_by=7)
    called_data = m.call_args.args[0]
    assert called_data["status"] == "draft"
    assert m.call_args.kwargs["created_by"] == 7


def test_create_my_test_default_actor_role_is_psychologist():
    with patch.object(service.storage, "create_test", return_value={"uuid": "x"}) as m:
        service.create_my_test(_base_test(), created_by=7)
    assert m.call_args.kwargs["actor_role"] == "psychologist"


@pytest.mark.parametrize("status_", ["draft", "needs_changes"])
def test_own_editable_test_ok_for_editable_statuses(status_):
    with patch.object(
        service.storage, "get_status_and_author",
        return_value={"status": status_, "created_by": 7},
    ):
        found = service._own_editable_test("u", 7)
    assert found["status"] == status_


@pytest.mark.parametrize("status_", ["in_review", "published"])
def test_own_editable_test_rejects_non_editable_status(status_):
    with patch.object(
        service.storage, "get_status_and_author",
        return_value={"status": status_, "created_by": 7},
    ):
        with pytest.raises(service.TestNotEditable):
            service._own_editable_test("u", 7)


def test_own_editable_test_not_found_is_404():
    with patch.object(service.storage, "get_status_and_author", return_value=None):
        with pytest.raises(ValueError, match="не найден"):
            service._own_editable_test("u", 7)


def test_own_editable_test_wrong_owner_is_404_not_403():
    # чужой тест неотличим от несуществующего (как session_notes) — 404, не 403
    with patch.object(
        service.storage, "get_status_and_author",
        return_value={"status": "draft", "created_by": 999},
    ):
        with pytest.raises(ValueError, match="не найден"):
            service._own_editable_test("u", 7)


def test_get_my_test_wrong_owner_is_404():
    with patch.object(
        service.storage, "get_test_by_uuid",
        return_value={"uuid": "u", "created_by": 999},
    ):
        with pytest.raises(ValueError, match="не найден"):
            service.get_my_test("u", author_id=7)


def test_get_my_test_own_ok():
    with patch.object(
        service.storage, "get_test_by_uuid",
        return_value={"uuid": "u", "created_by": 7},
    ):
        assert service.get_my_test("u", author_id=7)["uuid"] == "u"


def test_update_my_test_blocked_when_not_editable():
    with patch.object(
        service.storage, "get_status_and_author",
        return_value={"status": "in_review", "created_by": 7},
    ), patch.object(service.storage, "update_test") as m:
        with pytest.raises(service.TestNotEditable):
            service.update_my_test("u", {"title": "X"}, actor_id=7)
    m.assert_not_called()


def test_delete_my_test_blocked_when_not_editable():
    with patch.object(
        service.storage, "get_status_and_author",
        return_value={"status": "published", "created_by": 7},
    ), patch.object(service.storage, "delete_test") as m:
        with pytest.raises(service.TestNotEditable):
            service.delete_my_test("u", actor_id=7)
    m.assert_not_called()


# ── Этап F2.1: автор дорабатывает свой published тест (снимается с публикации) ─

@pytest.mark.parametrize("status_", ["draft", "needs_changes", "published"])
def test_own_updatable_test_ok_for_updatable_statuses(status_):
    with patch.object(
        service.storage, "get_status_and_author",
        return_value={"status": status_, "created_by": 7},
    ):
        found = service._own_updatable_test("u", 7)
    assert found["status"] == status_


def test_own_updatable_test_rejects_in_review():
    with patch.object(
        service.storage, "get_status_and_author",
        return_value={"status": "in_review", "created_by": 7},
    ):
        with pytest.raises(service.TestNotEditable):
            service._own_updatable_test("u", 7)


def test_own_updatable_test_wrong_owner_is_404_not_403():
    with patch.object(
        service.storage, "get_status_and_author",
        return_value={"status": "published", "created_by": 999},
    ):
        with pytest.raises(ValueError, match="не найден"):
            service._own_updatable_test("u", 7)


def test_update_my_test_of_published_passes_unpublish_event():
    with patch.object(
        service.storage, "get_status_and_author",
        return_value={"status": "published", "created_by": 7},
    ), patch.object(service.storage, "update_test", return_value={"uuid": "u"}) as m:
        service.update_my_test("u", {"title": "X"}, actor_id=7)
    assert m.call_args.kwargs["unpublish_event"] == "test_unpublished_for_edit"


@pytest.mark.parametrize("status_", ["draft", "needs_changes"])
def test_update_my_test_of_draft_like_does_not_unpublish(status_):
    with patch.object(
        service.storage, "get_status_and_author",
        return_value={"status": status_, "created_by": 7},
    ), patch.object(service.storage, "update_test", return_value={"uuid": "u"}) as m:
        service.update_my_test("u", {"title": "X"}, actor_id=7)
    assert m.call_args.kwargs["unpublish_event"] is None


def test_update_my_test_of_in_review_still_blocked():
    with patch.object(
        service.storage, "get_status_and_author",
        return_value={"status": "in_review", "created_by": 7},
    ), patch.object(service.storage, "update_test") as m:
        with pytest.raises(service.TestNotEditable):
            service.update_my_test("u", {"title": "X"}, actor_id=7)
    m.assert_not_called()


# ── Этап F2.2: автор дублирует свой тест (любой статус источника) ──────────────

@pytest.mark.parametrize("status_", ["draft", "needs_changes", "in_review", "published"])
def test_duplicate_my_test_ok_for_any_status(status_):
    with patch.object(
        service.storage, "get_status_and_author",
        return_value={"status": status_, "created_by": 7},
    ), patch.object(
        service.storage, "duplicate_test", return_value={"uuid": "copy"},
    ) as m:
        result = service.duplicate_my_test("u", actor_id=7)
    assert result == {"uuid": "copy"}
    assert m.call_args.kwargs["created_by"] == 7


def test_duplicate_my_test_wrong_owner_is_404_not_403():
    with patch.object(
        service.storage, "get_status_and_author",
        return_value={"status": "draft", "created_by": 999},
    ), patch.object(service.storage, "duplicate_test") as m:
        with pytest.raises(ValueError, match="не найден"):
            service.duplicate_my_test("u", actor_id=7)
    m.assert_not_called()


def test_duplicate_my_test_not_found_is_404():
    with patch.object(
        service.storage, "get_status_and_author", return_value=None,
    ), patch.object(service.storage, "duplicate_test") as m:
        with pytest.raises(ValueError, match="не найден"):
            service.duplicate_my_test("u", actor_id=7)
    m.assert_not_called()


def test_duplicate_my_test_default_actor_role_is_psychologist():
    with patch.object(
        service.storage, "get_status_and_author",
        return_value={"status": "draft", "created_by": 7},
    ), patch.object(
        service.storage, "duplicate_test", return_value={"uuid": "copy"},
    ) as m:
        service.duplicate_my_test("u", actor_id=7)
    assert m.call_args.kwargs["actor_role"] == "psychologist"
