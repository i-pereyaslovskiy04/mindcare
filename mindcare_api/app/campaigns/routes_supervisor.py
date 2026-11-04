"""
Кампании в кабинете супервизора (ADR-036, этап 4). Префикс: /api/supervisor/campaigns.

Доступ (router-level): require_role("supervisor") + запрет impersonation
(403 до handler, события нет — сам вход «под именем» уже записан). Admin без
роли supervisor доступа не имеет. NoStoreRoute: no-store на любом ответе.

  GET    /tests                      — тесты для кампаний (campaign_only);
  GET    ""  ?size&before            — список (keyset, новые сверху);
  POST   ""                          — создать {title, test_uuid};
  GET    /{uuid}                     — карточка со ссылкой;
  PATCH  /{uuid}/status {status}     — закрыть / открыть (повтор — без события);
  POST   /{uuid}/rotate-link         — новая ссылка, старая перестаёт работать;
  DELETE /{uuid}                     — удалить кампанию со всеми ответами;
  GET    /{uuid}/responses ?size&after — ответы с ФИО (fail-closed аудит);
  DELETE /{uuid}/responses/{resp}    — удалить один ответ (и его согласие);
  GET    /{uuid}/results ?faculty_code&gender&validity&type
                                     — первичная обработка: баллы, уровни,
                                       типы + сводка (fail-closed аудит);
  GET    /{uuid}/export.xlsx         — выгрузка (fail-closed аудит до файла).
Сбой обязательного аудита → 503 без данных (NoStoreRoute).
"""
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from app.auth.deps import get_current_user, require_role, resolve_role_or_403
from app.campaigns import analytics, export, storage_supervisor as store
from app.campaigns.schemas_supervisor import (
    CampaignCreateIn, CampaignDetailOut, CampaignListOut, CampaignResponseListOut,
    CampaignResultsOut, CampaignStatusIn, CampaignTestOut,
)
from app.tests.profiles import ito_sobchik
from app.core.no_store_route import NoStoreRoute
from app.core.public_urls import frontend_url
from app.student_verification.faculties import faculty_label


def _forbid_impersonation(current_user: dict = Depends(get_current_user)) -> None:
    if current_user.get("impersonator_user_id") is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Кампании недоступны при входе под именем пользователя",
        )


router = APIRouter(
    prefix="/supervisor/campaigns",
    tags=["supervisor: test campaigns"],
    route_class=NoStoreRoute,
    dependencies=[
        Depends(require_role("supervisor")),
        Depends(_forbid_impersonation),
    ],
)

_NOT_FOUND = "Кампания не найдена"


def _actor(current_user: dict) -> int:
    resolve_role_or_403(current_user, allowed={"supervisor"}, preferred="supervisor")
    return int(current_user["id"])


def _client(request: Request) -> tuple:
    ip = request.client.host if request.client else None
    return ip, request.headers.get("user-agent")


def link_path(token: str) -> str:
    return f"/c/{token}"


def _detail(data: dict) -> dict:
    token = data.pop("link_token")
    path = link_path(token)
    return {**data, "link_token": token, "link_path": path,
            "link_url": frontend_url(path)}


def _not_found():
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)


@router.get("/tests", response_model=list[CampaignTestOut])
def list_tests():
    return store.list_campaign_tests()


@router.get("", response_model=CampaignListOut)
def list_campaigns(size: int = Query(default=20, ge=1, le=100),
                   before: Optional[str] = Query(default=None, max_length=64)):
    try:
        data = store.list_campaigns(size=size, before=before)
    except store.NotFound:
        raise _not_found()
    return {"items": [_detail(i) for i in data["items"]], "has_more": data["has_more"]}


@router.post("", response_model=CampaignDetailOut, status_code=status.HTTP_201_CREATED)
def create_campaign(body: CampaignCreateIn, request: Request,
                    current_user: dict = Depends(get_current_user)):
    ip, ua = _client(request)
    try:
        data = store.create_campaign(title=body.title, test_uuid=body.test_uuid,
                                     actor_id=_actor(current_user), ip=ip,
                                     user_agent=ua)
    except store.TestNotAllowed:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="Этот тест нельзя использовать в кампании")
    return _detail(data)


@router.get("/{campaign_uuid}", response_model=CampaignDetailOut)
def get_campaign(campaign_uuid: str):
    try:
        return _detail(store.get_campaign(campaign_uuid))
    except store.NotFound:
        raise _not_found()


@router.patch("/{campaign_uuid}/status", response_model=CampaignDetailOut)
def set_status(campaign_uuid: str, body: CampaignStatusIn, request: Request,
               current_user: dict = Depends(get_current_user)):
    ip, ua = _client(request)
    try:
        return _detail(store.set_status(campaign_uuid, target=body.status,
                                        actor_id=_actor(current_user), ip=ip,
                                        user_agent=ua))
    except store.NotFound:
        raise _not_found()


