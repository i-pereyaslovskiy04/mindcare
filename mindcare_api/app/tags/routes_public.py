from fastapi import APIRouter, Query
from typing import Optional

from app.tags import service

router = APIRouter(prefix="/tags", tags=["tags"])


@router.get("/")
def list_tags_public(
    search: Optional[str] = Query(default=None, max_length=100),
    limit:  int = Query(default=20, ge=1, le=100),
):
    """
    Публичный список тегов для autocomplete в редакторе контента.
    Не требует авторизации. Возвращает только uuid и name.
    """
    return service.get_tags_public(search=search, limit=limit)
