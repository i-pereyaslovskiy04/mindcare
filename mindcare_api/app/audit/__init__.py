"""
Stage 4A — единый audit facade (auth_log + audit_log).

Публичная точка входа: record_event(). Транзакционный режим и failure policy владеет
registry; caller их не переопределяет. Перенос существующих writer'ов — Stage 4B.

Stage 6-0 — минимизированный data_change_log: record_data_change() + helpers.
Отдельная точка входа (строка DCL не событие), режим ТОЛЬКО ATOMIC/fail-closed.
Подключение business-caller'ов — Stage 6-B/6-C.
"""
from app.audit.contracts import (
    Actor,
    AuditError,
    AuditResult,
    AuditStorageError,
    Outcome,
    RequestContext,
    Target,
    TxMode,
    WriteState,
)
from app.audit.service import record_event

from app.audit.change_contracts import (
    ChangeValue,
    DataChangeError,
    DataChangeResult,
    DataChangeStorageError,
    Operation,
    ValuePolicy,
)
from app.audit.change_registry import is_value_allowed
from app.audit.data_change import project_changed_fields, record_data_change

__all__ = [
    "record_event",
    "Actor",
    "Target",
    "RequestContext",
    "Outcome",
    "AuditResult",
    "WriteState",
    "TxMode",
    "AuditError",
    "AuditStorageError",
    # ── Stage 6-0: data_change_log ──
    "record_data_change",
    "project_changed_fields",
    "is_value_allowed",
    "Operation",
    "ValuePolicy",
    "ChangeValue",
    "DataChangeResult",
    "DataChangeError",
    "DataChangeStorageError",
]
