from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class SessionNoteCreate(BaseModel):
    appointment_id:        Optional[int]  = None
    engagement_id:         Optional[int]  = None
    note_type:             Literal["general", "diagnosis", "plan", "followup"] = "general"
    content:               str            = Field(min_length=1, max_length=50000)
    is_shared_with_client: bool           = False


class SessionNoteUpdate(BaseModel):
    note_type:             Optional[Literal["general", "diagnosis", "plan", "followup"]] = None
    content:               Optional[str]  = Field(default=None, min_length=1, max_length=50000)
    is_shared_with_client: Optional[bool] = None


class SessionNoteRead(BaseModel):
    id:                    int
    uuid:                  str
    appointment_id:        Optional[int]
    engagement_id:         Optional[int]
    author_id:             int
    note_type:             str
    content:               str
    is_shared_with_client: bool
    version:               int
    created_at:            datetime
    updated_at:            datetime

    model_config = {"from_attributes": True}


class PaginatedNotesResponse(BaseModel):
    items: list[SessionNoteRead]
    total: int
    page:  int
    size:  int
