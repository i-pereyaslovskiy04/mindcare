"""
Выгрузка результатов кампании в xlsx (ADR-036) — чистая функция без БД.

Листы:
  «Результаты» — колонки строго по образцу заказчика (`Пример_Собчик.xlsx`):
                 № п/п, ФИО, Возраст, Пол, Факультет, Специальность, шкалы в
                 порядке L, F, IV, II, VI, VII, VIII, I, III, V; справа —
                 Достоверность, Тип, Дата прохождения. Ячейки баллов залиты по
                 уровню (легенда — на листе «Сводка»).
  «Уровни»     — те же участники, вместо баллов — уровни словами.
  «Сводка»     — первичная обработка: итоги, по шкалам (среднее, мин/макс,
                 распределение уровней), частоты типов, по факультетам и полу.
  «Ответы»     — Да/Нет по номерам вопросов.

Расчёты — app/campaigns/analytics.py (те же, что на экране результатов);
подписи, порядок шкал, уровни, достоверность и типы — из правил теста
кампании (ADR-037). Колонки «Достоверность»/«Тип» и лист «Уровни» — только
если в правилах есть соответствующие блоки.
Безопасность: текст записывается строкой (data_type='s') — ввод «=…» не
становится формулой. Файл содержит ПДн — имя файла их не содержит.
"""
import io
from datetime import datetime
from typing import Iterable, Optional
from zoneinfo import ZoneInfo

from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from app.campaigns import analytics
from app.tests import rules as R
from app.tests.rules import ScoringRulesV1

_TZ = ZoneInfo("Europe/Moscow")
XLSX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
# Заливка по оттенку уровня (пастельные, читаются при печати в ч/б как светлые).
_FILL = {
    "low": PatternFill("solid", fgColor="DDEBF7"),
    "norm": None,
    "accent": PatternFill("solid", fgColor="FFF2CC"),
    "maladaptive": PatternFill("solid", fgColor="F8CBAD"),
    "invalid": PatternFill("solid", fgColor="F8CBAD"),
    "valid": None,
}
_BOLD = Font(bold=True)


def _set(ws, row: int, col: int, value, *, bold: bool = False, fill=None):
    cell = ws.cell(row=row, column=col, value=value)
    if isinstance(value, str):
        cell.data_type = "s"     # никогда не формула
    if bold:
        cell.font = _BOLD
    if fill is not None:
        cell.fill = fill
    return cell


def _header(ws, titles: list[str], row: int = 1) -> None:
    for col, title in enumerate(titles, start=1):
        _set(ws, row, col, title, bold=True)


def _when(value: Optional[datetime]) -> str:
    if value is None:
        return ""
    return value.astimezone(_TZ).strftime("%d.%m.%Y %H:%M")


_ROMAN = ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X",
          "XI", "XII", "XIII", "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX")


def _scales_caption(codes: list[str]) -> str:
    """«I–VIII», если основные шкалы — подряд идущие римские номера; иначе
    перечень через запятую."""
    if len(codes) > 2 and set(codes) == set(_ROMAN[:len(codes)]):
        return f"{_ROMAN[0]}–{_ROMAN[len(codes) - 1]}"
    return ", ".join(codes)


def _person(i: int, r: dict) -> list:
    return [i, r["full_name"], r["age"],
            analytics.GENDER_LABELS.get(r["gender"], r["gender"]),
            analytics.faculty_name(r["faculty_code"]), r["specialty"]]


_PERSON_TITLES = ["№ п/п", "Фамилия Имя Отчество", "Возраст", "Пол", "Факультет",
                  "Специальность"]


def _fill(tones: dict, code: Optional[str]):
    if code in ("valid", "invalid"):
        return _FILL[code]
    return _FILL.get(tones.get(code))


