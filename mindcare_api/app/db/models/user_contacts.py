"""
Модель: контакты пользователя (ADR-032).

  UserContacts — зашифрованная коллекция ДОПОЛНИТЕЛЬНЫХ способов связи
                 владельца аккаунта (до 10: телефоны, email, мессенджеры,
                 соцсети, сайты, «другое») и счётчик версии для защиты от
                 потери правок при сохранении из двух вкладок.

Основной телефон остаётся в `users.phone` и здесь НЕ дублируется. Таблица 1:1 с
users и создаётся лишь при первом сохранении: чтение пустого списка строк не
создаёт. Удаление всех контактов строку не удаляет (зашифрованный пустой список,
версия растёт), иначе версия сбросилась бы в 0.

Отдельная таблица, а не колонки users: сущность User грузится на каждый запрос
(get_current_user), шифртекст не должен ехать вместе с ней и попадать в общие DTO.

SECURITY: contacts_enc — ТОЛЬКО Fernet `enc:v1:` (app/core/encryption.py), что
закреплено CHECK. Не логировать, не копировать в audit/data_change_log.
"""

from sqlalchemy import (
    CheckConstraint, Column, DateTime, ForeignKey, Integer, Text,
)
from sqlalchemy.sql import func

from app.db.base import Base


class UserContacts(Base):
    __tablename__ = "user_contacts"
    __table_args__ = (
        CheckConstraint(
            "contacts_enc LIKE 'enc:v1:%'", name="ck_user_contacts_enc_format",
        ),
        CheckConstraint("version >= 1", name="ck_user_contacts_version_positive"),
    )

    user_id      = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    contacts_enc = Column(Text, nullable=False)           # ТОЛЬКО enc:v1:
    version      = Column(Integer, nullable=False)
    created_at   = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at   = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
