"""
Кампании в кабинете супервизора (ADR-036, этап 4). Префикс: /api/supervisor/campaigns.

Доступ (router-level): require_role("supervisor"). Вход администратора «под
именем» супервизора разрешён (дополнение 2026-11-05): актор событий —
супервизор, в metadata — impersonator_user_id. Admin без роли supervisor
доступа не имеет. NoStoreRoute: no-store на любом ответе.

  GET    /tests                      — тесты для кампаний (campaign_only);
  GET    ""  ?size&before            — список (keyset, новые сверху);
  POST   ""                          — создать {title, test_uuid};
  GET    /{uuid}                     — карточка со ссылкой;
  PATCH  /{uuid} {title}             — переименовать (адрес ссылки не меняется;
                                       то же название — без события);
  PATCH  /{uuid}/status {status}     — закрыть / открыть (повтор — без события);
  PATCH  /{uuid}/schedule {opens_at, closes_at}
                                     — сроки ссылки (null — без ограничения;
                                       те же — без события);
  PUT    /{uuid}/access-code {access_code}
                                     — задать/сменить кодовое слово (хранится
                                       только bcrypt; слово больше не показывается);
  DELETE /{uuid}/access-code         — снять слово (не было — без события);
  POST   /{uuid}/rotate-link         — новая ссылка, старая перестаёт работать;
  DELETE /{uuid}                     — удалить кампанию со всеми ответами;
  GET    /{uuid}/responses ?size&after — ответы с ФИО (fail-closed аудит);
  DELETE /{uuid}/responses/{resp}    — удалить один ответ (и его согласие);
  GET    /{uuid}/results ?faculty_code&gender&validity&type
                                     — первичная обработка: баллы, уровни,
                                       типы + сводка (fail-closed аудит);
  GET    /{uuid}/statistics ?те же фильтры
                                     — статистика без ФИО: по дням, по вопросам,
                                       распределение баллов; меньше 5 участников —
                                       без распределений (аудит как у results);
  GET    /{uuid}/export.xlsx         — выгрузка (fail-closed аудит до файла).
Сбой обязательного аудита → 503 без данных (NoStoreRoute).
"""
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from app.auth.deps import get_current_user, require_role, resolve_role_or_403
from app.campaigns import access, analytics, export, storage_supervisor as store
from app.campaigns.schemas_supervisor import (
    CampaignAccessCodeIn, CampaignScheduleIn,
    CampaignCreateIn, CampaignDetailOut, CampaignListOut, CampaignRenameIn,
    CampaignResponseListOut,
    CampaignResultsOut, CampaignStatisticsOut, CampaignStatusIn, CampaignTestOut,
)
from app.tests import rules as test_rules
from app.core.no_store_route import NoStoreRoute
from app.core.public_urls import frontend_url
from app.student_verification.faculties import faculty_label


