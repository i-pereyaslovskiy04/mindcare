"""
Профиль ИТО Собчик (взрослый) — ключ, уровни, достоверность, типы (ADR-036).

Источник — методичка Собчик Л. Н. (2002), стр. 10–13, с исправлением опечатки
ключа: в шкале II стоит вопрос 49 (в книге ошибочно 40, который также в VIII);
совпадает с `ИТО (ключ).xls` заказчика. Обоснование — спецификация
docs/MODULES/test-campaigns-ito-spec.md §4.

Подсчёт баллов делает общий движок (app/tests/scoring.py): тест многошкальный,
вопрос «Да/Нет» single_choice, шкала в config["scale"], значимый вариант —
value_score 1. Здесь — только чистые функции поверх баллов шкал; без БД и HTTP.

Типы (документ заказчика `ИТО Собчик_шкалы_типы.docx`): все шкалы типа ≥ 8;
подходит несколько — все через «; »; при недостоверном результате (L > 5 или
F > 5) типы всё равно определяются и помечаются «(недостоверно)».
"""
from typing import Mapping, Optional

from app.tests.profiles.ito_sobchik_items import ITEMS

PROFILE = "ito_sobchik"
QUESTION_COUNT = 91

# Код шкалы → полная подпись (как в шапке выгрузки заказчика).
SCALE_LABELS: dict[str, str] = {
    "L": "L Ложь",
    "F": "F Аггравация",
    "I": "I Экстраверсия",
    "II": "II Спонтанность",
    "III": "III Агрессивность",
    "IV": "IV Ригидность",
    "V": "V Интроверсия",
    "VI": "VI Сензитивность",
    "VII": "VII Тревожность",
    "VIII": "VIII Лабильность",
}

# Порядок шкал в выгрузке — строго как в `Пример_Собчик.xlsx`.
EXPORT_SCALE_ORDER: tuple[str, ...] = (
    "L", "F", "IV", "II", "VI", "VII", "VIII", "I", "III", "V",
)

# Ключ: шкала → (номера со значимым «Да», номера со значимым «Нет»).
KEY: dict[str, tuple[tuple[int, ...], tuple[int, ...]]] = {
    "L":    ((16, 31, 45, 46, 60, 61, 75, 76, 90), ()),
    "F":    ((2, 17, 32, 47, 62, 64, 77, 79), ()),
    "I":    ((12, 27, 29, 42, 44, 72), (14, 57, 87)),
    "II":   ((4, 19, 21, 34, 49, 50), (6, 65, 80)),
    "III":  ((7, 22, 36, 37, 51, 53, 68), (66, 81)),
    "IV":   ((9, 24, 26, 39, 41, 56), (71, 83, 86)),
    "V":    ((3, 5, 33, 35, 48, 78), (18, 20, 63)),
    "VI":   ((15, 28, 43, 59, 89), (11, 13, 30, 74)),
    "VII":  ((8, 23, 38, 52, 54, 69, 84), (67, 82)),
    "VIII": ((10, 25, 40, 55, 58), (70, 73, 85, 88)),
}

# Порог недостоверности: L > 5 или F > 5.
VALIDITY_LIMIT = 5
VALIDITY_SCALES = ("L", "F")
INVALID_MARK = "недостоверно"

# Уровни основных шкал I–VIII (методичка, общее правило).
LEVELS: tuple[tuple[int, int, str], ...] = (
    (0, 2, "Гипоэмотивность, плохое самопонимание или неоткровенность"),
    (3, 4, "Норма"),
    (5, 7, "Акцентуированные черты"),
    (8, 9, "Дезадаптирующие свойства"),
)

TYPE_THRESHOLD = 8

# Тип → шкалы, которые все должны быть ≥ TYPE_THRESHOLD.
TYPES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Дезадаптивно-интровертированный, суицидальный риск", ("VII", "V", "F")),
    ("Социально активный, ранимый", ("I", "VI")),
    ("Тревожно-агрессивный, тенденция нападения, в том числе с антисоциальной "
     "тенденцией", ("VII", "I", "III", "II")),
    ("Тревожно-чувствительный, виктимный, суицидальный риск", ("VII", "VI", "VIII")),
    ("Защитно-агрессивный, конфликтный", ("II", "III", "IV", "V")),
    ("Неуравновешенный", ("VIII", "III")),
)

