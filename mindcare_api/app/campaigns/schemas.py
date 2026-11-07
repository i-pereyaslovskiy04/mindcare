"""
Схемы публичного API кампании (ADR-036).

GET отдаёт только то, что нужно для прохождения: тексты вопросов и вариантов
в порядке question_order / option_order. Баллы вариантов (value_score), config
и названия шкал НЕ отдаются — иначе ключ методики раскрыт.

POST строгий (extra=forbid): анкета, принятие согласия с версией, ответы.
"""
import re
import uuid as _uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.models.test_campaigns import RESPONDENT_AGE_MAX, RESPONDENT_AGE_MIN
from app.student_verification.faculties import FACULTY_CODES

MAX_ANSWERS = 500
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


def _clean_text(value: str, *, min_len: int, max_len: int) -> str:
    if not isinstance(value, str):
        raise ValueError("ожидается строка")
    if _CONTROL_RE.search(value):
        raise ValueError("недопустимые символы")
    cleaned = " ".join(value.split())
    if not (min_len <= len(cleaned) <= max_len):
        raise ValueError("недопустимая длина")
    return cleaned


# ── GET ───────────────────────────────────────────────────────────────────────

class PublicOptionRead(BaseModel):
    id: int
    text: str


class PublicQuestionRead(BaseModel):
    id: int
    number: int
    text: str
    options: list[PublicOptionRead]


class PublicConsentRead(BaseModel):
    version: int
    title: str
    content: str


class PublicFacultyRead(BaseModel):
    code: str
    label: str


class PublicCampaignRead(BaseModel):
    """При access_code_required и без верного слова — только «замок»:
    consent=None, вопросов и факультетов нет (их открывает POST /unlock)."""
    title: str
    test_title: str
    access_code_required: bool = False
    closes_at: Optional[datetime] = None
    instruction: str
    consent: Optional[PublicConsentRead]
    faculties: list[PublicFacultyRead]
    questions: list[PublicQuestionRead]


class CampaignUnlockIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    access_code: str = Field(min_length=1, max_length=200)


# ── POST ──────────────────────────────────────────────────────────────────────

class CampaignAnswerIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: int = Field(strict=True, ge=1)
    option_id: int = Field(strict=True, ge=1)


class CampaignSubmitIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    submission_key: _uuid.UUID
    full_name: str
    faculty_code: str
    specialty: str
    age: int = Field(strict=True, ge=RESPONDENT_AGE_MIN, le=RESPONDENT_AGE_MAX)
    gender: Literal["male", "female"]
    consent_accepted: Literal[True]
    consent_version: int = Field(strict=True, ge=1)
    answers: list[CampaignAnswerIn] = Field(min_length=1, max_length=MAX_ANSWERS)
    # Кодовое слово ссылки (если задано супервизором); не хранится и не логируется.
    access_code: Optional[str] = Field(default=None, max_length=200)

    @field_validator("full_name")
    @classmethod
    def _full_name(cls, v: str) -> str:
        return _clean_text(v, min_len=2, max_len=255)

    @field_validator("specialty")
    @classmethod
    def _specialty(cls, v: str) -> str:
        return _clean_text(v, min_len=2, max_len=255)

    @field_validator("faculty_code")
    @classmethod
    def _faculty(cls, v: str) -> str:
        if v not in FACULTY_CODES:
            raise ValueError("неизвестный факультет")
        return v


class CampaignSubmitOut(BaseModel):
    status: Literal["accepted"] = "accepted"
