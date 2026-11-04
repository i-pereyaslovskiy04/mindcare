"""
Проверка ответов кампании и подсчёт (ADR-036) — чистые функции, без БД.

Тест кампании — только вопросы single_choice; ответ обязателен на КАЖДЫЙ
вопрос (частичная отправка не принимается). Подсчёт — общий движок
app/tests/scoring.compute_result.
"""
from app.tests import scoring


class AnswersInvalid(Exception):
    """Ответы не соответствуют тесту: пропуск, дубль, чужой вопрос/вариант."""


def validate_answers(test: dict, answers: list[dict]) -> list[dict]:
    """Нормализованный список {question_id, option_id} в порядке вопросов теста."""
    options_of = {q["id"]: {o["id"] for o in q["options"]} for q in test["questions"]}
    chosen: dict[int, int] = {}
    for a in answers:
        qid, oid = a["question_id"], a["option_id"]
        if qid not in options_of:
            raise AnswersInvalid("unknown_question")
        if qid in chosen:
            raise AnswersInvalid("duplicate_question")
        if oid not in options_of[qid]:
            raise AnswersInvalid("foreign_option")
        chosen[qid] = oid
    if set(chosen) != set(options_of):
        raise AnswersInvalid("missing_answers")
    return [{"question_id": q["id"], "option_id": chosen[q["id"]]}
            for q in test["questions"]]


def compute(test: dict, answers: list[dict]) -> list[dict]:
    """Баллы шкал [{scale_name, score, max_score}] (многошкальный тест) или
    одна строка scale_name=None→'total' для одношкального."""
    result = scoring.compute_result(test, answers)
    if result["scales"]:
        return [{"scale_name": s["scale_name"], "score": s["score"],
                 "max_score": s["max_score"]} for s in result["scales"]]
    return [{"scale_name": "total", "score": result["total_score"] or 0,
             "max_score": result["max_possible"] or 0}]
