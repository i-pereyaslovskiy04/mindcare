"""
Backfill роли student существующим staff-пользователям.

Продуктовое решение: каждый staff-пользователь (psychologist / supervisor /
admin) неявно получает роль student, чтобы иметь доступ к кабинету студента
(переход через CabinetSwitcher). Новые staff получают роль в
users.storage.create_user; этот скрипт выдаёт её уже существующим.

Находит НЕ-удалённых пользователей с ≥1 активной staff-ролью, у которых нет
АКТИВНОЙ роли student, и:
  - если строки user_roles(student) нет вовсе — создаёт её;
  - если строка есть, но просрочена (expires_at в прошлом) — реактивирует
    (expires_at = NULL). UniqueConstraint(user_id, role_id) исключает дубли.

Роль student здесь — НЕ staff-роль: legal_basis / consent_records для неё не
пишутся (в отличие от self-registration студента). В списках реальных студентов
такие аккаунты изолируются предикатом «только student» (supervisor.get_students,
users.list_users). Логи не содержат email/ФИО (ПДн) — только user_id и роль.

Использование (из mindcare_api/):
    python scripts/backfill_student_role.py            # dry-run (по умолчанию)
    python scripts/backfill_student_role.py --dry-run  # явный dry-run
    python scripts/backfill_student_role.py --apply    # реальная запись в БД
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import or_

from app.db.session import SessionLocal
from app.db.models import Role, User, UserRole

STAFF_ROLES = ("psychologist", "supervisor", "admin")


def find_staff_needing_student(db, now: datetime) -> list[tuple[int, str]]:
    """[(user_id, primary_staff_role), ...] staff без активной роли student."""
    active = or_(UserRole.expires_at.is_(None), UserRole.expires_at > now)

    active_student_uids = (
        db.query(UserRole.user_id)
        .join(Role, Role.id == UserRole.role_id)
        .filter(Role.name == "student", active)
    )

    rows = (
        db.query(User.id, Role.name)
        .join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .filter(
            Role.name.in_(STAFF_ROLES),
            active,
            User.deleted_at.is_(None),
            ~User.id.in_(active_student_uids),
        )
        .distinct()
        .all()
    )
    # У пользователя может быть несколько staff-ролей — оставляем одну строку.
    by_user: dict[int, str] = {}
    for uid, role in rows:
        by_user.setdefault(uid, role)
    return sorted(by_user.items())


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill student role for staff")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true",
                       help="Показать, что будет сделано, без записи (default)")
    group.add_argument("--apply", action="store_true",
                       help="Реально выдать/реактивировать роль student")
    args = parser.parse_args()

    apply_mode = args.apply
    mode_label = "APPLY" if apply_mode else "DRY-RUN"
    print(f"=== Backfill роли student для staff — режим {mode_label} ===\n")

    now = datetime.now(timezone.utc)

    with SessionLocal() as db:
        student_role = db.query(Role).filter(Role.name == "student").first()
        if student_role is None:
            print("[FAIL] Роль 'student' отсутствует в справочнике roles — "
                  "проверьте seed. Ничего не сделано.")
            sys.exit(1)

        candidates = find_staff_needing_student(db, now)
        if not candidates:
            print("Все staff-пользователи уже имеют активную роль student. "
                  "Нечего делать.")
            return

        inserted = 0
        reactivated = 0
        for user_id, staff_role in candidates:
            existing = (
                db.query(UserRole)
                .filter(
                    UserRole.user_id == user_id,
                    UserRole.role_id == student_role.id,
                )
                .first()
            )
            if existing is not None:
                action = "reactivate"
                reactivated += 1
            else:
                action = "insert"
                inserted += 1
            print(f"  user_id={user_id:<6} staff_role={staff_role:<13} action={action}")

            if apply_mode:
                if existing is not None:
                    existing.expires_at = None
                else:
                    db.add(UserRole(user_id=user_id, role_id=student_role.id))

        if apply_mode:
            db.commit()
            print(f"\n[OK] Выдано новых: {inserted}, реактивировано: {reactivated}")
        else:
            print(f"\n[DRY-RUN] Было бы выдано новых: {inserted}, "
                  f"реактивировано: {reactivated}")
            print("Для реальной записи запустите с --apply")


if __name__ == "__main__":
    main()
