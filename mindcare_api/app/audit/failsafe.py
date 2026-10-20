"""
Stage 5A-2 — independently committed best-effort failure audit.

`record_secondary_failure` вызывается из route ТОЛЬКО в ветке доказанного
precommit business-отказа (`except service.AuthError`). Пишет `*_failed` через
facade `record_event` в независимой транзакции (INDEPENDENT/SOFT) — запись
переживает rollback бизнес-транзакции, НО это не гарантированная доставка
(gуarantee потребовала бы outbox/retry — отдельный этап).

Инвариант: НИКОГДА не заменяет исходный business HTTP-ответ и не бросает наружу.
Любой сбой САМОГО вторичного writer'а (validation `AuditError`, storage, любой
`Exception`) поглощается и возвращается `AuditResult(SOFT_FAILED)`. Broad catch
здесь допустим ТОЛЬКО вокруг вторичного логирования — он не классифицирует
business-исключение (то уже классифицировано вызывающим по типу). Диагностика
содержит лишь event + phase + класс исключения; без str(exc)/actor/target/
email/UUID/IP/ролей/metadata. Facade validation не ослабляется.
"""
from __future__ import annotations

import sys

from app.audit import (
    Actor, AuditResult, Outcome, RequestContext, WriteState, record_event,
)


def record_secondary_failure(
    *,
    event: str,
    actor: Actor,
    failure_reason_code: str,
    context: RequestContext,
) -> AuditResult:
    """
    Пишет `*_failed` (outcome=FAILURE, metadata={}, без target, без db).

    `failure_reason_code` ОБЯЗАТЕЛЕН — fallback-кода нет (его отсутствие на
    loggable-пути = programming contract error, не маскируется). Возвращает
    `AuditResult` (PERSISTED / SOFT_FAILED); наружу не бросает.
    """
    try:
        return record_event(
            event=event,
            actor=actor,
            outcome=Outcome.FAILURE,
            failure_reason_code=failure_reason_code,
            metadata={},
            context=context,
        )
    except Exception as exc:   # noqa: BLE001 — только сбой вторичного writer'а
        print(
            f"[AUDIT] event={event} phase=secondary error={type(exc).__name__}",
            file=sys.stderr,
        )
        return AuditResult(
            state=WriteState.SOFT_FAILED, event=event,
            error_class=type(exc).__name__,
        )
