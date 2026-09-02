from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Iterable, Optional

from app.auth import storage
from app.auth.roles import effective_role

_bearer = HTTPBearer(auto_error=False)


def _user_role_names(current_user: dict) -> list[str]:
    """
    Активные роли пользователя из current_user.

    Источник истины — список `roles` (ADR-018): если ключ `roles` присутствует,
    он авторитетен, включая явный пустой `[]` (пустое membership → 403, а не
    откат на stale legacy `role`). Legacy fallback на `role` допустим ТОЛЬКО
    при полном отсутствии ключа `roles` (старый dict без multi-role поля).
    Зеркалит frontend `normalizeRoles`.
    """
    if "roles" in current_user:
        return list(current_user["roles"] or [])
    role = current_user.get("role")
    return [role] if role else []


def get_session_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> str:
    """Извлекает токен сессии из заголовка Authorization: Bearer <token>."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Необходимо войти в аккаунт",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials


def get_current_user(token: str = Depends(get_session_token)) -> dict:
    """Проверяет сессию в БД и возвращает текущего пользователя."""
    session = storage.find_session(token)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Сессия истекла. Войдите снова.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    storage.touch_session(token)  # обновляем last_active

    user = storage.find_user_by_id(session["user_id"])
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Пользователь не найден",
        )

    # Impersonation (ADR-025): единая точка, где сессия становится user dict.
    # Если сессию создал администратор «под именем» — прокидываем отметку и имя
    # админа, чтобы фронт показал баннер возврата, а /me отдал серверную правду.
    impersonator_id = session.get("impersonator_user_id")
    if impersonator_id is not None:
        admin = storage.find_user_by_id(str(impersonator_id))
        user = {
            **user,
            "impersonator_user_id": impersonator_id,
            "impersonator_name": admin["name"] if admin else None,
        }
    return user


def require_role(*roles: str):
    """
    Фабрика зависимостей: проверяет пересечение активных ролей пользователя
    с разрешёнными (ADR-018 — multi-role).

    Пользователь с несколькими ролями (например admin+supervisor+psychologist)
    проходит, если хотя бы одна его активная роль входит в allowed. Single-role
    пользователи ведут себя как раньше.
    """
    allowed = set(roles)

    def checker(current_user: dict = Depends(get_current_user)) -> dict:
        if not (set(_user_role_names(current_user)) & allowed):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Недостаточно прав для выполнения действия",
            )
        return current_user
    return checker


def resolve_role_or_403(
    current_user: dict,
    *,
    allowed: Optional[Iterable[str]] = None,
    preferred: Optional[str] = None,
) -> str:
    """
    HTTP-обёртка над effective_role: возвращает валидную acting-роль или 403.

    Используется там, где нужен HTTP-контекст (audit/policy на route-специфичных
    endpoint-ах). После успешного require_role результат не должен быть None;
    если он всё же None (нет пересечения membership с allowed) — это 403, а не
    `actor_role=None` в audit.
    """
    role = effective_role(
        _user_role_names(current_user), allowed=allowed, preferred=preferred
    )
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав для выполнения действия",
        )
    return role
