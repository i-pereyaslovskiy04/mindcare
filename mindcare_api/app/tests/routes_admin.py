from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.exc import IntegrityError

from app.auth.deps import require_role, resolve_role_or_403
from app.tests import service
from app.tests.service import TestHasResults, TestTransitionError, TestTransitionForbidden
from app.tests.schemas import (
    TestCreate,
    TestUpdate,
    TestRead,
    TestAnalyzeIn,
    TestAnalysisRead,
    TestPreviewScoreIn,
    TestPreviewScoreRead,
    TestReturnIn,
    PaginatedTestsResponse,
)

router = APIRouter(
    prefix="/admin/tests",
    tags=["admin-tests"],
    dependencies=[Depends(require_role("admin", "supervisor"))],
)


def _client(request: Request) -> tuple[Optional[str], Optional[str]]:
    ip = request.client.host if request.client else None
    return ip, request.headers.get("user-agent")


def _acting_role(current_user: dict) -> str:
    # test CRUD доступен admin И supervisor; preferred=admin детерминирует
    # выбор для dual-role пользователя (ROLE_PRIORITY: admin выше supervisor).
    return resolve_role_or_403(
        current_user, allowed={"admin", "supervisor"}, preferred="admin",
    )


@router.get("", response_model=PaginatedTestsResponse)
def list_tests(
    page:      int            = Query(default=1, ge=1),
    size:      int            = Query(default=20, ge=1, le=100),
    search:    Optional[str]  = Query(default=None),
    is_active: Optional[bool] = Query(default=None),
    status_:   Optional[str]  = Query(default=None, alias="status"),
    current_user: dict = Depends(require_role("admin", "supervisor")),
):
    # status не передан → ВСЕ статусы (иначе мигрированные в draft тесты
    # пропали бы из вида админа после деплоя Этапа F).
    items, total = service.list_tests(
        page=page, size=size, search=search, is_active=is_active, status=status_,
    )
    return {"items": items, "total": total, "page": page, "size": size}


@router.post("/analyze", response_model=TestAnalysisRead)
def analyze_test(
    body: TestAnalyzeIn,
    current_user: dict = Depends(require_role("admin", "supervisor")),
):
    """
    Анализ несохранённого дерева: достижимый диапазон баллов и проблемы порогов
    (дыры в покрытии, недостижимые пороги, ссылки на несуществующие шкалы).

    Ничего не сохраняет. Нужен, чтобы конструктор показывал предупреждения, не
    дублируя scoring в JS: подсчёт остаётся единственным на бэке.

    Объявлен ДО `/{uuid}`-маршрутов намеренно — иначе FastAPI примет `analyze`
    за uuid теста.
    """
    return service.analyze_test(body.model_dump())


@router.post("/preview-score", response_model=TestPreviewScoreRead)
def preview_score(
    body: TestPreviewScoreIn,
    current_user: dict = Depends(require_role("admin", "supervisor")),
):
    """
    Пробный подсчёт несохранённого дерева: автор проверяет, какой балл и какую
    расшифровку получит студент, не публикуя методику. Ничего не сохраняет.

    Объявлен ДО `/{uuid}`-маршрутов намеренно (см. analyze_test).
    """
    return service.preview_score(body.model_dump())


@router.get("/{uuid}", response_model=TestRead)
def get_test(
    uuid: str,
    current_user: dict = Depends(require_role("admin", "supervisor")),
):
    test = service.get_test(uuid)
    if not test:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Тест не найден")
    return test


@router.post("", response_model=TestRead, status_code=status.HTTP_201_CREATED)
def create_test(
    body: TestCreate,
    request: Request,
    current_user: dict = Depends(require_role("admin", "supervisor")),
):
    ip, ua = _client(request)
    try:
        test = service.create_test(
            body.model_dump(),
            created_by=int(current_user["id"]),
            actor_role=_acting_role(current_user),
            ip=ip,
            user_agent=ua,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )
    return test


@router.patch("/{uuid}", response_model=TestRead)
def update_test(
    uuid: str,
    body: TestUpdate,
    request: Request,
    current_user: dict = Depends(require_role("admin", "supervisor")),
):
    ip, ua = _client(request)
    try:
        test = service.update_test(
            uuid, body.model_dump(exclude_unset=True),
            actor_id=int(current_user["id"]),
            actor_role=_acting_role(current_user),
            ip=ip,
            user_agent=ua,
        )
    except TestHasResults as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except IntegrityError:
        # defense-in-depth: между проверкой has_results и заменой вопросов мог
        # появиться результат — FK student_answers→questions (RESTRICT) не даст
        # удалить вопросы, и это тот же случай, что TestHasResults.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "По этому тесту уже есть результаты — его вопросы изменить "
                "нельзя. Создайте копию методики и правьте её."
            ),
        )
    except ValueError as exc:
        msg = str(exc)
        code = (
            status.HTTP_404_NOT_FOUND
            if "не найден" in msg
            else status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        raise HTTPException(status_code=code, detail=msg)
    return test


@router.post("/{uuid}/duplicate", response_model=TestRead, status_code=status.HTTP_201_CREATED)
def duplicate_test(
    uuid: str,
    request: Request,
    current_user: dict = Depends(require_role("admin", "supervisor")),
):
    """
    Копия методики как черновик (is_active=false). Штатный путь правки теста,
    по которому уже есть результаты: опубликованный инструмент не меняют,
    публикуют новую редакцию.
    """
    ip, ua = _client(request)
    try:
        test = service.duplicate_test(
            uuid,
            created_by=int(current_user["id"]),
            actor_role=_acting_role(current_user),
            ip=ip,
            user_agent=ua,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return test


@router.delete("/{uuid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_test(
    uuid: str,
    request: Request,
    current_user: dict = Depends(require_role("admin", "supervisor")),
):
    ip, ua = _client(request)
    try:
        service.delete_test(
            uuid,
            actor_id=int(current_user["id"]),
            actor_role=_acting_role(current_user),
            ip=ip,
            user_agent=ua,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


# ── moderation workflow (Этап F, ADR-016) ──────────────────────────────────────
# Не литеральные сегменты на месте {uuid} — shadowing с /analyze, /preview-score
# не грозит (та защита нужна только для литералов, совпадающих по позиции с uuid).

@router.post("/{uuid}/publish", response_model=TestRead)
def publish_test(
    uuid: str,
    request: Request,
    current_user: dict = Depends(require_role("admin", "supervisor")),
):
    """admin/supervisor публикуют тест (из draft/in_review/needs_changes)."""
    ip, ua = _client(request)
    try:
        return service.publish_test(
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


@router.post("/{uuid}/return", response_model=TestRead)
def return_test(
    uuid: str,
    body: TestReturnIn,
    request: Request,
    current_user: dict = Depends(require_role("admin", "supervisor")),
):
    """admin/supervisor возвращают тест на доработку (только из in_review).
    body.reason не логируется (audit metadata пустая — свободный текст)."""
    ip, ua = _client(request)
    try:
        return service.return_for_changes(
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
