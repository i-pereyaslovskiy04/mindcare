"""
Backfill legal basis records для существующих staff-пользователей (Stage 23b).

Находит пользователей с ролями psychologist / supervisor / admin, у которых
нет ни одной записи в user_legal_basis_records, и создаёт запись:

  basis_type   = "other"      (или "bootstrap", если пользователь опознан
                               как bootstrap-админ по старым consent_records
                               с user_agent='bootstrap-script')
  basis_source = "migration_backfill"
  comment      = "Backfill Stage 23b: основание задокументировано офлайн"

Старые consent_records НЕ удаляются и НЕ изменяются (историческая запись).

Использование (из mindcare_api/):
    python scripts/backfill_legal_basis.py            # dry-run (по умолчанию)
    python scripts/backfill_legal_basis.py --dry-run  # явный dry-run
    python scripts/backfill_legal_basis.py --apply    # реальная запись в БД
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal
from app.db.models import (
    ConsentRecord, Role, User, UserLegalBasisRecord, UserRole,
)

STAFF_ROLES = ("psychologist", "supervisor", "admin")
BACKFILL_COMMENT = "Backfill Stage 23b: основание задокументировано офлайн"


def find_staff_without_basis(db) -> list[tuple[int, str, str]]:
    """Возвращает [(user_id, email, role), ...] staff-юзеров без basis-записи."""
    rows = (
        db.query(User.id, User.email, Role.name)
        .join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .filter(
            Role.name.in_(STAFF_ROLES),
            User.deleted_at.is_(None),
            ~User.id.in_(
                db.query(UserLegalBasisRecord.user_id).distinct()
            ),
        )
        .distinct()
        .all()
    )
    return [(r[0], r[1], r[2]) for r in rows]


def is_bootstrap_user(db, user_id: int) -> bool:
    """Bootstrap-админы исторически получали consent с user_agent='bootstrap-script'."""
    return (
        db.query(ConsentRecord)
        .filter(
            ConsentRecord.user_id == user_id,
            ConsentRecord.user_agent == "bootstrap-script",
        )
        .first()
        is not None
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill user_legal_basis_records")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true",
                       help="Показать, что будет создано, без записи (default)")
    group.add_argument("--apply", action="store_true",
                       help="Реально создать записи в БД")
    args = parser.parse_args()

    apply_mode = args.apply
    mode_label = "APPLY" if apply_mode else "DRY-RUN"
    print(f"=== Backfill legal basis records — режим {mode_label} ===\n")

    with SessionLocal() as db:
        candidates = find_staff_without_basis(db)

        if not candidates:
            print("Все staff-пользователи уже имеют legal basis records. Нечего делать.")
            return

        created = 0
        for user_id, email, role in candidates:
            basis_type = "bootstrap" if is_bootstrap_user(db, user_id) else "other"
            print(f"  user_id={user_id:<6} role={role:<13} basis_type={basis_type:<10} {email}")

            if apply_mode:
                db.add(UserLegalBasisRecord(
                    user_id=user_id,
                    basis_type=basis_type,
                    basis_source="migration_backfill",
                    confirmed_by_user_id=None,
                    comment=BACKFILL_COMMENT,
                ))
            created += 1

        if apply_mode:
            db.commit()
            print(f"\n[OK] Создано записей: {created}")
        else:
            print(f"\n[DRY-RUN] Было бы создано записей: {created}")
            print("Для реальной записи запустите с --apply")


if __name__ == "__main__":
    main()
