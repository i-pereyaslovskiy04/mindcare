from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import JSONResponse, Response
from sqlalchemy.exc import IntegrityError

from app.auth.deps import require_role, resolve_role_or_403
from app.tests import service
from app.tests.guards import forbid_impersonation
from app.tests.service import (
    TestHasResults, TestStateChanged, TestTransitionError, TestTransitionForbidden,
)
from app.tests.schemas import (
    TestTextsIn,
    TestCreate,
    TestUpdate,
    TestRead,
    TestAnalyzeIn,
    TestAnalysisRead,
    TestPreviewScoreIn,
    TestPreviewScoreRead,
    TestDecisionIn,
    TestReturnIn,
    TestPendingCountOut,
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


# Литерал — ДО `/{uuid}` (иначе «pending-count» попал бы в get_test).
@router.get("/pending-count", response_model=TestPendingCountOut)
def pending_review_count(
    current_user: dict = Depends(require_role("admin", "supervisor")),
):
    """Число тестов на модерации — бейдж меню проверяющего (без аудита)."""
    return {"count": service.pending_review_count()}


# ── ADR-037: шаблон xlsx, выгрузка и импорт методики ─────────────────────────
# Объявлены ДО /{uuid}: иначе FastAPI примет «methodology-template.xlsx» за uuid.

def _xlsx(content: bytes, filename_ascii: str, filename_utf8: str) -> Response:
    from urllib.parse import quote
    from app.tests.methodology_xlsx import XLSX_MEDIA_TYPE
    return Response(content=content, media_type=XLSX_MEDIA_TYPE, headers={
        "Content-Disposition": (f'attachment; filename="{filename_ascii}"; '
                                f"filename*=UTF-8''{quote(filename_utf8)}"),
        "Cache-Control": "no-store, private",
    })


def _read_upload(file: UploadFile) -> bytes:
    from app.tests.methodology_xlsx import MAX_BYTES
    content = file.file.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail="Файл больше 2 МБ")
    return content


def _import(content: bytes, dry_run: bool, *, actor_id: int, actor_role: str, ip, ua):
    from app.tests.methodology_xlsx import ImportFileInvalid
    try:
        if dry_run:
            return service.import_preview(content)
        created, report = service.import_methodology(
            content, created_by=actor_id, actor_role=actor_role, ip=ip, user_agent=ua)
    except ImportFileInvalid as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    if created is None:
        return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            content={"detail": "Файл содержит ошибки", **report})
    return JSONResponse(status_code=status.HTTP_201_CREATED,
                        content={**report, "test_uuid": created["uuid"]})


def _export(test: dict) -> Response:
    from app.tests.methodology_xlsx import NotRepresentable
    try:
        content = service.export_methodology(test)
    except NotRepresentable as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return _xlsx(content, "methodology.xlsx", f"Методика_{test['title'][:80]}.xlsx")


@router.get("/methodology-template.xlsx")
def methodology_template(current_user: dict = Depends(require_role("admin", "supervisor"))):
    """Пустой шаблон методики (без ПДн, без аудита)."""
    return _xlsx(service.methodology_template(), "methodology-template.xlsx",
                 "Шаблон_методики.xlsx")


@router.post("/import")
def import_methodology(
    request: Request,
    file: UploadFile = File(...),
    dry_run: bool = Query(default=False),
    current_user: dict = Depends(require_role("admin", "supervisor")),
):
    """dry_run=true — проверка без сохранения: {ok, errors[{sheet,row,column,
    message}], warnings, summary}. Иначе — черновик (201, test_uuid) или 422 с
    тем же отчётом. Файл не сохраняется и не логируется."""
    ip, ua = _client(request)
    return _import(_read_upload(file), dry_run, actor_id=int(current_user["id"]),
                   actor_role=_acting_role(current_user), ip=ip, ua=ua)


@router.get("/{uuid}/methodology.xlsx")
def export_methodology(uuid: str,
                       current_user: dict = Depends(require_role("admin", "supervisor"))):
    test = service.get_test(uuid)
    if not test:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Тест не найден")
    return _export(test)


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
    except TestHasResults as exc:   # TestUsedByCampaigns (ADR-037)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


