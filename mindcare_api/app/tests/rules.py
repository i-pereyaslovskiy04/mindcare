"""
Правила обработки методики как данные (ADR-037).

`tests.scoring_rules` (JSONB) по схеме `ScoringRulesV1`: подписи и порядок шкал,
основные шкалы, общие уровни основных шкал, достоверность, типы, инструкция.
Баллы шкал по-прежнему считает общий движок (app/tests/scoring.py); здесь —
только чистые функции поверх уже посчитанных баллов. Без БД и HTTP.

Семантика совпадает с прежним профилем ИТО (app/tests/profiles/ito_sobchik.py):
  * уровень — только для основных шкал (main), по включительным диапазонам;
  * достоверность — все шкалы validity.scales не выше max_valid; нет блока — None;
  * тип — все его шкалы ≥ threshold; при недостоверности — с пометкой
    « (<invalid_mark>)», типы всё равно определяются.
"""
import re
from typing import Any, Mapping, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SCALE_CODE_RE = re.compile(r"^[0-9A-Za-zА-Яа-яЁё_]{1,20}$")
_LEVEL_CODE_RE = re.compile(r"^[a-z0-9_]{1,30}$")

MAX_SCALES = 50
MAX_LEVELS = 10
MAX_TYPES = 50
# Коды достоверности в той же карте уровней участника (analytics.enrich_row).
RESERVED_LEVEL_CODES = frozenset({"valid", "invalid"})


def _text(v: str, max_len: int, *, multiline: bool = False) -> str:
    if _CONTROL_RE.search(v) or (not multiline and ("\n" in v or "\r" in v)):
        raise ValueError("недопустимые символы")
    cleaned = v.strip() if multiline else " ".join(v.split())
    if not (1 <= len(cleaned) <= max_len):
        raise ValueError("недопустимая длина")
    return cleaned


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ScaleRule(_Strict):
    code: str
    label: str
    main: bool = False

    @field_validator("code")
    @classmethod
    def _code(cls, v: str) -> str:
        if not _SCALE_CODE_RE.match(v):
            raise ValueError("код шкалы: 1–20 букв, цифр или «_»")
        return v

    @field_validator("label")
    @classmethod
    def _label(cls, v: str) -> str:
        return _text(v, 100)


class LevelRule(_Strict):
    code: str
    label: str
    min: int = Field(ge=-100000, le=100000)
    max: int = Field(ge=-100000, le=100000)

    @field_validator("code")
    @classmethod
    def _code(cls, v: str) -> str:
        if not _LEVEL_CODE_RE.match(v):
            raise ValueError("код уровня: 1–30 строчных латинских букв, цифр или «_»")
        if v in RESERVED_LEVEL_CODES:
            raise ValueError("коды valid/invalid заняты под достоверность")
        return v

    @field_validator("label")
    @classmethod
    def _label(cls, v: str) -> str:
        return _text(v, 255)

    @model_validator(mode="after")
    def _range(self):
        if self.min > self.max:
            raise ValueError("нижняя граница уровня больше верхней")
        return self


class ValidityScale(_Strict):
    code: str
    max_valid: int = Field(ge=-100000, le=100000)


class ValidityRule(_Strict):
    scales: tuple[ValidityScale, ...] = Field(min_length=1, max_length=MAX_SCALES)
    invalid_mark: str = "недостоверно"

    @field_validator("invalid_mark")
    @classmethod
    def _mark(cls, v: str) -> str:
        return _text(v, 50)


class TypeItem(_Strict):
    name: str
    scales: tuple[str, ...] = Field(min_length=1, max_length=MAX_SCALES)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        return _text(v, 255)


class TypesRule(_Strict):
    threshold: int = Field(ge=-100000, le=100000)
    items: tuple[TypeItem, ...] = Field(min_length=1, max_length=MAX_TYPES)


class ScoringRulesV1(_Strict):
    version: int = Field(1, ge=1, le=1)
    instruction: Optional[str] = None
    scales: tuple[ScaleRule, ...] = Field(min_length=1, max_length=MAX_SCALES)
    levels: tuple[LevelRule, ...] = Field(default=(), max_length=MAX_LEVELS)
    validity: Optional[ValidityRule] = None
    types: Optional[TypesRule] = None

    @field_validator("instruction")
    @classmethod
    def _instruction(cls, v: Optional[str]) -> Optional[str]:
        return None if v is None or not v.strip() else _text(v, 2000, multiline=True)

    @model_validator(mode="after")
    def _references(self):
        codes = [s.code for s in self.scales]
        if len(set(codes)) != len(codes):
            raise ValueError("коды шкал повторяются")
        known = set(codes)
        level_codes = [lv.code for lv in self.levels]
        if len(set(level_codes)) != len(level_codes):
            raise ValueError("коды уровней повторяются")
        ordered = sorted(self.levels, key=lambda lv: lv.min)
        for a, b in zip(ordered, ordered[1:]):
            if b.min <= a.max:
                raise ValueError("диапазоны уровней пересекаются")
        if self.validity:
            vcodes = [v.code for v in self.validity.scales]
            if len(set(vcodes)) != len(vcodes):
                raise ValueError("шкала достоверности указана дважды")
            if not set(vcodes) <= known:
                raise ValueError("шкала достоверности не объявлена")
        if self.types:
            names = [t.name for t in self.types.items]
            if len(set(names)) != len(names):
                raise ValueError("названия типов повторяются")
            for t in self.types.items:
                if not set(t.scales) <= known:
                    raise ValueError("шкала типа не объявлена")
        return self


class RulesInvalid(ValueError):
    """Сохранённые правила не проходят схему (повреждённые данные)."""


