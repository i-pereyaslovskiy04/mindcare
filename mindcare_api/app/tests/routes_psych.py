"""
Psychologist-scoped роуты психодиагностики (Этап F, ADR-016).

Психолог создаёт и редактирует ТОЛЬКО свои тесты (tests.created_by == actor_id).
Правка (PATCH) допустима в draft/needs_changes/published (Этап F2.1) — правка
published-теста атомарно снимает его с публикации (status → draft) и требует
повторной отправки на модерацию; удаление (DELETE) остаётся ограничено
draft/needs_changes. in_review для обоих действий заблокирован — решение уже не
за автором, пока идёт проверка. Публикация/возврат на доработку по-прежнему
доступны только admin/supervisor (routes_admin.py). Владение и статус-гейт
проверяются в service (`_own_updatable_test`/`_own_editable_test`) — router-уровень
require_role("psychologist") гарантирует только роль, не авторство конкретного
теста; чужой тест → 404 («чужого неотличимо от несуществующего», как
session_notes), не редактируемый в данный момент статус → 409.

Дублирование (Этап F2.2) — БЕЗ ограничения по статусу источника (read-only
копирование, оригинал не мутируется): психолог может форкнуть свой тест в
ЛЮБОМ статусе, включая published/in_review, не трогая исходный. Копия всегда
draft, принадлежит тому же психологу (`service.duplicate_my_test`, тот же
storage.duplicate_test, что у admin/supervisor).

analyze/preview-score продублированы здесь (не в routes_admin.py): они чистые
stateless-вычисления без ownership-семантики, но router-level dependencies
routes_admin.py нельзя ослабить по одному роуту — проще и безопаснее дать
психологу собственный путь к тем же service.analyze_test/preview_score.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.auth.deps import require_role, resolve_role_or_403
from app.tests import service
from app.tests.service import TestHasResults, TestNotEditable, TestTransitionError, TestTransitionForbidden
from app.tests.schemas import (
    TestCreate,
    TestUpdate,
    TestRead,
    TestAnalyzeIn,
    TestAnalysisRead,
    TestPreviewScoreIn,
    TestPreviewScoreRead,
    PaginatedTestsResponse,
)

router = APIRouter(
    prefix="/psychologist/tests",
    tags=["psychologist-tests"],
    dependencies=[Depends(require_role("psychologist"))],
)


def _client(request: Request) -> tuple[Optional[str], Optional[str]]:
    ip = request.client.host if request.client else None
    return ip, request.headers.get("user-agent")


def _acting_role(current_user: dict) -> str:
    return resolve_role_or_403(
        current_user, allowed={"psychologist"}, preferred="psychologist",
    )


# ── analyze/preview-score — объявлены ДО /{uuid}-маршрутов (см. docstring) ────

@router.post("/analyze", response_model=TestAnalysisRead)
def analyze_test(
    body: TestAnalyzeIn,
    current_user: dict = Depends(require_role("psychologist")),
):
    """Анализ несохранённого дерева — тот же расчёт, что в admin-конструкторе.
    Stateless, ничего не сохраняет и не завязано на владение тестом."""
    return service.analyze_test(body.model_dump())


@router.post("/preview-score", response_model=TestPreviewScoreRead)
def preview_score(
    body: TestPreviewScoreIn,
    current_user: dict = Depends(require_role("psychologist")),
):
    """Пробный подсчёт несохранённого дерева. Ничего не сохраняет."""
    return service.preview_score(body.model_dump())


# ── CRUD своих тестов ───────────────────────────────────────────────────────

@router.get("", response_model=PaginatedTestsResponse)
def list_my_tests(
    page:    int           = Query(default=1, ge=1),
    size:    int            = Query(default=20, ge=1, le=100),
    search:  Optional[str]  = Query(default=None),
    status_: Optional[str]  = Query(default=None, alias="status"),
    current_user: dict = Depends(require_role("psychologist")),
):
    """Только свои тесты. status не передан → ВСЕ статусы — автор видит текущее
    состояние каждого."""
    items, total = service.list_my_tests(
        author_id=int(current_user["id"]), page=page, size=size,
        search=search, status=status_,
    )
    return {"items": items, "total": total, "page": page, "size": size}


@router.get("/{uuid}", response_model=TestRead)
def get_my_test(
    uuid: str,
    current_user: dict = Depends(require_role("psychologist")),
):
    try:
        return service.get_my_test(uuid, author_id=int(current_user["id"]))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post("", response_model=TestRead, status_code=status.HTTP_201_CREATED)
def create_my_test(
    body: TestCreate,
    request: Request,
    current_user: dict = Depends(require_role("psychologist")),
):
    """Создаёт тест ВСЕГДА как draft — присланный body.status игнорируется
    (публикует только admin/supervisor, ADR-016)."""
    ip, ua = _client(request)
    try:
        return service.create_my_test(
            body.model_dump(),
            created_by=int(current_user["id"]),
            actor_role=_acting_role(current_user),
            ip=ip, user_agent=ua,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )


@router.patch("/{uuid}", response_model=TestRead)
def update_my_test(
    uuid: str,
    body: TestUpdate,
    request: Request,
    current_user: dict = Depends(require_role("psychologist")),
):
    """Правка своего теста — draft/needs_changes/published (F2.1: правка
    published снимает его с публикации, см. service.update_my_test)."""
    ip, ua = _client(request)
    try:
        return service.update_my_test(
            uuid, body.model_dump(exclude_unset=True),
            actor_id=int(current_user["id"]),
            actor_role=_acting_role(current_user),
            ip=ip, user_agent=ua,
        )
    except TestNotEditable as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except TestHasResults as exc:
        # Достижимо для published с результатами: вопросы менять нельзя (FK из
        # student_answers), метаданные/интерпретацию — можно. storage.update_test
        # остаётся источником истины.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except ValueError as exc:
        msg = str(exc)
        code = (
            status.HTTP_404_NOT_FOUND if "не найден" in msg
            else status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        raise HTTPException(status_code=code, detail=msg)


@router.post("/{uuid}/duplicate", response_model=TestRead, status_code=status.HTTP_201_CREATED)
def duplicate_my_test(
    uuid: str,
    request: Request,
    current_user: dict = Depends(require_role("psychologist")),
):
    """Дублирует СВОЙ тест (Этап F2.2) — любой статус источника, включая
    published/in_review (read-only копирование, оригинал не меняется). Копия —
    независимый черновик. Чужой тест → 404."""
    ip, ua = _client(request)
    try:
        return service.duplicate_my_test(
            uuid,
            actor_id=int(current_user["id"]),
            actor_role=_acting_role(current_user),
            ip=ip, user_agent=ua,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.delete("/{uuid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_my_test(
    uuid: str,
    request: Request,
    current_user: dict = Depends(require_role("psychologist")),
):
    """Удаляет свой тест — только пока draft/needs_changes."""
    ip, ua = _client(request)
    try:
        service.delete_my_test(
            uuid,
            actor_id=int(current_user["id"]),
            actor_role=_acting_role(current_user),
            ip=ip, user_agent=ua,
        )
    except TestNotEditable as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


# ── moderation: отправка на модерацию ──────────────────────────────────────

@router.post("/{uuid}/submit-for-review", response_model=TestRead)
def submit_for_review(
    uuid: str,
    request: Request,
    current_user: dict = Depends(require_role("psychologist")),
):
    """Автор отправляет свой draft/needs_changes тест на модерацию (in_review).
    Чужой тест → 403 (TestTransitionForbidden); нелегальный переход состояния
    (напр. уже published) → 409 (TestTransitionError)."""
    ip, ua = _client(request)
    try:
        return service.submit_for_review(
            uuid,
            actor_id=int(current_user["id"]),
            actor_role=_acting_role(current_user),
            ip=ip, user_agent=ua,
        )
    except TestTransitionForbidden as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except TestTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
