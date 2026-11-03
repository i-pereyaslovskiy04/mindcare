"""
HTTP-зависимости новых маршрутов карточки клиента в модуле встреч (живут рядом
с routes; service их не импортирует).

Итог встречи и встречи клиента недоступны в impersonation-сессии (ADR-035):
вход «под именем» не должен отмечать итоги или читать встречи клиента за
психолога. Это auth-guard до бизнес-операции — как 403 require_role, события
нет (сам вход «под именем» уже записан admin_user_impersonated).
"""
from fastapi import Depends, HTTPException, status

from app.auth.deps import get_current_user


def forbid_impersonation(current_user: dict = Depends(get_current_user)) -> None:
    if current_user.get("impersonator_user_id") is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Действие недоступно при входе под именем пользователя",
        )
