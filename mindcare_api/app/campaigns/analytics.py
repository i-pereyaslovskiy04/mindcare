"""
Первичная обработка результатов кампании (ADR-036, ADR-037) — чистые функции
без БД.

Общая для экрана результатов и для xlsx, чтобы цифры совпадали:
  * enrich_row   — уровни по шкалам, достоверность, типы одного участника;
  * filter_rows  — серверные фильтры (факультет, пол, достоверность, тип);
  * summarize    — сводка по набору участников: средние, распределение
                   уровней, частоты типов, разбивки по факультетам и полу.

Правила обработки — `tests.scoring_rules` теста этой кампании
(ScoringRulesV1, app/tests/rules.py). Нет правил — уровни/типы не считаются,
сводка содержит только средние. Нет блока достоверности — is_valid = None.
"""
from collections import Counter
from statistics import mean
from typing import Optional

from app.student_verification.faculties import FACULTIES, faculty_label
from app.tests import rules as R
from app.tests.rules import ScoringRulesV1

VALIDITY_CODES = ("valid", "invalid")
GENDER_LABELS = {"male": "Муж", "female": "Жен"}
# Оттенки уровней для UI и xlsx — по рангу уровня (по возрастанию min):
# крайние — «низкий»/«высокий риск», середина — норма и выраженные черты.
TONES = ("low", "norm", "accent", "maladaptive")


def level_tones(rules: Optional[ScoringRulesV1]) -> dict[str, Optional[str]]:
    """Код уровня → оттенок. 4 уровня ИТО: low/norm/accent/maladaptive."""
    if rules is None or not rules.levels:
        return {}
    ordered = [lv.code for lv in sorted(rules.levels, key=lambda lv: lv.min)]
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


def level_list(rules: Optional[ScoringRulesV1]) -> list[dict]:
    """Уровни в порядке возрастания: [{code, label, min, max, tone}]."""
    if rules is None:
        return []
    tones = level_tones(rules)
    return [{"code": lv.code, "label": lv.label, "min": lv.min, "max": lv.max,
             "tone": tones[lv.code]}
            for lv in sorted(rules.levels, key=lambda lv: lv.min)]


def level_codes(rules: Optional[ScoringRulesV1]) -> list[str]:
    return [lv["code"] for lv in level_list(rules)]


def level_labels(rules: Optional[ScoringRulesV1]) -> dict[str, str]:
    return {lv["code"]: lv["label"] for lv in level_list(rules)}


def scale_order(rules: Optional[ScoringRulesV1], rows: list[dict]) -> list[str]:
    if rules is not None:
        return R.scale_order(rules)
    return sorted({name for r in rows for name in r["scores"]})


def enrich_row(row: dict, rules: Optional[ScoringRulesV1]) -> dict:
    """Добавляет levels {шкала: код}, is_valid, types [str]."""
    scores = row["scores"]
    if rules is None:
        return {**row, "levels": {}, "is_valid": None, "types": []}
    levels: dict = {}
    if rules.levels:
        levels = {s: R.level_of(rules, scores.get(s)) for s in R.main_scales(rules)}
    for code, limit in R.validity_scales(rules).items():
        value = scores.get(code)
        levels[code] = None if value is None else (
            "valid" if value <= limit else "invalid")
    return {**row, "levels": levels, "is_valid": R.is_valid(rules, scores),
            "types": R.types_of(rules, scores)}


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
    main = set(R.main_scales(rules)) if rules is not None and rules.levels else set()
    validity = R.validity_scales(rules)
    codes = level_codes(rules)
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
            item["levels"] = {c: counts.get(c, 0) for c in codes}
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
