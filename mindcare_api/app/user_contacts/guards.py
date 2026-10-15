"""
HTTP-зависимости контактов (живут рядом с routes; service их не импортирует).

Контакты недоступны в impersonation-сессии (ADR-031): вход «под именем» не
должен обходить согласованную политику доступа ни как владелец, ни как
сотрудник. Это auth-guard до бизнес-операции — как 403 require_role, события
нет (сам вход «под именем» уже записан admin_user_impersonated).
"""
from fastapi import Depends, HTTPException, status

from app.auth.deps import get_current_user


def forbid_impersonation(current_user: dict = Depends(get_current_user)) -> None:
    if current_user.get("impersonator_user_id") is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Контакты недоступны при входе под именем пользователя",
        )