def _results_sheet(ws, rows, scales, rules):
    has_validity = bool(R.validity_scales(rules))
    has_types = rules is not None and rules.types is not None
    tones = {s: analytics.level_tones(rules, s) for s in scales}
    norm_scales = [s for s in scales if s in R.norms_of(rules)]
    titles = [*_PERSON_TITLES, *[R.scale_label(rules, s) for s in scales],
              *[f"{R.scale_label(rules, s)} ({R.norms_of(rules)[s].title})" for s in norm_scales]]
    if has_validity:
        titles.append("Достоверность")
    if has_types:
        titles.append("Тип")
    titles.append("Дата прохождения")
    _header(ws, titles)
    ws.freeze_panes = "C2"
    first_scale_col = len(_PERSON_TITLES) + 1
    for i, r in enumerate(rows, start=1):
        row = i + 1
        for col, value in enumerate(_person(i, r), start=1):
            _set(ws, row, col, value)
        for j, s in enumerate(scales):
            _set(ws, row, first_scale_col + j, r["scores"].get(s),
                 fill=_fill(tones[s], r["levels"].get(s)))
        col = first_scale_col + len(scales)
        for s in norm_scales:
            _set(ws, row, col, r["norms"].get(s))
            col += 1
        if has_validity:
            _set(ws, row, col, "достоверно" if r["is_valid"] else R.invalid_mark(rules))
            col += 1
        if has_types:
            _set(ws, row, col, "; ".join(r["types"]))
            col += 1
        _set(ws, row, col, _when(r["submitted_at"]))
    widths = {1: 7, 2: 36, 3: 9, 4: 6, 5: 40, 6: 32}
    for c in range(1, len(titles) + 1):
        ws.column_dimensions[get_column_letter(c)].width = widths.get(c, 14)
    if has_types:
        ws.column_dimensions[get_column_letter(len(titles) - 1)].width = 60


def _levels_sheet(ws, rows, scales, rules):
    validity_text = {"valid": "Достоверно", "invalid": "Недостоверно"}
    text = {s: {**analytics.level_labels(rules, s), **validity_text} for s in scales}
    tones = {s: analytics.level_tones(rules, s) for s in scales}
    _header(ws, [*_PERSON_TITLES, *[R.scale_label(rules, s) for s in scales]])
    ws.freeze_panes = "C2"
    first = len(_PERSON_TITLES) + 1
    for i, r in enumerate(rows, start=1):
        for col, value in enumerate(_person(i, r), start=1):
            _set(ws, i + 1, col, value)
        for j, s in enumerate(scales):
            code = r["levels"].get(s)
            _set(ws, i + 1, first + j, text[s].get(code, ""), fill=_fill(tones[s], code))
    ws.column_dimensions["B"].width = 36
    ws.column_dimensions["E"].width = 40
    for j in range(len(scales)):
        ws.column_dimensions[get_column_letter(first + j)].width = 22


def _summary_sheet(ws, summary, scales, rules):
    levels = analytics.level_list(rules)
    own = analytics.scale_levels(rules)
    main = set(R.main_scales(rules)) if R.has_levels(rules) else set()
    r = 1
    _set(ws, r, 1, "Первичная обработка результатов", bold=True)
    r += 2
    for title, value in (("Участников", summary["total"]),
                         ("Достоверных", summary["valid"]),
                         (analytics.validity_title(rules), summary["invalid"]),
                         ("С выраженным типом", summary["with_type"])):
        if value is None:
            continue
        _set(ws, r, 1, title)
        _set(ws, r, 2, value)
        r += 1

    r += 1
    _set(ws, r, 1, "По шкалам", bold=True)
    r += 1
    _header(ws, ["Шкала", "Среднее", "Мин", "Макс",
                 *([lv["label"] for lv in levels] or (["Уровни"] if own else []))],
            row=r)
    for col, lv in enumerate(levels, start=5):
        ws.cell(row=r, column=col).fill = _FILL[lv["tone"]] or PatternFill()
    r += 1
    for item in summary["scales"]:
        values = [item["label"], item["mean"], item["min"], item["max"]]
        if item["scale"] in own:
            # свои уровни шкалы — «название: число» в колонках уровней
            values += [f"{lv['label']}: {item['levels'].get(lv['code'], 0)}"
                       for lv in own[item["scale"]]]
        elif item["scale"] in main:
            values += [item["levels"].get(lv["code"], 0) for lv in levels]
        elif item["levels"]:
            values += [f"достоверно: {item['levels'].get('valid', 0)}",
                       f"недостоверно: {item['levels'].get('invalid', 0)}"]
        for col, value in enumerate(values, start=1):
            _set(ws, r, col, value)
        r += 1

    if rules is not None and rules.types is not None:
        r += 1
        _set(ws, r, 1, f"Типы (все шкалы типа ≥ {rules.types.threshold})", bold=True)
        r += 1
        _header(ws, ["Тип", "Всего", "Из них недостоверно"], row=r)
        r += 1
        for t in summary["types"]:
            for col, value in enumerate((t["name"], t["count"], t["invalid"]), start=1):
                _set(ws, r, col, value)
            r += 1

    for title, groups in (("По факультетам", summary["by_faculty"]),
                          ("По полу", summary["by_gender"])):
        r += 1
        _set(ws, r, 1, title, bold=True)
        r += 1
        _header(ws, ["", "Участников", "Достоверных", "С типом",
                     *[f"Ср. {R.scale_label(rules, s)}" for s in scales]], row=r)
        r += 1
        for g in groups:
            values = [g["label"], g["count"], g["valid"], g["with_type"],
                      *[g["means"].get(s) for s in scales]]
            for col, value in enumerate(values, start=1):
                _set(ws, r, col, value)
            r += 1

    common_scales = [s for s in R.main_scales(rules) if s not in own]
    legends = ([(common_scales, levels)] if levels and common_scales else []) + \
        [([code], items) for code, items in own.items()]
    for codes, items in legends:
        r += 1
        _set(ws, r, 1, f"Уровни (шкалы {_scales_caption(codes)})", bold=True)
        r += 1
        for lv in items:
            _set(ws, r, 1, f"{lv['min']}–{lv['max']}", fill=_FILL[lv["tone"]])
            _set(ws, r, 2, lv["label"])
            r += 1
    ws.column_dimensions["A"].width = 60
    for c in range(2, 20):
        ws.column_dimensions[get_column_letter(c)].width = 16


