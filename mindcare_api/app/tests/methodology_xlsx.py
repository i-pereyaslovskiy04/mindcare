"""
Методика в шаблоне xlsx (ADR-037, этап 5) — чистые функции без БД и HTTP.

  build_workbook(test | None) — шаблон: пустой (test=None) или заполненный
                                методикой; первый лист — «Как заполнить»;
  parse_workbook(bytes)       — файл → данные TestCreate + ошибки с адресом
                                «лист / строка / колонка».

Листы: «Методика», «Варианты ответа», «Вопросы», «Ключ», «Шкалы», «Уровни»,
«Типы», «Интерпретация». Все вопросы — single_choice с ОБЩИМ набором вариантов
(«Да/Нет», шкала Лайкерта); вопрос — не больше одной шкалы (ограничение
движка app/tests/scoring.py). Вопрос без строк ключа — буферный (все варианты
0 баллов).

Безопасность: только .xlsx (zip), ≤ MAX_BYTES; openpyxl read_only + data_only
(формулы не исполняются, берётся закэшированное значение); лимиты строк;
текст записывается строкой (data_type='s') — «=…» не становится формулой.
Значения ячеек не логируются и не попадают в тексты ошибок.
"""
import io
import zipfile
from typing import Any, Optional

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MAX_BYTES = 2 * 1024 * 1024
MAX_QUESTIONS = 500
MAX_OPTIONS = 20
MAX_SCALES = 50
MAX_ROWS = 5000            # на любой лист (ключ: вопросы × варианты)

SHEET_HELP = "Как заполнить"
SHEET_META = "Методика"
SHEET_OPTIONS = "Варианты ответа"
SHEET_QUESTIONS = "Вопросы"
SHEET_KEY = "Ключ"
SHEET_SCALES = "Шкалы"
SHEET_LEVELS = "Уровни"
SHEET_TYPES = "Типы"
SHEET_INTERP = "Интерпретация"

HEADERS = {
    SHEET_META: ["Поле", "Значение"],
    SHEET_OPTIONS: ["Порядок", "Текст варианта"],
    SHEET_QUESTIONS: ["№", "Текст вопроса"],
    SHEET_KEY: ["Шкала", "№ вопроса", "Вариант (порядок)", "Балл"],
    SHEET_SCALES: ["Код", "Подпись", "Основная (да/нет)", "Предел достоверности"],
    SHEET_LEVELS: ["Код (латиница)", "Название", "От", "До"],
    SHEET_TYPES: ["Название типа", "Шкалы (через запятую)", "Порог"],
    SHEET_INTERP: ["Шкала (пусто — итоговый балл)", "От", "До", "Название", "Рекомендация"],
}
META_FIELDS = ("Название", "Описание", "Инструкция", "Подсчёт", "Только по ссылке")
SCORING = {"сумма": "sum", "sum": "sum", "среднее": "average", "average": "average",
           "взвешенная": "weighted", "weighted": "weighted"}
SCORING_OUT = {"sum": "сумма", "average": "среднее", "weighted": "взвешенная"}
YES = {"да", "yes", "1", "true", "+"}
NO = {"нет", "no", "0", "false", "-", ""}

