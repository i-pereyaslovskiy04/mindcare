"""
Модели: контент-модуль.
  Category        — иерархические категории (статьи, тесты, ресурсы)
  Article         — статьи блога
  ArticleCategory — M:N статьи ↔ категории
  News            — новости
  HelpResource    — справочник ресурсов помощи
  BannerSlide     — слайды баннера главной страницы
  ServiceCard     — карточки услуг страницы /services
  QuestionsAnswers — Q&A (вопрос студента → ответ психолога)
"""

import uuid as _uuid

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey,
    Integer, String, Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class Category(Base):
    __tablename__ = "categories"

    id            = Column(Integer, primary_key=True)
    name          = Column(String(100), nullable=False)
    slug          = Column(String(100), nullable=False, unique=True)
    parent_id     = Column(Integer, ForeignKey("categories.id", ondelete="SET NULL"))
    description   = Column(Text)
    display_order = Column(Integer, default=0)
    is_active     = Column(Boolean, default=True)
    created_at    = Column(DateTime(timezone=True), server_default=func.now())

    parent   = relationship("Category", remote_side="Category.id")
    children = relationship("Category", back_populates="parent", overlaps="parent")


class Article(Base):
    __tablename__ = "articles"

    id           = Column(Integer, primary_key=True)
    uuid         = Column(
        UUID(as_uuid=True), unique=True, nullable=False, default=_uuid.uuid4
    )
    title        = Column(String(255), nullable=False)
    slug         = Column(String(255), unique=True)
    excerpt      = Column(Text)
    content      = Column(Text)
    cover_image  = Column(Integer, ForeignKey("media_files.id", ondelete="SET NULL"))
    created_by   = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    is_published = Column(Boolean, default=False)
    published_at = Column(DateTime(timezone=True))
    created_at   = Column(DateTime(timezone=True), server_default=func.now())
    updated_at   = Column(DateTime(timezone=True), server_default=func.now())
    deleted_at   = Column(DateTime(timezone=True))

    categories = relationship(
        "ArticleCategory", back_populates="article", cascade="all, delete-orphan"
    )


class ArticleCategory(Base):
    __tablename__ = "article_categories"

    article_id  = Column(
        Integer, ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True
    )
    category_id = Column(
        Integer, ForeignKey("categories.id", ondelete="CASCADE"), primary_key=True
    )

    article  = relationship("Article", back_populates="categories")
    category = relationship("Category")


class News(Base):
    __tablename__ = "news"

    id           = Column(Integer, primary_key=True)
    uuid         = Column(
        UUID(as_uuid=True), unique=True, nullable=False, default=_uuid.uuid4
    )
    title        = Column(String(255), nullable=False)
    content      = Column(Text)
    cover_image  = Column(Integer, ForeignKey("media_files.id", ondelete="SET NULL"))
    created_by   = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    is_published = Column(Boolean, default=False)
    published_at = Column(DateTime(timezone=True))
    created_at   = Column(DateTime(timezone=True), server_default=func.now())
    updated_at   = Column(DateTime(timezone=True), server_default=func.now())
    deleted_at   = Column(DateTime(timezone=True))


class HelpResource(Base):
    __tablename__ = "help_resources"

    id            = Column(Integer, primary_key=True)
    category_id   = Column(Integer, ForeignKey("categories.id", ondelete="SET NULL"))
    name          = Column(String(255), nullable=False)
    phone         = Column(String(50))
    address       = Column(Text)
    website       = Column(String(255))
    working_hours = Column(String(255))
    display_order = Column(Integer, default=0)
    is_active     = Column(Boolean, default=True)
    created_at    = Column(DateTime(timezone=True), server_default=func.now())
    updated_at    = Column(DateTime(timezone=True), server_default=func.now())

    category = relationship("Category")


