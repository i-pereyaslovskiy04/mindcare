"""
Типизированные доменные отказы подтверждения студента (ADR-029).

code — стабильный машинный код: уходит клиенту в теле ответа ({detail, code})
и в failure_reason_code соответствующего *_failed события. message — текст для
пользователя (без ПДн). Ошибки поднимаются ДО commit: транзакция откатывается,
failure-аудит route пишет уже после отката.
"""


class VerificationStorageError(RuntimeError):
    """
    Технический сбой записи (flush / UPDATE / outbox / commit) — НЕ доменный
    отказ: не подкласс VerificationError, route его не ловит (→ 500) и
    failure-аудит (*_failed) не пишет. Создаётся ВНЕ блока except и
    поднимается `from None`: исходная SQLAlchemy-ошибка (SQL, параметры с
    ciphertext номера/пояснения) не попадает ни в __cause__, ни в __context__,
    ни в ASGI traceback. Текст фиксированный, без деталей.
    """

    def __init__(self):
        super().__init__("student verification storage failure")


class VerificationError(Exception):
    code: str = "internal_error"
    status_code: int = 500
    message: str = "Не удалось выполнить операцию"

    def __init__(self, message: str | None = None):
        if message is not None:
            self.message = message
        super().__init__(self.code)


# ── self-service (student) ───────────────────────────────────────────────────

class VerificationNotAllowed(VerificationError):
    code = "verification_not_allowed"
    status_code = 403
    message = (
        "Подтверждение статуса студента доступно только пользователю "
        "без служебных ролей."
    )


class ImpersonationForbidden(VerificationError):
    code = "impersonation_forbidden"
    status_code = 403
    message = "Действие недоступно при входе под именем пользователя."


class VerificationPendingExists(VerificationError):
    code = "verification_pending_exists"
    status_code = 409
    message = "Заявка уже отправлена и находится на проверке."


class AlreadyVerified(VerificationError):
    code = "already_verified"
    status_code = 409
    message = "Статус студента ДонГУ уже подтверждён."


class AccountInactive(VerificationError):
    code = "account_inactive"
    status_code = 409
    message = "Аккаунт отключён."


# ── проверка (supervisor) ─────────────────────────────────────────────────────

class VerificationNotFound(VerificationError):
    code = "verification_not_found"
    status_code = 404
    message = "Заявка не найдена."


class SelfReviewForbidden(VerificationError):
    code = "self_review_forbidden"
    status_code = 403
    message = "Нельзя проверять собственную заявку."


class ReviewerNotAllowed(VerificationError):
    code = "reviewer_not_allowed"
    status_code = 403
    message = "Недостаточно прав для проверки заявок."


class VerificationAlreadyDecided(VerificationError):
    code = "verification_already_decided"
    status_code = 409
    message = "По заявке уже принято другое решение."