router = APIRouter(
    prefix="/supervisor/campaigns",
    tags=["supervisor: test campaigns"],
    route_class=NoStoreRoute,
    dependencies=[
        Depends(require_role("supervisor")),
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
    return f"/test/{token}"


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
                                     actor_id=_actor(current_user),
            impersonator_id=current_user.get("impersonator_user_id"), ip=ip,
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


@router.patch("/{campaign_uuid}", response_model=CampaignDetailOut)
def rename_campaign(campaign_uuid: str, body: CampaignRenameIn, request: Request,
                    current_user: dict = Depends(get_current_user)):
    ip, ua = _client(request)
    try:
        return _detail(store.rename_campaign(campaign_uuid, title=body.title,
                                             actor_id=_actor(current_user),
            impersonator_id=current_user.get("impersonator_user_id"), ip=ip,
                                             user_agent=ua))
    except store.NotFound:
        raise _not_found()


@router.patch("/{campaign_uuid}/status", response_model=CampaignDetailOut)
def set_status(campaign_uuid: str, body: CampaignStatusIn, request: Request,
               current_user: dict = Depends(get_current_user)):
    ip, ua = _client(request)
    try:
        return _detail(store.set_status(campaign_uuid, target=body.status,
                                        actor_id=_actor(current_user),
            impersonator_id=current_user.get("impersonator_user_id"), ip=ip,
                                        user_agent=ua))
    except store.NotFound:
        raise _not_found()


@router.patch("/{campaign_uuid}/schedule", response_model=CampaignDetailOut)
def set_schedule(campaign_uuid: str, body: CampaignScheduleIn, request: Request,
                 current_user: dict = Depends(get_current_user)):
    ip, ua = _client(request)
    try:
        return _detail(store.set_schedule(
            campaign_uuid, opens_at=body.opens_at, closes_at=body.closes_at,
            actor_id=_actor(current_user),
            impersonator_id=current_user.get("impersonator_user_id"), ip=ip, user_agent=ua))
    except store.NotFound:
        raise _not_found()


@router.put("/{campaign_uuid}/access-code", response_model=CampaignDetailOut)
def set_access_code(campaign_uuid: str, body: CampaignAccessCodeIn, request: Request,
                    current_user: dict = Depends(get_current_user)):
    ip, ua = _client(request)
    actor_id = _actor(current_user)
    try:
        code_hash = access.hash_code(body.access_code)     # bcrypt — до транзакции
    except access.AccessCodeInvalid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Кодовое слово — от {access.CODE_MIN} до {access.CODE_MAX} символов, "
                   "без служебных символов")
    try:
        return _detail(store.set_access_code(
            campaign_uuid, code_hash=code_hash, actor_id=actor_id,
            impersonator_id=current_user.get("impersonator_user_id"), ip=ip, user_agent=ua))
    except store.NotFound:
        raise _not_found()


@router.delete("/{campaign_uuid}/access-code", response_model=CampaignDetailOut)
def clear_access_code(campaign_uuid: str, request: Request,
                      current_user: dict = Depends(get_current_user)):
    ip, ua = _client(request)
    try:
        return _detail(store.set_access_code(
            campaign_uuid, code_hash=None, actor_id=_actor(current_user),
            impersonator_id=current_user.get("impersonator_user_id"), ip=ip, user_agent=ua))
    except store.NotFound:
        raise _not_found()


@router.post("/{campaign_uuid}/rotate-link", response_model=CampaignDetailOut)
def rotate_link(campaign_uuid: str, request: Request,
                current_user: dict = Depends(get_current_user)):
    ip, ua = _client(request)
    try:
        return _detail(store.rotate_link(campaign_uuid, actor_id=_actor(current_user),
            impersonator_id=current_user.get("impersonator_user_id"),
                                         ip=ip, user_agent=ua))
    except store.NotFound:
        raise _not_found()


@router.delete("/{campaign_uuid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_campaign(campaign_uuid: str, request: Request,
                    current_user: dict = Depends(get_current_user)):
    ip, ua = _client(request)
    try:
        store.delete_campaign(campaign_uuid, actor_id=_actor(current_user),
            impersonator_id=current_user.get("impersonator_user_id"),
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
                                    actor_id=_actor(current_user),
            impersonator_id=current_user.get("impersonator_user_id"), ip=ip,
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
                              actor_id=_actor(current_user),
            impersonator_id=current_user.get("impersonator_user_id"), ip=ip, user_agent=ua)
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
            impersonator_id=current_user.get("impersonator_user_id"),
                                  ip=ip, user_agent=ua)
    except store.NotFound:
        raise _not_found()
    rules = data["rules"]
    enriched = [analytics.enrich_row(r, rules) for r in data["rows"]]
    rows = analytics.filter_rows(enriched, rules=rules, faculty_code=faculty_code,
                                 gender=gender, validity=validity, type_name=type_name)
    scales = analytics.scale_order(rules, enriched)
    return {
        "has_rules": rules is not None,
        "has_validity": bool(test_rules.validity_scales(rules)),
        "scales": [{"code": s, "label": test_rules.scale_label(rules, s),
                    "norm_title": (n.title if (n := test_rules.norms_of(rules).get(s)) else None)}
                   for s in scales],
        # Уровни по возрастанию с оттенком (low/norm/accent/maladaptive) для UI.
        "levels": analytics.level_list(rules),
        "level_labels": analytics.level_labels(rules),
        # Свои уровни шкал (ТЗ этапа 2, §4.1): {шкала: [{code, label, min, max, tone}]}.
        "scale_levels": analytics.scale_levels(rules),
        "validity_title": analytics.validity_title(rules),
        "type_threshold": rules.types.threshold
        if rules is not None and rules.types else None,
        "type_names": [t.name for t in rules.types.items]
        if rules is not None and rules.types else [],
        "faculties": [{"code": g["code"], "label": g["label"]}
                      for g in analytics.summarize(enriched, rules)["by_faculty"]],
        "total_all": len(enriched),
        "items": [{
            **{k: r[k] for k in ("uuid", "full_name", "faculty_code", "specialty",
                                 "age", "gender", "submitted_at", "scores",
                                 "levels", "is_valid", "types", "norms")},
            "faculty_label": faculty_label(r["faculty_code"]),
        } for r in rows],
        "summary": analytics.summarize(rows, rules),
    }


@router.get("/{campaign_uuid}/statistics", response_model=CampaignStatisticsOut)
def get_statistics(
    campaign_uuid: str,
    request: Request,
    faculty_code: Optional[str] = Query(default=None, max_length=64),
    gender: Optional[Literal["male", "female"]] = Query(default=None),
    validity: Optional[Literal["valid", "invalid"]] = Query(default=None),
    type_name: Optional[str] = Query(default=None, alias="type", max_length=200),
    current_user: dict = Depends(get_current_user),
):
    """Статистика по отфильтрованному набору (те же фильтры, что у results).
    ФИО не загружаются и не отдаются; аудит campaign_results_read — до отдачи."""
    ip, ua = _client(request)
    try:
        data = store.statistics_data(campaign_uuid, actor_id=_actor(current_user),
                                     impersonator_id=current_user.get("impersonator_user_id"),
                                     ip=ip, user_agent=ua)
    except store.NotFound:
        raise _not_found()
    rules = data["rules"]
    enriched = [analytics.enrich_row(r, rules) for r in data["rows"]]
    rows = analytics.filter_rows(enriched, rules=rules, faculty_code=faculty_code,
                                 gender=gender, validity=validity, type_name=type_name)
    return analytics.statistics(rows, rules, data["questions"])


@router.get("/{campaign_uuid}/export.xlsx")
def export_xlsx(campaign_uuid: str, request: Request,
                current_user: dict = Depends(get_current_user)):
    ip, ua = _client(request)
    try:
        data = store.export_data(campaign_uuid, actor_id=_actor(current_user),
            impersonator_id=current_user.get("impersonator_user_id"),
                                 ip=ip, user_agent=ua)
    except store.NotFound:
        raise _not_found()
    content = export.build_workbook(rules=data["rules"], rows=data["rows"],
                                    question_numbers=data["question_numbers"],
                                    questions=data["questions"])
    filename = f"campaign_{data['campaign_uuid'][:8]}.xlsx"
    return Response(
        content=content, media_type=export.XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
