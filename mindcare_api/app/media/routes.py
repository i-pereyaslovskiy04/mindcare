from fastapi import APIRouter, Depends, File, UploadFile

from app.auth.deps import require_role
from app.media import service
from app.media.schemas import MediaUploadResponse

router = APIRouter(prefix="/media", tags=["media"])


@router.post("/upload", response_model=MediaUploadResponse, status_code=201)
def upload_media(
    file: UploadFile = File(...),
    current_user: dict = Depends(require_role("admin", "supervisor")),
):
    """Загружает изображение (JPEG/PNG/WebP).
    Максимальный размер задаётся настройкой NEWS_IMAGE_MAX_SIZE_MB.
    Изображение автоматически ресайзится до 1920px и сохраняется как WebP.
    Возвращает uuid и url для последующего использования в статьях/новостях."""
    return service.upload_image(file, current_user["id"])
