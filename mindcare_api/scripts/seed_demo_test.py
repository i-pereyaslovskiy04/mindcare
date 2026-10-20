#!/usr/bin/env python3
"""
Сид демо-методики психодиагностики: PHQ-9 (шкала депрессии).

Идемпотентно: если активный тест с таким title уже есть — ничего не делает
(если не передан --force, который создаёт новую версию-копию заголовком).

PHQ-9 распространяется свободно (Pfizer, без необходимости разрешения).
9 вопросов, single_choice 0–3, scoring=sum, итог 0–27, 5 диапазонов
интерпретации. Используется как эталон для проверки скоринга/интерпретации
end-to-end.

Запуск (из mindcare_api/, после alembic upgrade head):
    python scripts/seed_demo_test.py
    python scripts/seed_demo_test.py --dry-run
"""

import argparse
import sys

# Позволяет запускать скрипт напрямую из mindcare_api/
sys.path.insert(0, ".")

from app.db.session import SessionLocal           # noqa: E402
from app.db.models import Test, User              # noqa: E402
from app.tests import storage                     # noqa: E402
from app.auth.storage import get_active_role_names  # noqa: E402
from app.auth.roles import primary_role           # noqa: E402

TITLE = "PHQ-9 — Шкала депрессии (демо)"

_PHQ9_PROMPT = (
    "За последние 2 недели как часто Вас беспокоили следующие проблемы?"
)
_PHQ9_ITEMS = [
    "Снижение интереса или удовольствия от занятий",
    "Подавленность, угнетённость или чувство безнадёжности",
    "Трудности с засыпанием, прерывистый сон или, наоборот, сонливость",
    "Усталость или упадок сил",
    "Плохой аппетит или переедание",
    "Плохое мнение о себе; чувство, что Вы неудачник или подвели себя/близких",
    "Трудности с концентрацией (чтение, просмотр телевизора и т.п.)",
    "Заторможенность или, наоборот, суетливость и неусидчивость",
    "Мысли о том, что Вам лучше умереть или причинить себе вред",
]
_PHQ9_OPTIONS = [
    ("Совсем нет", 0),
    ("Несколько дней", 1),
    ("Более половины дней", 2),
    ("Почти каждый день", 3),
]
_PHQ9_INTERPRETATIONS = [
    (0, 4,   "Минимальная депрессия",        "Симптомы выражены минимально. Специального вмешательства обычно не требуется."),
    (5, 9,   "Лёгкая депрессия",             "Лёгкая выраженность симптомов. Рекомендуется наблюдение и самопомощь."),
    (10, 14, "Умеренная депрессия",          "Умеренная выраженность. Рекомендуется консультация психолога службы."),
    (15, 19, "Умеренно тяжёлая депрессия",   "Выраженные симптомы. Желательна очная консультация специалиста."),
    (20, 27, "Тяжёлая депрессия",            "Высокая выраженность симптомов. Настоятельно рекомендуется обратиться к специалисту."),
]


def _build_data() -> dict:
    questions = []
    for idx, item in enumerate(_PHQ9_ITEMS, start=1):
        questions.append({
            "question_text": f"{_PHQ9_PROMPT}\n{idx}. {item}",
            "question_order": idx,
            "question_type": "single_choice",
            "is_required": True,
            "config": {},
            "options": [
                {"option_text": text, "option_order": o, "value_score": score}
                for o, (text, score) in enumerate(_PHQ9_OPTIONS)
            ],
        })
    interpretations = [
        {"scale_name": None, "min_score": lo, "max_score": hi,
         "label": label, "recommendation": rec}
        for (lo, hi, label, rec) in _PHQ9_INTERPRETATIONS
    ]
    return {
        "title": TITLE,
        "description": (
            "Опросник здоровья пациента PHQ-9 — скрининговая шкала депрессии. "
            "Результат носит ориентировочный характер и не является диагнозом."
        ),
        "scoring": "sum",
        "max_score": 27,
        "time_limit_min": None,
        "is_active": True,
        "category_ids": [],
        "tag_uuids": [],
        "questions": questions,
        "interpretations": interpretations,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Seed PHQ-9 demo test (idempotent).")
    ap.add_argument("--dry-run", action="store_true", help="Только проверка, без записи.")
    args = ap.parse_args()

    with SessionLocal() as db:
        exists = (
            db.query(Test.id)
            .filter(Test.title == TITLE, Test.deleted_at.is_(None))
            .first()
        )
        # created_by — первый пользователь (если есть), иначе NULL.
        # Stage 4B-5: create_test пишет ATOMIC audit и требует actor context —
        # резолвим фактическую роль created_by (bootstrap ops-path, не HTTP).
        first_user = db.query(User.id).order_by(User.id).first()
        created_by = first_user[0] if first_user else None
        actor_role = (
            primary_role(get_active_role_names(db, created_by))
            if created_by is not None else None
        )

    if exists:
        print(f"[SEED] Демо-тест уже существует: «{TITLE}» — пропуск.")
        return 0

    if args.dry_run:
        print(f"[SEED][dry-run] Был бы создан тест «{TITLE}» "
              f"(9 вопросов, sum 0–27, 5 интерпретаций).")
        return 0

    if created_by is None or actor_role not in ("admin", "supervisor"):
        print("[SEED] Нет пользователя с ролью admin/supervisor для "
              "атрибуции демо-теста — создайте админа (scripts/create_admin.py) "
              "и повторите.")
        return 1

    created = storage.create_test(
        _build_data(), created_by=created_by, actor_role=actor_role,
    )
    print(f"[SEED] Создан демо-тест «{TITLE}» uuid={created['uuid']} "
          f"(вопросов: {len(created['questions'])}, "
          f"интерпретаций: {len(created['interpretations'])}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