# Цвета диаграмм: одна серия — основной цвет интерфейса; уровни — по оттенку
# (как заливки ячеек, но насыщеннее, чтобы столбцы различались).
_BAR_COLOR = "2453A6"
_TONE_COLOR = {"low": "6FA8DC", "norm": "93C47D", "accent": "F6B26B",
               "maladaptive": "CC4125"}
_CHART_ROWS = 18          # высота блока «таблица + диаграмма» в строках


def _bar(title: str, x_title: str, y_title: str, *, horizontal: bool = False,
         stacked: bool = False) -> BarChart:
    chart = BarChart()
    chart.type = "bar" if horizontal else "col"
    chart.title = title
    chart.x_axis.title = x_title
    chart.y_axis.title = y_title
    chart.y_axis.majorGridlines = None
    chart.x_axis.delete = False
    chart.y_axis.delete = False
    chart.height, chart.width = 7.5, 16
    if stacked:
        chart.grouping = "stacked"
        chart.overlap = 100
    else:
        chart.legend = None          # одна серия — подпись в заголовке
    chart.gapWidth = 40
    return chart


def _single_series(ws, chart, *, col: int, first: int, last: int) -> None:
    """Значения — колонка col+1, подписи — col; строка first — заголовок."""
    data = Reference(ws, min_col=col + 1, min_row=first, max_row=last)
    cats = Reference(ws, min_col=col, min_row=first + 1, max_row=last)
    chart.add_data(data, titles_from_data=True)
    chart.set_categories(cats)
    chart.series[0].graphicalProperties.solidFill = _BAR_COLOR
    chart.series[0].graphicalProperties.line.solidFill = _BAR_COLOR


