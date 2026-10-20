"""
Модели: версионируемые политики согласия и факты согласия пользователей.

Критически важно для ФЗ-152 (персональные данные):
  consents        — версии политик (privacy_policy, data_processing, test_consent)
  consent_records — факт согласия конкретного пользователя на конкретную версию
"""

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey,
    Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class Consent(Base):
    __tablename__ = "consents"
    __table_args__ = (UniqueConstraint("policy_type", "version"),)

    id           = Column(Integer, primary_key=True)
    policy_type  = Column(String(100), nullable=False)   # privacy_policy / data_processing / test_consent
    version      = Column(Integer, nullable=False, default=1)
    title        = Column(String(255), nullable=False)
    content      = Column(Text, nullable=False)
    is_mandatory = Column(Boolean, default=True)
    published_at = Column(DateTime(timezone=True))
    created_at   = Column(DateTime(timezone=True), server_default=func.now())

    records = relationship("ConsentRecord", back_populates="consent")


class ConsentRecord(Base):
    __tablename__ = "consent_records"

    id          = Column(Integer, primary_key=True)
    user_id     = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    consent_id  = Column(
        Integer, ForeignKey("consents.id", ondelete="RESTRICT"), nullable=False
    )
    accepted    = Column(Boolean, nullable=False)
    ip_address  = Column(INET)
    user_agent  = Column(Text)
    accepted_at = Column(DateTime(timezone=True), server_default=func.now())
    revoked_at  = Column(DateTime(timezone=True))

    consent = relationship("Consent", back_populates="records")
