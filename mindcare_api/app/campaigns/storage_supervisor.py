"""
Хранилище кабинета супервизора для кампаний (ADR-036, этап 4).

Мутации кампании (закрыть/открыть, перевыпустить ссылку, удалить) — строка
test_campaigns под FOR UPDATE (сериализация с публичной отправкой под
FOR SHARE) + ATOMIC-событие в той же транзакции.

Чтение ФИО (список ответов, выгрузка) — fail-closed: событие INDEPENDENT/RAISE
пишется ДО отдачи данных; сбой → AuditError → 503 без ПДн.

Удаление — физическое (ADR-036): CASCADE на ответы/шкалы/ответы на вопросы,
записи согласия — тем же вызовом в той же транзакции (сначала ответы, потом
согласия: FK RESTRICT).
"""
import uuid as _uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func

from app.audit import Actor, Outcome, Target, record_event
from app.audit.request_context import build_request_context
from app.campaigns import access, tokens
from app.core.encryption import decrypt_text, encrypt_text
from app.db.models import (
    CampaignResponse, CampaignResponseAnswer, CampaignResponseScale,
    ConsentRecord, Option, Question, Test, TestCampaign,
)
from app.db.session import SessionLocal
from app.tests import rules as test_rules

CAMPAIGN_ENTITY = "test_campaign"
RESPONSE_ENTITY = "campaign_response"


class NotFound(Exception):
    """Кампания/ответ/тест не найдены (→ 404)."""


class TestNotAllowed(Exception):
    """Методика недоступна для кампании (не опубликована, выключена, удалена
    или заменена новой версией) → 422."""


def _uuid_or_none(value) -> Optional[_uuid.UUID]:
    if isinstance(value, _uuid.UUID):
        return value
    try:
        return _uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


def _meta(impersonator_id: Optional[int]) -> dict:
    """Вход администратора «под именем» супервизора (ADR-025): актор события —
    супервизор, кто действовал на самом деле — impersonator_user_id."""
    return {} if impersonator_id is None else {"impersonator_user_id": int(impersonator_id)}


def _event(db, name: str, actor_id: int, entity: str, entity_id: int, ctx,
           impersonator_id: Optional[int] = None) -> None:
    record_event(
        event=name,
        actor=Actor.user(actor_id, "supervisor"),
        target=Target(entity, entity_id),
        outcome=Outcome.SUCCESS,
        metadata=_meta(impersonator_id),
        context=ctx,
        db=db,
    )


def _locked(db, campaign_uuid) -> TestCampaign:
    uid = _uuid_or_none(campaign_uuid)
    campaign = None
    if uid is not None:
        campaign = (
            db.query(TestCampaign).filter(TestCampaign.uuid == uid)
            .with_for_update().populate_existing().first()
        )
    if campaign is None:
        raise NotFound()
    return campaign


def _counts(db, campaign_ids: list[int]) -> dict[int, int]:
    if not campaign_ids:
        return {}
    rows = (
        db.query(CampaignResponse.campaign_id, func.count(CampaignResponse.id))
        .filter(CampaignResponse.campaign_id.in_(campaign_ids))
        .group_by(CampaignResponse.campaign_id).all()
    )
    return dict(rows)


def _dto(campaign: TestCampaign, test: Optional[Test], count: int,
         with_link: bool = False) -> dict:
    data = {
        "uuid": str(campaign.uuid),
        "title": campaign.title,
        "status": campaign.status,
        "test_title": test.title if test else None,
        "test_uuid": str(test.uuid) if test else None,
        "responses_count": count,
        "created_at": campaign.created_at,
        "closed_at": campaign.closed_at,
        "opens_at": campaign.opens_at,
        "closes_at": campaign.closes_at,
        "access_code_set": campaign.access_code_hash is not None,
        # Что сейчас видит участник по ссылке: open | scheduled | expired | closed.
        "link_state": access.state(campaign.status, campaign.opens_at, campaign.closes_at),
    }
    if with_link:
        data["link_token"] = decrypt_text(campaign.link_token_enc)
    return data


# ── тесты для кампаний ────────────────────────────────────────────────────────

def _selectable():
    """ADR-037: методики общие — кампанию можно создать по любой опубликованной
    и включённой методике последней версии (campaign_only не требуется)."""
    return (Test.deleted_at.is_(None), Test.status == "published",
            Test.is_active.is_(True), Test.superseded_at.is_(None))


