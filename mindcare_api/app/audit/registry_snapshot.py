"""
Снимок имён audit-registry для сверки подписей журнала во frontend
(`mindcare_web/src/features/admin/audit/lib/auditRegistry.snapshot.json`).

Только стабильные машинные имена (события, коды отказа, типы сущностей, пары
таблица/поле data_change_log) — без политик, ролей и metadata. Источник истины
— REGISTRY / CHANGE_REGISTRY; файл пишет `scripts/export_audit_registry.py`,
а `tests/test_audit_registry_snapshot.py` требует, чтобы файл совпадал с
registry: новое событие без обновления снимка роняет backend-тест, а запись
снимка без подписи — frontend-тест (`auditLabels.test.js`).
"""
import json
from pathlib import Path

from app.audit.admin_policy import AUDIT_EVENT_NAMES, AUTH_EVENT_NAMES, ENTITY_TYPES
from app.audit.change_registry import CHANGE_REGISTRY
from app.audit.registry import REGISTRY

SNAPSHOT_PATH = (
    Path(__file__).resolve().parents[3]
    / "mindcare_web" / "src" / "features" / "admin" / "audit" / "lib"
    / "auditRegistry.snapshot.json"
)


def build_snapshot() -> dict:
    failure_codes = sorted({
        code for spec in REGISTRY.values() for code in spec.allowed_failure_codes
    })
    change_pairs = sorted(
        [table, field]
        for table, spec in CHANGE_REGISTRY.items()
        for field in spec.fields
    )
    return {
        "audit_events": sorted(AUDIT_EVENT_NAMES),
        "auth_events": sorted(AUTH_EVENT_NAMES),
        "failure_codes": failure_codes,
        "entity_types": sorted(ENTITY_TYPES),
        "change_pairs": change_pairs,
    }


def render_snapshot() -> str:
    return json.dumps(build_snapshot(), ensure_ascii=False, indent=2) + "\n"