# ── moderation workflow (Этап F, ADR-016) ──────────────────────────────────────
# Не литеральные сегменты на месте {uuid} — shadowing с /analyze, /preview-score
# не грозит (та защита нужна только для литералов, совпадающих по позиции с uuid).

def _state_changed(exc: TestStateChanged) -> JSONResponse:
    """Решение принято по устаревшему состоянию (или повтор уже принятого):
    без изменений, без success-события и уведомления. current_status позволяет
    UI отличить повтор того же решения от конфликта."""
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            "detail": "Состояние теста изменилось. Обновите список и проверьте тест снова.",
            "code": "test_state_changed",
            "current_status": exc.current_status,
        },
    )


@router.post(
    "/{uuid}/publish", response_model=TestRead,
    dependencies=[Depends(forbid_impersonation)],
)
def publish_test(
    uuid: str,
    body: TestDecisionIn,
    request: Request,
    current_user: dict = Depends(require_role("admin", "supervisor")),
):
    """admin/supervisor публикуют тест (из draft/in_review/needs_changes).
    Тело — состояние, которое видел проверяющий (expected_status +
    expected_updated_at); иное под блокировкой → 409 test_state_changed."""
    ip, ua = _client(request)
    try:
        return service.publish_test(
            uuid,
            actor_id=int(current_user["id"]),
            actor_role=_acting_role(current_user),
            expected_status=body.expected_status,
            expected_updated_at=body.expected_updated_at,
            ip=ip, user_agent=ua,
        )
    except TestStateChanged as exc:
        return _state_changed(exc)
    except TestTransitionForbidden as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except TestTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except service.RulesNotReady as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post(
    "/{uuid}/return", response_model=TestRead,
    dependencies=[Depends(forbid_impersonation)],
)
def return_test(
    uuid: str,
    body: TestReturnIn,
    request: Request,
    current_user: dict = Depends(require_role("admin", "supervisor")),
):
    """admin/supervisor возвращают тест на доработку (только из in_review).
    body.reason не логируется (audit metadata пустая — свободный текст); он
    передаётся автору только в зашифрованном system-сообщении. Ожидаемое
    состояние — как у публикации."""
    ip, ua = _client(request)
    try:
        return service.return_for_changes(
            uuid,
            actor_id=int(current_user["id"]),
            actor_role=_acting_role(current_user),
            expected_status=body.expected_status,
            expected_updated_at=body.expected_updated_at,
            reason=body.reason,
            ip=ip, user_agent=ua,
        )
    except TestStateChanged as exc:
        return _state_changed(exc)
    except TestTransitionForbidden as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except TestTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except service.RulesNotReady as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


# ── ADR-037: версии методики и исправление текстов ───────────────────────────

@router.post("/{uuid}/new-version", response_model=TestRead,
             status_code=status.HTTP_201_CREATED)
def create_new_version(
    uuid: str,
    request: Request,
    current_user: dict = Depends(require_role("admin", "supervisor")),
):
    """Новая версия методики — черновик с тем же lineage; прежние версии,
    результаты и кампании не меняются. Неопубликованная версия уже есть → 409."""
    ip, ua = _client(request)
    try:
        return service.create_new_version(
            uuid, actor_id=int(current_user["id"]),
            actor_role=_acting_role(current_user), ip=ip, user_agent=ua)
    except service.DraftVersionExists as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.patch("/{uuid}/texts", response_model=TestRead)
def correct_texts(
    uuid: str,
    body: TestTextsIn,
    request: Request,
    current_user: dict = Depends(require_role("admin", "supervisor")),
):
    """Опечатки в текстах вопросов, вариантов и инструкции — в любом статусе и
    при наличии результатов. Состав и баллы не меняются."""
    ip, ua = _client(request)
    try:
        return service.correct_texts(
            uuid, body.model_dump(exclude_unset=True),
            actor_id=int(current_user["id"]),
            actor_role=_acting_role(current_user), ip=ip, user_agent=ua)
    except TestStateChanged as exc:
        return _state_changed(exc)
    except service.TextsStructureChanged as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
