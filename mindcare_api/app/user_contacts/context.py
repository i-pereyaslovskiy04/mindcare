"""Проверенный actor-контекст, который route передаёт в service (без FastAPI)."""
from dataclasses import dataclass


@dataclass(frozen=True)
class OwnerContext:
    user_id: int
    role: str          # роль аудита, определённая сервером по membership


@dataclass(frozen=True)
class StaffContext:
    user_id: int
    roles: frozenset   # активные membership-роли (roles[]), не «выбранный кабинет»
