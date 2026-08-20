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


class ProfileActorContextError(RuntimeError):
    """
    Stage 5A-2: отсутствует authenticated actor context при self-profile update
    (internal wiring-баг, precommit). Подкласс RuntimeError → существующие
    `pytest.raises(RuntimeError)` остаются валидны. Несёт стабильный audit_code
    для durable failure-аудита; общий RuntimeError им НЕ подменяется.
    """
    audit_code = "internal_error"
