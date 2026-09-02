import uuid as _uuid
from typing import Optional

from app.db.session import SessionLocal
from app.db.models import MediaFile


def create_media_record(
    *,
    file_name: str,
    file_path: str,
    mime_type: str,
    file_size_bytes: int,
    width_px: Optional[int],
    height_px: Optional[int],
    uploaded_by: int,
    file_type: str = "image",
    duration_seconds: Optional[int] = None,
    thumbnail_path: Optional[str] = None,
) -> dict:
    with SessionLocal() as db:
        media = MediaFile(
            file_name=file_name,
            file_path=file_path,
            file_type=file_type,
            mime_type=mime_type,
            file_size_bytes=file_size_bytes,
            width_px=width_px,
            height_px=height_px,
            duration_seconds=duration_seconds,
            thumbnail_path=thumbnail_path,
            uploaded_by=uploaded_by,
        )
        db.add(media)
        db.commit()
        db.refresh(media)
        return {
            "id":              media.id,
            "uuid":            str(media.uuid),
            "file_name":       media.file_name,
            "file_path":       media.file_path,
            "file_type":       media.file_type,
            "mime_type":       media.mime_type,
            "file_size_bytes": media.file_size_bytes,
            "width_px":        media.width_px,
            "height_px":       media.height_px,
        }


def get_media_by_uuid(uuid_str: str) -> Optional[dict]:
    """Возвращает запись медиафайла по UUID или None."""
    try:
        uuid_obj = _uuid.UUID(uuid_str)
    except ValueError:
        return None

    with SessionLocal() as db:
        media = (
            db.query(MediaFile)
            .filter(MediaFile.uuid == uuid_obj, MediaFile.is_active.is_(True))
            .first()
        )
        if not media:
            return None
        return {
            "id":        media.id,
            "uuid":      str(media.uuid),
            "file_path": media.file_path,
            "mime_type": media.mime_type,
        }
