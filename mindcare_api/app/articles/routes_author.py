"""
Свои статьи автора (ADR-034; supervisor — Дополнение 2026-10-28).

  /api/psychologist/articles*  — require_role("psychologist"): создание —
      черновик, публикует проверяющий (supervisor/admin) через
      /api/review/articles после POST /{uuid}/submit.
  /api/supervisor/articles*    — require_role("supervisor"): тот же CRUD своих
      статей, но публикует автор сам — POST /{uuid}/publish (draft /
      needs_changes → published), без очереди: как у тестов, где staff
      публикует draft напрямую. submit у супервизора нет.

Роль — по membership roles[]; только СВОИ статьи (created_by = actor; чужая или
отсутствующая — один и тот же 404). Роль события аудита — роль роутера. Вне
impersonation (403): вход «под именем» не публикует контент от чужого имени.

  GET    ""                       — свои статьи (page, size, search, status)
  GET    "/{uuid}"                — своя статья целиком (+ комментарий проверки)
  POST   ""                       — создать черновик (201)
  PATCH  "/{uuid}"                — правка; published → снимается с публикации;
                                    in_review → 409
  DELETE "/{uuid}"                — удалить (draft / needs_changes), иначе 409
  POST   "/{uuid}/submit"         — психолог: на проверку (draft / needs_changes)
  POST   "/{uuid}/publish"        — супервизор: опубликовать (draft / needs_changes)
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse

from app.articles import moderation_storage as ms
from app.articles.schemas import (
    ArticleStatus, AuthorArticleCreate, AuthorArticleRead, AuthorArticleUpdate,
    PaginatedAuthorArticlesResponse,
)
from app.auth.deps import get_current_user, require_role

STATUS_LABELS = {
    "draft": "Черновик", "in_review": "На проверке",
    "needs_changes": "На доработке", "published": "Опубликовано",
}


def forbid_impersonation(current_user: dict = Depends(get_current_user)) -> None:
    if current_user.get("impersonator_user_id") is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Материалы недоступны при входе под именем пользователя",
        )


def _meta(request: Request) -> dict:
    return {
        "ip": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
    }


def _not_found():
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Материал не найден")


def _conflict(exc: ms.ArticleStateConflict) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={
            "detail": f"Действие недоступно: материал в статусе «{STATUS_LABELS.get(exc.current_status, exc.current_status)}».",
            "code": "article_state_conflict",
            "current_status": exc.current_status,
        },
    )


def build_author_router(role: str, *, prefix: str, tags: list[str]) -> APIRouter:
    """Роутер своих статей для роли автора (psychologist / supervisor)."""
    router = APIRouter(
        prefix=prefix,
        tags=tags,
        dependencies=[Depends(require_role(role)), Depends(forbid_impersonation)],
    )

    @router.get("", response_model=PaginatedAuthorArticlesResponse)
    def list_my_articles(
        page: int = Query(default=1, ge=1),
        size: int = Query(default=20, ge=1, le=100),
        search: Optional[str] = Query(default=None, max_length=200),
        status_filter: Optional[ArticleStatus] = Query(default=None, alias="status"),
        current_user: dict = Depends(get_current_user),
    ):
        items, total = ms.list_own(
            int(current_user["id"]), page=page, size=size, search=search, status=status_filter,
        )
        return {"items": items, "total": total, "page": page, "size": size}

    @router.get("/{article_uuid}", response_model=AuthorArticleRead)
    def get_my_article(article_uuid: str, current_user: dict = Depends(get_current_user)):
        article = ms.get_own(int(current_user["id"]), article_uuid)
        if article is None:
            _not_found()
        return article

    @router.post("", response_model=AuthorArticleRead, status_code=status.HTTP_201_CREATED)
    def create_my_article(
        body: AuthorArticleCreate, request: Request, current_user: dict = Depends(get_current_user),
    ):
        title = body.title.strip()
        if not title:
            raise HTTPException(status_code=422, detail="Введите заголовок")
        data = {**body.model_dump(), "title": title}
        return ms.create_own(int(current_user["id"]), data, role=role, **_meta(request))

    @router.patch("/{article_uuid}", response_model=AuthorArticleRead)
    def update_my_article(
        article_uuid: str, body: AuthorArticleUpdate, request: Request,
        current_user: dict = Depends(get_current_user),
    ):
        data = body.model_dump(exclude_unset=True)
        if "title" in data:
            if data["title"] is None or not data["title"].strip():
                raise HTTPException(status_code=422, detail="Введите заголовок")
            data["title"] = data["title"].strip()
        try:
            return ms.update_own(
                int(current_user["id"]), article_uuid, data, role=role, **_meta(request),
            )
        except ms.ArticleNotFound:
            _not_found()
        except ms.ArticleStateConflict as exc:
            return _conflict(exc)

    @router.delete("/{article_uuid}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_my_article(
        article_uuid: str, request: Request, current_user: dict = Depends(get_current_user),
    ):
        try:
            ms.delete_own(int(current_user["id"]), article_uuid, role=role, **_meta(request))
        except ms.ArticleNotFound:
            _not_found()
        except ms.ArticleStateConflict as exc:
            return _conflict(exc)
        return Response(status_code=204)

    if role == "supervisor":
        @router.post("/{article_uuid}/publish", response_model=AuthorArticleRead)
        def publish_my_article(
            article_uuid: str, request: Request, current_user: dict = Depends(get_current_user),
        ):
            try:
                return ms.publish_own(int(current_user["id"]), article_uuid, **_meta(request))
            except ms.ArticleNotFound:
                _not_found()
            except ms.ArticleStateConflict as exc:
                return _conflict(exc)
    else:
        @router.post("/{article_uuid}/submit", response_model=AuthorArticleRead)
        def submit_my_article(
            article_uuid: str, request: Request, current_user: dict = Depends(get_current_user),
        ):
            try:
                return ms.submit_own(int(current_user["id"]), article_uuid, **_meta(request))
            except ms.ArticleNotFound:
                _not_found()
            except ms.ArticleStateConflict as exc:
                return _conflict(exc)

    return router


router = build_author_router(
    "psychologist", prefix="/psychologist/articles", tags=["psychologist-articles"],
)
supervisor_router = build_author_router(
    "supervisor", prefix="/supervisor/articles", tags=["supervisor-articles"],
)
