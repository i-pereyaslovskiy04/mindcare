"""
Бизнес-логика модуля психодиагностики (Этап A — admin CRUD).

Не знает про FastAPI/HTTP. Валидация структуры теста выбрасывает ValueError —
роутер транслирует в HTTP 422/404.
"""

import random as _random
from typing import Optional

from app.audit import Actor, Outcome, Target, record_event
from app.audit.request_context import build_request_context
from app.tests import notifications, storage, scoring
from app.tests import rules as test_rules
from app.tests.storage import TestHasResults, TestStateChanged  # noqa: F401  (ре-экспорт для routes)
from app.tests.storage import DraftVersionExists, TextsStructureChanged  # noqa: F401

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

        # Вес вопроса (для scoring=weighted): если задан — целое ≥ 1.
        weight = (q.get("config") or {}).get("weight")
        if weight is not None and (
            isinstance(weight, bool) or not isinstance(weight, int) or weight < 1
        ):
            raise ValueError(f"Вопрос #{idx}: вес (weight) должен быть целым ≥ 1")

        # Изображения: явно прикреплённый файл обязан существовать. В отличие от
        # категорий/тегов НЕ пропускаем молча — иначе автор сохранит и потеряет
        # картинку без предупреждения.
        for m in q.get("media", []) or []:
            if not storage.media_exists(m["media_uuid"]):
                raise ValueError(
                    f"Вопрос #{idx}: изображение не найдено или недоступно"
                )
        for oi, o in enumerate(options, start=1):
            for m in o.get("media", []) or []:
                if not storage.media_exists(m["media_uuid"]):
                    raise ValueError(
                        f"Вопрос #{idx}, вариант #{oi}: "
                        "изображение не найдено или недоступно"
                    )

    _validate_scale_coverage(questions)


def _scale_name(question: dict) -> Optional[str]:
    """Имя шкалы вопроса из config['scale']; пустая строка → None."""
    name = (question.get("config") or {}).get("scale")
    return name.strip() if isinstance(name, str) and name.strip() else None


def _is_filler(question: dict) -> bool:
    options = question.get("options") or []
    return (question["question_type"] in ("single_choice", "multiple_choice")
            and bool(options)
            and all(int(o.get("value_score") or 0) == 0 for o in options))


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

    # Буферный вопрос (ADR-037; например, № 1 и 91 ИТО) — без шкалы и с нулевыми
    # баллами всех вариантов: в подсчёт не входит ни в каком режиме, это не
    # недосмотр автора.
    without = [idx for idx, q in scored
               if _scale_name(q) is None and not _is_filler(q)]
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
    if data.get("scoring_rules") is not None:
        # ADR-037: каноничная JSON-форма (кортежи → списки, нормализованные строки).
        try:
            data["scoring_rules"] = test_rules.dump(test_rules.parse(data["scoring_rules"]))
        except test_rules.RulesInvalid:
            raise ValueError("Правила обработки не соответствуют схеме") from None
    return data


class RulesNotReady(ValueError):
    """ADR-037: правила не согласованы с вопросами — на проверку и к публикации
    такой тест не уходит (422). В черновике — только предупреждение."""


def ensure_rules_ready(test: dict) -> None:
    issues = test_rules.check_against_bounds(
        test_rules.parse(test.get("scoring_rules")), scoring.score_bounds(test))
    if issues:
        raise RulesNotReady(
            "Правила обработки не согласованы с вопросами: "
            + "; ".join(test_rules.describe(i) for i in issues[:5]))


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

    rules = test_rules.parse(test.get("scoring_rules"))
    rule_issues = [{**i, "message": test_rules.describe(i)}
                   for i in test_rules.check_against_bounds(rules, bounds)]

    if not bounds:
        # черновик без скорящихся вопросов
        return {"score_bounds": [], "issues": [], "rule_issues": rule_issues}

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
        "rule_issues": rule_issues,
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

    computed = scoring.compute_result(
        {
            "scoring": data.get("scoring", "sum"),
            "questions": prepared,
            "interpretations": data.get("interpretations") or [],
        },
        answers,
    )
    # ADR-037: автор видит уровни, достоверность и типы на пробном прохождении.
    rules = test_rules.parse(data.get("scoring_rules"))
    scores = {sc["scale_name"]: sc["score"] for sc in computed.get("scales", [])}
    computed["levels"] = {code: test_rules.level_of(rules, scores.get(code), code)
                          for code in test_rules.main_scales(rules)} \
        if test_rules.has_levels(rules) else {}
    computed["rule_summary"] = test_rules.summarize(rules, scores)
    return computed


