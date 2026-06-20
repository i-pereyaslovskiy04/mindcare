#!/usr/bin/env python3
"""
PreToolUse hook: версионный бэкап изменяемых файлов проекта MindCare.

Срабатывает ПЕРЕД Edit/Write/MultiEdit/NotebookEdit и сохраняет текущую
(до-правочную) версию файла в `.backups/files/` внутри проекта, сохраняя
историю:

  <project>/.backups/files/<относительный путь>/<UTC-таймстамп><ext>

Каждое изменение создаёт новый файл-версию — старые не перезаписываются.
Скрипт лежит в трекаемой `scripts/` (версионируется в git и общий для команды);
сами бэкапы (`.backups/files/`) — gitignored. Пути НЕ захардкожены: корень
проекта вычисляется относительно этого скрипта. Никогда не блокирует операцию
(всегда exit 0).

Подключается как PreToolUse-hook в .claude/settings.json:
  python3 "$CLAUDE_PROJECT_DIR/scripts/backup_hook.py"
"""

import json
import os
import shutil
import sys
from datetime import datetime, timezone

# Скрипт лежит в <project>/scripts/ → корень проекта на уровень выше.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
BACKUP_ROOT = os.path.join(PROJECT_ROOT, ".backups")
FILES_DIR = os.path.join(BACKUP_ROOT, "files")
MAX_BYTES = 25 * 1024 * 1024  # не копировать гигантские файлы


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    tool_input = payload.get("tool_input") or {}
    file_path = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not file_path:
        return 0

    abs_path = os.path.realpath(file_path)

    # Только файлы внутри проекта и не из самой папки бэкапов.
    if not abs_path.startswith(PROJECT_ROOT + os.sep):
        return 0
    if abs_path.startswith(BACKUP_ROOT + os.sep):
        return 0

    # Нечего бэкапить, если файл ещё не существует (создание нового).
    if not os.path.isfile(abs_path):
        return 0
    try:
        if os.path.getsize(abs_path) > MAX_BYTES:
            return 0
    except OSError:
        return 0

    rel = os.path.relpath(abs_path, PROJECT_ROOT)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%S.%fZ")
    ext = os.path.splitext(abs_path)[1]
    dest_dir = os.path.join(FILES_DIR, rel)
    dest = os.path.join(dest_dir, f"{ts}{ext}")

    try:
        os.makedirs(dest_dir, exist_ok=True)
        shutil.copy2(abs_path, dest)
    except Exception as exc:  # бэкап best-effort, не валим операцию
        print(f"[backup_hook] WARN: {exc}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
