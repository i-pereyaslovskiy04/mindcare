"""
Первичная обработка результатов кампании (ADR-036, ADR-037) — чистые функции
без БД.

Общая для экрана результатов и для xlsx, чтобы цифры совпадали:
  * enrich_row   — уровни по шкалам, достоверность, типы одного участника;
  * filter_rows  — серверные фильтры (факультет, пол, достоверность, тип);
  * summarize    — сводка по набору участников: средние, распределение
                   уровней, частоты типов, разбивки по факультетам и полу;
  * statistics   — статистика (ТЗ этапа 2, §7): прохождения по дням, ответы
                   по вопросам, распределение баллов шкал. Распределения
                   скрываются, если участников меньше MIN_GROUP (защита от
                   узнавания по маленькой группе).

Правила обработки — `tests.scoring_rules` теста этой кампании
(ScoringRulesV1, app/tests/rules.py). Нет правил — уровни/типы не считаются,
сводка содержит только средние. Нет блока достоверности — is_valid = None.
"""
from collections import Counter
from datetime import timedelta, timezone
from statistics import mean
from typing import Optional

from app.student_verification.faculties import FACULTIES, faculty_label
from app.tests import rules as R
from app.tests.rules import ScoringRulesV1

VALIDITY_CODES = ("valid", "invalid")
# Меньше участников — распределения ответов и баллов не показываются.
MIN_GROUP = 5
_MSK = timezone(timedelta(hours=3))
GENDER_LABELS = {"male": "Муж", "female": "Жен"}
# Оттенки уровней для UI и xlsx — по рангу уровня (по возрастанию min):
# крайние — «низкий»/«высокий риск», середина — норма и выраженные черты.
TONES = ("low", "norm", "accent", "maladaptive")


def level_tones(rules: Optional[ScoringRulesV1],
                scale: Optional[str] = None) -> dict[str, Optional[str]]:
    """Код уровня → оттенок (уровни шкалы: свои или общие). 4 уровня ИТО:
    low/norm/accent/maladaptive."""
    levels = R.levels_for(rules, scale)
    if not levels:
        return {}
    ordered = [lv.code for lv in sorted(levels, key=lambda lv: lv.min)]
    n = len(ordered)
    if n == 1:
        tones = ["norm"]
    elif n == 2:
        tones = ["norm", "maladaptive"]
    elif n == 3:
        tones = ["low", "norm", "maladaptive"]
    else:
        tones = ["low", "norm", *(["accent"] * (n - 3)), "maladaptive"]
    return dict(zip(ordered, tones))


def level_list(rules: Optional[ScoringRulesV1],
               scale: Optional[str] = None) -> list[dict]:
    """Уровни шкалы (без scale — общие) по возрастанию: [{code, label, min, max, tone}]."""
    tones = level_tones(rules, scale)
    return [{"code": lv.code, "label": lv.label, "min": lv.min, "max": lv.max,
             "tone": tones[lv.code]}
            for lv in sorted(R.levels_for(rules, scale), key=lambda lv: lv.min)]


def level_codes(rules: Optional[ScoringRulesV1], scale: Optional[str] = None) -> list[str]:
    return [lv["code"] for lv in level_list(rules, scale)]


def level_labels(rules: Optional[ScoringRulesV1], scale: Optional[str] = None) -> dict[str, str]:
    return {lv["code"]: lv["label"] for lv in level_list(rules, scale)}


def scale_levels(rules: Optional[ScoringRulesV1]) -> dict[str, list[dict]]:
    """Свои уровни основных шкал: {шкала: level_list}. Шкалы с общими уровнями
    сюда не входят — для них верхнеуровневый level_list(rules)."""
    return {code: level_list(rules, code) for code in R.own_levels(rules)}


def scale_order(rules: Optional[ScoringRulesV1], rows: list[dict]) -> list[str]:
    if rules is not None:
        return R.scale_order(rules)
    return sorted({name for r in rows for name in r["scores"]})


