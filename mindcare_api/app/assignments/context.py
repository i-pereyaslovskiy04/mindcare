"""Проверенный actor-контекст, который route передаёт в service (без FastAPI)."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ClientContext:
    """Владелец заданий: membership-роль student подтверждена require_role."""
    user_id: int


@dataclass(frozen=True)
class PsychologistContext:
    """Автор заданий: membership-роль psychologist подтверждена require_role."""
    user_id: int