class BannerSlide(Base):
    __tablename__ = "banner_slides"

    id            = Column(Integer, primary_key=True)
    uuid          = Column(UUID(as_uuid=True), unique=True, nullable=False, default=_uuid.uuid4)
    label         = Column(String(255))
    title         = Column(String(255), nullable=False)
    highlight     = Column(String(255))
    sub           = Column(Text)
    image_id      = Column(Integer, ForeignKey("media_files.id", ondelete="SET NULL"))
    link_url      = Column(String(2048))
    # Страница, на которой показывается слайд: 'home' | 'services' | 'about' |
    # 'materials' (расширяется по мере переноса других PageHero-страниц на этот
    # же механизм — см. app/banner_slides/schemas.py::BannerPlacement).
    placement     = Column(String(50), nullable=False, server_default="home")
    display_order = Column(Integer, default=0)
    is_active     = Column(Boolean, default=True)
    created_at    = Column(DateTime(timezone=True), server_default=func.now())
    updated_at    = Column(DateTime(timezone=True), server_default=func.now())


class ServiceCard(Base):
    __tablename__ = "service_cards"

    id            = Column(Integer, primary_key=True)
    uuid          = Column(UUID(as_uuid=True), unique=True, nullable=False, default=_uuid.uuid4)
    title         = Column(String(255), nullable=False)
    description   = Column(Text, nullable=False)
    # Список пунктов-преимуществ услуги; редактируется в форме админки как
    # textarea (по строке на пункт). Единственная страница-получатель —
    # /services, поэтому, в отличие от BannerSlide, нет поля placement.
    benefits      = Column(JSONB, nullable=False, default=list)
    image_id      = Column(Integer, ForeignKey("media_files.id", ondelete="SET NULL"))
    link_url      = Column(String(2048))
    display_order = Column(Integer, default=0)
    is_active     = Column(Boolean, default=True)
    created_at    = Column(DateTime(timezone=True), server_default=func.now())
    updated_at    = Column(DateTime(timezone=True), server_default=func.now())


class Tag(Base):
    __tablename__ = "tags"

    id         = Column(Integer, primary_key=True)
    uuid       = Column(UUID(as_uuid=True), unique=True, nullable=False, default=_uuid.uuid4)
    name       = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    article_tags = relationship("ArticleTag", back_populates="tag", cascade="all, delete-orphan")
    news_tags    = relationship("NewsTag",    back_populates="tag", cascade="all, delete-orphan")
    test_tags    = relationship("TestTag",    back_populates="tag", cascade="all, delete-orphan")


class ArticleTag(Base):
    __tablename__ = "article_tags"

    article_id = Column(Integer, ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True)
    tag_id     = Column(Integer, ForeignKey("tags.id",    ondelete="CASCADE"), primary_key=True)

    article = relationship("Article")
    tag     = relationship("Tag", back_populates="article_tags")


class NewsTag(Base):
    __tablename__ = "news_tags"

    news_id = Column(Integer, ForeignKey("news.id", ondelete="CASCADE"), primary_key=True)
    tag_id  = Column(Integer, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)

    news = relationship("News")
    tag  = relationship("Tag", back_populates="news_tags")


class TestTag(Base):
    __tablename__ = "test_tags"

    test_id = Column(Integer, ForeignKey("tests.id", ondelete="CASCADE"), primary_key=True)
    tag_id  = Column(Integer, ForeignKey("tags.id",  ondelete="CASCADE"), primary_key=True)

    test = relationship("Test")
    tag  = relationship("Tag", back_populates="test_tags")


class QuestionsAnswers(Base):
    __tablename__ = "questions_answers"

    id                       = Column(Integer, primary_key=True)
    uuid                     = Column(
        UUID(as_uuid=True), unique=True, nullable=False, default=_uuid.uuid4
    )
    author_id                = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    assigned_psychologist_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL")
    )
    question_text            = Column(Text, nullable=False)
    answer_text              = Column(Text)
    status                   = Column(String(20), default="pending")     # pending / answered / closed
    visibility               = Column(String(20), default="private")     # private / public / anonymous
    display_name             = Column(String(255))
    created_at               = Column(DateTime(timezone=True), server_default=func.now())
    answered_at              = Column(DateTime(timezone=True))
    updated_at               = Column(DateTime(timezone=True), server_default=func.now())
