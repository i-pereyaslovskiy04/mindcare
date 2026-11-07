"""
Публичный API кампании (ADR-036). Префикс: /api/public/campaigns. Без авторизации.

  GET  /{token}         — анкета: название, инструкция, текст согласия,
                          каталог факультетов, вопросы (без баллов и шкал);
                          при кодовом слове — только «замок»
                          (access_code_required, без вопросов);
                          до начала срока — 409 campaign_not_started + opens_at.
  POST /{token}/unlock  — {access_code} → та же анкета; неверное — 403
                          access_code_invalid.
  POST /{token}/submit  — анкета + принятие согласия (версия) + ответы на все
                          вопросы. 201 — принято; 200 — повтор того же
                          submission_key; 404 — нет/закрыта/срок истёк/тест удалён;
                          403 access_code_invalid (+ access_code в теле);
                          409 campaign_not_started;
                          409 consent_outdated; 422 — ответы/поля; 429; 503 —
                          сбой обязательного аудита (ничего не сохранено).

NoStoreRoute: Cache-Control: no-store на любом ответе, 422 без значений полей
(ФИО не эхоится). Результат респонденту не показывается.

Rate limit — по request.client.host. За reverse-proxy без --proxy-headers это
адрес прокси, а студенты в аудитории сидят за одним NAT: лимиты — общий
потолок на сотни прохождений, а не ограничение одного человека.
"""
from fastapi import APIRouter, HTTPException, Request, Response, status

from app.campaigns import service
from app.campaigns.schemas import (
    CampaignSubmitIn, CampaignSubmitOut, CampaignUnlockIn, PublicCampaignRead,
)
from app.core.no_store_route import NoStoreRoute, no_store_json
from app.core.rate_limit import RateLimitExceeded, enforce as enforce_rate_limit

router = APIRouter(
    prefix="/public/campaigns",
    tags=["public: test campaigns"],
    route_class=NoStoreRoute,
)

_NOT_FOUND = "Ссылка недействительна или опрос завершён."
_RATE_LIMIT = "Слишком много запросов. Подождите несколько минут и повторите."
_WRONG_CODE = {"detail": "Неверное кодовое слово.", "code": "access_code_invalid"}


def _not_started(exc):
    return no_store_json(409, {
        "detail": "Тестирование ещё не началось.",
        "code": "campaign_not_started",
        "opens_at": exc.opens_at.isoformat() if exc.opens_at else None,
    })


def _client(request: Request):
    ip = request.client.host if request.client else None
    return ip, request.headers.get("user-agent")


def _limit(action: str, ip) -> None:
    try:
        enforce_rate_limit(action, ip=ip)
    except RateLimitExceeded:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail=_RATE_LIMIT)


@router.get("/{token}", response_model=PublicCampaignRead)
def get_campaign(token: str, request: Request):
    ip, _ = _client(request)
    _limit("campaign_read", ip)
    try:
        return service.get_public_campaign(token)
    except service.CampaignNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    except service.CampaignNotStarted as exc:
        return _not_started(exc)


@router.post("/{token}/unlock", response_model=PublicCampaignRead)
def unlock_campaign(token: str, body: CampaignUnlockIn, request: Request):
    ip, _ = _client(request)
    _limit("campaign_code", ip)
    try:
        return service.get_public_campaign(token, body.access_code, unlock=True)
    except service.CampaignNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    except service.CampaignNotStarted as exc:
        return _not_started(exc)
    except service.AccessCodeWrong:
        return no_store_json(403, _WRONG_CODE)


@router.post("/{token}/submit", response_model=CampaignSubmitOut,
             status_code=status.HTTP_201_CREATED)
def submit_campaign(token: str, body: CampaignSubmitIn, request: Request,
                    response: Response):
    ip, ua = _client(request)
    _limit("campaign_submit", ip)
    if body.access_code is not None:
        _limit("campaign_code", ip)     # отправка — тоже попытка слова
    payload = body.model_dump()
    payload["answers"] = [a.model_dump() for a in body.answers]
    try:
        outcome = service.submit(token, payload, ip=ip, user_agent=ua)
    except service.CampaignNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    except service.CampaignNotStarted as exc:
        return _not_started(exc)
    except service.AccessCodeWrong:
        return no_store_json(403, _WRONG_CODE)
    except service.ConsentOutdated:
        return no_store_json(409, {
            "detail": "Текст согласия обновился. Обновите страницу и примите его снова.",
            "code": "consent_outdated",
        })
    except service.AnswersInvalid as exc:
        return no_store_json(422, {
            "detail": "Ответьте на все вопросы анкеты.",
            "code": str(exc),
        })
    if outcome == "replay":
        response.status_code = status.HTTP_200_OK
    return {"status": "accepted"}
