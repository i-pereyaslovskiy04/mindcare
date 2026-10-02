"""
Типизированные ошибки social login (Stage Social Auth 2B).

Модуль-лист: не импортирует service/storage/routes. audit_code — стабильный
failure_reason_code для failed_login (registry), внешний код — фиксированный
контракт для фронтенда; сообщения не содержат ПДн/секретов/текста провайдера.
"""
from typing import Optional


class OAuthProviderUnavailableError(Exception):
    """Провайдер не зарегистрирован/неактивен → 404 oauth_provider_unavailable."""


class OAuthTicketInvalidError(Exception):
    """Ticket невалиден: не найден, истёк, уже использован или не того kind.
    Наружу причины не различаются."""
    audit_code = "oauth_ticket_invalid"


class OAuthLoginDenied(Exception):
    """
    Доменный отказ входа через провайдера (заблокирован, удалён, нет ролей,
    не чистый студент, identity удалена/переназначена).

    В complete_login_atomic ловится ВНУТРИ транзакции: списание ticket
    коммитится (ticket сожжён навсегда), сессия не создаётся, затем
    исключение пробрасывается дальше.
    """

    def __init__(self, audit_code: str, provider: Optional[str] = None):
        super().__init__(audit_code)
        self.audit_code = audit_code
        # Провайдер списанного ticket (для auth_log.auth_method) — проставляет
        # storage.complete_login_atomic из строки ticket, не из запроса.
        self.provider = provider

    @property
    def external_code(self) -> str:
        if self.audit_code == "social_login_not_allowed":
            return "social_login_not_allowed"
        return "account_unavailable"
