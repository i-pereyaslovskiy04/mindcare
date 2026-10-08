"""
Pydantic-схемы подтверждения студента ДонГУ (ADR-029).

Номер билета — СТРОКА: ведущие нули сохраняются; проверяются только trim,
обязательность, максимальная длина и отсутствие управляющих символов. Формат и
глобальная уникальность номера намеренно не проверяются (не подтверждены
организацией). Номер не возвращается ни в собственном статусе, ни в списке —
только в карточке supervisor'а (под проверкой доступа и аудитом).
"""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, field_validator

from app.student_verification.faculties import FACULTY_CODES

TICKET_NUMBER_MAX_LEN = 50
REJECTION_REASON_MAX_LEN = 1000

FacultyCode = Literal[FACULTY_CODES]          # ровно коды каталога
RequestStatus = Literal["pending", "approved", "rejected"]
MyStatus = Literal["not_submitted", "pending", "approved", "rejected"]
ListStatusFilter = Literal["pending", "approved", "rejected", "all"]


def _has_control_chars(value: str) -> bool:
    return any(ord(c) < 32 or ord(c) == 127 for c in value)


class SubmitIn(BaseModel):
    """POST /api/student-verification/me. Лишние поля (user_id и пр.) → 422."""

    model_config = ConfigDict(extra="forbid")

    faculty_code: FacultyCode
    ticket_number: str

    @field_validator("ticket_number")
    @classmethod
    def _ticket(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Укажите номер студенческого билета")
        if len(stripped) > TICKET_NUMBER_MAX_LEN:
            raise ValueError(
                "Номер студенческого билета не должен превышать "
                f"{TICKET_NUMBER_MAX_LEN} символов"
            )
        if _has_control_chars(stripped):
            raise ValueError("Номер студенческого билета содержит недопустимые символы")
        return stripped


class RejectIn(BaseModel):
    """POST …/{uuid}/reject: пояснение обязательно (trim, 1..1000)."""

    model_config = ConfigDict(extra="forbid")

    reason: str

    @field_validator("reason")
    @classmethod
    def _reason(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Укажите пояснение отказа")
        if len(stripped) > REJECTION_REASON_MAX_LEN:
            raise ValueError(
                "Пояснение отказа не должно превышать "
                f"{REJECTION_REASON_MAX_LEN} символов"
            )
        return stripped


class FacultyOut(BaseModel):
    code: str
    label: Optional[str] = None


class FacultiesOut(BaseModel):
    items: list[FacultyOut]


class MyRequestOut(BaseModel):
    uuid: str
    status: RequestStatus
    faculty: FacultyOut
    submitted_at: datetime
    reviewed_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None


class MyVerificationOut(BaseModel):
    status: MyStatus
    can_submit: bool
    current: Optional[MyRequestOut] = None


class ApplicantOut(BaseModel):
    uuid: str
    full_name: str
    email: str
    is_active: bool


class ReviewerOut(BaseModel):
    full_name: Optional[str] = None


class VerificationListItem(BaseModel):
    uuid: str
    status: RequestStatus
    faculty: FacultyOut
    submitted_at: datetime
    reviewed_at: Optional[datetime] = None
    student: ApplicantOut
    reviewer: Optional[ReviewerOut] = None


class PaginatedVerificationsOut(BaseModel):
    items: list[VerificationListItem]
    total: int
    page: int
    size: int


class HistoryItem(BaseModel):
    uuid: str
    status: RequestStatus
    faculty: FacultyOut
    submitted_at: datetime
    reviewed_at: Optional[datetime] = None


class VerificationCardOut(VerificationListItem):
    ticket_number: str
    rejection_reason: Optional[str] = None
    can_review: bool
    history: list[HistoryItem]
