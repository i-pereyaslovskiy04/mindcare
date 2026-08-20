"""
Бизнес-логика модуля психодиагностики (Этап A — admin CRUD).

Не знает про FastAPI/HTTP. Валидация структуры теста выбрасывает ValueError —
роутер транслирует в HTTP 422/404.
"""

from typing import Optional

from app.tests import storage, scoring
from app.tests.storage import TestHasResults  # noqa: F401  (ре-экспорт для routes)

_CHOICE_TYPES = {"single_choice", "multiple_choice"}
# Типы, участвующие в подсчёте баллов (free_text — не участвует).
_SCORED_TYPES = _CHOICE_TYPES | {"scale"}


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

    _validate_scale_coverage(questions)


def _scale_name(question: dict) -> Optional[str]:
    """Имя шкалы вопроса из config['scale']; пустая строка → None."""
    name = (question.get("config") or {}).get("scale")
    return name.strip() if isinstance(name, str) and name.strip() else None


def _validate_scale_coverage(questions: list[dict]) -> None:
    """
    Правило «все шкалы или ни одной».

    scoring.compute_result считает тест многошкальным, если шкала указана хотя бы
    у одного вопроса, и молча выбрасывает из подсчёта все вопросы без шкалы
    (total_score при этом становится NULL). Частично заполненные шкалы — почти
    всегда недосмотр в конструкторе, поэтому ловим их на сохранении, а не молча
    теряем вопросы при прохождении.
    """
    scored = [
        (idx, q) for idx, q in enumerate(questions, start=1)
        if q["question_type"] in _SCORED_TYPES
    ]
    if not scored:
        return

    without = [idx for idx, q in scored if _scale_name(q) is None]
    if without and len(without) != len(scored):
        listed = ", ".join(f"#{i}" for i in without)
        raise ValueError(
            "Шкала указана не у всех вопросов: если тест многошкальный, шкала "
            f"обязательна для каждого вопроса, участвующего в подсчёте. "
            f"Без шкалы: {listed}"
        )


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


# ── анализ порогов интерпретации ──────────────────────────────────────────────

def analyze_test(test: dict) -> dict:
    """
    Достижимый диапазон баллов + проблемы порогов интерпретации.

    Это предупреждения, а не ошибки валидации, и намеренно: правило можно
    проверить только когда известны И вопросы, И пороги, а PATCH частичный
    (можно прислать одни interpretations). Наполовину применённое правило хуже
    отсутствующего — поэтому 422 здесь не поднимаем, а показываем автору
    в конструкторе.

    kind:
      gap           — диапазон баллов, не покрытый ни одним порогом
                      (студент получит результат без расшифровки);
      out_of_range  — порог целиком вне достижимого диапазона (недостижим);
      unknown_scale — порог ссылается на шкалу, которой нет ни у одного вопроса.
    """
    bounds = scoring.score_bounds(test)
    interpretations = test.get("interpretations") or []
    by_scale = {b["scale_name"]: b for b in bounds}
    issues: list[dict] = []

    if not bounds:
        return {"score_bounds": [], "issues": []}   # черновик без скорящихся вопросов

    for i in interpretations:
        scale = i.get("scale_name")
        b = by_scale.get(scale)
        if b is None:
            issues.append({
                "scale_name": scale, "min_score": i["min_score"],
                "max_score": i["max_score"], "kind": "unknown_scale",
                "label": i.get("label"),
            })
        elif i["max_score"] < b["min_score"] or i["min_score"] > b["max_score"]:
            issues.append({
                "scale_name": scale, "min_score": i["min_score"],
                "max_score": i["max_score"], "kind": "out_of_range",
                "label": i.get("label"),
            })

    for b in bounds:
        scale = b["scale_name"]
        items = sorted(
            (i for i in interpretations if i.get("scale_name") == scale),
            key=lambda x: x["min_score"],
        )
        if not items:
            continue   # интерпретация вообще не задана — это черновик, не дыра

        cursor = b["min_score"]
        for i in items:
            if i["min_score"] > cursor:
                issues.append({
                    "scale_name": scale, "min_score": cursor,
                    "max_score": min(i["min_score"] - 1, b["max_score"]),
                    "kind": "gap", "label": None,
                })
            cursor = max(cursor, i["max_score"] + 1)
            if cursor > b["max_score"]:
                break
        if cursor <= b["max_score"]:
            issues.append({
                "scale_name": scale, "min_score": cursor,
                "max_score": b["max_score"], "kind": "gap", "label": None,
            })

    return {
        "score_bounds": bounds,
        "issues": [i for i in issues if i["min_score"] <= i["max_score"]],
    }


