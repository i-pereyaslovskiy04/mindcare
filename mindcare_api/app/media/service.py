import io
import uuid as _uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, UploadFile, status
from PIL import Image, UnidentifiedImageError

from app.media import storage

ALLOWED_MIME = frozenset({"image/jpeg", "image/png", "image/gif", "image/webp"})
MAX_BYTES = 5 * 1024 * 1024  # 5 МБ
_EXT_MAP = {
    "image/jpeg": "jpg",
    "image/png":  "png",
    "image/gif":  "gif",
    "image/webp": "webp",
}

# Соответствие PIL-форматов расширениям файлов
_PIL_EXT = {"JPEG": "jpg", "PNG": "png", "GIF": "gif", "WEBP": "webp"}

# mindcare_api/media/ — рядом с app/
_MEDIA_ROOT = Path(__file__).resolve().parent.parent.parent / "media"


def _dest(ext: str) -> tuple[Path, str]:
    """Возвращает (абсолютный путь к файлу, URL-путь для клиента)."""
    now = datetime.now(timezone.utc)
    rel = Path("uploads") / str(now.year) / f"{now.month:02d}"
    ((_MEDIA_ROOT) / rel).mkdir(parents=True, exist_ok=True)
    filename = f"{_uuid.uuid4()}.{ext}"
    abs_path = _MEDIA_ROOT / rel / filename
    url = f"/media/uploads/{now.year}/{now.month:02d}/{filename}"
    return abs_path, url


def upload_image(file: UploadFile, user_id: int) -> dict:
    if file.content_type not in ALLOWED_MIME:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Допустимые форматы: JPEG, PNG, GIF, WebP",
        )

    data = file.file.read()

    if len(data) > MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Файл не должен превышать 5 МБ",
        )

    width_px: Optional[int] = None
    height_px: Optional[int] = None
    img_ext = _EXT_MAP[file.content_type]  # fallback по MIME
    try:
        # verify() проверяет реальный формат по содержимому (не только MIME)
        img = Image.open(io.BytesIO(data))
        img.verify()
        # После verify() объект закрыт — открываем заново для размеров и формата
        img = Image.open(io.BytesIO(data))
        width_px, height_px = img.size
        if img.format and img.format in _PIL_EXT:
            img_ext = _PIL_EXT[img.format]
    except (UnidentifiedImageError, Exception):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Файл не является допустимым изображением",
        )

    ext = img_ext
    abs_path, url = _dest(ext)
    abs_path.write_bytes(data)

    record = storage.create_media_record(
        file_name=file.filename or abs_path.name,
        file_path=url,
        mime_type=file.content_type,
        file_size_bytes=len(data),
        width_px=width_px,
        height_px=height_px,
        uploaded_by=user_id,
    )
    record["url"] = url
    return record
