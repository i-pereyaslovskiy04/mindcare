import io
import uuid as _uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from PIL import Image, UnidentifiedImageError

from app.audit import Actor, Outcome, Target, record_event
from app.core.config import settings
from app.media import storage

ALLOWED_MIME = frozenset({"image/jpeg", "image/png", "image/webp"})
MAX_BYTES = settings.NEWS_IMAGE_MAX_SIZE_MB * 1024 * 1024
MAX_WIDTH_PX = 1920

# Аудио/видео: без Pillow/транскодирования, сохраняем как есть. Длительность не
# извлекаем (нет системных зависимостей) — плеер в браузере покажет её сам.
AV_ALLOWED_MIME = {
    "audio/mpeg": "mp3",
    "audio/mp4":  "m4a",
    "audio/aac":  "aac",
    "audio/ogg":  "ogg",
    "video/mp4":  "mp4",
    "video/webm": "webm",
}
AV_MAX_BYTES = settings.MEDIA_AV_MAX_SIZE_MB * 1024 * 1024

# mindcare_api/media/ — рядом с app/
_MEDIA_ROOT = Path(__file__).resolve().parent.parent.parent / "media"


def _dest(ext: str) -> tuple[Path, str]:
    """Возвращает (абсолютный путь к файлу, URL-путь для клиента)."""
    now = datetime.now(timezone.utc)
    rel = Path("uploads") / str(now.year) / f"{now.month:02d}"
    (_MEDIA_ROOT / rel).mkdir(parents=True, exist_ok=True)
    filename = f"{_uuid.uuid4()}.{ext}"
    abs_path = _MEDIA_ROOT / rel / filename
    url = f"/media/uploads/{now.year}/{now.month:02d}/{filename}"
    return abs_path, url


def upload_image(file: UploadFile, user_id: int, actor_role: str) -> dict:
    if file.content_type not in ALLOWED_MIME:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Допустимые форматы: JPEG, PNG, WebP",
        )

    data = file.file.read()

    if len(data) > MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Файл не должен превышать {settings.NEWS_IMAGE_MAX_SIZE_MB} МБ",
        )

    try:
        # verify() проверяет реальный формат по содержимому (не только MIME)
        img = Image.open(io.BytesIO(data))
        img.verify()
        # После verify() объект закрыт — открываем заново
        img = Image.open(io.BytesIO(data))
    except (UnidentifiedImageError, Exception):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Файл не является допустимым изображением",
        )

    # Ресайз: уменьшить до MAX_WIDTH_PX с сохранением пропорций
    if img.width > MAX_WIDTH_PX:
        ratio = MAX_WIDTH_PX / img.width
        img = img.resize(
            (MAX_WIDTH_PX, round(img.height * ratio)),
            Image.LANCZOS,
        )

    # Нормализация режима для WebP
    if img.mode == "P" and "transparency" in img.info:
        img = img.convert("RGBA")
    elif img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")

    # Сохранение оптимизированной версии как WebP
    output = io.BytesIO()
    img.save(output, format="WEBP", quality=85, method=4)
    optimized = output.getvalue()
    width_px, height_px = img.size

    abs_path, url = _dest("webp")
    abs_path.write_bytes(optimized)

    record = storage.create_media_record(
        file_name=abs_path.name,
        file_path=url,
        mime_type="image/webp",
        file_size_bytes=len(optimized),
        width_px=width_px,
        height_px=height_px,
        uploaded_by=user_id,
    )
    record["url"] = url

    # Audit soft-fail: сбой не ломает загрузку (у записи свой commit выше).
    # Target — внутренний media_files.id; metadata только нечувствительное.
    record_event(
        event="media_uploaded",
        actor=Actor.user(user_id, actor_role),
        target=Target("media_file", record["id"]),
        outcome=Outcome.SUCCESS,
        metadata={
            "file_type": "image",
            "mime_type": record["mime_type"],
            "file_size": record["file_size_bytes"],
        },
        context=None,
        db=None,
    )
    return record


def upload_av(file: UploadFile, user_id: int, actor_role: str) -> dict:
    """Загрузка аудио/видео для вопросов тестов. Файл сохраняется как есть."""
    ext = AV_ALLOWED_MIME.get(file.content_type)
    if ext is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Допустимые форматы: MP3, M4A, AAC, OGG (аудио); MP4, WebM (видео)",
        )

    data = file.file.read()
    if len(data) > AV_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Файл не должен превышать {settings.MEDIA_AV_MAX_SIZE_MB} МБ",
        )

    kind = "video" if file.content_type.startswith("video/") else "audio"
    abs_path, url = _dest(ext)
    abs_path.write_bytes(data)

    record = storage.create_media_record(
        file_name=abs_path.name,
        file_path=url,
        mime_type=file.content_type,
        file_size_bytes=len(data),
        width_px=None,
        height_px=None,
        uploaded_by=user_id,
        file_type=kind,
    )
    record["url"] = url

    record_event(
        event="media_uploaded",
        actor=Actor.user(user_id, actor_role),
        target=Target("media_file", record["id"]),
        outcome=Outcome.SUCCESS,
        metadata={
            "file_type": kind,
            "mime_type": record["mime_type"],
            "file_size": record["file_size_bytes"],
        },
        context=None,
        db=None,
    )
    return record