def preview_score(data: dict) -> dict:
    """
    Пробный подсчёт несохранённого дерева — тот же scoring.compute_result, что
    у студента. Ничего не пишет в БД.

    Дерево ещё не сохранено, поэтому вопросы адресуются по question_order, а
    варианты по option_order; здесь мы синтезируем такие же id, какие рисует
    конструктор в предпросмотре (см. lib/testShape.toPreviewQuestions), и
    отдаём их обычному скорингу.

    Обязательность вопросов НЕ проверяется намеренно: автор пробует частичные
    наборы ответов, а неотвеченный вопрос даёт 0 — как и в compute_result.
    """
    questions = data.get("questions") or []
    prepared, by_order = [], {}
    for q in questions:
        order = q["question_order"]
        qid = order + 1
        prepared_q = {
            **q,
            "id": qid,
            "options": [
                {**o, "id": qid * 1000 + o["option_order"]}
                for o in (q.get("options") or [])
            ],
        }
        prepared.append(prepared_q)
        by_order[order] = prepared_q

    answers = []
    for a in data.get("answers") or []:
        q = by_order.get(a["question_order"])
        if q is None:
            continue
        ans = {"question_id": q["id"]}
        if a.get("option_order") is not None:
            ans["option_id"] = q["id"] * 1000 + a["option_order"]
        if a.get("selected_option_orders"):
            ans["selected_options"] = [
                q["id"] * 1000 + o for o in a["selected_option_orders"]
            ]
        if a.get("scale_value") is not None:
            ans["scale_value"] = a["scale_value"]
        if a.get("free_text_answer") is not None:
            ans["free_text_answer"] = a["free_text_answer"]
        answers.append(ans)

    return scoring.compute_result(
        {
            "scoring": data.get("scoring", "sum"),
            "questions": prepared,
            "interpretations": data.get("interpretations") or [],
        },
        answers,
    )


# ── public API ────────────────────────────────────────────────────────────────

def list_tests(
    page: int, size: int, search: Optional[str], is_active: Optional[bool],
) -> tuple[list[dict], int]:
    return storage.find_tests(page=page, size=size, search=search, is_active=is_active)


def get_test(uuid: str) -> Optional[dict]:
    return storage.get_test_by_uuid(uuid)


def create_test(
    data: dict,
    created_by: int,
    *,
    actor_role: Optional[str] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    data = _normalize(data)
    return storage.create_test(
        data, created_by=created_by,
        actor_role=actor_role, ip=ip, user_agent=user_agent,
    )


def update_test(
    uuid: str,
    data: dict,
    *,
    actor_id: Optional[int] = None,
    actor_role: Optional[str] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    data = _normalize(data)
    if data.get("questions") is not None and storage.test_has_results(uuid):
        raise TestHasResults(
            "По этому тесту уже есть результаты — его вопросы изменить нельзя. "
            "Создайте копию методики и правьте её."
        )
    result = storage.update_test(
        uuid, data,
        actor_id=actor_id, actor_role=actor_role, ip=ip, user_agent=user_agent,
    )
    if result is None:
        raise ValueError("Тест не найден")
    return result


def duplicate_test(
    uuid: str,
    created_by: int,
    *,
    actor_role: Optional[str] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    result = storage.duplicate_test(
        uuid, created_by=created_by,
        actor_role=actor_role, ip=ip, user_agent=user_agent,
    )
    if result is None:
        raise ValueError("Тест не найден")
    return result


def delete_test(
    uuid: str,
    *,
    actor_id: Optional[int] = None,
    actor_role: Optional[str] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> None:
    if not storage.delete_test(
        uuid,
        actor_id=actor_id, actor_role=actor_role, ip=ip, user_agent=user_agent,
    ):
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


def accept_test_consent(
    user_id: int, ip: Optional[str], user_agent: Optional[str],
    *,
    actor_role: Optional[str] = None,
) -> dict:
    consent = storage.get_active_test_consent()
    if not consent:
        raise ConfigError("Политика согласия на тестирование не настроена")
    storage.save_consent_record(
        user_id, consent["id"], ip=ip, user_agent=user_agent,
        actor_role=actor_role,
    )
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
        elif qtype == "free_text":
            # обязательный free_text не должен проходить пробелами: фронт делает
            # trim в isAnswered, но на сервер полагаться нельзя только на фронт
            if q["is_required"] and not (a.get("free_text_answer") or "").strip():
                raise ValueError("Текстовый ответ не может быть пустым")


def submit_test(
    uuid: str, user_id: int, answers: list[dict],
    ip: Optional[str] = None, user_agent: Optional[str] = None,
    *,
    actor_role: Optional[str] = None,
) -> dict:
    test = storage.get_active_test_full(uuid)
    if not test:
        raise ValueError("Тест не найден")

    _ensure_consent(user_id)          # ФЗ-152 gate
    _validate_answers(test, answers)

    computed = scoring.compute_result(test, answers)
    saved = storage.save_result(
        user_id, uuid, computed, answers,
        actor_role=actor_role, ip=ip, user_agent=user_agent,
    )
    if saved is None:
        raise ValueError("Тест не найден")
    return saved


def list_results(user_id: int, page: int, size: int) -> tuple[list[dict], int]:
    return storage.find_user_results(user_id, page=page, size=size)


def get_result(user_id: int, result_uuid: str) -> Optional[dict]:
    return storage.get_user_result(user_id, result_uuid)
