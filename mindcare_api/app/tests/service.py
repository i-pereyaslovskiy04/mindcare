"""
Бизнес-логика модуля психодиагностики (Этап A — admin CRUD).

Не знает про FastAPI/HTTP. Валидация структуры теста выбрасывает ValueError —
роутер транслирует в HTTP 422/404.
"""

from typing import Optional

from app.tests import storage, scoring

_CHOICE_TYPES = {"single_choice", "multiple_choice"}


class ConsentRequired(Exception):
    """У пользователя нет принятого актуального согласия `test_consent`."""


class ConfigError(Exception):
    """Отсутствует seed-политика `test_consent` — проблема reference data."""


# ── валидация ─────────────────────────────────────────────────────────────────

def _validate_questions(questions: list[dict]) -> None:
    if not questions:
        return  # пустой тест-черновик допустим на Этапе A

    orders = [q["question_order"] for q in questions]
    if len(orders) != len(set(orders)):
        raise ValueError("question_order должен быть уникальным в пределах теста")

    for idx, q in enumerate(questions, start=1):
        qtype = q["question_type"]
        options = q.get("options", [])

        if qtype in _CHOICE_TYPES:
            if len(options) < 2:
                raise ValueError(
                    f"Вопрос #{idx}: для {qtype} нужно минимум 2 варианта ответа"
                )
            opt_orders = [o["option_order"] for o in options]
            if len(opt_orders) != len(set(opt_orders)):
                raise ValueError(
                    f"Вопрос #{idx}: option_order должен быть уникальным"
                )
        elif qtype == "scale":
            cfg = q.get("config") or {}
            lo, hi = cfg.get("min"), cfg.get("max")
            if not isinstance(lo, int) or not isinstance(hi, int) or lo >= hi:
                raise ValueError(
                    f"Вопрос #{idx}: scale требует config с целыми min < max"
                )
        # free_text — варианты/конфиг не требуются


def _validate_interpretations(interpretations: list[dict]) -> None:
    if not interpretations:
        return

    # группируем по шкале (None = по итоговому баллу теста)
    by_scale: dict[Optional[str], list[dict]] = {}
    for i in interpretations:
        if i["min_score"] > i["max_score"]:
            raise ValueError(
                f"Интерпретация «{i['label']}»: min_score не может быть больше max_score"
            )
        by_scale.setdefault(i.get("scale_name"), []).append(i)

    for scale, items in by_scale.items():
        ordered = sorted(items, key=lambda x: x["min_score"])
        for prev, cur in zip(ordered, ordered[1:]):
            if cur["min_score"] <= prev["max_score"]:
                where = f"шкалы «{scale}»" if scale else "итогового балла"
                raise ValueError(
                    f"Пересекающиеся диапазоны интерпретации для {where}"
                )


def _normalize(data: dict) -> dict:
    if data.get("title") is not None:
        title = data["title"].strip()
        if not title:
            raise ValueError("Название теста не может быть пустым")
        data["title"] = title
    if "questions" in data and data["questions"] is not None:
        _validate_questions(data["questions"])
    if "interpretations" in data and data["interpretations"] is not None:
        _validate_interpretations(data["interpretations"])
    return data


# ── public API ────────────────────────────────────────────────────────────────

def list_tests(
    page: int, size: int, search: Optional[str], is_active: Optional[bool],
) -> tuple[list[dict], int]:
    return storage.find_tests(page=page, size=size, search=search, is_active=is_active)


def get_test(uuid: str) -> Optional[dict]:
    return storage.get_test_by_uuid(uuid)


def create_test(data: dict, created_by: int) -> dict:
    data = _normalize(data)
    return storage.create_test(data, created_by=created_by)


def update_test(uuid: str, data: dict) -> dict:
    data = _normalize(data)
    result = storage.update_test(uuid, data)
    if result is None:
        raise ValueError("Тест не найден")
    return result


def delete_test(uuid: str) -> None:
    if not storage.delete_test(uuid):
        raise ValueError("Тест не найден")


# ══════════════════════════════════════════════════════════════════════════════
# Student-facing: прохождение, submit, результаты, consent (Этап B)
# ══════════════════════════════════════════════════════════════════════════════

def list_active_tests(page: int, size: int, search: Optional[str]) -> tuple[list[dict], int]:
    return storage.find_active_tests(page=page, size=size, search=search)