# ── public API ────────────────────────────────────────────────────────────────

def list_tests(
    page: int, size: int, search: Optional[str], is_active: Optional[bool],
    status: Optional[str] = None,
) -> tuple[list[dict], int]:
    # status=None (по умолчанию) — все статусы, см. storage.find_tests.
    return storage.find_tests(
        page=page, size=size, search=search, is_active=is_active, status=status,
    )


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
    # Правила (ADR-037) сверяет storage под блокировкой: то же значение — можно.
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


def create_new_version(
    uuid: str, *, actor_id: int, actor_role: str,
    ip: Optional[str] = None, user_agent: Optional[str] = None,
) -> dict:
    """ADR-037: новая версия методики (admin/supervisor — любой; психолог —
    своей, см. create_my_new_version). DraftVersionExists → 409."""
    result = storage.create_new_version(
        uuid, actor_id=actor_id, actor_role=actor_role, ip=ip, user_agent=user_agent)
    if result is None:
        raise ValueError("Тест не найден")
    return result


def correct_texts(
    uuid: str, data: dict, *, actor_id: int, actor_role: str,
    ip: Optional[str] = None, user_agent: Optional[str] = None,
) -> dict:
    """ADR-037: исправление опечаток admin/supervisor — в любом статусе и при
    наличии результатов; статус не меняется."""
    payload = {k: v for k, v in data.items() if k != "expected_updated_at"}
    result = storage.correct_texts(
        uuid, payload, actor_id=actor_id, actor_role=actor_role,
        expected_updated_at=data["expected_updated_at"], ip=ip, user_agent=user_agent)
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
# Moderation workflow (Этап F, ADR-016)
# ══════════════════════════════════════════════════════════════════════════════

class TestTransitionError(Exception):
    """Такого перехода не существует в машине состояний (напр. published→draft,
    draft→needs_changes) → route мапит на 409 (конфликт состояния ресурса)."""


class TestTransitionForbidden(Exception):
    """Переход существует, но у актора нет прав (не автор / не staff) → route
    мапит на 403 (как NotesAccessError в session_notes)."""


# Легальные переходы: {текущий: {целевой: (кто может, audit-событие)}}.
# "author" — только автор (tests.created_by == actor_id); "staff" — admin/supervisor.
# published не имеет исходящих переходов здесь: «снять с публикации» — существующий
# is_active toggle (update_test), не смена status (см. видимость: published AND is_active).
_TRANSITIONS = {
    "draft": {
        "in_review": ("author", "test_submitted_for_review"),
        "published": ("staff", "test_published"),
    },
    "needs_changes": {
        "in_review": ("author", "test_submitted_for_review"),
        "published": ("staff", "test_published"),
    },
    "in_review": {
        "published":     ("staff", "test_published"),
        "needs_changes": ("staff", "test_returned_for_changes"),
    },
}


def _validate_transition(current: str, target: str, actor_role: str, is_author: bool) -> str:
    """Возвращает имя audit-события для перехода или бросает TestTransitionError."""
    rule = _TRANSITIONS.get(current, {}).get(target)
    if rule is None:
        raise TestTransitionError(f"Недопустимый переход статуса: {current} → {target}")
    who, event = rule
    if who == "author" and not is_author:
        raise TestTransitionForbidden("Отправить на модерацию может только автор теста")
    if who == "staff" and actor_role not in ("admin", "supervisor"):
        raise TestTransitionForbidden(
            "Публикация и возврат на доработку доступны только admin/supervisor"
        )
    return event


