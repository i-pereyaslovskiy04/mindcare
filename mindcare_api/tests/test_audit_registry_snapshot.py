"""
Снимок имён audit-registry для frontend-подписей журнала совпадает с текущим
REGISTRY / CHANGE_REGISTRY. Падение означает: registry изменился, а снимок —
нет. Обновить: `python scripts/export_audit_registry.py`, затем добавить
подписи новых имён в `auditLabels.js` (его тест сверяется с этим файлом).
"""
import json

from app.audit.registry import REGISTRY
from app.audit.registry_snapshot import SNAPSHOT_PATH, build_snapshot, render_snapshot


def test_snapshot_file_matches_registry():
    assert SNAPSHOT_PATH.exists(), f"нет снимка: {SNAPSHOT_PATH}"
    assert SNAPSHOT_PATH.read_text(encoding="utf-8") == render_snapshot(), (
        "auditRegistry.snapshot.json устарел — запустите scripts/export_audit_registry.py"
    )


def test_snapshot_covers_whole_registry():
    snap = build_snapshot()
    assert set(snap["audit_events"]) | set(snap["auth_events"]) == set(REGISTRY)
    assert len(snap["audit_events"]) + len(snap["auth_events"]) == len(REGISTRY)
    json.dumps(snap)   # только JSON-совместимые имена