def list_campaign_tests() -> list[dict]:
    with SessionLocal() as db:
        tests = (
            db.query(Test).filter(*_selectable())
            .order_by(Test.title, Test.id).all()
        )
        return [{"uuid": str(t.uuid), "title": t.title} for t in tests]


# ── кампании ──────────────────────────────────────────────────────────────────

def create_campaign(*, title: str, test_uuid, actor_id: int, ip, user_agent,
        impersonator_id: Optional[int] = None) -> dict:
    ctx = build_request_context(ip=ip, user_agent=user_agent)
    uid = _uuid_or_none(test_uuid)
    with SessionLocal() as db:
        test = (db.query(Test).filter(Test.uuid == uid, *_selectable()).first()
                if uid else None)
        if test is None:
            raise TestNotAllowed()
        token = tokens.generate_token(title)
        campaign = TestCampaign(
            test_id=test.id, title=title,
            link_token_hash=tokens.hash_token(token),
            link_token_enc=encrypt_text(token),
            created_by=actor_id,
        )
        db.add(campaign)
        db.flush()
        _event(db, "test_campaign_created", actor_id, CAMPAIGN_ENTITY, campaign.id, ctx, impersonator_id)
        db.commit()
        db.refresh(campaign)
        return _dto(campaign, test, 0, with_link=True)


def list_campaigns(*, size: int, before: Optional[str]) -> dict:
    with SessionLocal() as db:
        q = db.query(TestCampaign)
        if before:
            cursor = db.query(TestCampaign).filter(
                TestCampaign.uuid == _uuid_or_none(before)).first() \
                if _uuid_or_none(before) else None
            if cursor is None:
                raise NotFound()
            q = q.filter(
                (TestCampaign.created_at < cursor.created_at)
                | ((TestCampaign.created_at == cursor.created_at)
                   & (TestCampaign.id < cursor.id))
            )
        rows = (q.order_by(TestCampaign.created_at.desc(), TestCampaign.id.desc())
                .limit(size + 1).all())
        has_more = len(rows) > size
        rows = rows[:size]
        tests = {t.id: t for t in db.query(Test).filter(
            Test.id.in_({r.test_id for r in rows})).all()} if rows else {}
        counts = _counts(db, [r.id for r in rows])
        return {
            "items": [_dto(r, tests.get(r.test_id), counts.get(r.id, 0), with_link=True)
                      for r in rows],
            "has_more": has_more,
        }


def get_campaign(campaign_uuid) -> dict:
    uid = _uuid_or_none(campaign_uuid)
    with SessionLocal() as db:
        campaign = (db.query(TestCampaign).filter(TestCampaign.uuid == uid).first()
                    if uid else None)
        if campaign is None:
            raise NotFound()
        test = db.get(Test, campaign.test_id)
        count = _counts(db, [campaign.id]).get(campaign.id, 0)
        return _dto(campaign, test, count, with_link=True)


def set_status(campaign_uuid, *, target: str, actor_id: int, ip, user_agent,
        impersonator_id: Optional[int] = None) -> dict:
    """open ↔ closed. Повтор текущего состояния — без изменений и события."""
    ctx = build_request_context(ip=ip, user_agent=user_agent)
    with SessionLocal() as db:
        campaign = _locked(db, campaign_uuid)
        if campaign.status != target:
            campaign.status = target
            campaign.closed_at = (datetime.now(timezone.utc)
                                  if target == "closed" else None)
            campaign.updated_at = datetime.now(timezone.utc)
            name = "test_campaign_closed" if target == "closed" else "test_campaign_reopened"
            _event(db, name, actor_id, CAMPAIGN_ENTITY, campaign.id, ctx, impersonator_id)
            db.commit()
        test = db.get(Test, campaign.test_id)
        count = _counts(db, [campaign.id]).get(campaign.id, 0)
        return _dto(campaign, test, count, with_link=True)