def _charts_sheet(ws, rows: list[dict], scales: list[str],
                  rules: Optional[ScoringRulesV1]) -> None:
    """Лист «Графики» (нативные диаграммы Excel): прохождения по дням,
    уровни основных шкал, распределение баллов по каждой шкале. Данные
    каждой диаграммы — таблицей слева от неё (диаграмма ссылается на ячейки)."""
    r = 1
    _set(ws, r, 1, "Графики по всем участникам кампании", bold=True)
    r += 2

    # ── по дням ──
    days = analytics.by_day(rows)
    if days:
        _header(ws, ["Дата", "Прошли"], row=r)
        for i, d in enumerate(days, start=1):
            y, m, dd = d["date"].split("-")
            _set(ws, r + i, 1, f"{dd}.{m}.{y}")
            _set(ws, r + i, 2, d["count"])
        chart = _bar("Прохождения по дням", "Дата", "Участников")
        _single_series(ws, chart, col=1, first=r, last=r + len(days))
        ws.add_chart(chart, f"E{r}")
        r += max(len(days) + 3, _CHART_ROWS)

    # ── уровни основных шкал ──
    main = [s for s in R.main_scales(rules) if s in scales] if R.has_levels(rules) else []
    summary = {i["scale"]: i for i in analytics.summarize(rows, rules)["scales"]}
    own = analytics.scale_levels(rules)
    groups = []
    common_scales = [s for s in main if s not in own]
    if common_scales and analytics.level_list(rules):
        groups.append(("Уровни по основным шкалам", common_scales, analytics.level_list(rules)))
    for s in main:
        if s in own:
            groups.append((f"Уровни: {R.scale_label(rules, s)}", [s], own[s]))
    for title, codes, levels in groups:
        _header(ws, ["Шкала", *[lv["label"] for lv in levels]], row=r)
        for i, s in enumerate(codes, start=1):
            _set(ws, r + i, 1, R.scale_label(rules, s))
            for j, lv in enumerate(levels, start=2):
                _set(ws, r + i, j, summary[s]["levels"].get(lv["code"], 0))
        chart = _bar(title, "Шкала", "Участников", horizontal=True, stacked=True)
        data = Reference(ws, min_col=2, max_col=1 + len(levels), min_row=r, max_row=r + len(codes))
        chart.add_data(data, titles_from_data=True)
        chart.set_categories(Reference(ws, min_col=1, min_row=r + 1, max_row=r + len(codes)))
        for series, lv in zip(chart.series, levels):
            color = _TONE_COLOR.get(lv["tone"], _BAR_COLOR)
            series.graphicalProperties.solidFill = color
            series.graphicalProperties.line.solidFill = "FFFFFF"
        chart.height = max(7.5, 1.2 + 0.8 * len(codes))
        ws.add_chart(chart, f"{get_column_letter(len(levels) + 3)}{r}")
        r += max(len(codes) + 3, int(chart.height * 2) + 3, _CHART_ROWS)

    # ── распределение баллов ──
    for h in analytics.scale_histograms(rows, rules):
        if not h["bins"]:
            continue
        _header(ws, ["Балл", h["label"]], row=r)
        for i, b in enumerate(h["bins"], start=1):
            _set(ws, r + i, 1, b["score"])
            _set(ws, r + i, 2, b["count"])
        chart = _bar(f"Распределение баллов: {h['label']}", "Балл", "Участников")
        _single_series(ws, chart, col=1, first=r, last=r + len(h["bins"]))
        ws.add_chart(chart, f"E{r}")
        r += max(len(h["bins"]) + 3, _CHART_ROWS)
    ws.column_dimensions["A"].width = 28


def _question_stats_sheet(ws, stats: list[dict]) -> None:
    """Вопрос × вариант: число и доля выбравших (ТЗ этапа 2, §7)."""
    _header(ws, ["№", "Вопрос", "Ответили", "Вариант", "Выбрали", "%"])
    r = 2
    for q in stats:
        for i, o in enumerate(q["options"]):
            if i == 0:
                _set(ws, r, 1, q["number"])
                _set(ws, r, 2, q["text"])
                _set(ws, r, 3, q["answered"])
            _set(ws, r, 4, o["text"])
            _set(ws, r, 5, o["count"])
            _set(ws, r, 6, o["percent"])
            r += 1
    ws.freeze_panes = "A2"
    ws.column_dimensions["B"].width = 70
    ws.column_dimensions["D"].width = 30


def build_workbook(*, rules: Optional[ScoringRulesV1], rows: list[dict],
                   question_numbers: Iterable[int],
                   questions: Optional[list[dict]] = None) -> bytes:
    """rows: [{full_name, age, gender, faculty_code, specialty, submitted_at,
    scores: {scale: int}, answers: {номер: 'Да'|'Нет'}}] в порядке выгрузки."""
    enriched = [analytics.enrich_row(r, rules) for r in rows]
    scales = analytics.scale_order(rules, enriched)

    wb = Workbook()
    _results_sheet(wb.active, enriched, scales, rules)
    wb.active.title = "Результаты"
    if rules is not None and (R.has_levels(rules) or rules.validity):
        _levels_sheet(wb.create_sheet("Уровни"), enriched, scales, rules)
    _summary_sheet(wb.create_sheet("Сводка"),
                   analytics.summarize(enriched, rules), scales, rules)

    numbers = list(question_numbers)
    ws = wb.create_sheet("Ответы")
    _header(ws, ["№ п/п", "Фамилия Имя Отчество", *[str(n) for n in numbers]])
    for i, r in enumerate(enriched, start=1):
        _set(ws, i + 1, 1, i)
        _set(ws, i + 1, 2, r["full_name"])
        for col, n in enumerate(numbers, start=3):
            _set(ws, i + 1, col, r["answers"].get(n, ""))
    ws.column_dimensions["B"].width = 36

    if questions:
        _question_stats_sheet(wb.create_sheet("Статистика по вопросам"),
                              analytics.question_stats(enriched, questions))
    if enriched:
        _charts_sheet(wb.create_sheet("Графики"), enriched, scales, rules)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
