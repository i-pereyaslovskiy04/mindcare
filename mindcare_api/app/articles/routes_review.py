"""
Модерация статей психологов (ADR-034): /api/review/articles*.

require_role("admin", "supervisor") — по membership roles[]; роль аудита —
подтверждённая membership (admin предпочтительнее, как у модерации тестов).
Вне impersonation. Видны только статьи на проверке (in_review); черновики
авторов проверяющему недоступны.

  GET  ""                 — очередь: статьи на проверке (page, size)
  GET  "/pending-count"   — только число статей на проверке (бейдж меню, без
                            аудита, как у заявок подтверждения студента)
  GET  "/{uuid}"          — статья на проверке целиком (предпросмотр)
  POST "/{uuid}/publish"  — in_review → published, иначе 409
  POST "/{uuid}/return"   — in_review → needs_changes {comment?}, иначе 409;
                            комментарий хранится зашифрованным, видит автор,
                            в журнал и логи не попадает

После publish/return автор получает system-сообщение (post-commit, soft-fail;
своё решение — без уведомления), см. app/articles/notifications.py.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse

from app.articles import moderation_storage as ms
from app.articles import notifications
from app.articles.routes_author import STATUS_LABELS, forbid_impersonation
from app.articles.schemas import (
    ArticleRead, PaginatedArticlesResponse, PendingCountOut, ReviewReturnIn,
)
from app.auth.deps import get_current_user, require_role, resolve_role_or_403

router = APIRouter(
    prefix="/review/articles",
    tags=["review-articles"],
    dependencies=[Depends(require_role("admin", "supervisor")), Depends(forbid_impersonation)],
)


def _acting_role(current_user: dict) -> str:
    return resolve_role_or_403(current_user, allowed={"admin", "supervisor"}, preferred="admin")


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
            "detail": f"Материал уже не на проверке (статус «{STATUS_LABELS.get(exc.current_status, exc.current_status)}»).",
            "code": "article_state_conflict",
            "current_status": exc.current_status,
        },
    )


@router.get("", response_model=PaginatedArticlesResponse)
def review_queue(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    items, total = ms.review_list(page=page, size=size)
    return {"items": items, "total": total, "page": page, "size": size}


# Статический маршрут — ДО /{article_uuid}.
@router.get("/pending-count", response_model=PendingCountOut)
def review_pending_count(current_user: dict = Depends(get_current_user)):
    return {"count": ms.pending_count()}


@router.get("/{article_uuid}", response_model=ArticleRead)
def review_article(article_uuid: str, current_user: dict = Depends(get_current_user)):
    article = ms.review_get(article_uuid)
    if article is None:
        _not_found()
    return article


@router.post("/{article_uuid}/publish", response_model=ArticleRead)
def publish_article(
    article_uuid: str, request: Request, current_user: dict = Depends(get_current_user),
):
    role = _acting_role(current_user)
    try:
        result = ms.publish(int(current_user["id"]), role, article_uuid, **_meta(request))
    except ms.ArticleNotFound:
        _not_found()
    except ms.ArticleStateConflict as exc:
        return _conflict(exc)
    notifications.notify_author("published", result.pop("_notify", None))
    return result


@router.post("/{article_uuid}/return", response_model=ArticleRead)
def return_article(
    article_uuid: str, body: ReviewReturnIn, request: Request,
    current_user: dict = Depends(get_current_user),
):
    role = _acting_role(current_user)
    comment = (body.comment or "").strip() or None
    try:
        result = ms.return_for_changes(
            int(current_user["id"]), role, article_uuid, comment, **_meta(request),
        )
    except ms.ArticleNotFound:
        _not_found()
    except ms.ArticleStateConflict as exc:
        return _conflict(exc)
    notifications.notify_author("returned", result.pop("_notify", None))
    return result
