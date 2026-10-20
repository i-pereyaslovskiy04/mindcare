"""
Pydantic-схемы модуля психолога.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class MyStudentItem(BaseModel):
    engagement_id: int
    student_id:    int
    student_uuid:  str
    full_name:     str
    email:         str
    assigned_at:   Optional[datetime] = None
    status:        str

    model_config = {"from_attributes": True}


class PaginatedMyStudentsResponse(BaseModel):
    items: list[MyStudentItem]
    total: int
    page:  int
    size:  int


class MyStudentDetail(BaseModel):
    engagement_id: int
    student_id:    int
    student_uuid:  str
    full_name:     str
    email:         str
    assigned_at:   Optional[datetime] = None
    registered_at: Optional[datetime] = None
    status:        str

    model_config = {"from_attributes": True}