def _apply_transition(
    uuid: str, target: str,
    *,
    actor_id: int, actor_role: str,
    reason: Optional[str] = None,
    expected_status: Optional[str] = None,
    expected_updated_at=None,
    ip: Optional[str] = None, user_agent: Optional[str] = None,
) -> dict:
    """
    Проверка состояния, легальность, права, смена статуса и success-аудит —
    в ОДНОЙ транзакции под FOR UPDATE строки теста (storage.transition_atomic).
    created_by IS NULL (автор удалён, ON DELETE SET NULL) → is_author всегда
    False: submit-for-review такого черновика недоступен никому, но
    admin/supervisor публикуют его напрямую — тупика нет.
    """
    def decide(current: str, created_by: Optional[int]) -> str:
        is_author = created_by is not None and created_by == actor_id
        return _validate_transition(current, target, actor_role, is_author)

    found = storage.transition_atomic(
        uuid, target,
        decide=decide, ready_check=ensure_rules_ready,
        expected_status=expected_status, expected_updated_at=expected_updated_at,
        actor_id=actor_id, actor_role=actor_role, ip=ip, user_agent=user_agent,
    )
    if found is None:
        raise ValueError("Тест не найден")
    result, previous = found
    # Только реально принятое решение по проверке (статус под блокировкой был
    # in_review) — автору system-сообщением после commit (soft-fail).
    if previous == "in_review" and target in ("published", "needs_changes"):
        notifications.notify_author(
            "published" if target == "published" else "returned",
            author_id=result.get("created_by"), actor_id=actor_id, test=result, reason=reason,
        )
    return result


def pending_review_count() -> int:
    return storage.pending_review_count()


def submit_for_review(
    uuid: str, *, actor_id: int, actor_role: str,
    ip: Optional[str] = None, user_agent: Optional[str] = None,
) -> dict:
    """Автор отправляет свой draft/needs_changes тест на модерацию (in_review)."""
    return _apply_transition(
        uuid, "in_review",
        actor_id=actor_id, actor_role=actor_role, ip=ip, user_agent=user_agent,
    )


def publish_test(
    uuid: str, *, actor_id: int, actor_role: str,
    expected_status: str, expected_updated_at,
    ip: Optional[str] = None, user_agent: Optional[str] = None,
) -> dict:
    """admin/supervisor публикуют тест (из draft/in_review/needs_changes).
    expected_status = in_review — решение по проверке (уведомляет автора);
    draft/needs_changes — намеренная прямая публикация. Состояние иное, чем
    видел проверяющий, → TestStateChanged (409) без изменений."""
    return _apply_transition(
        uuid, "published",
        actor_id=actor_id, actor_role=actor_role,
        expected_status=expected_status, expected_updated_at=expected_updated_at,
        ip=ip, user_agent=user_agent,
    )


def return_for_changes(
    uuid: str, *, actor_id: int, actor_role: str,
    expected_status: str, expected_updated_at,
    reason: Optional[str] = None,
    ip: Optional[str] = None, user_agent: Optional[str] = None,
) -> dict:
    """admin/supervisor возвращают тест на доработку (только из in_review).
    reason — только в system-сообщение автору (не хранится и не логируется)."""
    return _apply_transition(
        uuid, "needs_changes",
        actor_id=actor_id, actor_role=actor_role, reason=reason,
        expected_status=expected_status, expected_updated_at=expected_updated_at,
        ip=ip, user_agent=user_agent,
    )


# ══════════════════════════════════════════════════════════════════════════════
# Авторство psychologist (Этап F2, ADR-016)
# ══════════════════════════════════════════════════════════════════════════════

_EDITABLE_STATUSES = {"draft", "needs_changes"}
# Этап F2.1 (ADR-016): автор может дорабатывать и СВОЙ published тест — правка
# снимает его с публикации (update_my_test передаёт unpublish_event в
# storage.update_test). in_review остаётся заблокирован — решение уже не за
# автором, пока идёт проверка супервизором.
_UPDATABLE_STATUSES = _EDITABLE_STATUSES | {"published"}


class TestNotEditable(Exception):
    """Тест не в редактируемом для этого действия статусе → route мапит на 409."""


def _own_editable_test(uuid: str, actor_id: int) -> dict:
    """Гейт для DELETE — только draft/needs_changes (published/in_review нельзя
    удалить автору). {"status","created_by"} — если тест существует, принадлежит
    actor_id и редактируем; иначе исключение. Чужой/несуществующий → ValueError
    (404, «чужого неотличимо от несуществующего», как session_notes). Свой, но
    не в editable-статусе → TestNotEditable (409)."""
    found = storage.get_status_and_author(uuid)
    if found is None or found["created_by"] != actor_id:
        raise ValueError("Тест не найден")
    if found["status"] not in _EDITABLE_STATUSES:
        raise TestNotEditable("Тест на проверке или опубликован — удалить нельзя")
    return found


