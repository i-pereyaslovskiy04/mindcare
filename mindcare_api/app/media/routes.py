from fastapi import APIRouter, Depends, File, UploadFile

from app.auth.deps import require_role, resolve_role_or_403
from app.media import service
from app.media.schemas import MediaUploadResponse

router = APIRouter(prefix="/media", tags=["media"])

_UPLOAD_ROLES = {"admin", "supervisor", "psychologist"}


@router.post("/upload", response_model=MediaUploadResponse, status_code=201)
def upload_media(
    file: UploadFile = File(...),
    current_user: dict = Depends(require_role("admin", "supervisor", "psychologist")),
):
    """Загружает изображение (JPEG/PNG/WebP).
    Доступно admin, supervisor и psychologist (общая медиатека для контента,
    supervisor-CMS: баннеры/карточки услуг, и психодиагностики: медиа в вопросах
    своих тестов — Этап F2). Максимальный размер — настройка NEWS_IMAGE_MAX_SIZE_MB.
    Изображение автоматически ресайзится до 1920px и сохраняется как WebP.
    Возвращает uuid и url для последующего использования в статьях/новостях."""
    actor_role = resolve_role_or_403(
        current_user, allowed=_UPLOAD_ROLES, preferred="admin",
    )
    return service.upload_image(file, int(current_user["id"]), actor_role)


@router.post("/upload/av", response_model=MediaUploadResponse, status_code=201)
def upload_av(
    file: UploadFile = File(...),
    current_user: dict = Depends(require_role("admin", "supervisor", "psychologist")),
):
    """Загружает аудио/видео (для вопросов тестов).
    MP3/M4A/AAC/OGG (аудио), MP4/WebM (видео); лимит — MEDIA_AV_MAX_SIZE_MB.
    Файл сохраняется как есть (без транскодирования и извлечения длительности)."""
    actor_role = resolve_role_or_403(
        current_user, allowed=_UPLOAD_ROLES, preferred="admin",
    )
    return service.upload_av(file, int(current_user["id"]), actor_role)
