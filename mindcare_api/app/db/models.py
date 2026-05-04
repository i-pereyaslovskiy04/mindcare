import uuid as _uuid

from sqlalchemy import Column, String, Integer, Boolean, DateTime, Enum, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.session import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_0900_ai_ci"}

    id                = Column(Integer, primary_key=True, autoincrement=True)
    full_name         = Column(String(255), nullable=False)
    email             = Column(String(255), nullable=False, unique=True, index=True)
    password_hash     = Column(String(255), nullable=False)
    role              = Column(Enum("student", "psychologist", "admin"), nullable=False)
    registration_date = Column(DateTime, server_default=func.now(), nullable=True)
    last_login        = Column(DateTime, nullable=True)
    is_active         = Column(Boolean, default=True)

    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_0900_ai_ci"}

    id         = Column(Integer, primary_key=True, autoincrement=True)
    token_hash = Column(String(64), nullable=False, index=True)
    user_id    = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    user = relationship("User", back_populates="refresh_tokens")


class OtpVerification(Base):
    __tablename__ = "otp_verifications"
    __table_args__ = {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_0900_ai_ci"}

    id            = Column(String(36), primary_key=True, default=lambda: str(_uuid.uuid4()))
    email         = Column(String(255), nullable=False, index=True)
    code          = Column(String(6),   nullable=False)
    name          = Column(String(255), nullable=False)
    password_hash = Column(String(255), nullable=False)
    attempts      = Column(Integer,     nullable=False, default=0)
    expires_at    = Column(DateTime,    nullable=False)
    created_at    = Column(DateTime,    nullable=False)
    last_sent_at  = Column(DateTime,    nullable=False)