def _own_updatable_test(uuid: str, actor_id: int) -> dict:
    """Гейт для UPDATE — draft/needs_changes/published (F2.1); только in_review
    заблокирован. Та же ownership-семантика 404 vs 409, что и _own_editable_test."""
    found = storage.get_status_and_author(uuid)
    if found is None or found["created_by"] != actor_id:
        raise ValueError("Тест не найден")
    if found["status"] not in _UPDATABLE_STATUSES:
        raise TestNotEditable("Тест на проверке — редактировать нельзя")
    return found


def list_my_tests(
    author_id: int, page: int, size: int,
    search: Optional[str] = None, status: Optional[str] = None,
) -> tuple[list[dict], int]:
    return storage.find_my_tests(
        author_id, page=page, size=size, search=search, status=status,
    )


def get_my_test(uuid: str, author_id: int) -> dict:
    """Просмотр своего теста — ЛЮБОЙ статус (не только editable); правка отдельно
    гейтится в update_my_test/delete_my_test."""
    test = storage.get_test_by_uuid(uuid)
    if test is None or test.get("created_by") != author_id:
        raise ValueError("Тест не найден")
    return test


def create_my_test(
    data: dict, created_by: int,
    *, actor_role: str = "psychologist",
    ip: Optional[str] = None, user_agent: Optional[str] = None,
) -> dict:
    """Психолог создаёт тест ВСЕГДА как draft — присланный status игнорируется
    (защита от прямого вызова API с status=published: публикует только
    admin/supervisor, ADR-016)."""
    data = {**data, "status": "draft"}
    data = _normalize(data)
    return storage.create_test(
        data, created_by=created_by,
        actor_role=actor_role, ip=ip, user_agent=user_agent,
    )


def update_my_test(
    uuid: str, data: dict, *, actor_id: int, actor_role: str = "psychologist",
    ip: Optional[str] = None, user_agent: Optional[str] = None,
) -> dict:
    """Правка своего теста — draft/needs_changes/published (F2.1). Правка
    published-теста атомарно снимает его с публикации (unpublish_event) — тест
    возвращается в draft и требует повторной отправки на модерацию (submit-for-
    review). has_results-проверка на вопросах теперь ДОСТИЖИМА (published может
    иметь результаты) — storage.update_test её выполняет и остаётся единственным
    источником истины; она срабатывает ДО unpublish-мутации (см. storage), так
    что неуспешная правка вопросов не снимает тест с публикации попутно."""
    found = _own_updatable_test(uuid, actor_id)
    data = _normalize(data)
    unpublish_event = (
        "test_unpublished_for_edit" if found["status"] == "published" else None
    )
    try:
        result = storage.update_test(
            uuid, data,
            actor_id=actor_id, actor_role=actor_role, ip=ip, user_agent=user_agent,
            unpublish_event=unpublish_event, expected_status=found["status"],
        )
    except TestStateChanged:
        # Статус сменился между гейтом и записью (например, тест только что
        # опубликовали или отправили на проверку) — правка не применяется.
        raise TestNotEditable("Статус теста изменился — обновите страницу и повторите правку")
    if result is None:
        raise ValueError("Тест не найден")
    return result


def delete_my_test(
    uuid: str, *, actor_id: int, actor_role: str = "psychologist",
    ip: Optional[str] = None, user_agent: Optional[str] = None,
) -> None:
    found = _own_editable_test(uuid, actor_id)
    try:
        deleted = storage.delete_test(
            uuid, actor_id=actor_id, actor_role=actor_role, ip=ip, user_agent=user_agent,
            expected_status=found["status"],
        )
    except TestStateChanged:
        raise TestNotEditable("Статус теста изменился — обновите страницу")
    if not deleted:
        raise ValueError("Тест не найден")


def _own_test_uuid(uuid: str, actor_id: int) -> None:
    """Гейт владения для duplicate — БЕЗ ограничения по статусу: дублирование не
    мутирует оригинал (read + insert новой независимой копии), поэтому любой
    статус источника (включая published/in_review) допустим. Чужой/несуществующий
    → ValueError (404, «чужого неотличимо от несуществующего», как session_notes)."""
    found = storage.get_status_and_author(uuid)
    if found is None or found["created_by"] != actor_id:
        raise ValueError("Тест не найден")


