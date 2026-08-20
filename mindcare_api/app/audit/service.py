"""
Stage 4A — record_event facade: валидация → build ORM row → запись по tx_mode.

Транзакционный режим ФИКСИРОВАН registry (без публичного override). Ошибка записи
журнала НЕ создаёт audit-строку с outcome=failure: она превращается в
AuditStorageError (RAISE) или AuditResult(SOFT_FAILED) (SOFT). Диагностика содержит
только имя события и класс исключения.

Не переносит существующие writer'ы (Stage 4B). Импортирует только contracts/registry/
validation + app.db (session/models) — без routes/service/storage.
"""
from __future__ import annotations

import sys
from typing import Mapping, Optional

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.db.models import AuditLog, AuthLog

from app.audit.contracts import (
    SYSTEM_ROLE, Actor, AuditResult, AuditStorageError, Destination, FailurePolicy,
    Outcome, RequestContext, Target, TxMode, WriteState,
)
from app.audit.registry import get_spec
from app.audit import validation


def record_event(
    *,
    event: str,
    actor: Actor,
    target: Optional[Target] = None,
    outcome: Outcome = Outcome.SUCCESS,
    failure_reason_code: Optional[str] = None,
    metadata: Optional[Mapping[str, object]] = None,
    context: Optional[RequestContext] = None,
    user_email: Optional[str] = None,
    db: Optional[Session] = None,
) -> AuditResult:
    """Единая точка входа аудита. Транзакционный режим определяется registry.

    Контрактные/валидационные нарушения → AuditError (до session). Сбой хранилища →
    AuditStorageError (RAISE) или AuditResult(SOFT_FAILED) (SOFT).
    """
    spec = get_spec(event)                       # unknown → AuditError

    validation.validate_actor(spec, actor)
    validation.validate_target(spec, target)
    validation.validate_outcome(spec, outcome, failure_reason_code)
    safe_meta = validation.validate_metadata(spec, metadata)
    validation.validate_context(context)
    norm_email = validation.validate_email(spec, user_email)

    # tx/db совместимость — до любой записи (без публичного override режима).
    if spec.tx_mode is TxMode.ATOMIC:
        if db is None:
            raise validation.AuditError("atomic event requires a caller db session")
    else:  # INDEPENDENT
        if db is not None:
            raise validation.AuditError("independent event must not receive a caller db")

    row = _build_row(spec, actor, target, outcome, failure_reason_code,
                     safe_meta, context, norm_email)
    return _write(spec, row, db)


# ── ORM mapping ───────────────────────────────────────────────────────────────

def _actor_user_id(actor: Actor) -> Optional[int]:
    return actor.user_id if actor.kind == "user" else None


def _actor_role(actor: Actor) -> Optional[str]:
    if actor.kind == "user":
        return actor.role
    if actor.kind == "system":
        return SYSTEM_ROLE
    return None  # anonymous


def _build_row(spec, actor, target, outcome, failure_reason_code, meta, ctx, email):
    ip = ctx.ip_address if ctx else None
    ua = ctx.user_agent if ctx else None
    session_id = ctx.session_id_hash if ctx else None

    if spec.destination is Destination.AUTH_LOG:
        return AuthLog(
            event=spec.name,
            user_id=_actor_user_id(actor),
            user_email=email,
            success=(outcome is Outcome.SUCCESS),
            failure_reason=failure_reason_code,
            ip_address=ip,
            user_agent=ua,
            session_id=session_id,
        )

    # AUDIT_LOG
    return AuditLog(
        event_type=spec.name,
        user_id=_actor_user_id(actor),
        user_role=_actor_role(actor),
        entity_type=target.entity_type if target else None,
        entity_id=target.entity_id if target else None,
        outcome=outcome.value,
        failure_reason_code=failure_reason_code,
        description=(spec.static_description
                     if spec.description_policy.value == "static" else None),
        log_metadata=meta,
        ip_address=ip,
        user_agent=ua,
        session_id=session_id,
        request_url=(ctx.request_path if ctx else None),
        request_method=(ctx.request_method if ctx else None),
    )


# ── Запись ────────────────────────────────────────────────────────────────────
#
# Правило: ошибка ЖУРНАЛА (factory/add/commit/rollback/close) не превращается в
# business-outcome. Первичный сбой (factory/add/commit) решает итоговое состояние
# по failure_policy. rollback/close — ВСЕГДА best-effort: их собственные ошибки
# никогда не заменяют уже определённый результат (ни успешный PERSISTED, ни
# исходную ошибку add/commit) — только санитизированная диагностика в stderr.

def _diag(event: str, phase: str, error_class: str) -> None:
    # Только имя события, фаза и класс исключения — без actor/target/email/IP/
    # metadata/SQL/URL БД/raw exception text.
    print(f"[AUDIT] event={event} phase={phase} error={error_class}", file=sys.stderr)


def _handle_primary_failure(spec, phase: str, exc: Exception) -> AuditResult:
    """Первичный сбой (factory/add/commit) → RAISE или SOFT_FAILED по registry."""
    error_class = type(exc).__name__
    if spec.failure_policy is FailurePolicy.RAISE:
        raise AuditStorageError(f"audit storage failure for {spec.name}") from None
    _diag(spec.name, phase, error_class)
    return AuditResult(
        state=WriteState.SOFT_FAILED, event=spec.name, error_class=error_class,
    )


def _best_effort_rollback(spec, session) -> None:
    """rollback никогда не бросает наружу; своя ошибка не заменяет исходную."""
    try:
        session.rollback()
    except Exception as exc:
        _diag(spec.name, "rollback", type(exc).__name__)


def _best_effort_close(spec, session) -> None:
    """close никогда не бросает наружу; своя ошибка не меняет уже определённый
    результат (в т.ч. не превращает успешный commit в SOFT_FAILED)."""
    try:
        session.close()
    except Exception as exc:
        _diag(spec.name, "close", type(exc).__name__)


def _write_atomic(spec, row, db: Session) -> AuditResult:
    # ATOMIC: только db.add; caller коммитит. ATOMIC всегда failure_policy=RAISE
    # (enforced registry) — сбой всегда даёт sanitized AuditStorageError.
    try:
        db.add(row)
    except Exception as exc:
        return _handle_primary_failure(spec, "add", exc)
    return AuditResult(state=WriteState.STAGED, event=spec.name)


def _write_independent(spec, row) -> AuditResult:
    # Phase: factory — сбой самого SessionLocal() тоже обрабатывается policy;
    # session ещё не существует → rollback/close не требуются.
    try:
        session = SessionLocal()
    except Exception as exc:
        return _handle_primary_failure(spec, "factory", exc)

    # Phase: add
    try:
        session.add(row)
    except Exception as exc:
        _best_effort_rollback(spec, session)
        _best_effort_close(spec, session)
        return _handle_primary_failure(spec, "add", exc)

    # Phase: commit
    try:
        session.commit()
    except Exception as exc:
        _best_effort_rollback(spec, session)
        _best_effort_close(spec, session)
        return _handle_primary_failure(spec, "commit", exc)

    # Commit успешен — запись уже зафиксирована. close — best-effort: его сбой
    # НЕ откатывает PERSISTED в SOFT_FAILED и не вызывает повторный commit/add.
    _best_effort_close(spec, session)
    return AuditResult(state=WriteState.PERSISTED, event=spec.name)


def _write(spec, row, db: Optional[Session]) -> AuditResult:
    if spec.tx_mode is TxMode.ATOMIC:
        return _write_atomic(spec, row, db)
    return _write_independent(spec, row)