def enrich_row(row: dict, rules: Optional[ScoringRulesV1]) -> dict:
    """Добавляет levels {шкала: код}, is_valid, types [str], norms {шкала:
    стандартный балл} (по анкете участника: пол, возраст, факультет)."""
    scores = row["scores"]
    if rules is None:
        return {**row, "levels": {}, "is_valid": None, "types": [], "norms": {}}
    levels: dict = {}
    if R.has_levels(rules):
        levels = {s: R.level_of(rules, scores.get(s), s) for s in R.main_scales(rules)}
    for code, limit in R.validity_scales(rules).items():
        value = scores.get(code)
        levels[code] = None if value is None else (
            "valid" if value <= limit else "invalid")
    profile = {f: row.get(f) for f in R.NORM_FIELDS}
    norms = {s: R.norm_value(rules, s, scores.get(s), profile) for s in R.norms_of(rules)}
    return {**row, "levels": levels, "is_valid": R.is_valid(rules, scores),
            "types": R.types_of(rules, scores), "norms": norms}


def filter_rows(rows: list[dict], *, rules: Optional[ScoringRulesV1] = None,
                faculty_code: Optional[str] = None,
                gender: Optional[str] = None, validity: Optional[str] = None,
                type_name: Optional[str] = None) -> list[dict]:
    """rows — уже обогащённые enrich_row. type_name — имя типа без пометки
    или '__none__' (участники без типа)."""
    out = []
    for r in rows:
        if faculty_code and r["faculty_code"] != faculty_code:
            continue
        if gender and r["gender"] != gender:
            continue
        if validity == "valid" and r["is_valid"] is not True:
            continue
        if validity == "invalid" and r["is_valid"] is not False:
            continue
        if type_name == "__none__" and r["types"]:
            continue
        if type_name and type_name != "__none__" and \
                type_name not in {R.type_base(rules, t) for t in r["types"]}:
            continue
        out.append(r)
    return out


def _scale_stats(rows: list[dict], scales: list[str],
                 rules: Optional[ScoringRulesV1]) -> list[dict]:
    main = set(R.main_scales(rules)) if R.has_levels(rules) else set()
    validity = R.validity_scales(rules)
    stats = []
    for s in scales:
        values = [r["scores"][s] for r in rows if r["scores"].get(s) is not None]
        item = {
            "scale": s,
            "label": R.scale_label(rules, s),
            "mean": round(mean(values), 2) if values else None,
            "min": min(values) if values else None,
            "max": max(values) if values else None,
            "levels": {},
        }
        if s in main:
            counts = Counter(r["levels"].get(s) for r in rows)
            item["levels"] = {c: counts.get(c, 0) for c in level_codes(rules, s)}
        elif s in validity:
            counts = Counter(r["levels"].get(s) for r in rows)
            item["levels"] = {c: counts.get(c, 0) for c in VALIDITY_CODES}
        stats.append(item)
    return stats


def _group(rows: list[dict], key: str, scales: list[str], labels: dict) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(r[key], []).append(r)
    out = []
    for code in sorted(groups, key=lambda c: list(labels).index(c) if c in labels else 999):
        members = groups[code]
        out.append({
            "code": code,
            "label": labels.get(code) or code,
            "count": len(members),
            "valid": sum(1 for r in members if r["is_valid"] is True),
            "with_type": sum(1 for r in members if r["types"]),
            "means": {
                s: (round(mean(v), 2) if (v := [r["scores"][s] for r in members
                                               if r["scores"].get(s) is not None])
                    else None)
                for s in scales
            },
        })
    return out


