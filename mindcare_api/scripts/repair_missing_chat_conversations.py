"""
Repair: создать недостающие engagement-беседы для активных связей (Stage 31o).

До Stage 31o assign/transfer не создавали chat_conversation — беседа создавалась
лениво при первом обращении студента. У уже существующих active engagements,
к которым студент ещё не обращался, беседы может не быть, поэтому психолог не
видит диалог. Скрипт идемпотентно создаёт недостающие беседы.

Обрабатываются ТОЛЬКО активные связи:
    status = 'active' AND ended_at IS NULL
    и у которых нет chat_conversation (type='engagement') с этим engagement_id.

Скрипт НЕ трогает: transferred/completed engagements, system-беседы, сообщения,
существующие беседы. Ничего не удаляет.

Использование (из mindcare_api/):
    python scripts/repair_missing_chat_conversations.py            # dry-run (default)
    python scripts/repair_missing_chat_conversations.py --dry-run  # явный dry-run
    python scripts/repair_missing_chat_conversations.py --apply    # реальная запись
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.chat import storage as chat_storage
from app.db.session import SessionLocal
from app.db.models import ChatConversation, TherapyEngagement


def find_active_engagements_without_conversation(db) -> list[int]:
    """ID активных engagements, у которых нет engagement-беседы."""
    rows = (
        db.query(TherapyEngagement.id)
        .filter(
            TherapyEngagement.status == "active",
            TherapyEngagement.ended_at.is_(None),
            ~TherapyEngagement.id.in_(
                db.query(ChatConversation.engagement_id).filter(
                    ChatConversation.engagement_id.isnot(None)
                )
            ),
        )
        .order_by(TherapyEngagement.id)
        .all()
    )
    return [r[0] for r in rows]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Создать недостающие engagement-беседы для active связей"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true",
                       help="Показать, что будет создано, без записи (default)")
    group.add_argument("--apply", action="store_true",
                       help="Реально создать недостающие беседы")
    args = parser.parse_args()

    apply_mode = args.apply
    mode_label = "APPLY" if apply_mode else "DRY-RUN"
    print(f"=== Repair missing chat conversations — режим {mode_label} ===\n")

    found = 0
    created = 0
    skipped = 0

    with SessionLocal() as db:
        engagement_ids = find_active_engagements_without_conversation(db)
        found = len(engagement_ids)

        if not engagement_ids:
            print("Все активные связи уже имеют беседу. Нечего исправлять.")
            return

        for eng_id in engagement_ids:
            _conv, was_created = chat_storage.ensure_engagement_conversation(db, eng_id)
            if was_created:
                created += 1
                print(f"  engagement id={eng_id:<6} -> conversation создана")
            else:
                # Гонка/уже создано между SELECT и flush — идемпотентно пропускаем.
                skipped += 1
                print(f"  engagement id={eng_id:<6} -> беседа уже есть, пропуск")

        if apply_mode:
            db.commit()
            print(f"\n[OK] Найдено: {found}, создано: {created}, пропущено: {skipped}")
        else:
            db.rollback()
            print(f"\n[DRY-RUN] Найдено: {found}, было бы создано: {created}, "
                  f"пропущено: {skipped}")
            print("Для реальной записи запустите с --apply")


if __name__ == "__main__":
    main()
