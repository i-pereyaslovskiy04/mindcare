"""
Избранные материалы (ADR-034): /api/materials/favorites*.

Любой вошедший пользователь — для себя (адресуется текущий пользователь, чужой
id не передаётся). Вне impersonation (403 до бизнес-операции, без события):
вход «под именем» не должен ни читать, ни менять личные отметки. Ответы — без
кеша. Отдельных аудит-событий нет (ADR-034).

  GET    /api/materials/favorites/ids            → {uuids, count}
  GET    /api/materials/favorites?page&size&search&category_id
                                                 → PaginatedArticlesResponse
  PUT    /api/materials/favorites/{article_uuid} → 204 (повтор — no-op);
                                                   404 — материал недоступен;
                                                   409 — достигнут предел
  DELETE /api/materials/favorites/{article_uuid} → 204 (повтор — no-op)
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse

from app.articles.schemas import PaginatedArticlesResponse
from app.auth.deps import get_current_user
from app.db.models.material_favorites import FAVORITES_LIMIT
from app.material_favorites import service
from app.material_favorites.schemas import FavoriteIdsOut
from app.material_favorites.storage import ArticleNotAvailable, FavoritesLimitReached

NO_STORE = "no-store, private"


def forbid_impersonation(current_user: dict = Depends(get_current_user)) -> None:
    if current_user.get("impersonator_user_id") is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Избранное недоступно при входе под именем пользователя",
        )


router = APIRouter(
    prefix="/materials/favorites",
    tags=["material-favorites"],
    dependencies=[Depends(forbid_impersonation)],
)


@router.get("/ids", response_model=FavoriteIdsOut)
def favorite_ids(response: Response, current_user: dict = Depends(get_current_user)):
    response.headers["Cache-Control"] = NO_STORE
    return service.favorite_ids(int(current_user["id"]))


@router.get("", response_model=PaginatedArticlesResponse)
def list_favorites(
    response: Response,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=100),
    search: Optional[str] = Query(default=None, max_length=200),
    category_id: Optional[int] = Query(default=None),
    current_user: dict = Depends(get_current_user),
):
    response.headers["Cache-Control"] = NO_STORE
    return service.list_favorites(
        int(current_user["id"]), page=page, size=size, search=search, category_id=category_id,
    )


@router.put("/{article_uuid}", status_code=status.HTTP_204_NO_CONTENT)
def add_favorite(article_uuid: UUID, current_user: dict = Depends(get_current_user)):
    try:
        service.add_favorite(int(current_user["id"]), article_uuid)
    except ArticleNotAvailable:
        return JSONResponse(
            status_code=404,
            content={"detail": "Материал недоступен", "code": "material_not_available"},
            headers={"Cache-Control": NO_STORE},
        )
    except FavoritesLimitReached:
        return JSONResponse(
            status_code=409,
            content={
                "detail": f"В избранном может быть не больше {FAVORITES_LIMIT} материалов.",
                "code": "favorites_limit",
            },
            headers={"Cache-Control": NO_STORE},
        )
    return Response(status_code=204, headers={"Cache-Control": NO_STORE})


@router.delete("/{article_uuid}", status_code=status.HTTP_204_NO_CONTENT)
def remove_favorite(article_uuid: UUID, current_user: dict = Depends(get_current_user)):
    service.remove_favorite(int(current_user["id"]), article_uuid)
    return Response(status_code=204, headers={"Cache-Control": NO_STORE})
