"""Схемы кабинета супервизора для кампаний (ADR-036, этап 4)."""
import re
import uuid as _uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


class CampaignTestOut(BaseModel):
    uuid: str
    title: str


def _clean_title(v: str) -> str:
    if _CONTROL_RE.search(v):
        raise ValueError("недопустимые символы")
    cleaned = " ".join(v.split())
    if not (2 <= len(cleaned) <= 255):
        raise ValueError("недопустимая длина")
    return cleaned


class CampaignCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    test_uuid: _uuid.UUID

    @field_validator("title")
    @classmethod
    def _title(cls, v: str) -> str:
        return _clean_title(v)


class CampaignRenameIn(BaseModel):
    """Переименование: меняется только название, адрес ссылки — нет."""
    model_config = ConfigDict(extra="forbid")

    title: str

    @field_validator("title")
    @classmethod
    def _title(cls, v: str) -> str:
        return _clean_title(v)


class CampaignStatusIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["open", "closed"]


class CampaignScheduleIn(BaseModel):
    """Сроки ссылки; null — без ограничения. Время — с часовым поясом."""
    model_config = ConfigDict(extra="forbid")

    opens_at: Optional[datetime]
    closes_at: Optional[datetime]

    @model_validator(mode="after")
    def _order(self):
        for value in (self.opens_at, self.closes_at):
            if value is not None and value.tzinfo is None:
                raise ValueError("время указывается с часовым поясом")
        if self.opens_at and self.closes_at and self.opens_at >= self.closes_at:
            raise ValueError("начало должно быть раньше окончания")
        return self


class CampaignAccessCodeIn(BaseModel):
    """Кодовое слово: 4–64 символа после схлопывания пробелов (app/campaigns/access.py)."""
    model_config = ConfigDict(extra="forbid")

    access_code: str = Field(min_length=1, max_length=200)


class CampaignOut(BaseModel):
    uuid: str
    title: str
    status: Literal["open", "closed"]
    test_title: Optional[str]
    test_uuid: Optional[str]
    responses_count: int
    created_at: datetime
    closed_at: Optional[datetime]
    opens_at: Optional[datetime] = None
    closes_at: Optional[datetime] = None
    access_code_set: bool = False
    link_state: Literal["open", "scheduled", "expired", "closed"] = "open"


class CampaignDetailOut(CampaignOut):
    link_token: str
    link_path: str
    link_url: Optional[str]   # None — FRONTEND_PUBLIC_URL не задан


class CampaignListOut(BaseModel):
    items: list[CampaignDetailOut]
    has_more: bool


class CampaignResponseOut(BaseModel):
    uuid: str
    full_name: str
    faculty_code: str
    faculty_label: Optional[str]
    specialty: str
    age: int
    gender: Literal["male", "female"]
    submitted_at: datetime


class CampaignResponseListOut(BaseModel):
    items: list[CampaignResponseOut]
    has_more: bool


# ── результаты (первичная обработка) ─────────────────────────────────────────

class ResultScaleOut(BaseModel):
    code: str
    label: str


class ResultRowOut(BaseModel):
    uuid: str
    full_name: str
    faculty_code: str
    faculty_label: Optional[str]
    specialty: str
    age: int
    gender: Literal["male", "female"]
    submitted_at: datetime
    scores: dict[str, int]
    levels: dict[str, Optional[str]]
    is_valid: Optional[bool]
    types: list[str]


class ScaleStatOut(BaseModel):
    scale: str
    label: str
    mean: Optional[float]
    min: Optional[int]
    max: Optional[int]
    levels: dict[str, int]


class TypeStatOut(BaseModel):
    name: str
    count: int
    invalid: int


class GroupStatOut(BaseModel):
    code: str
    label: str
    count: int
    valid: int
    with_type: int
    means: dict[str, Optional[float]]


class ResultsSummaryOut(BaseModel):
    total: int
    valid: Optional[int]
    invalid: Optional[int]
    with_type: int
    scales: list[ScaleStatOut]
    types: list[TypeStatOut]
    by_faculty: list[GroupStatOut]
    by_gender: list[GroupStatOut]


class ResultLevelOut(BaseModel):
    code: str
    label: str
    min: int
    max: int
    tone: Literal["low", "norm", "accent", "maladaptive"]


class CampaignResultsOut(BaseModel):
    # ADR-037: что считается — из правил теста кампании.
    has_rules: bool
    has_validity: bool
    scales: list[ResultScaleOut]
    levels: list[ResultLevelOut]          # по возрастанию, с оттенком для UI
    level_labels: dict[str, str]
    scale_levels: dict[str, list[ResultLevelOut]] = {}   # свои уровни шкал
    validity_title: str                   # «Недостоверных (L или F > 5)»
    type_threshold: Optional[int]
    type_names: list[str]
    faculties: list[ResultScaleOut]   # факультеты всех участников (для фильтра)
    total_all: int
    items: list[ResultRowOut]
    summary: ResultsSummaryOut
