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

Нормы (ТЗ редактора методик, этап 2, §5): `scales[].norms` — таблицы «сырой
балл → стандартный балл» по группам с условиями на поля анкеты кампании
(пол, возраст, факультет). Применяются только в тестировании по ссылке:
в каталоге студента пола и возраста нет. Группа — первая подходящая; нет
подходящей или балл вне таблицы — значение не считается (None).
"""
import re
from typing import Any, Literal, Mapping, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SCALE_CODE_RE = re.compile(r"^[0-9A-Za-zА-Яа-яЁё_]{1,20}$")
_LEVEL_CODE_RE = re.compile(r"^[a-z0-9_]{1,30}$")

MAX_SCALES = 50
MAX_LEVELS = 10
MAX_TYPES = 50
MAX_NORM_GROUPS = 20
MAX_NORM_ROWS = 200
# Поля анкеты кампании, по которым выбирается группа норм. Новое поле анкеты —
# добавить сюда (и в NORM_FIELD_KIND): схема правил при этом не меняется.
NORM_FIELDS = ("gender", "age", "faculty_code")
NORM_FIELD_KIND = {"gender": "eq", "faculty_code": "eq", "age": "range"}
NORM_KIND_LABELS = {"sten": "Стены", "t": "T-баллы", "stanine": "Станайны",
                    "percentile": "Процентили", "custom": "Стандартный балл"}
_NORM_KIND_RE = re.compile(r"^[a-z_]{1,20}$")
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


class NormRow(_Strict):
    min: int = Field(ge=-100000, le=100000)
    max: int = Field(ge=-100000, le=100000)
    value: int = Field(ge=-100000, le=100000)

    @model_validator(mode="after")
    def _range(self):
        if self.min > self.max:
            raise ValueError("нижняя граница строки нормы больше верхней")
        return self


class NormCondition(_Strict):
    field: Literal["gender", "age", "faculty_code"]
    eq: Optional[str] = Field(default=None, min_length=1, max_length=64)
    min: Optional[int] = Field(default=None, ge=0, le=200)
    max: Optional[int] = Field(default=None, ge=0, le=200)

    @model_validator(mode="after")
    def _shape(self):
        if NORM_FIELD_KIND[self.field] == "eq":
            if self.eq is None or self.min is not None or self.max is not None:
                raise ValueError("условие по полу или факультету — точное значение")
        else:
            if self.eq is not None or (self.min is None and self.max is None):
                raise ValueError("условие по возрасту — от и/или до")
            if self.min is not None and self.max is not None and self.min > self.max:
                raise ValueError("возраст «от» больше «до»")
        return self

    def matches(self, profile: Mapping[str, Any]) -> bool:
        value = profile.get(self.field)
        if value is None:
            return False
        if self.eq is not None:
            return str(value) == self.eq
        return (self.min is None or value >= self.min) and (self.max is None or value <= self.max)


class NormGroup(_Strict):
    when: tuple[NormCondition, ...] = Field(default=(), max_length=len(NORM_FIELDS))
    table: tuple[NormRow, ...] = Field(min_length=1, max_length=MAX_NORM_ROWS)

    @model_validator(mode="after")
    def _check(self):
        fields = [c.field for c in self.when]
        if len(set(fields)) != len(fields):
            raise ValueError("поле условия нормы указано дважды")
        ordered = sorted(self.table, key=lambda r: r.min)
        for a, b in zip(ordered, ordered[1:]):
            if b.min <= a.max:
                raise ValueError("строки таблицы норм пересекаются")
        return self

    def value_of(self, score: int) -> Optional[int]:
        for row in self.table:
            if row.min <= score <= row.max:
                return row.value
        return None


class ScaleNorms(_Strict):
    kind: str = "custom"
    label: Optional[str] = None
    groups: tuple[NormGroup, ...] = Field(min_length=1, max_length=MAX_NORM_GROUPS)

    @field_validator("kind")
    @classmethod
    def _kind(cls, v: str) -> str:
        if not _NORM_KIND_RE.match(v):
            raise ValueError("тип норм: строчные латинские буквы")
        return v

    @field_validator("label")
    @classmethod
    def _label(cls, v: Optional[str]) -> Optional[str]:
        return None if v is None or not v.strip() else _text(v, 50)

    @property
    def title(self) -> str:
        return self.label or NORM_KIND_LABELS.get(self.kind, "Стандартный балл")

    def group_for(self, profile: Mapping[str, Any]) -> Optional[NormGroup]:
        for g in self.groups:
            if all(c.matches(profile) for c in g.when):
                return g
        return None


class ScaleRule(_Strict):
    code: str
    label: str
    main: bool = False
    # Свои уровни шкалы (ТЗ этапа 2, §4.1); пусто — общие `levels` правил.
    levels: tuple["LevelRule", ...] = Field(default=(), max_length=MAX_LEVELS)
    # Нормы (ТЗ этапа 2, §5): только тестирование по ссылке.
    norms: Optional[ScaleNorms] = None

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

    @model_validator(mode="after")
    def _own_levels(self):
        _check_levels(self.levels)
        return self


def _check_levels(levels) -> None:
    codes = [lv.code for lv in levels]
    if len(set(codes)) != len(codes):
        raise ValueError("коды уровней повторяются")
    ordered = sorted(levels, key=lambda lv: lv.min)
    for a, b in zip(ordered, ordered[1:]):
        if b.min <= a.max:
            raise ValueError("диапазоны уровней пересекаются")


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
        _check_levels(self.levels)
        for sc in self.scales:
            if sc.levels and not sc.main:
                raise ValueError("свои уровни задаются только у основной шкалы")
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
    """Модель → JSONB. Пустые `scales[].levels` не пишутся: правила без своих
    уровней сохраняются в прежнем виде (ИТО, эталоны)."""
    if rules is None:
        return None
    out = rules.model_dump(mode="json")
    for sc in out["scales"]:
        if not sc.get("levels"):
            sc.pop("levels", None)
        if sc.get("norms") is None:
            sc.pop("norms", None)
        else:
            if sc["norms"].get("label") is None:
                sc["norms"].pop("label", None)
            for g in sc["norms"]["groups"]:
                g["when"] = [{k: v for k, v in c.items() if v is not None} for c in g["when"]]
    return out


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


def levels_for(rules: Optional[ScoringRulesV1], scale: Optional[str] = None) -> tuple:
    """Уровни шкалы: свои, если заданы, иначе общие."""
    if rules is None:
        return ()
    if scale is not None:
        for sc in rules.scales:
            if sc.code == scale and sc.levels:
                return sc.levels
    return rules.levels


def own_levels(rules: Optional[ScoringRulesV1]) -> dict[str, tuple]:
    """{шкала: свои уровни} — только шкалы, где они заданы."""
    return {} if rules is None else {sc.code: sc.levels for sc in rules.scales if sc.levels}


def has_levels(rules: Optional[ScoringRulesV1]) -> bool:
    """Считается ли уровень хоть у одной шкалы (общие или свои уровни)."""
    return rules is not None and (bool(rules.levels) or bool(own_levels(rules)))


def level_of(rules: Optional[ScoringRulesV1], score: Optional[int],
             scale: Optional[str] = None) -> Optional[str]:
    """Код уровня (своего у шкалы или общего); None — вне диапазонов или нет уровней."""
    if rules is None or score is None:
        return None
    for lv in levels_for(rules, scale):
        if lv.min <= score <= lv.max:
            return lv.code
    return None


def norms_of(rules: Optional[ScoringRulesV1]) -> dict[str, ScaleNorms]:
    """{шкала: нормы} — только шкалы с нормами, в порядке шкал."""
    return {} if rules is None else {sc.code: sc.norms for sc in rules.scales if sc.norms}


def norm_value(rules: Optional[ScoringRulesV1], scale: str, score: Optional[int],
               profile: Mapping[str, Any]) -> Optional[int]:
    """Стандартный балл по нормам шкалы и анкете участника (пол, возраст,
    факультет); None — норм нет, группа не подошла или балл вне таблицы."""
    norms = norms_of(rules).get(scale)
    if norms is None or score is None:
        return None
    group = norms.group_for(profile)
    return None if group is None else group.value_of(int(score))


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
    for code in main_scales(rules):
        ordered = sorted(levels_for(rules, code), key=lambda lv: lv.min)
        b = by_scale.get(code)
        if b is None or not ordered:
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
    for code, norms in norms_of(rules).items():
        b = by_scale.get(code)
        if b is None:
            continue
        for g in norms.groups:
            cursor = b["min_score"]
            for row in sorted(g.table, key=lambda r: r.min):
                if row.max < cursor:
                    continue
                if row.min > cursor:
                    issues.append({"kind": "norm_gap", "scale_name": code,
                                   "min_score": cursor,
                                   "max_score": min(row.min - 1, b["max_score"])})
                cursor = max(cursor, row.max + 1)
                if cursor > b["max_score"]:
                    break
            if cursor <= b["max_score"]:
                issues.append({"kind": "norm_gap", "scale_name": code,
                               "min_score": cursor, "max_score": b["max_score"]})
    seen, out = set(), []
    for i in issues:
        key = (i["kind"], i["scale_name"], i["min_score"], i["max_score"])
        if key in seen or (i["min_score"] is not None and i["min_score"] > i["max_score"]):
            continue
        seen.add(key)
        out.append(i)
    return out


ISSUE_TEXT = {
    "scale_missing": "у вопросов есть шкала «{s}», которой нет в правилах",
    "scale_unused": "шкала «{s}» из правил не встречается ни в одном вопросе",
    "level_gap": "уровни не покрывают баллы {lo}–{hi} шкалы «{s}»",
    "norm_gap": "таблица норм не покрывает баллы {lo}–{hi} шкалы «{s}»",
}


def describe(issue: dict) -> str:
    return ISSUE_TEXT[issue["kind"]].format(
        s=issue["scale_name"], lo=issue["min_score"], hi=issue["max_score"])
