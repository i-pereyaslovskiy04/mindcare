"""
Первичная обработка результатов кампании (ADR-036) — чистые функции без БД.

Общая для экрана результатов и для xlsx, чтобы цифры совпадали:
  * enrich_row   — уровни по шкалам, достоверность, типы одного участника;
  * filter_rows  — серверные фильтры (факультет, пол, достоверность, тип);
  * summarize    — сводка по набору участников: средние, распределение
                   уровней, частоты типов, разбивки по факультетам и полу.

Профиль методики — ИТО Собчик (единственный профиль кампаний). Для теста без
профиля уровни/типы не считаются, сводка содержит только средние.
"""
from collections import Counter
from statistics import mean
from typing import Optional

from app.student_verification.faculties import FACULTIES, faculty_label
from app.tests.profiles import ito_sobchik as ito

MAIN_SCALES = ("I", "II", "III", "IV", "V", "VI", "VII", "VIII")
# Коды уровней — стабильны для UI и xlsx; подписи — из профиля.
LEVEL_CODES = ("low", "norm", "accent", "maladaptive")
LEVEL_LABELS = dict(zip(LEVEL_CODES, (label for _, _, label in ito.LEVELS)))
VALIDITY_CODES = ("valid", "invalid")
GENDER_LABELS = {"male": "Муж", "female": "Жен"}


def level_code(score: Optional[int]) -> Optional[str]:
    if score is None:
        return None
    for code, (lo, hi, _) in zip(LEVEL_CODES, ito.LEVELS):
        if lo <= score <= hi:
            return code
    return None


def scale_order(profile: Optional[str], rows: list[dict]) -> list[str]:
    if profile == ito.PROFILE:
        return list(ito.EXPORT_SCALE_ORDER)
    return sorted({name for r in rows for name in r["scores"]})


def enrich_row(row: dict, profile: Optional[str]) -> dict:
    """Добавляет levels {шкала: код}, is_valid, types [str] (для ИТО)."""
    scores = row["scores"]
    if profile != ito.PROFILE:
        return {**row, "levels": {}, "is_valid": None, "types": []}
    levels = {s: level_code(scores.get(s)) for s in MAIN_SCALES}
    for s in ito.VALIDITY_SCALES:
        value = scores.get(s)
        levels[s] = None if value is None else (
            "valid" if value <= ito.VALIDITY_LIMIT else "invalid")
    return {**row, "levels": levels, "is_valid": ito.is_valid(scores),
            "types": ito.types_of(scores)}


def _type_base(name: str) -> str:
    """Тип без пометки «(недостоверно)» — для фильтра и частот."""
    suffix = f" ({ito.INVALID_MARK})"
    return name[:-len(suffix)] if name.endswith(suffix) else name


def filter_rows(rows: list[dict], *, faculty_code: Optional[str] = None,
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
                type_name not in {_type_base(t) for t in r["types"]}:
            continue
        out.append(r)
    return out


def _scale_stats(rows: list[dict], scales: list[str]) -> list[dict]:
    stats = []
    for s in scales:
        values = [r["scores"][s] for r in rows if r["scores"].get(s) is not None]
        item = {
            "scale": s,
            "label": ito.SCALE_LABELS.get(s, s),
            "mean": round(mean(values), 2) if values else None,
            "min": min(values) if values else None,
            "max": max(values) if values else None,
            "levels": {},
        }
        if s in MAIN_SCALES:
            counts = Counter(r["levels"].get(s) for r in rows)
            item["levels"] = {c: counts.get(c, 0) for c in LEVEL_CODES}
        elif s in ito.VALIDITY_SCALES:
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


def summarize(rows: list[dict], profile: Optional[str]) -> dict:
    """Сводка по обогащённым строкам."""
    scales = scale_order(profile, rows)
    is_ito = profile == ito.PROFILE
    type_counts: Counter = Counter()
    type_invalid: Counter = Counter()
    for r in rows:
        for t in r["types"]:
            base = _type_base(t)
            type_counts[base] += 1
            if base != t:
                type_invalid[base] += 1
    types = [
        {"name": name, "count": type_counts.get(name, 0),
         "invalid": type_invalid.get(name, 0)}
        for name, _ in (ito.TYPES if is_ito else ())
    ]
    return {
        "total": len(rows),
        "valid": sum(1 for r in rows if r["is_valid"] is True) if is_ito else None,
        "invalid": sum(1 for r in rows if r["is_valid"] is False) if is_ito else None,
        "with_type": sum(1 for r in rows if r["types"]),
        "scales": _scale_stats(rows, scales),
        "types": types,
        "by_faculty": _group(rows, "faculty_code", scales, dict(FACULTIES)),
        "by_gender": _group(rows, "gender", scales, GENDER_LABELS),
    }


def faculty_name(code: str) -> str:
    return faculty_label(code) or code
