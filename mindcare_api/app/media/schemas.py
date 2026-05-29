from typing import Optional
from pydantic import BaseModel


class MediaUploadResponse(BaseModel):
    uuid: str
    url: str
    file_name: str
    mime_type: str
    file_size_bytes: int
    width_px: Optional[int] = None
    height_px: Optional[int] = None