def rename_campaign(campaign_uuid, *, title: str, actor_id: int, ip, user_agent,
        impersonator_id: Optional[int] = None) -> dict:
    """Новое название. Токен ссылки не меняется: уже разосланный адрес
    продолжает работать (slug в нём остаётся от прежнего названия).
    То же название — без изменений и события."""
    ctx = build_request_context(ip=ip, user_agent=user_agent)
    with SessionLocal() as db:
        campaign = _locked(db, campaign_uuid)
        if campaign.title != title:
            campaign.title = title
            campaign.updated_at = datetime.now(timezone.utc)
            _event(db, "test_campaign_renamed", actor_id, CAMPAIGN_ENTITY,
                   campaign.id, ctx, impersonator_id)
            db.commit()
        test = db.get(Test, campaign.test_id)
        count = _counts(db, [campaign.id]).get(campaign.id, 0)
        return _dto(campaign, test, count, with_link=True)


def set_schedule(campaign_uuid, *, opens_at, closes_at, actor_id: int, ip, user_agent,
                 impersonator_id: Optional[int] = None) -> dict:
    """Сроки ссылки (любое из значений — None, то есть без ограничения).
    Те же значения — без изменений и события. Порядок дат проверяет схема."""
    ctx = build_request_context(ip=ip, user_agent=user_agent)
    with SessionLocal() as db:
        campaign = _locked(db, campaign_uuid)
        if (campaign.opens_at, campaign.closes_at) != (opens_at, closes_at):
            campaign.opens_at = opens_at
            campaign.closes_at = closes_at
            campaign.updated_at = datetime.now(timezone.utc)
            _event(db, "test_campaign_schedule_changed", actor_id, CAMPAIGN_ENTITY,
                   campaign.id, ctx, impersonator_id)
            db.commit()
        test = db.get(Test, campaign.test_id)
        count = _counts(db, [campaign.id]).get(campaign.id, 0)
        return _dto(campaign, test, count, with_link=True)


def set_access_code(campaign_uuid, *, code_hash: Optional[str], actor_id: int, ip,
                    user_agent, impersonator_id: Optional[int] = None) -> dict:
    """code_hash — bcrypt нового слова (посчитан вызывающим ВНЕ транзакции) или
    None — снять слово. Задание слова пишет событие всегда (сравнить с прежним
    без открытого текста нельзя); снятие отсутствующего — без события."""
    ctx = build_request_context(ip=ip, user_agent=user_agent)
    with SessionLocal() as db:
        campaign = _locked(db, campaign_uuid)
        if code_hash is not None or campaign.access_code_hash is not None:
            campaign.access_code_hash = code_hash
            campaign.updated_at = datetime.now(timezone.utc)
            _event(db, "test_campaign_access_code_changed", actor_id, CAMPAIGN_ENTITY,
                   campaign.id, ctx, impersonator_id)
            db.commit()
        test = db.get(Test, campaign.test_id)
        count = _counts(db, [campaign.id]).get(campaign.id, 0)
        return _dto(campaign, test, count, with_link=True)


def rotate_link(campaign_uuid, *, actor_id: int, ip, user_agent,
        impersonator_id: Optional[int] = None) -> dict:
    ctx = build_request_context(ip=ip, user_agent=user_agent)
    with SessionLocal() as db:
        campaign = _locked(db, campaign_uuid)
        token = tokens.generate_token(campaign.title)
        campaign.link_token_hash = tokens.hash_token(token)
        campaign.link_token_enc = encrypt_text(token)
        campaign.updated_at = datetime.now(timezone.utc)
        _event(db, "test_campaign_link_rotated", actor_id, CAMPAIGN_ENTITY,
               campaign.id, ctx, impersonator_id)
        db.commit()
        test = db.get(Test, campaign.test_id)
        count = _counts(db, [campaign.id]).get(campaign.id, 0)
        return _dto(campaign, test, count, with_link=True)


def delete_campaign(campaign_uuid, *, actor_id: int, ip, user_agent,
        impersonator_id: Optional[int] = None) -> None:
    ctx = build_request_context(ip=ip, user_agent=user_agent)
    with SessionLocal() as db:
        campaign = _locked(db, campaign_uuid)
        campaign_id = campaign.id
        consent_ids = [r.consent_record_id for r in db.query(
            CampaignResponse.consent_record_id).filter(
            CampaignResponse.campaign_id == campaign_id)]
        db.query(TestCampaign).filter(TestCampaign.id == campaign_id) \
            .delete(synchronize_session=False)
        if consent_ids:
            db.query(ConsentRecord).filter(ConsentRecord.id.in_(consent_ids)) \
                .delete(synchronize_session=False)
        _event(db, "test_campaign_deleted", actor_id, CAMPAIGN_ENTITY, campaign_id, ctx, impersonator_id)
        db.commit()