HELP_TEXT = (
    "Шаблон методики MindCare. Заполните листы и загрузите файл в разделе «Тесты» → "
    "«Импорт из xlsx». Будет создан черновик: его можно проверить в конструкторе и "
    "отправить на проверку.",
    "",
    "«Методика»: Название (обязательно), Описание, Инструкция (показывается участнику "
    "перед вопросами), Подсчёт: сумма | среднее | взвешенная, Только по ссылке: да/нет.",
    "«Варианты ответа»: общий набор для всех вопросов по порядку (1, 2, …), например "
    "«Да», «Нет» или шкала 1–5.",
    "«Вопросы»: № по порядку без пропусков (1, 2, 3 …) и текст.",
    "«Ключ»: строка на каждый значимый ответ — шкала, № вопроса, порядок варианта и "
    "балл. Вопрос относится не больше чем к одной шкале. Вопрос без строк ключа "
    "в подсчёте не участвует. Пустая шкала — подсчёт по итоговому баллу (тогда пустая "
    "у всех строк).",
    "«Шкалы»: код (как в ключе), подпись, основная (да — для неё считается уровень), "
    "предел достоверности — только для шкал достоверности (балл выше предела делает "
    "результат недостоверным). Порядок строк — порядок колонок в выгрузке.",
    "«Уровни»: общие для основных шкал диапазоны баллов включительно; код — латиницей "
    "(low, norm …), без пересечений.",
    "«Типы»: название, шкалы через запятую, порог (одинаковый для всех строк). Тип "
    "выражен, если все его шкалы набрали не меньше порога.",
    "«Интерпретация»: необязательные пороги с текстом по шкале или по итоговому баллу "
    "— то, что видит студент в своём результате.",
    "",
    "Пример заполненного шаблона — выгрузка любой методики кнопкой «Выгрузить в xlsx» "
    "(например, ИТО).",
)


# ── выгрузка ──────────────────────────────────────────────────────────────────

class NotRepresentable(ValueError):
    """Методику нельзя выразить шаблоном (разные наборы вариантов, не
    single_choice) — выгрузка невозможна → 422."""


def _set(ws, row: int, col: int, value) -> None:
    cell = ws.cell(row=row, column=col, value=value)
    if isinstance(value, str):
        cell.data_type = "s"


def _header(ws, titles: list[str]) -> None:
    for col, title in enumerate(titles, start=1):
        _set(ws, 1, col, title)
        ws.cell(row=1, column=col).font = Font(bold=True)
        ws.column_dimensions[get_column_letter(col)].width = 18 if col > 1 else 22


def _rows(ws, rows: list[list]) -> None:
    for r, values in enumerate(rows, start=2):
        for c, value in enumerate(values, start=1):
            if value is not None and value != "":
                _set(ws, r, c, value)


