from fastapi import APIRouter, Query

from app.banner_slides import service
from app.banner_slides.schemas import BannerPlacement, PublicBannerSlideRead

router = APIRouter(prefix="/banner-slides", tags=["public: banner-slides"])


@router.get("", response_model=list[PublicBannerSlideRead])
def list_public_banner_slides(placement: BannerPlacement = Query(default="home")):
    """Активные слайды баннера страницы placement, отсортированные по
    display_order. Без auth."""
    return service.list_public_banner_slides(placement=placement)
