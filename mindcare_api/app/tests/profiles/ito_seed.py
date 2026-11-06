"""
Создание теста ИТО Собчик в БД (ADR-036) — общая функция для
scripts/seed_ito_sobchik.py и тестов.

Тест создаётся с scoring_profile='ito_sobchik' и campaign_only=True: он вне
каталога студента и `/api/tests`, проходится только по ссылке кампании и не
редактируется через конструктор. Идемпотентно: существующий (не удалённый)
тест профиля возвращается как есть, если его структура совпадает с ключом;
расхождение — ошибка (молча «чинить» тест с ответами нельзя).

Аудит не пишется: это системная загрузка методики, а не действие пользователя
(как seed согласий в app/db/seed.py).
"""
from typing import Optional

from app.db.models import Option, Question, Test, TestInterpretation
from app.tests.profiles import ito_sobchik

TITLE = "ИТО — Индивидуально-типологический опросник (Собчик Л. Н.)"
DESCRIPTION = (
    "Индивидуально-типологический опросник для взрослых. 91 утверждение, "
    "ответы «Да» / «Нет». " + ito_sobchik.INSTRUCTION
)


class ItoTestMismatch(Exception):
    """Тест профиля в БД не совпадает с ключом модуля (вопросы/баллы/шкалы)."""


def find_ito_test(db) -> Optional[Test]:
    return (
        db.query(Test)
        .filter(Test.scoring_profile == ito_sobchik.PROFILE,
                Test.deleted_at.is_(None))
        .order_by(Test.id)
        .first()
    )


def structure_of(db, test_id: int) -> list[tuple]:
    """Структура для сверки: (порядок, текст, тип, шкала, [(текст, балл)…])."""
    rows = []
    questions = (
        db.query(Question).filter(Question.test_id == test_id)
        .order_by(Question.question_order).all()
    )
    for q in questions:
        opts = (
            db.query(Option).filter(Option.question_id == q.id)
            .order_by(Option.option_order).all()
        )
        rows.append((
            q.question_order, q.question_text, q.question_type,
            (q.config or {}).get("scale"),
            [(o.option_text, o.value_score) for o in opts],
        ))
    return rows


def expected_structure() -> list[tuple]:
    return [
        (q["question_order"], q["question_text"], q["question_type"],
         q["config"].get("scale"),
         [(o["option_text"], o["value_score"]) for o in q["options"]])
        for q in ito_sobchik.questions()
    ]


def ensure_ito_test(db) -> tuple[Test, bool]:
    """(тест, создан_ли_сейчас). Коммит — на вызывающей стороне."""
    existing = find_ito_test(db)
    if existing is not None:
        if not existing.campaign_only:
            raise ItoTestMismatch("тест профиля ИТО не помечен campaign_only")
        if structure_of(db, existing.id) != expected_structure():
            raise ItoTestMismatch("вопросы теста ИТО в БД расходятся с ключом")
        if existing.scoring_rules is None:   # ADR-037: тест до миграции правил
            existing.scoring_rules = ito_sobchik.scoring_rules()
        return existing, False

    test = Test(
        title=TITLE,
        description=DESCRIPTION,
        scoring="sum",
        status="published",
        is_active=True,
        scoring_profile=ito_sobchik.PROFILE,
        scoring_rules=ito_sobchik.scoring_rules(),   # ADR-037
        campaign_only=True,
    )
    db.add(test)
    db.flush()
    for q in ito_sobchik.questions():
        question = Question(
            test_id=test.id,
            question_text=q["question_text"],
            question_order=q["question_order"],
            question_type=q["question_type"],
            is_required=q["is_required"],
            config=q["config"],
        )
        db.add(question)
        db.flush()
        for o in q["options"]:
            db.add(Option(question_id=question.id, **o))
    for i in ito_sobchik.interpretations():
        db.add(TestInterpretation(test_id=test.id, **i))
    db.flush()
    return test, True