def build_workbook(test: Optional[dict] = None) -> bytes:
    """test — dict storage._test_to_dict (или None — пустой шаблон)."""
    wb = Workbook()
    help_ws = wb.active
    help_ws.title = SHEET_HELP
    for i, line in enumerate(HELP_TEXT, start=1):
        _set(help_ws, i, 1, line)
    help_ws.column_dimensions["A"].width = 120

    sheets = {name: wb.create_sheet(name) for name in HEADERS}
    for name, ws in sheets.items():
        _header(ws, HEADERS[name])
    sheets[SHEET_QUESTIONS].column_dimensions["B"].width = 90
    sheets[SHEET_META].column_dimensions["B"].width = 90
    sheets[SHEET_TYPES].column_dimensions["A"].width = 60

    rules = (test or {}).get("scoring_rules") or {}
    meta = {
        "Название": (test or {}).get("title"),
        "Описание": (test or {}).get("description"),
        "Инструкция": rules.get("instruction"),
        "Подсчёт": SCORING_OUT.get((test or {}).get("scoring") or "sum", "сумма"),
        "Только по ссылке": "да" if (test or {}).get("campaign_only") else "нет",
    }
    _rows(sheets[SHEET_META], [[k, meta[k]] for k in META_FIELDS])
    if test is None:
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    questions = sorted(test.get("questions") or [], key=lambda q: q["question_order"])
    option_texts: Optional[list[str]] = None
    key_rows, question_rows = [], []
    for n, q in enumerate(questions, start=1):
        if q["question_type"] != "single_choice":
            raise NotRepresentable("В шаблоне — только вопросы с одним выбором ответа")
        opts = sorted(q.get("options") or [], key=lambda o: o["option_order"])
        texts = [o["option_text"] for o in opts]
        if option_texts is None:
            option_texts = texts
        elif texts != option_texts:
            raise NotRepresentable("У вопросов разные наборы вариантов ответа")
        if q.get("media"):
            raise NotRepresentable("Медиа в вопросах шаблоном не переносятся")
        question_rows.append([n, q["question_text"]])
        scale = (q.get("config") or {}).get("scale") or ""
        scored = [(i, o["value_score"]) for i, o in enumerate(opts, start=1) if o["value_score"]]
        if scale and not scored:
            scored = [(1, 0)]       # шкала без баллов — сохраняем принадлежность
        for i, score in scored:
            key_rows.append([scale, n, i, score])
    _rows(sheets[SHEET_OPTIONS], [[i, t] for i, t in enumerate(option_texts or [], start=1)])
    _rows(sheets[SHEET_QUESTIONS], question_rows)
    _rows(sheets[SHEET_KEY], key_rows)

    limits = {v["code"]: v["max_valid"] for v in (rules.get("validity") or {}).get("scales", [])}
    _rows(sheets[SHEET_SCALES], [
        [s["code"], s["label"], "да" if s.get("main") else "нет", limits.get(s["code"])]
        for s in rules.get("scales") or []])
    _rows(sheets[SHEET_LEVELS], [
        [lv["code"], lv["label"], lv["min"], lv["max"]] for lv in rules.get("levels") or []])
    types = rules.get("types") or {}
    _rows(sheets[SHEET_TYPES], [
        [t["name"], ", ".join(t["scales"]), types.get("threshold")]
        for t in types.get("items") or []])
    _rows(sheets[SHEET_INTERP], [
        [i.get("scale_name") or "", i["min_score"], i["max_score"], i["label"],
         i.get("recommendation") or ""]
        for i in test.get("interpretations") or []])
    if limits and (rules.get("validity") or {}).get("invalid_mark") not in (None, "недостоверно"):
        _rows(sheets[SHEET_META], [[k, meta[k]] for k in META_FIELDS] +
              [["Пометка недостоверности", rules["validity"]["invalid_mark"]]])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ── разбор ────────────────────────────────────────────────────────────────────

class ImportFileInvalid(ValueError):
    """Файл не читается как xlsx (не zip, слишком большой, повреждён) → 422."""


class _Errors:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def add(self, sheet: str, row: Optional[int], column: Optional[str], message: str) -> None:
        if len(self.items) < 200:
            self.items.append({"sheet": sheet, "row": row, "column": column,
                               "message": message})


def _text(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def _int(v: Any) -> Optional[int]:
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v) if v.is_integer() else None
    try:
        return int(str(v).strip())
    except ValueError:
        return None


def _read_rows(wb, name: str, errors: _Errors, *, required: bool) -> list[tuple[int, tuple]]:
    """Строки данных листа (без заголовка и полностью пустых): [(номер строки, значения)]."""
    if name not in wb.sheetnames:
        if required:
            errors.add(name, None, None, "лист не найден")
        return []
    out = []
    for idx, values in enumerate(wb[name].iter_rows(min_row=2, values_only=True), start=2):
        if idx > MAX_ROWS + 1:
            errors.add(name, idx, None, f"слишком много строк (больше {MAX_ROWS})")
            break
        values = tuple(values[:8]) if values else ()
        if all(v is None or _text(v) == "" for v in values):
            continue
        out.append((idx, values + (None,) * (8 - len(values))))
    return out


def _col(i: int) -> str:
    return get_column_letter(i + 1)


def parse_workbook(content: bytes) -> tuple[Optional[dict], list[dict]]:
    """Файл → (данные TestCreate без статуса | None, ошибки). Данные возвращаются
    только если ошибок разбора нет; проверку схемы и правил делает сервис."""
    if len(content) > MAX_BYTES:
        raise ImportFileInvalid("Файл больше 2 МБ")
    if not content.startswith(b"PK\x03\x04") or not zipfile.is_zipfile(io.BytesIO(content)):
        raise ImportFileInvalid("Это не файл xlsx")
    try:
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception:   # noqa: BLE001 — любой сбой openpyxl = непригодный файл
        raise ImportFileInvalid("Файл xlsx повреждён или не читается") from None
    try:
        return _parse(wb)
    finally:
        wb.close()


