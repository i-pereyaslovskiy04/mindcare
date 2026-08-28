from fastapi import APIRouter

from app.service_cards import service
from app.service_cards.schemas import PublicServiceCardRead

router = APIRouter(prefix="/service-cards", tags=["public: service-cards"])


@router.get("", response_model=list[PublicServiceCardRead])
def list_public_service_cards():
    """Активные карточки услуг, отсортированные по display_order. Без auth."""
    return service.list_public_service_cards()
