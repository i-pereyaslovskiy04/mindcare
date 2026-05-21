"""
Модели: медиафайлы и их версии (thumbnails, resized copies).
"""

import uuid as _uuid

from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, ForeignKey,
    Integer, String,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class MediaFile(Base):
    __tablename__ = "media_files"

    id               = Column(Integer, primary_key=True)
    uuid             = Column(
        UUID(as_uuid=True), unique=True, nullable=False, default=_uuid.uuid4
    )
    file_name        = Column(String(255), nullable=False)
    file_path        = Column(String(500), nullable=False)
    file_type        = Column(String(20), nullable=False)    # image / video / document / audio
    mime_type        = Column(String(100))
    file_size_bytes  = Column(BigInteger)
    width_px         = Column(Integer)
    height_px        = Column(Integer)
    duration_seconds = Column(Integer)
    thumbnail_path   = Column(String(500))
    file_metadata    = Column("metadata", JSONB, default=dict)
    uploaded_by      = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    is_active        = Column(Boolean, default=True)
    created_at       = Column(DateTime(timezone=True), server_default=func.now())
    deleted_at       = Column(DateTime(timezone=True))

    versions = relationship(
        "MediaVersion", back_populates="original", cascade="all, delete-orphan"
    )


class MediaVersion(Base):
    __tablename__ = "media_versions"

    id                = Column(Integer, primary_key=True)
    original_media_id = Column(
        Integer, ForeignKey("media_files.id", ondelete="CASCADE"), nullable=False
    )
    version_type      = Column(String(20), nullable=False)   # thumbnail / small / medium / large
    file_path         = Column(String(500), nullable=False)
    file_size_bytes   = Column(BigInteger)
    width_px          = Column(Integer)
    height_px         = Column(Integer)
    created_at        = Column(DateTime(timezone=True), server_default=func.now())

    original = relationship("MediaFile", back_populates="versions")