def _parse(wb) -> tuple[Optional[dict], list[dict]]:
    errors = _Errors()

    meta = {}
    for row, v in _read_rows(wb, SHEET_META, errors, required=True):
        meta[_text(v[0])] = (row, v[1])
    title = _text(meta.get("Название", (None, None))[1])
    if not title:
        errors.add(SHEET_META, meta.get("Название", (None,))[0], "B", "нет названия методики")
    scoring_raw = _text(meta.get("Подсчёт", (None, "сумма"))[1]).lower() or "сумма"
    scoring = SCORING.get(scoring_raw)
    if scoring is None:
        errors.add(SHEET_META, meta.get("Подсчёт", (None,))[0], "B",
                   "подсчёт: сумма, среднее или взвешенная")
    campaign_raw = _text(meta.get("Только по ссылке", (None, "нет"))[1]).lower()
    if campaign_raw not in YES | NO:
        errors.add(SHEET_META, meta.get("Только по ссылке", (None,))[0], "B", "нужно «да» или «нет»")

    options: list[str] = []
    for i, (row, v) in enumerate(_read_rows(wb, SHEET_OPTIONS, errors, required=True), start=1):
        if _int(v[0]) != i:
            errors.add(SHEET_OPTIONS, row, "A", f"порядок должен идти подряд: ожидалось {i}")
        if not _text(v[1]):
            errors.add(SHEET_OPTIONS, row, "B", "пустой текст варианта")
        options.append(_text(v[1]))
    if len(options) < 2:
        errors.add(SHEET_OPTIONS, None, None, "нужно не меньше двух вариантов ответа")
    if len(options) > MAX_OPTIONS:
        errors.add(SHEET_OPTIONS, None, None, f"не больше {MAX_OPTIONS} вариантов")

    questions: list[str] = []
    for i, (row, v) in enumerate(_read_rows(wb, SHEET_QUESTIONS, errors, required=True), start=1):
        if _int(v[0]) != i:
            errors.add(SHEET_QUESTIONS, row, "A", f"номера должны идти подряд: ожидалось {i}")
        if not _text(v[1]):
            errors.add(SHEET_QUESTIONS, row, "B", "пустой текст вопроса")
        questions.append(_text(v[1]))
    if not questions:
        errors.add(SHEET_QUESTIONS, None, None, "нет ни одного вопроса")
    if len(questions) > MAX_QUESTIONS:
        errors.add(SHEET_QUESTIONS, None, None, f"не больше {MAX_QUESTIONS} вопросов")

    scale_of: dict[int, str] = {}
    scores: dict[tuple[int, int], int] = {}
    for row, v in _read_rows(wb, SHEET_KEY, errors, required=True):
        scale, number, option, score = _text(v[0]), _int(v[1]), _int(v[2]), _int(v[3])
        if number is None or not 1 <= number <= len(questions):
            errors.add(SHEET_KEY, row, "B", "нет такого вопроса")
            continue
        if option is None or not 1 <= option <= len(options):
            errors.add(SHEET_KEY, row, "C", "нет такого варианта")
            continue
        if score is None:
            errors.add(SHEET_KEY, row, "D", "балл — целое число")
            continue
        if number in scale_of and scale_of[number] != scale:
            errors.add(SHEET_KEY, row, "A", f"вопрос {number} уже относится к другой шкале")
            continue
        if (number, option) in scores:
            errors.add(SHEET_KEY, row, "C", "этот вариант вопроса уже указан")
            continue
        scale_of[number] = scale
        scores[(number, option)] = score

    scales, limits = [], {}
    for row, v in _read_rows(wb, SHEET_SCALES, errors, required=False):
        code = _text(v[0])
        if not code:
            errors.add(SHEET_SCALES, row, "A", "пустой код шкалы")
            continue
        main = _text(v[2]).lower()
        if main not in YES | NO:
            errors.add(SHEET_SCALES, row, "C", "нужно «да» или «нет»")
        if _text(v[3]):
            limit = _int(v[3])
            if limit is None:
                errors.add(SHEET_SCALES, row, "D", "предел — целое число")
            else:
                limits[code] = limit
        scales.append({"code": code, "label": _text(v[1]) or code, "main": main in YES})
    if len(scales) > MAX_SCALES:
        errors.add(SHEET_SCALES, None, None, f"не больше {MAX_SCALES} шкал")

    levels = []
    for row, v in _read_rows(wb, SHEET_LEVELS, errors, required=False):
        lo, hi = _int(v[2]), _int(v[3])
        if lo is None or hi is None:
            errors.add(SHEET_LEVELS, row, "C" if lo is None else "D", "граница — целое число")
            continue
        levels.append({"code": _text(v[0]), "label": _text(v[1]) or _text(v[0]),
                       "min": lo, "max": hi})

    types, thresholds = [], set()
    for row, v in _read_rows(wb, SHEET_TYPES, errors, required=False):
        codes = [c.strip() for c in _text(v[1]).replace(";", ",").split(",") if c.strip()]
        if not codes:
            errors.add(SHEET_TYPES, row, "B", "не указаны шкалы типа")
            continue
        thr = _int(v[2])
        if thr is None:
            errors.add(SHEET_TYPES, row, "C", "порог — целое число")
            continue
        thresholds.add(thr)
        types.append({"name": _text(v[0]), "scales": codes})
    if len(thresholds) > 1:
        errors.add(SHEET_TYPES, None, "C", "порог должен быть одинаковым у всех типов")

    interpretations = []
    for row, v in _read_rows(wb, SHEET_INTERP, errors, required=False):
        lo, hi = _int(v[1]), _int(v[2])
        if lo is None or hi is None:
            errors.add(SHEET_INTERP, row, "B" if lo is None else "C", "граница — целое число")
            continue
        if not _text(v[3]):
            errors.add(SHEET_INTERP, row, "D", "нет названия уровня")
            continue
        interpretations.append({"scale_name": _text(v[0]) or None, "min_score": lo,
                                "max_score": hi, "label": _text(v[3]),
                                "recommendation": _text(v[4]) or None})

    if _text(meta.get("Инструкция", (None, ""))[1]) and not scales:
        errors.add(SHEET_SCALES, None, None,
                   "инструкция хранится в правилах обработки — заполните лист «Шкалы»")
    if errors.items:
        return None, errors.items

    data_questions = []
    for n, text in enumerate(questions, start=1):
        config = {"scale": scale_of[n]} if scale_of.get(n) else {}
        data_questions.append({
            "question_text": text, "question_order": n, "question_type": "single_choice",
            "is_required": True, "config": config, "media": [],
            "options": [{"option_text": o, "option_order": i - 1,
                         "value_score": scores.get((n, i), 0), "media": []}
                        for i, o in enumerate(options, start=1)],
        })
    rules = None
    if scales:
        rules = {"version": 1, "instruction": _text(meta.get("Инструкция", (None, ""))[1]) or None,
                 "scales": scales, "levels": levels, "validity": None, "types": None}
        if limits:
            rules["validity"] = {
                "scales": [{"code": c, "max_valid": lim} for c, lim in limits.items()],
                "invalid_mark": _text(meta.get("Пометка недостоверности",
                                               (None, ""))[1]) or "недостоверно"}
        if types:
            rules["types"] = {"threshold": thresholds.pop(), "items": types}
    return {
        "title": title,
        "description": _text(meta.get("Описание", (None, ""))[1]) or None,
        "scoring": scoring,
        "campaign_only": campaign_raw in YES,
        "questions": data_questions,
        "interpretations": interpretations,
        "scoring_rules": rules,
    }, []