def create_my_new_version(
    uuid: str, *, actor_id: int, actor_role: str = "psychologist",
    ip: Optional[str] = None, user_agent: Optional[str] = None,
) -> dict:
    """Новая версия СВОЕЙ методики (ADR-037): та же ownership-семантика 404,
    что у дублирования; версия — черновик автора, публикует супервизор/админ."""
    _own_test_uuid(uuid, actor_id)
    return create_new_version(uuid, actor_id=actor_id, actor_role=actor_role,
                              ip=ip, user_agent=user_agent)


def correct_my_texts(
    uuid: str, data: dict, *, actor_id: int, actor_role: str = "psychologist",
    ip: Optional[str] = None, user_agent: Optional[str] = None,
) -> dict:
    """Исправление текстов СВОЕЙ методики: гейт как у правки (F2.1) — на
    проверке нельзя, опубликованная снимается с публикации и уходит на
    повторную модерацию (иначе автор менял бы видимый студентам текст в обход
    проверки)."""
    found = _own_updatable_test(uuid, actor_id)
    payload = {k: v for k, v in data.items() if k != "expected_updated_at"}
    try:
        result = storage.correct_texts(
            uuid, payload, actor_id=actor_id, actor_role=actor_role,
            expected_updated_at=data["expected_updated_at"],
            expected_status=found["status"],
            unpublish_event=("test_unpublished_for_edit"
                             if found["status"] == "published" else None),
            ip=ip, user_agent=user_agent)
    except TestStateChanged:
        raise TestNotEditable("Методика изменилась — обновите страницу и повторите")
    if result is None:
        raise ValueError("Тест не найден")
    return result


def duplicate_my_test(
    uuid: str, *, actor_id: int, actor_role: str = "psychologist",
    ip: Optional[str] = None, user_agent: Optional[str] = None,
) -> dict:
    """Психолог дублирует СВОЙ тест (Этап F2.2) — переиспользует общий
    storage.duplicate_test (тот же путь, что admin/supervisor): копия создаётся
    как draft, is_active=False, version=1, created_by=этот же психолог. Оригинал
    не меняется — в отличие от update_my_test('published'), дублирование не
    снимает исходный тест с публикации."""
    _own_test_uuid(uuid, actor_id)
    result = storage.duplicate_test(
        uuid, created_by=actor_id,
        actor_role=actor_role, ip=ip, user_agent=user_agent,
    )
    if result is None:
        raise ValueError("Тест не найден")
    return result


# ══════════════════════════════════════════════════════════════════════════════
# Student-facing: прохождение, submit, результаты, consent (Этап B)
# ══════════════════════════════════════════════════════════════════════════════

def list_active_tests(page: int, size: int, search: Optional[str]) -> tuple[list[dict], int]:
    return storage.find_active_tests(page=page, size=size, search=search)


def _strip_take(test: dict) -> dict:
    """
    Проекция теста для прохождения: БЕЗ value_score (ключа теста) и БЕЗ порогов
    интерпретации. config вопроса сохраняется (min/max шкалы нужны фронту).

    Случайный порядок (флаги shuffle_questions/shuffle_options) применяется здесь
    — он презентационный: submit и scoring адресуют по question_id/option_id,
    поэтому перестановка ничего не ломает. question_order/option_order остаются в
    выдаче как есть (клиент их игнорирует).
    """
    questions = [
        {
            "id": q["id"],
            "question_text": q["question_text"],
            "question_order": q["question_order"],
            "question_type": q["question_type"],
            "is_required": q["is_required"],
            "config": q["config"],
            "media": q.get("media", []),   # изображение — не ключ теста
            "options": [
                {
                    "id": o["id"],
                    "option_text": o["option_text"],
                    "option_order": o["option_order"],
                    "media": o.get("media", []),
                }
                for o in q["options"]
            ],
        }
        for q in test["questions"]
    ]

    if test.get("shuffle_options"):
        for q in questions:
            _random.shuffle(q["options"])
    if test.get("shuffle_questions"):
        _random.shuffle(questions)

    return {
        "uuid": test["uuid"],
        "title": test["title"],
        "description": test["description"],
        "time_limit_min": test["time_limit_min"],
        "questions": questions,
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

def _validate_answers(test: dict, answers: list[dict], timed_out: bool = False) -> None:
    by_qid = {q["id"]: q for q in test["questions"]}
    answered = {a["question_id"] for a in answers}

    # При таймауте обязательность не проверяем: авто-submit сохраняет то, что
    # успели ответить (неотвеченные вопросы дают 0 в compute_result).
    if not timed_out:
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
    timed_out: bool = False,
) -> dict:
    test = storage.get_active_test_full(uuid)
    if not test:
        raise ValueError("Тест не найден")

    _ensure_consent(user_id)          # ФЗ-152 gate
    _validate_answers(test, answers, timed_out=timed_out)

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


