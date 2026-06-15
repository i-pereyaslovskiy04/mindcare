"""
Модель: документированное основание обработки персональных данных.

UserLegalBasisRecord — фиксация того, что у организации есть документированное
основание для создания учётной записи и обработки ПДн пользователя
(admin-created psychologist/supervisor/admin, bootstrap-админ, backfill).

НЕ путать с ConsentRecord:
  - consent_records       — личное согласие субъекта (студент сам принимает
                            политику при регистрации);
  - user_legal_basis_records — основание организации (трудовое, служебное,
                            договорное, приказ). Админ НЕ «соглашается за
                            пользователя» — он подтверждает наличие
                            документированного основания.

Не использовать consent_records как суррогат legal basis для психологов,
супервизоров и администраторов.
"""

from sqlalchemy import (
    BigInteger, Column, DateTime, ForeignKey,
    Integer, String, Text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.sql import func

from app.db.base import Base


class UserLegalBasisRecord(Base):
    __tablename__ = "user_legal_basis_records"

    id                   = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id              = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    # service_duty / employment / contract / administrative_order / other
    # служебные: bootstrap / role_change
    basis_type           = Column(String(50), nullable=False, index=True)
    # admin_ui / bootstrap_script / migration_backfill
    basis_source         = Column(String(50), nullable=False)
    basis_reference      = Column(String(255))   # «Приказ №…», «Договор №…»
    confirmed_by_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )
    confirmed_at         = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    ip_address           = Column(INET)
    user_agent           = Column(Text)
    comment              = Column(Text)
    record_metadata      = Column("metadata", JSONB)
