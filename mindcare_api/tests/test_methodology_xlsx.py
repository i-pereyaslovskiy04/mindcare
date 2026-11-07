"""
Шаблон методики xlsx (ADR-037, ТЗ этапа 2 §3) — чистые функции, без БД.

  - свой набор вариантов у вопроса (лист «Варианты вопросов»): синтетическая
    методика в духе HADS (14 вопросов, разные тексты вариантов, обратный ключ,
    2 шкалы) — выгрузка → разбор → те же вопросы, варианты, ключ и правила;
  - ИТО по-прежнему выгружается общим набором «Да/Нет»;
  - ошибки нового листа — с адресом лист/строка/колонка, без содержимого ячеек.
"""
import io

from openpyxl import Workbook, load_workbook

from app.tests import methodology_xlsx as mx
from app.tests.profiles import ito_sobchik as ito

# Синтетические формулировки (не тексты реальной методики).
_SETS = [
    ["всегда", "часто", "иногда", "никогда"],
    ["очень сильно", "заметно", "слегка", "совсем нет"],
    ["постоянно", "большую часть дня", "время от времени", "почти никогда"],
]


def _hads_like() -> dict:
    questions = []
    for n in range(1, 15):
        texts = _SETS[n % 3]
        scores = [3, 2, 1, 0] if n % 2 else [0, 1, 2, 3]     # прямой / обратный ключ
        questions.append({
            "question_order": n, "question_text": f"Синтетическое утверждение {n}",
            "question_type": "single_choice", "is_required": True,
            "config": {"scale": "A" if n <= 7 else "D"}, "media": [],
            "options": [{"option_order": i, "option_text": t, "value_score": s, "media": []}
                        for i, (t, s) in enumerate(zip(texts, scores))],
        })
    return {
        "title": "Синтетика HADS", "description": None, "scoring": "sum",
        "campaign_only": True, "questions": questions, "interpretations": [],
        "scoring_rules": {
            "version": 1, "instruction": "Отметьте подходящий ответ.",
            "scales": [{"code": "A", "label": "Тревога", "main": True},
                       {"code": "D", "label": "Депрессия", "main": True}],
            "levels": [{"code": "norm", "label": "Норма", "min": 0, "max": 7},
                       {"code": "sub", "label": "Субклиническая", "min": 8, "max": 10},
                       {"code": "clin", "label": "Клиническая", "min": 11, "max": 21}],
            "validity": None, "types": None,
        },
    }


def _shape(questions):
    return [(q["question_order"], q["question_text"], (q["config"] or {}).get("scale"),
             [(o["option_text"], o["value_score"])
              for o in sorted(q["options"], key=lambda o: o["option_order"])])
            for q in sorted(questions, key=lambda q: q["question_order"])]


def _sheet_rows(content: bytes, name: str) -> list[tuple]:
    wb = load_workbook(io.BytesIO(content), read_only=True)
    return [r for r in wb[name].iter_rows(min_row=2, values_only=True)
            if any(v is not None for v in r)]


def test_own_option_sets_roundtrip():
    src = _hads_like()
    content = mx.build_workbook(src)
    assert _sheet_rows(content, mx.SHEET_OPTIONS) == []
    assert len(_sheet_rows(content, mx.SHEET_QOPTIONS)) == 14 * 4
    data, errors = mx.parse_workbook(content)
    assert errors == []
    assert _shape(data["questions"]) == _shape(src["questions"])
    assert data["scoring_rules"]["scales"] == src["scoring_rules"]["scales"]
    assert data["scoring_rules"]["levels"] == src["scoring_rules"]["levels"]


def test_ito_still_uses_common_set():
    src = {"title": "ИТО", "description": None, "scoring": "sum", "campaign_only": True,
           "questions": ito.questions(), "interpretations": [],
           "scoring_rules": ito.scoring_rules()}
    content = mx.build_workbook(src)
    assert _sheet_rows(content, mx.SHEET_OPTIONS) == [(1, "Да"), (2, "Нет")]
    assert _sheet_rows(content, mx.SHEET_QOPTIONS) == []
    data, errors = mx.parse_workbook(content)
    assert errors == []
    assert _shape(data["questions"]) == _shape(src["questions"])


def _book(common=(), own=(), questions=2, key=()) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = mx.SHEET_META
    ws.append(["Поле", "Значение"])
    ws.append(["Название", "Секрет-метка-qwe"])
    sheet = wb.create_sheet(mx.SHEET_OPTIONS)
    sheet.append(mx.HEADERS[mx.SHEET_OPTIONS])
    for row in common:
        sheet.append(list(row))
    sheet = wb.create_sheet(mx.SHEET_QOPTIONS)
    sheet.append(mx.HEADERS[mx.SHEET_QOPTIONS])
    for row in own:
        sheet.append(list(row))
    sheet = wb.create_sheet(mx.SHEET_QUESTIONS)
    sheet.append(mx.HEADERS[mx.SHEET_QUESTIONS])
    for n in range(1, questions + 1):
        sheet.append([n, f"Вопрос {n}"])
    sheet = wb.create_sheet(mx.SHEET_KEY)
    sheet.append(mx.HEADERS[mx.SHEET_KEY])
    for row in key:
        sheet.append(list(row))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_mixed_own_and_common():
    content = _book(common=[(1, "Да"), (2, "Нет")],
                    own=[(2, 1, "мало"), (2, 2, "средне"), (2, 3, "много")],
                    key=[("", 2, 3, 2), ("", 1, 1, 1)])
    data, errors = mx.parse_workbook(content)
    assert errors == []
    q1, q2 = data["questions"]
    assert [o["option_text"] for o in q1["options"]] == ["Да", "Нет"]
    assert [(o["option_text"], o["value_score"]) for o in q2["options"]] == [
        ("мало", 0), ("средне", 0), ("много", 2)]


def test_own_options_errors_have_address():
    content = _book(own=[(1, 1, "а"), (1, 3, "в"), (5, 1, "x"), (1, 4, "")],
                    key=[("", 1, 9, 1)])
    data, errors = mx.parse_workbook(content)
    assert data is None
    S = mx.SHEET_QOPTIONS
    assert {"sheet": S, "row": 3, "column": "B",
            "message": "порядок у вопроса 1 должен идти подряд: ожидалось 2"} in errors
    assert {"sheet": S, "row": 4, "column": "A", "message": "нет такого вопроса"} in errors
    assert {"sheet": S, "row": 5, "column": "C", "message": "пустой текст варианта"} in errors
    # у вопроса 2 нет вариантов, общего набора нет
    assert any(e["sheet"] == mx.SHEET_OPTIONS and "вопросов 2" in e["message"] for e in errors)
    assert {"sheet": mx.SHEET_KEY, "row": 2, "column": "C",
            "message": "нет такого варианта у этого вопроса"} in errors
    assert "Секрет-метка-qwe" not in repr(errors)


def test_single_own_option_is_error():
    content = _book(common=[(1, "Да"), (2, "Нет")], own=[(1, 1, "один")])
    data, errors = mx.parse_workbook(content)
    assert data is None
    assert {"sheet": mx.SHEET_QOPTIONS, "row": 2, "column": "A",
            "message": "у вопроса 1 нужно не меньше двух вариантов"} in errors


def test_old_file_without_new_sheet_still_parses():
    wb = load_workbook(io.BytesIO(_book(common=[(1, "Да"), (2, "Нет")])))
    del wb[mx.SHEET_QOPTIONS]
    buf = io.BytesIO()
    wb.save(buf)
    data, errors = mx.parse_workbook(buf.getvalue())
    assert errors == []
    assert len(data["questions"]) == 2