def summarize(rows: list[dict], rules: Optional[ScoringRulesV1]) -> dict:
    """Сводка по обогащённым строкам."""
    scales = scale_order(rules, rows)
    has_validity = bool(R.validity_scales(rules))
    type_counts: Counter = Counter()
    type_invalid: Counter = Counter()
    for r in rows:
        for t in r["types"]:
            base = R.type_base(rules, t)
            type_counts[base] += 1
            if base != t:
                type_invalid[base] += 1
    type_items = rules.types.items if rules is not None and rules.types else ()
    types = [
        {"name": t.name, "count": type_counts.get(t.name, 0),
         "invalid": type_invalid.get(t.name, 0)}
        for t in type_items
    ]
    return {
        "total": len(rows),
        "valid": sum(1 for r in rows if r["is_valid"] is True) if has_validity else None,
        "invalid": sum(1 for r in rows if r["is_valid"] is False) if has_validity else None,
        "with_type": sum(1 for r in rows if r["types"]),
        "scales": _scale_stats(rows, scales, rules),
        "types": types,
        "by_faculty": _group(rows, "faculty_code", scales, dict(FACULTIES)),
        "by_gender": _group(rows, "gender", scales, GENDER_LABELS),
    }


def validity_title(rules: Optional[ScoringRulesV1]) -> str:
    """«Недостоверных (L или F > 5)» — из правил достоверности."""
    limits = R.validity_scales(rules)
    if not limits:
        return "Недостоверных"
    if len(set(limits.values())) == 1:
        limit = next(iter(limits.values()))
        return f"Недостоверных ({' или '.join(limits)} > {limit})"
    return "Недостоверных (" + " или ".join(f"{c} > {v}" for c, v in limits.items()) + ")"


def faculty_name(code: str) -> str:
    return faculty_label(code) or code


# ── статистика (ТЗ этапа 2, §7) ──────────────────────────────────────────────

def _percent(count: int, total: int) -> float:
    return round(100 * count / total, 1) if total else 0.0


def by_day(rows: list[dict]) -> list[dict]:
    """Прохождения по датам (московским), по возрастанию."""
    counts = Counter(r["submitted_at"].astimezone(_MSK).date().isoformat() for r in rows)
    return [{"date": d, "count": counts[d]} for d in sorted(counts)]


def question_stats(rows: list[dict], questions: list[dict]) -> list[dict]:
    """По каждому вопросу — сколько выбрали каждый вариант. rows[].answers —
    {номер вопроса: текст варианта}; questions — [{number, text, options}]."""
    out = []
    for q in questions:
        counts = Counter(r["answers"].get(q["number"]) for r in rows)
        answered = sum(c for text, c in counts.items() if text is not None)
        out.append({
            "number": q["number"], "text": q["text"], "answered": answered,
            "options": [{"text": t, "count": counts.get(t, 0),
                         "percent": _percent(counts.get(t, 0), answered)}
                        for t in q["options"]],
        })
    return out


def scale_histograms(rows: list[dict], rules: Optional[ScoringRulesV1]) -> list[dict]:
    """Распределение сырых баллов каждой шкалы: все значения от наименьшего
    до наибольшего встретившегося (пустые — 0)."""
    out = []
    for s in scale_order(rules, rows):
        values = Counter(r["scores"][s] for r in rows if r["scores"].get(s) is not None)
        bins = ([{"score": v, "count": values.get(v, 0)}
                 for v in range(min(values), max(values) + 1)] if values else [])
        out.append({"scale": s, "label": R.scale_label(rules, s), "bins": bins})
    return out


def statistics(rows: list[dict], rules: Optional[ScoringRulesV1],
               questions: list[dict]) -> dict:
    """rows — обогащённые enrich_row и отфильтрованные. При числе участников
    меньше MIN_GROUP — только total и by_day (too_few=True)."""
    too_few = len(rows) < MIN_GROUP
    return {
        "total": len(rows),
        "min_group": MIN_GROUP,
        "too_few": too_few,
        "by_day": by_day(rows),
        "questions": [] if too_few else question_stats(rows, questions),
        "scales": [] if too_few else scale_histograms(rows, rules),
    }