# ── ответы ────────────────────────────────────────────────────────────────────

def list_responses(campaign_uuid, *, size: int, after: Optional[str],
                   actor_id: int, ip, user_agent,
        impersonator_id: Optional[int] = None) -> dict:
    """Страница ответов с ФИО. Событие campaign_responses_read пишется ДО отдачи
    (INDEPENDENT/RAISE); пустая страница — без события (ФИО не раскрыты)."""
    ctx = build_request_context(ip=ip, user_agent=user_agent)
    uid = _uuid_or_none(campaign_uuid)
    with SessionLocal() as db:
        campaign = (db.query(TestCampaign).filter(TestCampaign.uuid == uid).first()
                    if uid else None)
        if campaign is None:
            raise NotFound()
        q = db.query(CampaignResponse).filter(
            CampaignResponse.campaign_id == campaign.id)
        if after:
            aid = _uuid_or_none(after)
            cursor = (db.query(CampaignResponse).filter(
                CampaignResponse.uuid == aid,
                CampaignResponse.campaign_id == campaign.id).first()
                if aid else None)
            if cursor is None:
                raise NotFound()
            q = q.filter(
                (CampaignResponse.submitted_at > cursor.submitted_at)
                | ((CampaignResponse.submitted_at == cursor.submitted_at)
                   & (CampaignResponse.id > cursor.id))
            )
        rows = (q.order_by(CampaignResponse.submitted_at, CampaignResponse.id)
                .limit(size + 1).all())
        has_more = len(rows) > size
        rows = rows[:size]
        items = [{
            "uuid": str(r.uuid),
            "full_name": decrypt_text(r.full_name_enc),
            "faculty_code": r.faculty_code,
            "specialty": r.specialty,
            "age": r.age,
            "gender": r.gender,
            "submitted_at": r.submitted_at,
        } for r in rows]
        campaign_id = campaign.id
    if items:
        record_event(
            event="campaign_responses_read",
            actor=Actor.user(actor_id, "supervisor"),
            target=Target(CAMPAIGN_ENTITY, campaign_id),
            outcome=Outcome.SUCCESS,
            metadata=_meta(impersonator_id),
            context=ctx,
        )
    return {"items": items, "has_more": has_more}


def delete_response(campaign_uuid, response_uuid, *, actor_id: int, ip,
                    user_agent, impersonator_id: Optional[int] = None) -> None:
    ctx = build_request_context(ip=ip, user_agent=user_agent)
    rid = _uuid_or_none(response_uuid)
    with SessionLocal() as db:
        campaign = _locked(db, campaign_uuid)
        response = (db.query(CampaignResponse).filter(
            CampaignResponse.uuid == rid,
            CampaignResponse.campaign_id == campaign.id).first() if rid else None)
        if response is None:
            raise NotFound()
        response_id, consent_id = response.id, response.consent_record_id
        db.query(CampaignResponse).filter(CampaignResponse.id == response_id) \
            .delete(synchronize_session=False)
        db.query(ConsentRecord).filter(ConsentRecord.id == consent_id) \
            .delete(synchronize_session=False)
        _event(db, "campaign_response_deleted", actor_id, RESPONSE_ENTITY,
               response_id, ctx, impersonator_id)
        db.commit()


# ── выгрузка ──────────────────────────────────────────────────────────────────

