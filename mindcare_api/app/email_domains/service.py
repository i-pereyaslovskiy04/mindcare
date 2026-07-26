"""
Бизнес-логика allowlist почтовых доменов.

Импортирует `storage` / `policy` / `errors`. Storages НЕ импортируют этот
модуль (направление `service → storage`). Раздаёт две вещи:
  - `assert_email_domain_allowed(email)` — ранний read-check для register_init;
  - admin CRUD-обёртки (валидация домена через policy → storage).
"""

from typing import Optional

from app.email_domains import storage
from app.email_domains.errors import DomainError, EmailDomainNotAllowedError
from app.email_domains.policy import (
    extract_domain, is_valid_domain, normalize_domain,
)

_NOT_ALLOWED_MESSAGE = (
    "Регистрация доступна только для разрешённых почтовых доменов."
)
_INVALID_DOMAIN_MESSAGE = (
    "Некорректный домен. Укажите доменное имя вида example.ru без @, "
    "пробелов, протокола, порта, пути и подстановочных символов."
)


# ── Политика при создании (ранний путь) ────────────────────────────────────────

def assert_email_domain_allowed(email: str) -> None:
    """
    Ранняя проверка домена email до создания OTP/письма (register_init).

    Отдельный short read (storage.is_domain_active открывает свою сессию, без
    блокировки). Authoritative in-tx проверка выполняется отдельно внутри
    транзакции создания (storage.assert_email_domain_allowed_in_tx).
    Raises EmailDomainNotAllowedError.
    """
    domain = extract_domain(email)
    if not domain or not storage.is_domain_active(domain):
        raise EmailDomainNotAllowedError(_NOT_ALLOWED_MESSAGE)


# ── Admin CRUD ─────────────────────────────────────────────────────────────────

def list_domains() -> list[dict]:
    return storage.list_domains()


def create_domain(
    *,
    raw_domain: str,
    comment: Optional[str],
    actor_id: Optional[int],
    actor_role: Optional[str],
    ip: Optional[str],
    user_agent: Optional[str],
) -> dict:
    """
    Добавляет домен. Нормализует и валидирует (невалидный → DomainError 422).
    Уникальность (в т.ч. против отключённого) — в storage через UNIQUE (409).
    """
    domain = normalize_domain(raw_domain)
    if not is_valid_domain(domain):
        raise DomainError(_INVALID_DOMAIN_MESSAGE, 422)
    return storage.create_domain(
        domain=domain,
        comment=_clean_comment(comment),
        actor_id=actor_id,
        actor_role=actor_role,
        ip=ip,
        user_agent=user_agent,
    )


def update_domain(
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
    Disable / reactivate / update-comment. Пустой запрос (ни is_active, ни
    comment) → DomainError 422 (defense-in-depth, дублирует guard роутера).
    """
    if new_is_active is None and not comment_provided:
        raise DomainError(
            "Пустой запрос: укажите is_active и/или comment", 422
        )
    return storage.set_domain_state(
        domain_id=domain_id,
        new_is_active=new_is_active,
        comment_provided=comment_provided,
        new_comment=_clean_comment(new_comment) if comment_provided else None,
        actor_id=actor_id,
        actor_role=actor_role,
        ip=ip,
        user_agent=user_agent,
    )


def _clean_comment(comment: Optional[str]) -> Optional[str]:
    """Trim; пустая строка → None."""
    if comment is None:
        return None
    stripped = comment.strip()
    return stripped or None
