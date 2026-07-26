"""
Подсчёт результата теста (Этап B) — чистые функции, без БД и HTTP.

Поддерживает (MVP):
  - агрегацию sum / average;
  - 4 типа вопросов: single_choice, multiple_choice, scale, free_text
    (free_text в скоринг не входит);
  - одношкальные и многошкальные тесты (шкала вопроса — в config["scale"]);
  - интерпретацию по порогам (test_interpretations).

Вход — нормализованные dict'ы (как из storage), выход — dict результата,
готовый к сохранению в test_results / test_result_scales.
"""

from typing import Optional

_CHOICE = "single_choice"
_MULTI = "multiple_choice"
_SCALE = "scale"
_FREE = "free_text"


# ── балл и максимум одного вопроса ────────────────────────────────────────────

def score_question(question: dict, answer: dict) -> Optional[int]:
    """Балл за вопрос по ответу. None — вопрос не участвует в скоринге (free_text)."""
    qtype = question["question_type"]

    if qtype == _CHOICE:
        opt_id = answer.get("option_id")
        for o in question["options"]:
            if o["id"] == opt_id:
                return o["value_score"]
        return 0

    if qtype == _MULTI:
        selected = set(answer.get("selected_options") or [])
        return sum(
            o["value_score"] for o in question["options"] if o["id"] in selected
        )

    if qtype == _SCALE:
        return int(answer.get("scale_value") or 0)

    return None  # free_text


def max_question_score(question: dict) -> Optional[int]:
    qtype = question["question_type"]
    if qtype == _CHOICE:
        scores = [o["value_score"] for o in question["options"]]
        return max(scores) if scores else 0
    if qtype == _MULTI:
        return sum(max(0, o["value_score"]) for o in question["options"])
    if qtype == _SCALE:
        cfg = question.get("config") or {}
        return int(cfg.get("max") or 0)
    return None  # free_text


def min_question_score(question: dict) -> Optional[int]:
    """
    Минимально достижимый балл за вопрос — зеркало max_question_score.

    Для multiple_choice учитываем, что _validate_answers требует непустой набор:
    минимум — сумма всех отрицательных вариантов, а если отрицательных нет,
    то самый дешёвый одиночный вариант.
    """
    qtype = question["question_type"]
    scores = [o["value_score"] for o in question.get("options", [])]

    if qtype == _CHOICE:
        return min(scores) if scores else 0
    if qtype == _MULTI:
        negatives = [s for s in scores if s < 0]
        if negatives:
            return sum(negatives)
        return min(scores) if scores else 0
    if qtype == _SCALE:
        cfg = question.get("config") or {}
        return int(cfg.get("min") or 0)
    return None  # free_text


# ── агрегация ─────────────────────────────────────────────────────────────────

def _aggregate(values: list[int], method: str) -> int:
    if not values:
        return 0
    if method == "average":
        return round(sum(values) / len(values))
    return sum(values)  # sum (по умолчанию)


def _interpret(interpretations: list[dict], scale_name: Optional[str], score: int) -> Optional[dict]:
    """Находит порог для (scale_name, score). scale_name=None → итоговый балл теста."""
    for i in interpretations:
        if i.get("scale_name") == scale_name and i["min_score"] <= score <= i["max_score"]:
            return i
    return None


def _scale_of(question: dict) -> Optional[str]:
    cfg = question.get("config") or {}
    name = cfg.get("scale")
    return name if isinstance(name, str) and name.strip() else None


def score_bounds(test: dict) -> list[dict]:
    """
    Достижимый диапазон баллов теста — [{scale_name, min_score, max_score}].

    Разбиение на шкалы и агрегация повторяют compute_result: тест считается
    многошкальным, если шкала есть хотя бы у одного вопроса; scale_name=None —
    итоговый балл одношкального теста. Тест без скорящихся вопросов даёт [].
    """
    method = test.get("scoring", "sum")
    questions = test.get("questions") or []
    multi_scale = any(_scale_of(q) for q in questions)

    def _bounds_of(qs: list[dict]) -> Optional[tuple[int, int]]:
        los, his = [], []
        for q in qs:
            lo, hi = min_question_score(q), max_question_score(q)
            if lo is None or hi is None:   # free_text не участвует
                continue
            los.append(lo)
            his.append(hi)
        if not los:
            return None
        return _aggregate(los, method), _aggregate(his, method)

    if multi_scale:
        buckets: dict[str, list[dict]] = {}
        for q in questions:
            sname = _scale_of(q)
            if sname:
                buckets.setdefault(sname, []).append(q)
        rows = []
        for sname, qs in buckets.items():
            b = _bounds_of(qs)
            if b:
                rows.append({"scale_name": sname, "min_score": b[0], "max_score": b[1]})
        return rows

    b = _bounds_of(questions)
    return [{"scale_name": None, "min_score": b[0], "max_score": b[1]}] if b else []


# ── основной расчёт ───────────────────────────────────────────────────────────

def compute_result(test: dict, answers: list[dict]) -> dict:
    """
    Возвращает:
      {
        "total_score": int | None,   # None для многошкального теста
        "max_possible": int | None,
        "scoring_used": str,
        "recommendations": str | None,
        "scales": [ {scale_name, score, max_score, interpretation, label} ... ],
      }
    """
    method = test.get("scoring", "sum")
    interpretations = test.get("interpretations", [])
    by_id = {a["question_id"]: a for a in answers}

    multi_scale = any(_scale_of(q) for q in test["questions"])

    if multi_scale:
        scales: dict[str, dict] = {}
        for q in test["questions"]:
            sname = _scale_of(q)
            if not sname:
                continue
            ans = by_id.get(q["id"])
            sc = score_question(q, ans) if ans else 0
            mx = max_question_score(q)
            if sc is None:  # free_text внутри шкалы игнорируем
                continue
            bucket = scales.setdefault(sname, {"scores": [], "maxes": []})
            bucket["scores"].append(sc)
            bucket["maxes"].append(mx or 0)

        scale_rows = []
        for sname, b in scales.items():
            s = _aggregate(b["scores"], method)
            m = _aggregate(b["maxes"], method)
            interp = _interpret(interpretations, sname, s)
            scale_rows.append({
                "scale_name": sname,
                "score": s,
                "max_score": m,
                "interpretation": (interp or {}).get("recommendation"),
                "label": (interp or {}).get("label"),
            })

        return {
            "total_score": None,
            "max_possible": None,
            "scoring_used": method,
            "recommendations": None,
            "scales": scale_rows,
        }

    # одношкальный тест: итоговый балл по всем участвующим вопросам
    scores, maxes = [], []
    for q in test["questions"]:
        ans = by_id.get(q["id"])
        sc = score_question(q, ans) if ans else 0
        if sc is None:  # free_text
            continue
        scores.append(sc)
        maxes.append(max_question_score(q) or 0)

    total = _aggregate(scores, method)
    max_possible = _aggregate(maxes, method)
    interp = _interpret(interpretations, None, total)
    recommendations = None
    if interp:
        label, rec = interp.get("label"), interp.get("recommendation")
        recommendations = f"{label}: {rec}" if rec else label

    return {
        "total_score": total,
        "max_possible": max_possible,
        "scoring_used": method,
        "recommendations": recommendations,
        "scales": [],
    }
