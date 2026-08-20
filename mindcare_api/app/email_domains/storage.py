"""
Работа с БД для allowlist почтовых доменов.

Слои: этот модуль импортирует только `policy` (pure) и `errors`; он НЕ
импортирует `email_domains.service` (направление `service → storage`
сохранено). Внешние creation-storages (auth/users/supervisor) вызывают
`assert_email_domain_allowed_in_tx` и ловят `EmailDomainNotAllowedError`.

Конкурентность:
  - `assert_email_domain_allowed_in_tx` берёт FOR SHARE на активной строке
    домена → удерживает разрешённый домен до commit создания пользователя;
  - `set_domain_state` берёт transaction-scoped advisory lock (фиксированная
    числовая пара) + FOR UPDATE на строках → сериализует отключения и не даёт
    отключить последний активный домен из двух конкурентных транзакций.
"""

from datetime import datetime, timezone
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from app.audit import Actor, Outcome, Target, record_event
from app.audit.request_context import build_request_context
from app.db.session import SessionLocal
from app.db.models import AllowedEmailDomain
from app.email_domains.errors import DomainError, EmailDomainNotAllowedError
from app.email_domains.policy import extract_domain

# Стабильные между процессами константы для pg_advisory_xact_lock(key1, key2).
# key1 — ОТРИЦАТЕЛЬНЫЙ, чтобы гарантированно не пересекаться с appointment-локом
# (`acquire_slot_lock` использует положительный psychologist_id как key1).
_DOMAIN_LOCK_KEY1 = -2_100_000_000
_DOMAIN_LOCK_KEY2 = 1

_NOT_ALLOWED_MESSAGE = (
    "Регистрация доступна только для разрешённых почтовых доменов."
)