INSTRUCTION = (
    "Прочитайте каждое утверждение и выберите «Да», если согласны с ним, "
    "или «Нет», если не согласны. Отвечайте искренне: правильных и "
    "неправильных ответов нет."
)


# ── ключ ──────────────────────────────────────────────────────────────────────

def scale_for_item(number: int) -> Optional[tuple[str, str]]:
    """(шкала, значимый ответ 'yes'|'no') для номера утверждения; None — вне шкал."""
    for scale, (yes, no) in KEY.items():
        if number in yes:
            return scale, "yes"
        if number in no:
            return scale, "no"
    return None


def max_score(scale: str) -> int:
    yes, no = KEY[scale]
    return len(yes) + len(no)


def validate_key() -> None:
    """Самопроверка: каждый из вопросов 2–90 — ровно в одной шкале, 1 и 91 — ни в
    одной; текстов ровно 91. Нарушение — ошибка программиста (AssertionError)."""
    assert len(ITEMS) == QUESTION_COUNT, len(ITEMS)
    seen: dict[int, str] = {}
    for scale, (yes, no) in KEY.items():
        for n in (*yes, *no):
            assert n not in seen, f"вопрос {n} в {seen[n]} и {scale}"
            seen[n] = scale
    assert set(seen) == set(range(2, QUESTION_COUNT)), sorted(
        set(range(2, QUESTION_COUNT)) ^ set(seen)
    )
    assert set(KEY) == set(SCALE_LABELS) == set(EXPORT_SCALE_ORDER)


# ── интерпретация ─────────────────────────────────────────────────────────────

def level_of(score: int) -> Optional[str]:
    for lo, hi, label in LEVELS:
        if lo <= score <= hi:
            return label
    return None


def is_valid(scores: Mapping[str, int]) -> bool:
    return all(int(scores.get(s, 0)) <= VALIDITY_LIMIT for s in VALIDITY_SCALES)


def types_of(scores: Mapping[str, int]) -> list[str]:
    """Типы, у которых все шкалы ≥ порога; при недостоверности — с пометкой."""
    mark = "" if is_valid(scores) else f" ({INVALID_MARK})"
    return [
        f"{name}{mark}"
        for name, scales in TYPES
        if all(int(scores.get(s, 0)) >= TYPE_THRESHOLD for s in scales)
    ]


def summarize(scores: Mapping[str, int]) -> dict:
    """Итог для выгрузки: достоверность и типы строкой (пусто — ни одного)."""
    return {
        "is_valid": is_valid(scores),
        "validity_label": "достоверно" if is_valid(scores) else INVALID_MARK,
        "types": "; ".join(types_of(scores)),
    }


# ── описание теста для seed ───────────────────────────────────────────────────

def interpretations() -> list[dict]:
    """Пороги test_interpretations по каждой шкале (формат admin-конструктора)."""
    rows: list[dict] = []
    for scale in ("I", "II", "III", "IV", "V", "VI", "VII", "VIII"):
        for lo, hi, label in LEVELS:
            rows.append({"scale_name": scale, "min_score": lo, "max_score": hi,
                         "label": label, "recommendation": None})
    for scale in VALIDITY_SCALES:
        rows.append({"scale_name": scale, "min_score": 0,
                     "max_score": VALIDITY_LIMIT, "label": "Достоверно",
                     "recommendation": None})
        rows.append({"scale_name": scale, "min_score": VALIDITY_LIMIT + 1,
                     "max_score": max_score(scale), "label": "Недостоверно",
                     "recommendation": None})
    return rows


def questions() -> list[dict]:
    """91 вопрос «Да/Нет»: значимый вариант — value_score 1, другой — 0;
    1 и 91 — без шкалы (оба варианта 0)."""
    result: list[dict] = []
    for number, text in enumerate(ITEMS, start=1):
        found = scale_for_item(number)
        config: dict = {}
        yes_score = no_score = 0
        if found:
            scale, keyed = found
            config["scale"] = scale
            yes_score, no_score = (1, 0) if keyed == "yes" else (0, 1)
        result.append({
            "question_order": number,
            "question_text": text,
            "question_type": "single_choice",
            "is_required": True,
            "config": config,
            "options": [
                {"option_order": 1, "option_text": "Да", "value_score": yes_score},
                {"option_order": 2, "option_text": "Нет", "value_score": no_score},
            ],
        })
    return result


validate_key()
