"""
Модель: избранные материалы пользователя (ADR-034).

  MaterialFavorite — отметка «в избранном» для опубликованной статьи
                     библиотеки. Одна строка на пару (пользователь, статья);
                     повторное добавление — no-op.

Содержимого не хранит — только связи и время добавления (порядок списка).
Удаление пользователя или статьи (физическое) удаляет отметки каскадом;
снятая с публикации или мягко удалённая статья в избранном не показывается,
но отметка сохраняется и вернётся при повторной публикации.
"""
from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, PrimaryKeyConstraint
from sqlalchemy.sql import func

from app.db.base import Base

# Потолок отметок на пользователя (защита списка «моё избранное» от разрастания).
FAVORITES_LIMIT = 500


class MaterialFavorite(Base):
    __tablename__ = "material_favorites"
    __table_args__ = (
        PrimaryKeyConstraint("user_id", "article_id", name="material_favorites_pkey"),
        # Список «моё избранное» — новые сначала.
        Index("ix_material_favorites_user_created", "user_id", "created_at"),
        # Каскад при удалении статьи.
        Index("ix_material_favorites_article_id", "article_id"),
    )

    user_id    = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    article_id = Column(Integer, ForeignKey("articles.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
