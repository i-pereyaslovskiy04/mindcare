#!/usr/bin/env python3
"""
cleanup_orphan_attachments.py — удаление незавершённых pre-upload вложений.

Orphan = chat_attachment с message_id IS NULL, created_at < cutoff, deleted_at IS NULL.
Такие записи появляются если upload прошёл, но send_message не был вызван
(клиент закрыл вкладку, сеть упала и т.п.).

Использование:
    cd mindcare_api/
    python scripts/cleanup_orphan_attachments.py            # dry-run по умолчанию
    python scripts/cleanup_orphan_attachments.py --apply    # реальное удаление
    python scripts/cleanup_orphan_attachments.py --hours 48 # другой cutoff (по умолчанию 24)

Что происходит при --apply:
  1. Физический файл удаляется с диска.
  2. Строка chat_attachment soft-delete (deleted_at = now).
  3. Записи НЕ удаляются физически из БД — для audit trail.

Безопасность:
  - Не удаляет вложения, уже привязанные к сообщениям (message_id IS NOT NULL).
  - Не удаляет уже soft-deleted строки.
  - Dry-run ничего не меняет, только выводит что было бы удалено.
  - original_filename в лог не попадает (может содержать ПДн).
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Добавляем корень mindcare_api/ в PYTHONPATH для импорта app.*
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from app.chat.attachment_storage import delete_file, file_exists
from app.chat.storage import get_orphan_attachments, soft_delete_attachment


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Очистка orphan chat attachments (без привязанного message_id)."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Реальное удаление. Без флага — dry-run.",
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=24,
        help="Возраст orphan в часах (default: 24). Записи моложе порога не трогаются.",
    )
    args = parser.parse_args()

    cutoff = datetime.now(timezone.utc) - timedelta(hours=args.hours)
    mode   = "APPLY" if args.apply else "DRY-RUN"

    print(
        f"[{mode}] Поиск orphan attachments старше {args.hours}ч "
        f"(cutoff: {cutoff.isoformat()})"
    )

    rows = get_orphan_attachments(cutoff)
    if not rows:
        print(f"[{mode}] Orphan attachments не найдены.")
        return 0

    print(f"[{mode}] Найдено: {len(rows)} orphan attachment(s)")

    deleted_files = 0
    soft_deleted  = 0
    errors        = 0

    for att in rows:
        uuid_str = str(att.uuid)
        key      = att.storage_key

        if not args.apply:
            exists = file_exists(key)
            print(
                f"  [DRY-RUN] uuid={uuid_str}  size={att.file_size}B  "
                f"mime={att.mime_type}  file_on_disk={exists}"
            )
            continue

        # Реальное удаление: физический файл, затем soft-delete строки
        try:
            removed = delete_file(key)
            if removed:
                deleted_files += 1
        except Exception as exc:
            print(
                f"  [ERROR] uuid={uuid_str}: удаление файла: {exc}",
                file=sys.stderr,
            )
            errors += 1
            continue   # не soft-delete если файл не удалён

        try:
            soft_delete_attachment(att.id)
            soft_deleted += 1
            print(
                f"  [DELETED] uuid={uuid_str}  size={att.file_size}B  "
                f"mime={att.mime_type}  file_removed={removed}"
            )
        except Exception as exc:
            print(
                f"  [ERROR] uuid={uuid_str}: soft-delete в БД: {exc}",
                file=sys.stderr,
            )
            errors += 1

    if args.apply:
        print(
            f"[APPLY] Итого: {soft_deleted} soft-deleted, "
            f"{deleted_files} файлов удалено, {errors} ошибок."
        )

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
