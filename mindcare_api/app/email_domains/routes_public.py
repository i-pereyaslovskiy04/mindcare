"""
Публичное чтение allowlist почтовых доменов — подсказка формы регистрации.
Префикс: /api/public/email-domains. Без авторизации.

Отдаёт ТОЛЬКО имена активных доменов: без id, комментариев, дат и отключённых
строк. Это подсказка, а не проверка: допуск решает регистрация (init — ранняя
проверка, confirm — authoritative в транзакции создания). Обычное чтение:
данные не меняются, аудит-событие не пишется.
"""

from fastapi import APIRouter, Response

from app.email_domains import service
from app.email_domains.schemas import PublicEmailDomainsRead

router = APIRouter(
    prefix="/public/email-domains",
    tags=["public: email domains"],
)


@router.get("", response_model=PublicEmailDomainsRead)
def list_public_email_domains(response: Response):
    """Активные домены регистрации по email, по возрастанию. Без auth."""
    response.headers["Cache-Control"] = "no-store"
    return {"domains": service.list_public_domains()}