def _strip_take(test: dict) -> dict:
    """
    Проекция теста для прохождения: БЕЗ value_score (ключа теста) и БЕЗ порогов
    интерпретации. config вопроса сохраняется (min/max шкалы нужны фронту).
    """
    return {
        "uuid": test["uuid"],
        "title": test["title"],
        "description": test["description"],
        "time_limit_min": test["time_limit_min"],
        "questions": [
            {
                "id": q["id"],
                "question_text": q["question_text"],
                "question_order": q["question_order"],
                "question_type": q["question_type"],
                "is_required": q["is_required"],
                "config": q["config"],
                "options": [
                    {
                        "id": o["id"],
                        "option_text": o["option_text"],
                        "option_order": o["option_order"],
                    }
                    for o in q["options"]
                ],
            }
            for q in test["questions"]
        ],
    }


def get_test_for_take(uuid: str) -> Optional[dict]:
    test = storage.get_active_test_full(uuid)
    if not test:
        return None
    return _strip_take(test)


# ── consent ───────────────────────────────────────────────────────────────────

def get_test_consent_status(user_id: int) -> dict:
    consent = storage.get_active_test_consent()
    if not consent:
        raise ConfigError("Политика согласия на тестирование не настроена")
    accepted = storage.has_accepted_consent(user_id, consent["id"])
    return {**consent, "accepted": accepted}


def accept_test_consent(user_id: int, ip: Optional[str], user_agent: Optional[str]) -> dict:
    consent = storage.get_active_test_consent()
    if not consent:
        raise ConfigError("Политика согласия на тестирование не настроена")
    storage.save_consent_record(user_id, consent["id"], ip=ip, user_agent=user_agent)
    return {**consent, "accepted": True}


def _ensure_consent(user_id: int) -> None:
    consent = storage.get_active_test_consent()
    if not consent:
        raise ConfigError("Политика согласия на тестирование не настроена")
    if not storage.has_accepted_consent(user_id, consent["id"]):
        raise ConsentRequired("Требуется согласие на прохождение психодиагностики")


# ── submit ────────────────────────────────────────────────────────────────────

def _validate_answers(test: dict, answers: list[dict]) -> None:
    by_qid = {q["id"]: q for q in test["questions"]}
    answered = {a["question_id"] for a in answers}

    for q in test["questions"]:
        if q["is_required"] and q["id"] not in answered:
            raise ValueError(f"Вопрос «{q['question_text'][:40]}» обязателен")

    for a in answers:
        q = by_qid.get(a["question_id"])
        if not q:
            raise ValueError("Ответ на вопрос не из этого теста")
        qtype = q["question_type"]
        opt_ids = {o["id"] for o in q["options"]}

        if qtype == "single_choice":
            if a.get("option_id") is None or a["option_id"] not in opt_ids:
                raise ValueError("Некорректный вариант ответа (single_choice)")
        elif qtype == "multiple_choice":
            sel = set(a.get("selected_options") or [])
            if not sel or not sel.issubset(opt_ids):
                raise ValueError("Некорректные варианты ответа (multiple_choice)")
        elif qtype == "scale":
            cfg = q.get("config") or {}
            lo, hi = cfg.get("min"), cfg.get("max")
            val = a.get("scale_value")
            if val is None or (isinstance(lo, int) and val < lo) or (isinstance(hi, int) and val > hi):
                raise ValueError("Значение шкалы вне допустимого диапазона")


def submit_test(
    uuid: str, user_id: int, answers: list[dict],
    ip: Optional[str] = None, user_agent: Optional[str] = None,
) -> dict:
    test = storage.get_active_test_full(uuid)
    if not test:
        raise ValueError("Тест не найден")

    _ensure_consent(user_id)          # ФЗ-152 gate
    _validate_answers(test, answers)

    computed = scoring.compute_result(test, answers)
    saved = storage.save_result(user_id, uuid, computed, answers)
    if saved is None:
        raise ValueError("Тест не найден")
    return saved


def list_results(user_id: int, page: int, size: int) -> tuple[list[dict], int]:
    return storage.find_user_results(user_id, page=page, size=size)


def get_result(user_id: int, result_uuid: str) -> Optional[dict]:
    return storage.get_user_result(user_id, result_uuid)
