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


class OAuthRegistrationError(Exception):
    """
    Отказ регистрации через провайдера (Stage Social Auth 4): init или confirm.

    code        — стабильный внешний код в теле ответа ({detail, code});
    message     — фиксированный текст для пользователя (без ПДн и SQL);
    status_code — 400/409/422/429/500, никогда 401;
    audit_code  — failure_reason_code для `registration_failed` (None — отказ не
                  аудируется: шаг init, как и у регистрации по паролю);
    provider    — провайдер ticket (для auth_log.auth_method), только из БД;
    email       — email из ticket (для auth_log.user_email).

    Доменный отказ НЕ означает «неверный код»: технический сбой сюда не
    заворачивается и уходит как есть (500).
    """

    def __init__(
        self, code: str, message: str, status_code: int, *,
        audit_code: Optional[str] = None,
        provider: Optional[str] = None,
        email: Optional[str] = None,
    ):
        super().__init__(code)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.audit_code = audit_code
        self.provider = provider
        self.email = email


# ── фиксированные тексты и фабрики отказов регистрации ───────────────────────

EMAIL_EXISTS_MESSAGE = (
    "Аккаунт с таким email уже существует. Войдите по email и паролю."
)
IDENTITY_LINKED_MESSAGE = (
    "Этот внешний аккаунт уже привязан к MindCare. Начните вход заново."
)
REGISTRATION_INTERNAL_MESSAGE = (
    "Не удалось завершить регистрацию. Обратитесь в поддержку."
)


def email_exists_error(provider=None, email=None, *, audited=False):
    """Один и тот же отказ для активного и soft-deleted аккаунта: состояние,
    роли и привязки существующего аккаунта не раскрываются."""
    return OAuthRegistrationError(
        "email_already_exists", EMAIL_EXISTS_MESSAGE, 409,
        audit_code="email_already_exists" if audited else None,
        provider=provider, email=email,
    )


def identity_linked_error(provider=None, email=None, *, audited=False):
    return OAuthRegistrationError(
        "oauth_identity_already_linked", IDENTITY_LINKED_MESSAGE, 409,
        audit_code="oauth_identity_already_linked" if audited else None,
        provider=provider, email=email,
    )
