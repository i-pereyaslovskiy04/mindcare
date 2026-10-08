"""
Stage 5A-2 — типизированные precommit-ошибки домена users.

Leaf-модуль: НЕ импортирует service/storage/routes (во избежание циклов). Каждый
класс несёт стабильный `audit_code` (класс-атрибут) для durable failure-аудита;
маппинг в HTTP/AuthError и failure-событие делается по ТИПУ, без строкового
анализа сообщений. Все ошибки возникают строго ДО `db.commit()` (rollback-
confirmed precommit).
"""
from __future__ import annotations


class EmailAlreadyExistsError(ValueError):
    """Email уже занят (active или soft-deleted User)."""
    audit_code = "email_already_exists"


class UserNotFoundError(ValueError):
    """Целевой пользователь не найден при admin update (precommit)."""
    audit_code = "user_not_found"


class InvalidUserRequestError(ValueError):
    """Некорректный запрос: пустой PATCH или malformed UUID (UPDATE)."""
    audit_code = "invalid_request"


class SelfLifecycleProtectedError(ValueError):
    """
    ADR-028: администратор пытается отключить (или «удалить») собственный
    аккаунт. Guard по стабильному actor_id == target_id — ДО любых мутаций.
    """
    audit_code = "self_admin_protected"


class AccountAlreadyDisabledError(ValueError):
    """ADR-028: аккаунт уже отключён (is_active=false и/или deleted_at)."""
    audit_code = "account_already_disabled"


class AccountAlreadyActiveError(ValueError):
    """ADR-028: восстанавливать нечего — аккаунт активен и не удалён."""
    audit_code = "account_already_active"


class LifecycleEndpointRequiredError(ValueError):
    """
    ADR-028: устаревший путь изменения lifecycle (DELETE / PATCH is_active)
    отклонён — только POST /deactivate (с причиной) и POST /restore.
    """
    audit_code = "lifecycle_endpoint_required"


class RoleConfigError(RuntimeError):
    """
    Отсутствует разрешённая Role в seed/БД — configuration/internal failure
    (НЕ пользовательский invalid role). Precommit.
    """
    audit_code = "internal_error"


class ActorContextError(RuntimeError):
    """
    Отсутствует authenticated actor context у admin create/update/delete —
    internal wiring-баг (не пользовательский ввод). Precommit. Подкласс
    RuntimeError → существующие `pytest.raises(RuntimeError)` остаются валидны.
    """
    audit_code = "internal_error"