def _load_rows(db, campaign_uuid, *, with_answers: bool, with_names: bool = True) -> dict:
    """Все ответы кампании (по времени прохождения) с баллами шкал и, по
    запросу, ответами на вопросы (+ структура вопросов). ФИО расшифровывается
    здесь, только если with_names (статистике имена не нужны)."""
    uid = _uuid_or_none(campaign_uuid)
    campaign = (db.query(TestCampaign).filter(TestCampaign.uuid == uid).first()
                if uid else None)
    if campaign is None:
        raise NotFound()
    test = db.get(Test, campaign.test_id)
    responses = (db.query(CampaignResponse)
                 .filter(CampaignResponse.campaign_id == campaign.id)
                 .order_by(CampaignResponse.submitted_at, CampaignResponse.id)
                 .all())
    ids = [r.id for r in responses]
    scores: dict[int, dict] = {i: {} for i in ids}
    answers: dict[int, dict] = {i: {} for i in ids}
    if ids:
        for s in db.query(CampaignResponseScale).filter(
                CampaignResponseScale.response_id.in_(ids)):
            scores[s.response_id][s.scale_name] = s.score
        if with_answers:
            pairs = (
                db.query(CampaignResponseAnswer.response_id,
                         Question.question_order, Option.option_text)
                .join(Question, Question.id == CampaignResponseAnswer.question_id)
                .join(Option, Option.id == CampaignResponseAnswer.option_id)
                .filter(CampaignResponseAnswer.response_id.in_(ids))
            )
            for response_id, number, text in pairs:
                answers[response_id][number] = text
    numbers, questions = [], []
    if with_answers:
        qs = (db.query(Question).filter(Question.test_id == campaign.test_id)
              .order_by(Question.question_order, Question.id).all())
        numbers = [q.question_order for q in qs]
        opts: dict[int, list[str]] = {q.id: [] for q in qs}
        if qs:
            for o in (db.query(Option).filter(Option.question_id.in_(opts))
                      .order_by(Option.question_id, Option.option_order, Option.id)):
                opts[o.question_id].append(o.option_text)
        questions = [{"number": q.question_order, "text": q.question_text,
                      "options": opts[q.id]} for q in qs]
    rows = [{
        "uuid": str(r.uuid),
        "full_name": decrypt_text(r.full_name_enc) if with_names else None,
        "age": r.age, "gender": r.gender,
        "faculty_code": r.faculty_code, "specialty": r.specialty,
        "submitted_at": r.submitted_at,
        "scores": scores[r.id], "answers": answers[r.id],
    } for r in responses]
    return {
        "campaign_id": campaign.id,
        "campaign_uuid": str(campaign.uuid),
        # ADR-037: правила обработки теста этой кампании (её версии методики).
        "rules": test_rules.parse(test.scoring_rules) if test else None,
        "rows": rows,
        "question_numbers": numbers,
        "questions": questions,
    }


def _record_read(event: str, actor_id: int, campaign_id: int, ctx,
                 impersonator_id: Optional[int] = None) -> None:
    record_event(
        event=event,
        actor=Actor.user(actor_id, "supervisor"),
        target=Target(CAMPAIGN_ENTITY, campaign_id),
        outcome=Outcome.SUCCESS,
        metadata=_meta(impersonator_id),
        context=ctx,
    )


def export_data(campaign_uuid, *, actor_id: int, ip, user_agent,
        impersonator_id: Optional[int] = None) -> dict:
    """Данные для xlsx: событие campaign_results_exported (INDEPENDENT/RAISE)
    пишется ДО возврата; сбой → AuditError, файл не формируется."""
    ctx = build_request_context(ip=ip, user_agent=user_agent)
    with SessionLocal() as db:
        result = _load_rows(db, campaign_uuid, with_answers=True)
    _record_read("campaign_results_exported", actor_id, result["campaign_id"], ctx, impersonator_id)
    return result


def statistics_data(campaign_uuid, *, actor_id: int, ip, user_agent,
                    impersonator_id: Optional[int] = None) -> dict:
    """Ответы на вопросы и баллы для статистики (без ФИО). Тот же доступ и то
    же событие, что у экрана результатов (campaign_results_read,
    INDEPENDENT/RAISE, до возврата, если есть участники)."""
    ctx = build_request_context(ip=ip, user_agent=user_agent)
    with SessionLocal() as db:
        result = _load_rows(db, campaign_uuid, with_answers=True, with_names=False)
    if result["rows"]:
        _record_read("campaign_results_read", actor_id, result["campaign_id"], ctx, impersonator_id)
    return result


def results_data(campaign_uuid, *, actor_id: int, ip, user_agent,
        impersonator_id: Optional[int] = None) -> dict:
    """Баллы всех участников для экрана результатов (с ФИО). Событие
    campaign_results_read (INDEPENDENT/RAISE) — ДО возврата, если есть хотя бы
    один участник; сбой → AuditError, данные не отдаются."""
    ctx = build_request_context(ip=ip, user_agent=user_agent)
    with SessionLocal() as db:
        result = _load_rows(db, campaign_uuid, with_answers=False)
    if result["rows"]:
        _record_read("campaign_results_read", actor_id, result["campaign_id"], ctx, impersonator_id)
    return result