# ══════════════════════════════════════════════════════════════════════════════
# Staff-доступ к результатам (Этап E, ADR-016; дополнение 2026-10-29)
# ══════════════════════════════════════════════════════════════════════════════
#
# psychologist — список, деталь и ответы только при СТРОГОМ активном
#   сопровождении с активным клиентом (клиент может иметь staff-роли); любой
#   отказ — один и тот же ResultNotAvailable (route: 404 + test_result_read_failed);
# supervisor   — список и деталь «чистого» активного студента (иначе 404),
#   ответов нет (403);
# admin        — доступа нет (роутер).
# Проверка области — в storage ДО чтения содержимого. Чтение детали и ответов
# фиксируется test_result_content_read (INDEPENDENT + RAISE, fail-closed):
# событие пишется после чтения и ДО возврата; AuditError пробрасывается — route
# отвечает 503 без содержимого. Список — metadata-only, без события.

class ResultAccessError(Exception):
    """Невалидная active-роль или действие недоступно роли → route мапит на 403."""


class ResultNotFound(Exception):
    """supervisor: студент/результат не найден → route мапит на 404."""


class ResultNotAvailable(Exception):
    """psychologist: нет результата или области доступа → 404 + *_read_failed."""
    failure_reason = "access_denied"


# Роли с доступом к результатам (admin ИСКЛЮЧЁН по ADR-016). Консервативный
# порядок при multi-role без X-Active-Role: psychologist (scoped) < supervisor (любые).
_STAFF_RESULT_ROLES = ("supervisor", "psychologist")
_STAFF_RESULT_CONSERVATIVE = ("psychologist", "supervisor")


def _resolve_staff_result_role(role_names, requested: Optional[str]) -> str:
    """Детерминированная acting-роль из ролей пользователя (см. session_notes)."""
    holder = [r for r in _STAFF_RESULT_ROLES if r in set(role_names)]
    if not holder:
        raise ResultAccessError("Нет подходящей роли для доступа к результатам")
    if requested is not None:
        if requested not in holder:
            raise ResultAccessError("Указанная активная роль недоступна для этого действия")
        return requested
    if len(holder) == 1:
        return holder[0]
    for role in _STAFF_RESULT_CONSERVATIVE:
        if role in holder:
            return role
    return holder[0]   # недостижимо


def list_student_results(
    *, current_user: dict, requested_role: Optional[str],
    student_uuid, page: int, size: int,
) -> tuple[list[dict], int]:
    """Metadata-список результатов (без баллов и без события)."""
    role = _resolve_staff_result_role(current_user.get("roles") or [], requested_role)
    if role == "psychologist":
        found = storage.list_results_for_psychologist(
            int(current_user["id"]), student_uuid, page, size,
        )
        if found is None:
            raise ResultNotAvailable()
        return found
    found = storage.list_results_for_supervisor(student_uuid, page, size)
    if found is None:
        raise ResultNotFound("Студент не найден")
    return found


def _record_content_read(actor_id: int, role: str, result_id: int, ip, user_agent) -> None:
    # INDEPENDENT + RAISE (fail-closed): сбой записи → AuditError наружу,
    # содержимое не возвращается. db НЕ передаётся.
    record_event(
        event="test_result_content_read",
        actor=Actor.user(int(actor_id), role),
        target=Target("test_result", result_id),
        outcome=Outcome.SUCCESS,
        metadata={},
        context=build_request_context(ip=ip, user_agent=user_agent),
    )


def get_staff_result(
    *, current_user: dict, requested_role: Optional[str], result_uuid,
    ip: Optional[str] = None, user_agent: Optional[str] = None,
) -> dict:
    """Полный результат (баллы, шкалы, интерпретации) + content-read событие."""
    role = _resolve_staff_result_role(current_user.get("roles") or [], requested_role)
    found = storage.read_result_for_staff(
        role=role, actor_id=int(current_user["id"]), result_uuid=result_uuid,
    )
    if found is None:
        if role == "psychologist":
            raise ResultNotAvailable()
        raise ResultNotFound("Результат не найден")
    _record_content_read(current_user["id"], role, found["result_id"], ip, user_agent)
    return found["data"]