def _row_to_dict(row: AllowedEmailDomain) -> dict:
    return {
        "id":         row.id,
        "domain":     row.domain,
        "is_active":  row.is_active,
        "comment":    row.comment,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


# ── Проверка политики ──────────────────────────────────────────────────────────

def is_domain_active(domain: str) -> bool:
    """
    Ранний read-check (открывает свою короткую сессию, без блокировки).
    Используется в register_init до создания OTP/письма. `domain` — уже
    нормализованный.
    """
    if not domain:
        return False
    with SessionLocal() as db:
        found = (
            db.query(AllowedEmailDomain.id)
            .filter(
                AllowedEmailDomain.domain == domain,
                AllowedEmailDomain.is_active.is_(True),
            )
            .first()
        )
        return found is not None


def assert_email_domain_allowed_in_tx(db, email: str) -> None:
    """
    Authoritative in-tx проверка: домен email должен быть активен в allowlist.

    Принимает ПЕРЕДАННУЮ сессию `db` (своей не открывает) и берёт FOR SHARE на
    найденной активной строке домена — так разрешённый домен нельзя отключить,
    пока транзакция создания пользователя не завершится. Нет активной строки →
    EmailDomainNotAllowedError (вызывающий мапит в HTTP 422). Вызывать ДО
    необратимых шагов (создание пользователя, consume OTP).
    """
    domain = extract_domain(email)
    if not domain:
        raise EmailDomainNotAllowedError(_NOT_ALLOWED_MESSAGE)
    found = db.execute(
        sa.select(AllowedEmailDomain.id)
        .where(
            AllowedEmailDomain.domain == domain,
            AllowedEmailDomain.is_active.is_(True),
        )
        .with_for_update(read=True)  # PostgreSQL FOR SHARE
    ).first()
    if found is None:
        raise EmailDomainNotAllowedError(_NOT_ALLOWED_MESSAGE)


# ── Admin CRUD ─────────────────────────────────────────────────────────────────

def list_domains() -> list[dict]:
    """Все домены (активные + отключённые), sort по domain asc."""
    with SessionLocal() as db:
        rows = (
            db.query(AllowedEmailDomain)
            .order_by(AllowedEmailDomain.domain.asc())
            .all()
        )
        return [_row_to_dict(r) for r in rows]


def _require_actor(actor_id: Optional[int], actor_role: Optional[str]) -> None:
    """
    Fail-closed actor context: изменение allowlist — привилегированная admin-операция.
    Отсутствие actor_id/actor_role — внутренний wiring-баг (routes всегда передают
    admin через _actor). RuntimeError до любой мутации → транзакция не открывается/
    откатывается без частичных изменений. Сообщение без ПДн.
    """
    if actor_id is None or actor_role is None:
        raise RuntimeError(
            "email domain change requires authenticated actor context "
            "(actor_id and actor_role)"
        )


def _record_domain_event(
    db, *, event_type: str, domain_row: AllowedEmailDomain,
    actor_id: int, actor_role: str,
    ip: Optional[str], user_agent: Optional[str],
) -> None:
    """
    ATOMIC audit изменения домена через единый facade (та же caller-транзакция,
    db=db; facade только db.add, без commit/rollback/close). metadata пуста, а
    description не пишется — domain/comment/before/after в журнал не попадают
    (defense against ПДн в comment); субъект восстановим по entity_id.
    """
    record_event(
        event=event_type,
        actor=Actor.user(actor_id, actor_role),
        target=Target("allowed_email_domain", domain_row.id),
        outcome=Outcome.SUCCESS,
        context=build_request_context(ip=ip, user_agent=user_agent),
        db=db,
    )


def create_domain(
    *,
    domain: str,
    comment: Optional[str],
    actor_id: Optional[int],
    actor_role: Optional[str],
    ip: Optional[str],
    user_agent: Optional[str],
) -> dict:
    """
    Добавляет домен в allowlist (активным). `domain` уже нормализован и
    провалидирован в service. Уникальность нормализованного домена авторитетна
    на уровне БД: IntegrityError по ux_allowed_email_domains_domain → 409;
    прочие IntegrityError не маскируются под duplicate.
    """
    _require_actor(actor_id, actor_role)
    with SessionLocal() as db:
        row = AllowedEmailDomain(
            domain=domain,
            is_active=True,
            comment=comment,
            created_by_user_id=actor_id,
        )
        db.add(row)
        try:
            db.flush()  # ловим нарушение UNIQUE до записи AuditLog
        except IntegrityError as exc:
            db.rollback()
            # psycopg2 (PostgreSQL) экспонирует constraint_name через .diag —
            # надёжнее substring-поиска по str(exc.orig) (не зависит от текста
            # сообщения/локали). Другие IntegrityError не маскируем под 409.
            constraint_name = getattr(
                getattr(exc.orig, "diag", None), "constraint_name", None
            )
            if constraint_name == "ux_allowed_email_domains_domain":
                raise DomainError(
                    f"Домен '{domain}' уже есть в списке. Если он отключён — "
                    f"включите его повторно (реактивация).",
                    409,
                )
            raise
        _record_domain_event(
            db, event_type="email_domain_add", domain_row=row,
            actor_id=actor_id, actor_role=actor_role, ip=ip, user_agent=user_agent,
        )
        db.commit()
        db.refresh(row)
        return _row_to_dict(row)


def set_domain_state(
    *,
    domain_id: int,
    new_is_active: Optional[bool],
    comment_provided: bool,
    new_comment: Optional[str],
    actor_id: Optional[int],
    actor_role: Optional[str],
    ip: Optional[str],
    user_agent: Optional[str],
) -> dict:
    """
    Disable / reactivate / update-comment для домена.

    - `new_is_active=None` → is_active не меняем; иначе выставляем;
    - `comment_provided=False` → comment не трогаем; иначе выставляем new_comment
      (в т.ч. None для очистки).

    Concurrency: transaction-scoped advisory lock (фиксированная пара) сериализует
    операции над allowlist; активные строки блокируются FOR UPDATE. Нельзя
    отключить последний активный домен (две конкурентные disable-транзакции не
    оставят 0 активных) → 409. No-op (ничего не изменилось) не пишет audit и не
    трогает updated_at. Не найден → 404. Audit атомарен с изменением.
    """
    _require_actor(actor_id, actor_role)
    with SessionLocal() as db:
        # Transaction-scoped mutex по фиксированному policy-key.
        db.execute(
            sa.text("SELECT pg_advisory_xact_lock(:k1, :k2)"),
            {"k1": _DOMAIN_LOCK_KEY1, "k2": _DOMAIN_LOCK_KEY2},
        )

        row = (
            db.query(AllowedEmailDomain)
            .filter(AllowedEmailDomain.id == domain_id)
            .with_for_update()
            .first()
        )
        if row is None:
            raise DomainError("Домен не найден", 404)

        is_active_before = row.is_active
        will_disable = new_is_active is False and is_active_before is True
        will_reactivate = new_is_active is True and is_active_before is False
        comment_changed = comment_provided and (new_comment != row.comment)
        is_active_changed = will_disable or will_reactivate

        if not is_active_changed and not comment_changed:
            # No-op: не пишем audit, не трогаем updated_at.
            return _row_to_dict(row)

        if will_disable:
            # Заблокировать все активные строки и посчитать — нельзя уронить до 0.
            active_rows = (
                db.query(AllowedEmailDomain.id)
                .filter(AllowedEmailDomain.is_active.is_(True))
                .order_by(AllowedEmailDomain.id.asc())
                .with_for_update()
                .all()
            )
            if len(active_rows) <= 1:
                raise DomainError(
                    "Нельзя отключить последний активный домен: хотя бы один "
                    "домен должен оставаться активным.",
                    409,
                )

        if new_is_active is not None:
            row.is_active = new_is_active
        if comment_provided:
            row.comment = new_comment
        row.updated_at = datetime.now(timezone.utc)

        if is_active_changed:
            event_type = (
                "email_domain_disable" if will_disable
                else "email_domain_reactivate"
            )
        else:
            event_type = "email_domain_update"

        _record_domain_event(
            db, event_type=event_type, domain_row=row,
            actor_id=actor_id, actor_role=actor_role, ip=ip, user_agent=user_agent,
        )
        db.commit()
        db.refresh(row)
        return _row_to_dict(row)