def parse(raw: Any) -> Optional[ScoringRulesV1]:
    """JSONB → модель; None — правил нет. Невалидное — RulesInvalid."""
    if raw is None:
        return None
    if isinstance(raw, ScoringRulesV1):
        return raw
    try:
        return ScoringRulesV1.model_validate(raw)
    except ValidationError:
        raise RulesInvalid("scoring_rules не соответствуют схеме") from None


def dump(rules: Optional[ScoringRulesV1]) -> Optional[dict]:
    return None if rules is None else rules.model_dump(mode="json")


# ── вычисления ────────────────────────────────────────────────────────────────

def scale_order(rules: Optional[ScoringRulesV1], present: Mapping[str, Any] = ()) -> list[str]:
    """Порядок шкал: из правил, иначе — по алфавиту из имеющихся баллов."""
    if rules is not None:
        return [s.code for s in rules.scales]
    return sorted(present)


def scale_label(rules: Optional[ScoringRulesV1], code: str) -> str:
    if rules is not None:
        for s in rules.scales:
            if s.code == code:
                return s.label
    return code


def main_scales(rules: Optional[ScoringRulesV1]) -> list[str]:
    return [] if rules is None else [s.code for s in rules.scales if s.main]


def validity_scales(rules: Optional[ScoringRulesV1]) -> dict[str, int]:
    if rules is None or rules.validity is None:
        return {}
    return {v.code: v.max_valid for v in rules.validity.scales}


def invalid_mark(rules: Optional[ScoringRulesV1]) -> str:
    if rules is None or rules.validity is None:
        return "недостоверно"
    return rules.validity.invalid_mark


def level_of(rules: Optional[ScoringRulesV1], score: Optional[int]) -> Optional[str]:
    """Код уровня по общему набору уровней; None — вне диапазонов или нет уровней."""
    if rules is None or score is None:
        return None
    for lv in rules.levels:
        if lv.min <= score <= lv.max:
            return lv.code
    return None


def is_valid(rules: Optional[ScoringRulesV1], scores: Mapping[str, int]) -> Optional[bool]:
    limits = validity_scales(rules)
    if not limits:
        return None
    return all(int(scores.get(code, 0)) <= limit for code, limit in limits.items())


def types_of(rules: Optional[ScoringRulesV1], scores: Mapping[str, int]) -> list[str]:
    if rules is None or rules.types is None:
        return []
    mark = "" if is_valid(rules, scores) is not False else f" ({invalid_mark(rules)})"
    threshold = rules.types.threshold
    return [
        f"{t.name}{mark}"
        for t in rules.types.items
        if all(int(scores.get(s, 0)) >= threshold for s in t.scales)
    ]


def type_base(rules: Optional[ScoringRulesV1], name: str) -> str:
    """Имя типа без пометки недостоверности."""
    suffix = f" ({invalid_mark(rules)})"
    return name[:-len(suffix)] if name.endswith(suffix) else name


def summarize(rules: Optional[ScoringRulesV1], scores: Mapping[str, int]) -> Optional[dict]:
    """Снимок для test_results.rule_summary: {is_valid, types}; None — правил
    достоверности и типов нет."""
    if rules is None or (rules.validity is None and rules.types is None):
        return None
    return {"is_valid": is_valid(rules, scores), "types": types_of(rules, scores)}


# ── согласованность с вопросами (analyze_test, гейт публикации) ──────────────

def check_against_bounds(rules: Optional[ScoringRulesV1],
                         bounds: list[dict]) -> list[dict]:
    """Проблемы правил относительно вопросов теста. bounds —
    scoring.score_bounds(test): [{scale_name, min_score, max_score}].

    kind:
      scale_missing — у вопросов есть шкала, которой нет в правилах;
      scale_unused  — шкала правил не встречается ни в одном вопросе;
      level_gap     — уровни не покрывают часть диапазона основной шкалы.
    Пустой список — правила согласованы (или правил нет).
    """
    if rules is None:
        return []
    issues: list[dict] = []
    by_scale = {b["scale_name"]: b for b in bounds if b["scale_name"] is not None}
    declared = [s.code for s in rules.scales]
    for code in by_scale:
        if code not in declared:
            issues.append({"kind": "scale_missing", "scale_name": code,
                           "min_score": None, "max_score": None})
    for code in declared:
        if code not in by_scale:
            issues.append({"kind": "scale_unused", "scale_name": code,
                           "min_score": None, "max_score": None})
    if rules.levels:
        ordered = sorted(rules.levels, key=lambda lv: lv.min)
        for code in main_scales(rules):
            b = by_scale.get(code)
            if b is None:
                continue
            cursor = b["min_score"]
            for lv in ordered:
                if lv.max < cursor:
                    continue
                if lv.min > cursor:
                    issues.append({"kind": "level_gap", "scale_name": code,
                                   "min_score": cursor,
                                   "max_score": min(lv.min - 1, b["max_score"])})
                cursor = max(cursor, lv.max + 1)
                if cursor > b["max_score"]:
                    break
            if cursor <= b["max_score"]:
                issues.append({"kind": "level_gap", "scale_name": code,
                               "min_score": cursor, "max_score": b["max_score"]})
    return [i for i in issues
            if i["min_score"] is None or i["min_score"] <= i["max_score"]]


ISSUE_TEXT = {
    "scale_missing": "у вопросов есть шкала «{s}», которой нет в правилах",
    "scale_unused": "шкала «{s}» из правил не встречается ни в одном вопросе",
    "level_gap": "уровни не покрывают баллы {lo}–{hi} шкалы «{s}»",
}


def describe(issue: dict) -> str:
    return ISSUE_TEXT[issue["kind"]].format(
        s=issue["scale_name"], lo=issue["min_score"], hi=issue["max_score"])
