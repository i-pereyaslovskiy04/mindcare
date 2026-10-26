"""
Stage 4B-1 — лёгкие типизированные внутренние ошибки auth.

Модуль-лист: НЕ импортирует service/storage/routes (во избежание циклов). Позволяет
маппить OTP-сбои в стабильные audit_code по ТИПУ исключения, без строкового матчинга
русских сообщений. Оба типа — подклассы ValueError, поэтому существующие
`except ValueError` и тесты `pytest.raises(ValueError)` остаются совместимыми.
"""
from __future__ import annotations


class OtpInvalidError(ValueError):
    """OTP не найден / использован / неверный код / исчерпаны попытки."""


class OtpExpiredError(ValueError):
    """Срок действия OTP истёк."""


class OtpAttemptsExhaustedError(OtpInvalidError):
    """Попытки ввода кода исчерпаны: запись OTP удалена, нужен новый код."""


class RegistrationReferenceInvalidError(OtpInvalidError):
    """
    registration_reference (otp_verifications.id из ссылки в письме) не
    указывает на действующий выпуск кода обычной регистрации: неизвестен,
    уже использован, заменён новым выпуском или это запись другого потока
    (reset / регистрация через провайдера).
    """


class RegistrationEmailTakenError(Exception):
    """
    Выпуск кода регистрации: email уже принадлежит строке users (проверка под
    lock выпуска). Не ValueError — не смешивается с отказом по cooldown.
    """


class ProfileActorContextError(RuntimeError):
    """
    Stage 5A-2: отсутствует authenticated actor context при self-profile update
    (internal wiring-баг, precommit). Подкласс RuntimeError → существующие
    `pytest.raises(RuntimeError)` остаются валидны. Несёт стабильный audit_code
    для durable failure-аудита; общий RuntimeError им НЕ подменяется.
    """
    audit_code = "internal_error"