def get_staff_result_answers(
    *, current_user: dict, requested_role: Optional[str], result_uuid,
    ip: Optional[str] = None, user_agent: Optional[str] = None,
) -> dict:
    """Ответы прохождения — только психологу клиента; то же content-read событие."""
    role = _resolve_staff_result_role(current_user.get("roles") or [], requested_role)
    if role != "psychologist":
        raise ResultAccessError("Ответы на вопросы доступны только психологу клиента")
    found = storage.read_result_for_staff(
        role=role, actor_id=int(current_user["id"]), result_uuid=result_uuid,
        with_answers=True,
    )
    if found is None:
        raise ResultNotAvailable()
    _record_content_read(current_user["id"], role, found["result_id"], ip, user_agent)
    return found["data"]


# ══════════════════════════════════════════════════════════════════════════════
# Импорт и выгрузка методики в шаблоне xlsx (ADR-037, этап 5)
# ══════════════════════════════════════════════════════════════════════════════

def _import_check(content: bytes) -> tuple[Optional[dict], dict]:
    """Разбор + те же проверки, что у конструктора (схема TestCreate,
    _normalize, правила). → (данные | None, ответ dry_run)."""
    from pydantic import ValidationError

    from app.tests import methodology_xlsx as mx
    from app.tests.schemas import TestCreate

    data, errors = mx.parse_workbook(content)
    report = {"ok": False, "errors": errors, "warnings": [], "summary": None}
    if data is None:
        return None, report
    try:
        model = TestCreate.model_validate({**data, "status": "draft"})
        clean = _normalize(model.model_dump())
    except ValidationError as exc:
        report["errors"] = [{"sheet": None, "row": None, "column": None,
                             "message": "Данные не прошли проверку: "
                             + ".".join(str(p) for p in e["loc"]) + " — " + e["msg"]}
                            for e in exc.errors()[:50]]
        return None, report
    except ValueError as exc:
        report["errors"] = [{"sheet": None, "row": None, "column": None, "message": str(exc)}]
        return None, report
    rules = test_rules.parse(clean.get("scoring_rules"))
    report["warnings"] = [test_rules.describe(i) for i in
                          test_rules.check_against_bounds(rules, scoring.score_bounds(clean))]
    report["ok"] = True
    option_sets = {tuple(o["option_text"] for o in sorted(q["options"], key=lambda o: o["option_order"]))
                   for q in clean["questions"]}
    report["summary"] = {
        "title": clean["title"],
        "questions": len(clean["questions"]),
        # общий набор — число вариантов; свои наборы у вопросов — None и число наборов
        "options": (len(clean["questions"][0]["options"]) if len(option_sets) == 1 else None),
        "option_sets": len(option_sets),
        "scales": len(rules.scales) if rules else 0,
        "levels": (len(rules.levels) + sum(len(v) for v in test_rules.own_levels(rules).values())
                   if rules else 0),
        "types": len(rules.types.items) if rules and rules.types else 0,
        "interpretations": len(clean["interpretations"]),
    }
    return clean, report


def import_preview(content: bytes) -> dict:
    """dry_run: ничего не сохраняет и не аудирует."""
    return _import_check(content)[1]


def import_methodology(
    content: bytes, *, created_by: int, actor_role: str,
    ip: Optional[str] = None, user_agent: Optional[str] = None,
) -> tuple[Optional[dict], dict]:
    """Импорт — ВСЕГДА черновик (и для admin/supervisor: публикация — отдельным
    решением после проверки в конструкторе). Событие test_imported."""
    clean, report = _import_check(content)
    if clean is None:
        return None, report
    created = storage.create_test(
        {**clean, "status": "draft"}, created_by=created_by, event="test_imported",
        actor_role=actor_role, ip=ip, user_agent=user_agent,
    )
    return created, report


def export_methodology(test: dict) -> bytes:
    from app.tests import methodology_xlsx as mx
    return mx.build_workbook(test)


def methodology_template() -> bytes:
    from app.tests import methodology_xlsx as mx
    return mx.build_workbook(None)
