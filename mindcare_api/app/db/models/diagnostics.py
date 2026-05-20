"""
Модели: психодиагностика.
  Test / Question / Option  — структура теста
  TestResult / StudentAnswer — результаты прохождения
  TestResultScale           — шкалы результата (для многошкальных тестов)
"""

import uuid as _uuid

from sqlalchemy import (
    ARRAY, Boolean, Column, DateTime, ForeignKey,
    Integer, String, Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class Test(Base):
    __tablename__ = "tests"

    id             = Column(Integer, primary_key=True)
    uuid           = Column(
        UUID(as_uuid=True), unique=True, nullable=False, default=_uuid.uuid4
    )
    title          = Column(String(255), nullable=False)
    description    = Column(Text)
    version        = Column(Integer, default=1)
    scoring        = Column(String(20), default="sum")   # sum / average / scale
    max_score      = Column(Integer)
    time_limit_min = Column(Integer)
    created_by     = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    is_active      = Column(Boolean, default=True)
    created_at     = Column(DateTime(timezone=True), server_default=func.now())
    updated_at     = Column(DateTime(timezone=True), server_default=func.now())
    deleted_at     = Column(DateTime(timezone=True))

    questions  = relationship(
        "Question", back_populates="test", cascade="all, delete-orphan"
    )
    categories = relationship(
        "TestCategory", back_populates="test", cascade="all, delete-orphan"
    )


class TestCategory(Base):
    __tablename__ = "test_categories"

    test_id     = Column(
        Integer, ForeignKey("tests.id", ondelete="CASCADE"), primary_key=True
    )
    category_id = Column(
        Integer, ForeignKey("categories.id", ondelete="CASCADE"), primary_key=True
    )

    test     = relationship("Test", back_populates="categories")
    category = relationship("Category")


class Question(Base):
    __tablename__ = "questions"

    id             = Column(Integer, primary_key=True)
    test_id        = Column(
        Integer, ForeignKey("tests.id", ondelete="CASCADE"), nullable=False
    )
    question_text  = Column(Text, nullable=False)
    question_order = Column(Integer, nullable=False)
    question_type  = Column(String(20), default="single_choice")
    is_required    = Column(Boolean, default=True)
    config         = Column(JSONB, default=dict)
    created_at     = Column(DateTime(timezone=True), server_default=func.now())
    updated_at     = Column(DateTime(timezone=True), server_default=func.now())

    test    = relationship("Test", back_populates="questions")
    options = relationship(
        "Option", back_populates="question", cascade="all, delete-orphan"
    )
    media   = relationship(
        "QuestionMedia", back_populates="question", cascade="all, delete-orphan"
    )


class Option(Base):
    __tablename__ = "options"

    id           = Column(Integer, primary_key=True)
    question_id  = Column(
        Integer, ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )
    option_text  = Column(Text, nullable=False)
    option_order = Column(Integer, nullable=False)
    value_score  = Column(Integer, default=0)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())

    question = relationship("Question", back_populates="options")
    media    = relationship(
        "OptionMedia", back_populates="option", cascade="all, delete-orphan"
    )


class QuestionMedia(Base):
    __tablename__ = "question_media"

    id            = Column(Integer, primary_key=True)
    question_id   = Column(
        Integer, ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )
    media_id      = Column(
        Integer, ForeignKey("media_files.id", ondelete="CASCADE"), nullable=False
    )
    media_role    = Column(String(20), default="main")
    display_order = Column(Integer, default=1)
    caption       = Column(Text)

    question = relationship("Question", back_populates="media")
    media    = relationship("MediaFile")


class OptionMedia(Base):
    __tablename__ = "option_media"

    id            = Column(Integer, primary_key=True)
    option_id     = Column(
        Integer, ForeignKey("options.id", ondelete="CASCADE"), nullable=False
    )
    media_id      = Column(
        Integer, ForeignKey("media_files.id", ondelete="CASCADE"), nullable=False
    )
    media_role    = Column(String(20), default="icon")
    display_order = Column(Integer, default=1)

    option = relationship("Option", back_populates="media")
    media  = relationship("MediaFile")


class TestResult(Base):
    __tablename__ = "test_results"

    id              = Column(Integer, primary_key=True)
    uuid            = Column(
        UUID(as_uuid=True), unique=True, nullable=False, default=_uuid.uuid4
    )
    user_id         = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    test_id         = Column(
        Integer, ForeignKey("tests.id", ondelete="RESTRICT"), nullable=False
    )
    test_version    = Column(Integer, nullable=False)
    total_score     = Column(Integer)
    max_possible    = Column(Integer)
    scoring_used    = Column(String(20))
    recommendations = Column(Text)
    submitted_at    = Column(DateTime(timezone=True), server_default=func.now())
    created_at      = Column(DateTime(timezone=True), server_default=func.now())

    scales  = relationship(
        "TestResultScale", back_populates="test_result", cascade="all, delete-orphan"
    )
    answers = relationship(
        "StudentAnswer", back_populates="test_result", cascade="all, delete-orphan"
    )


class TestResultScale(Base):
    __tablename__ = "test_result_scales"

    id             = Column(Integer, primary_key=True)
    test_result_id = Column(
        Integer, ForeignKey("test_results.id", ondelete="CASCADE"), nullable=False
    )
    scale_name     = Column(String(100), nullable=False)
    score          = Column(Integer, nullable=False)
    max_score      = Column(Integer)
    interpretation = Column(Text)
    scale_metadata = Column("metadata", JSONB, default=dict)

    test_result = relationship("TestResult", back_populates="scales")


class StudentAnswer(Base):
    __tablename__ = "student_answers"

    id               = Column(Integer, primary_key=True)
    test_result_id   = Column(
        Integer, ForeignKey("test_results.id", ondelete="CASCADE"), nullable=False
    )
    question_id      = Column(
        Integer, ForeignKey("questions.id", ondelete="RESTRICT"), nullable=False
    )
    option_id        = Column(
        Integer, ForeignKey("options.id", ondelete="RESTRICT")
    )
    free_text_answer = Column(Text)
    scale_value      = Column(Integer)
    selected_options = Column(ARRAY(Integer))
    time_spent_sec   = Column(Integer)

    test_result = relationship("TestResult", back_populates="answers")
