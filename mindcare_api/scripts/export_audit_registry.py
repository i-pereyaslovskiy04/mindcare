"""
Пишет снимок имён audit-registry для frontend-подписей журнала
(app/audit/registry_snapshot.py). Запускать после любого изменения REGISTRY или
CHANGE_REGISTRY:

    python scripts/export_audit_registry.py           # записать файл
    python scripts/export_audit_registry.py --check   # exit 1, если файл устарел

Только чтение registry; БД не нужна.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.audit.registry_snapshot import SNAPSHOT_PATH, render_snapshot  # noqa: E402


def main() -> int:
    expected = render_snapshot()
    if "--check" in sys.argv[1:]:
        current = SNAPSHOT_PATH.read_text(encoding="utf-8") if SNAPSHOT_PATH.exists() else ""
        if current != expected:
            print(f"[audit-snapshot] устарел: {SNAPSHOT_PATH}", file=sys.stderr)
            return 1
        print("[audit-snapshot] актуален")
        return 0
    SNAPSHOT_PATH.write_text(expected, encoding="utf-8", newline="\n")
    print(f"[audit-snapshot] записан: {SNAPSHOT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
