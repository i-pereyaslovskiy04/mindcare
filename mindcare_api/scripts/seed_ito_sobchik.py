#!/usr/bin/env python3
"""
Загрузка теста ИТО Собчик (ADR-036): 91 утверждение «Да/Нет», ключ 10 шкал,
пороги уровней. Тест — только для кампаний (campaign_only), вне каталога студента.

Идемпотентно: если тест профиля уже есть и совпадает с ключом — ничего не
меняет; если расходится — exit 1 без изменений.

Запуск (из mindcare_api/, после alembic upgrade head):
    python scripts/seed_ito_sobchik.py --dry-run
    python scripts/seed_ito_sobchik.py
"""
import argparse
import sys

sys.path.insert(0, ".")

from app.db.session import SessionLocal                              # noqa: E402
from app.tests.profiles.ito_seed import ItoTestMismatch, ensure_ito_test  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--dry-run", action="store_true",
                        help="проверить и откатить, ничего не сохранять")
    args = parser.parse_args()

    with SessionLocal() as db:
        try:
            test, created = ensure_ito_test(db)
        except ItoTestMismatch as exc:
            db.rollback()
            print(f"ОШИБКА: {exc}. Изменений нет.")
            return 1
        uuid = str(test.uuid) if test.uuid else "—"
        if args.dry_run:
            db.rollback()
            print("dry-run:", "тест был бы создан" if created
                  else f"тест уже есть и совпадает с ключом ({uuid})")
            return 0
        db.commit()
        db.refresh(test)
        print("Создан тест ИТО:" if created else "Тест ИТО уже есть:", test.uuid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
