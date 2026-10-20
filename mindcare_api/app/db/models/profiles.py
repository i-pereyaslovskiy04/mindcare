"""
Модели: профили студентов, психологов, экстренные контакты.
"""

from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey,
    Integer, String, Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class StudentProfile(Base):
    __tablename__ = "student_profiles"

    id          = Column(Integer, primary_key=True)
    user_id     = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, unique=True,
    )
    study_group = Column(String(50))
    study_year  = Column(Integer)
    faculty     = Column(String(255))
    birth_date  = Column(Date)
    gender      = Column(String(20))
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="student_profile")


class PsychologistProfile(Base):
    __tablename__ = "psychologist_profiles"

    id               = Column(Integer, primary_key=True)
    user_id          = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, unique=True,
    )
    specialization   = Column(String(255))
    bio              = Column(Text)
    experience_years = Column(Integer)
    education        = Column(Text)
    is_accepting     = Column(Boolean, default=True)
    created_at       = Column(DateTime(timezone=True), server_default=func.now())
    updated_at       = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="psychologist_profile")


class EmergencyContact(Base):
    __tablename__ = "emergency_contacts"

    id          = Column(Integer, primary_key=True)
    user_id     = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    contact_name = Column(String(255), nullable=False)
    # Атрибут contact_rel → колонка "relationship" (зарезервировано в SQLAlchemy)
    contact_rel  = Column("relationship", String(100))
    phone        = Column(String(50), nullable=False)
    email        = Column(String(255))
    is_primary   = Column(Boolean, default=False)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="emergency_contacts")
