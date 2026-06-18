from datetime import date
from typing import List, Optional

from pydantic import BaseModel, field_validator


class EmotionRead(BaseModel):
    key:        str
    label:      str
    sort_order: int

    model_config = {"from_attributes": True}


class DiaryEntryWrite(BaseModel):
    mood_score: int
    entry_text: Optional[str] = ""
    emotions:   List[str]     = []

    @field_validator("mood_score")
    @classmethod
    def validate_mood_score(cls, v: int) -> int:
        if not 1 <= v <= 10:
            raise ValueError("mood_score должен быть от 1 до 10")
        return v

    @field_validator("emotions")
    @classmethod
    def deduplicate_emotions(cls, v: List[str]) -> List[str]:
        seen: set = set()
        result: List[str] = []
        for key in v:
            if key not in seen:
                seen.add(key)
                result.append(key)
        return result


class DiaryEntryRead(BaseModel):
    entry_date: date
    mood_score: Optional[int]
    entry_text: str
    emotions:   List[str]


class DiaryEntryListItem(BaseModel):
    uuid:       str
    entry_date: date
    mood_score: int
    entry_text: str
    emotions:   List[str]
    created_at: str
    updated_at: str


class PaginatedEntriesResponse(BaseModel):
    items:  List[DiaryEntryListItem]
    total:  int
    limit:  int
    offset: int


class SummaryPoint(BaseModel):
    date:       date
    label:      str
    mood_score: Optional[int]


class DiarySummaryRead(BaseModel):
    period:        str
    entries_count: int
    points:        List[SummaryPoint]
