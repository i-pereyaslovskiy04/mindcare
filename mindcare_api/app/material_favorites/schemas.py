"""Pydantic-схемы избранных материалов (ADR-034)."""
from pydantic import BaseModel


class FavoriteIdsOut(BaseModel):
    uuids: list[str]
    count: int