@router.post("/{campaign_uuid}/rotate-link", response_model=CampaignDetailOut)
def rotate_link(campaign_uuid: str, request: Request,
                current_user: dict = Depends(get_current_user)):
    ip, ua = _client(request)
    try:
        return _detail(store.rotate_link(campaign_uuid, actor_id=_actor(current_user),
                                         ip=ip, user_agent=ua))
    except store.NotFound:
        raise _not_found()


@router.delete("/{campaign_uuid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_campaign(campaign_uuid: str, request: Request,
                    current_user: dict = Depends(get_current_user)):
    ip, ua = _client(request)
    try:
        store.delete_campaign(campaign_uuid, actor_id=_actor(current_user),
                              ip=ip, user_agent=ua)
    except store.NotFound:
        raise _not_found()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{campaign_uuid}/responses", response_model=CampaignResponseListOut)
def list_responses(campaign_uuid: str, request: Request,
                   size: int = Query(default=50, ge=1, le=200),
                   after: Optional[str] = Query(default=None, max_length=64),
                   current_user: dict = Depends(get_current_user)):
    ip, ua = _client(request)
    try:
        data = store.list_responses(campaign_uuid, size=size, after=after,
                                    actor_id=_actor(current_user), ip=ip,
                                    user_agent=ua)
    except store.NotFound:
        raise _not_found()
    for item in data["items"]:
        item["faculty_label"] = faculty_label(item["faculty_code"])
    return data


@router.delete("/{campaign_uuid}/responses/{response_uuid}",
               status_code=status.HTTP_204_NO_CONTENT)
def delete_response(campaign_uuid: str, response_uuid: str, request: Request,
                    current_user: dict = Depends(get_current_user)):
    ip, ua = _client(request)
    try:
        store.delete_response(campaign_uuid, response_uuid,
                              actor_id=_actor(current_user), ip=ip, user_agent=ua)
    except store.NotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Ответ не найден")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{campaign_uuid}/results", response_model=CampaignResultsOut)
def get_results(
    campaign_uuid: str,
    request: Request,
    faculty_code: Optional[str] = Query(default=None, max_length=64),
    gender: Optional[Literal["male", "female"]] = Query(default=None),
    validity: Optional[Literal["valid", "invalid"]] = Query(default=None),
    type_name: Optional[str] = Query(default=None, alias="type", max_length=200),
    current_user: dict = Depends(get_current_user),
):
    """Первичная обработка: баллы, уровни, достоверность и типы каждого
    участника (с ФИО) + сводка по отфильтрованному набору. Фильтры —
    на сервере. Аудит campaign_results_read — до отдачи (fail-closed)."""
    ip, ua = _client(request)
    try:
        data = store.results_data(campaign_uuid, actor_id=_actor(current_user),
                                  ip=ip, user_agent=ua)
    except store.NotFound:
        raise _not_found()
    profile = data["profile"]
    enriched = [analytics.enrich_row(r, profile) for r in data["rows"]]
    rows = analytics.filter_rows(enriched, faculty_code=faculty_code, gender=gender,
                                 validity=validity, type_name=type_name)
    scales = analytics.scale_order(profile, enriched)
    is_ito = profile == ito_sobchik.PROFILE
    return {
        "profile": profile,
        "scales": [{"code": s, "label": ito_sobchik.SCALE_LABELS.get(s, s)}
                   for s in scales],
        "level_labels": dict(analytics.LEVEL_LABELS) if is_ito else {},
        "type_names": [name for name, _ in ito_sobchik.TYPES] if is_ito else [],
        "faculties": [{"code": g["code"], "label": g["label"]}
                      for g in analytics.summarize(enriched, profile)["by_faculty"]],
        "total_all": len(enriched),
        "items": [{
            **{k: r[k] for k in ("uuid", "full_name", "faculty_code", "specialty",
                                 "age", "gender", "submitted_at", "scores",
                                 "levels", "is_valid", "types")},
            "faculty_label": faculty_label(r["faculty_code"]),
        } for r in rows],
        "summary": analytics.summarize(rows, profile),
    }


@router.get("/{campaign_uuid}/export.xlsx")
def export_xlsx(campaign_uuid: str, request: Request,
                current_user: dict = Depends(get_current_user)):
    ip, ua = _client(request)
    try:
        data = store.export_data(campaign_uuid, actor_id=_actor(current_user),
                                 ip=ip, user_agent=ua)
    except store.NotFound:
        raise _not_found()
    content = export.build_workbook(profile=data["profile"], rows=data["rows"],
                                    question_numbers=data["question_numbers"])
    filename = f"campaign_{data['campaign_uuid'][:8]}.xlsx"
    return Response(
        content=content, media_type=export.XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
