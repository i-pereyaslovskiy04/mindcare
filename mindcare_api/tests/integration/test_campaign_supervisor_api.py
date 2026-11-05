"""
Integration: кампании в кабинете супервизора (ADR-036, этап 4).

Покрывает: доступ (только supervisor; admin/psychologist/student → 403;
impersonation → 403); создание только с campaign_only-тестом; ссылка
работает публично; закрытие/открытие (повтор без события); перевыпуск ссылки
(старая → 404); список участников с ФИО под fail-closed аудитом (пустая
страница — без события; сбой аудита → 503 без ФИО); выгрузка xlsx (колонки
образца, no-store, аудит до файла, сбой → 503); удаление ответа и кампании
(с записями согласия, ATOMIC-события); keyset списка кампаний.
"""
import io
import uuid as _uuid

import bcrypt
import pytest
from openpyxl import load_workbook

from app.audit import AuditError
from app.auth import storage as auth_storage
from app.campaigns import storage_supervisor
from app.db.models import (
    AuditLog, CampaignResponse, ConsentRecord, Test as TestModel, TestCampaign,
    User,
)
from app.db.session import SessionLocal
from app.tests.profiles.ito_seed import ensure_ito_test
from tests.integration.conftest import create_multi_role_user, create_test_user
from tests.integration.test_campaign_public_api import _payload

PASSWORD = "SecurePass42!"
BASE = "/api/supervisor/campaigns"


# ─── fixtures / helpers ───────────────────────────────────────────────────────

def _login(client, role: str):
    user = auth_storage.save_user({
        "name": f"Campaign {role} {_uuid.uuid4().hex[:6]}",
        "email": f"integ_camp_{role}_{_uuid.uuid4().hex[:10]}@example.com",
        "hashed_password": bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode(),
        "role": role,
    })
    r = client.post("/api/auth/login", json={"email": user["email"], "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['session_token']}"}, int(user["id"])


@pytest.fixture()
def env(client):
    """Тест ИТО + супервизор; уборка всех кампаний теста и их согласий."""
    with SessionLocal() as db:
        test, created = ensure_ito_test(db)
        db.commit()
        test_id, test_uuid = test.id, str(test.uuid)
    headers, sup_id = _login(client, "supervisor")
    yield {"test_id": test_id, "test_uuid": test_uuid, "headers": headers,
           "sup_id": sup_id}
    with SessionLocal() as db:
        ids = [c.id for c in db.query(TestCampaign.id)
               .filter(TestCampaign.test_id == test_id)]
        consent_ids = [r.consent_record_id for r in db.query(CampaignResponse)
                       .filter(CampaignResponse.campaign_id.in_(ids))] if ids else []
        if ids:
            db.query(TestCampaign).filter(TestCampaign.id.in_(ids)) \
                .delete(synchronize_session=False)
        if consent_ids:
            db.query(ConsentRecord).filter(ConsentRecord.id.in_(consent_ids)) \
                .delete(synchronize_session=False)
        if created:
            db.query(TestModel).filter(TestModel.id == test_id) \
                .delete(synchronize_session=False)
        db.commit()


def _create(client, env, title="integ Кампания") -> dict:
    r = client.post(BASE, headers=env["headers"],
                    json={"title": title, "test_uuid": env["test_uuid"]})
    assert r.status_code == 201, r.text
    return r.json()


def _token(campaign: dict) -> str:
    return campaign["link_token"]


def _submit(client, token: str, name: str = "Петров Пётр Петрович") -> None:
    body = _payload(client, token, full_name=name)
    r = client.post(f"/api/public/campaigns/{token}/submit", json=body)
    assert r.status_code == 201, r.text


def _events(name: str, entity_id: int) -> int:
    with SessionLocal() as db:
        return db.query(AuditLog).filter(AuditLog.event_type == name,
                                         AuditLog.entity_id == entity_id).count()


def _campaign_id(uuid: str) -> int:
    with SessionLocal() as db:
        return db.query(TestCampaign.id) \
            .filter(TestCampaign.uuid == _uuid.UUID(uuid)).scalar()


def _no_store(r) -> None:
    assert r.headers.get("cache-control") == "no-store, private"


# ─── доступ ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("role", ["admin", "psychologist"])
def test_other_staff_forbidden(client, env, role):
    headers, _ = _login(client, role)
    assert client.get(BASE, headers=headers).status_code == 403
    r = client.post(BASE, headers=headers,
                    json={"title": "x x", "test_uuid": env["test_uuid"]})
    assert r.status_code == 403


def test_student_and_anonymous_forbidden(client, env):
    email = f"integ_camp_student_{_uuid.uuid4().hex[:10]}@example.com"
    create_test_user(email, PASSWORD)
    r = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    headers = {"Authorization": f"Bearer {r.json()['session_token']}"}
    assert client.get(BASE, headers=headers).status_code == 403
    assert client.get(BASE).status_code == 401


def test_impersonated_supervisor_forbidden(client, env):
    admin_token, _, _ = create_multi_role_user(client, ["admin"])
    with SessionLocal() as db:
        sup_uuid = str(db.get(User, env["sup_id"]).uuid)
    r = client.post(f"/api/admin/users/{sup_uuid}/impersonate",
                    headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200, r.text
    imp = {"Authorization": f"Bearer {r.json()['session_token']}"}
    assert client.get(BASE, headers=imp).status_code == 403
    r = client.post(BASE, headers=imp,
                    json={"title": "x x", "test_uuid": env["test_uuid"]})
    assert r.status_code == 403


# ─── создание и ссылка ────────────────────────────────────────────────────────

def test_create_and_link_works_publicly(client, env):
    tests = client.get(f"{BASE}/tests", headers=env["headers"]).json()
    assert env["test_uuid"] in {t["uuid"] for t in tests}

    camp = _create(client, env, title="  integ   1 курс  ")
    assert camp["title"] == "integ 1 курс"
    assert camp["status"] == "open" and camp["responses_count"] == 0
    assert camp["link_path"] == f"/test/{camp['link_token']}"
    assert camp["link_token"].startswith("integ-1-kurs-")
    assert _events("test_campaign_created", _campaign_id(camp["uuid"])) == 1
    assert client.get(f"/api/public/campaigns/{_token(camp)}").status_code == 200

    r = client.get(f"{BASE}/{camp['uuid']}", headers=env["headers"])
    assert r.status_code == 200 and r.json()["link_token"] == camp["link_token"]
    _no_store(r)


def test_create_with_regular_test_rejected(client, env):
    with SessionLocal() as db:
        regular = TestModel(title=f"integ regular {_uuid.uuid4().hex[:6]}")
        db.add(regular)
        db.commit()
        regular_uuid, regular_id = str(regular.uuid), regular.id
    try:
        r = client.post(BASE, headers=env["headers"],
                        json={"title": "integ x", "test_uuid": regular_uuid})
        assert r.status_code == 422
    finally:
        with SessionLocal() as db:
            db.query(TestModel).filter(TestModel.id == regular_id).delete()
            db.commit()


# ─── статус и ссылка ──────────────────────────────────────────────────────────

def test_close_reopen_idempotent(client, env):
    camp = _create(client, env)
    cid = _campaign_id(camp["uuid"])
    url = f"{BASE}/{camp['uuid']}/status"
    r = client.patch(url, headers=env["headers"], json={"status": "closed"})
    assert r.status_code == 200 and r.json()["status"] == "closed"
    assert r.json()["closed_at"] is not None
    assert client.get(f"/api/public/campaigns/{_token(camp)}").status_code == 404
    client.patch(url, headers=env["headers"], json={"status": "closed"})
    assert _events("test_campaign_closed", cid) == 1

    r = client.patch(url, headers=env["headers"], json={"status": "open"})
    assert r.json()["status"] == "open" and r.json()["closed_at"] is None
    assert _events("test_campaign_reopened", cid) == 1
    assert client.get(f"/api/public/campaigns/{_token(camp)}").status_code == 200


def test_rotate_link_invalidates_old(client, env):
    camp = _create(client, env)
    r = client.post(f"{BASE}/{camp['uuid']}/rotate-link", headers=env["headers"])
    assert r.status_code == 200
    new = r.json()["link_token"]
    assert new != camp["link_token"]
    # Читаемая часть из названия сохраняется, меняется случайный хвост.
    assert new.rsplit("-", 1)[0] == camp["link_token"].rsplit("-", 1)[0]
    assert client.get(f"/api/public/campaigns/{camp['link_token']}").status_code == 404
    assert client.get(f"/api/public/campaigns/{new}").status_code == 200
    assert _events("test_campaign_link_rotated", _campaign_id(camp["uuid"])) == 1


def test_unknown_campaign_404(client, env):
    for url in (f"{BASE}/{_uuid.uuid4()}", f"{BASE}/not-a-uuid",
                f"{BASE}/{_uuid.uuid4()}/responses"):
        assert client.get(url, headers=env["headers"]).status_code == 404


# ─── участники ────────────────────────────────────────────────────────────────

def test_responses_list_with_audit(client, env):
    camp = _create(client, env)
    cid = _campaign_id(camp["uuid"])
    url = f"{BASE}/{camp['uuid']}/responses"

    r = client.get(url, headers=env["headers"])
    assert r.json() == {"items": [], "has_more": False}
    assert _events("campaign_responses_read", cid) == 0

    _submit(client, _token(camp), "Первый Участник")
    _submit(client, _token(camp), "Второй Участник")
    r = client.get(url, headers=env["headers"], params={"size": 1})
    assert r.status_code == 200
    _no_store(r)
    page1 = r.json()
    assert [i["full_name"] for i in page1["items"]] == ["Первый Участник"]
    assert page1["has_more"] is True
    item = page1["items"][0]
    assert item["faculty_label"] == "Учетно-финансовый факультет"
    r = client.get(url, headers=env["headers"],
                   params={"size": 1, "after": item["uuid"]})
    assert [i["full_name"] for i in r.json()["items"]] == ["Второй Участник"]
    assert _events("campaign_responses_read", cid) == 2

    detail = client.get(f"{BASE}/{camp['uuid']}", headers=env["headers"]).json()
    assert detail["responses_count"] == 2


def test_responses_audit_failure_503_without_names(client, env, monkeypatch):
    camp = _create(client, env)
    _submit(client, _token(camp), "Скрытый Участник")

    def boom(**_kw):
        raise AuditError("injected")

    monkeypatch.setattr(storage_supervisor, "record_event", boom)
    r = client.get(f"{BASE}/{camp['uuid']}/responses", headers=env["headers"])
    assert r.status_code == 503
    _no_store(r)
    assert "Скрытый" not in r.text


# ─── выгрузка ─────────────────────────────────────────────────────────────────

def test_export_xlsx(client, env):
    camp = _create(client, env)
    _submit(client, _token(camp), "=HYPERLINK(\"http://evil\")")
    r = client.get(f"{BASE}/{camp['uuid']}/export.xlsx", headers=env["headers"])
    assert r.status_code == 200, r.text
    _no_store(r)
    assert r.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    assert "attachment" in r.headers["content-disposition"]
    assert "HYPERLINK" not in r.headers["content-disposition"]

    wb = load_workbook(io.BytesIO(r.content))
    ws = wb["Результаты"]
    header = [c.value for c in ws[1]]
    assert header[:16] == [
        "№ п/п", "Фамилия Имя Отчество", "Возраст", "Пол", "Факультет",
        "Специальность", "L Ложь", "F Аггравация", "IV Ригидность",
        "II Спонтанность", "VI Сензитивность", "VII Тревожность",
        "VIII Лабильность", "I Экстраверсия", "III Агрессивность", "V Интроверсия",
    ]
    assert header[16:] == ["Достоверность", "Тип", "Дата прохождения"]
    row = [c.value for c in ws[2]]
    assert row[1] == "=HYPERLINK(\"http://evil\")"
    assert ws.cell(2, 2).data_type == "s"
    assert row[3] == "Жен" and row[4] == "Учетно-финансовый факультет"
    assert row[6:16] == [0, 0, 3, 3, 4, 2, 4, 3, 2, 3]
    assert row[16] == "достоверно"
    answers = wb["Ответы"]
    assert answers.max_column == 2 + 91
    assert _events("campaign_results_exported", _campaign_id(camp["uuid"])) == 1


def test_export_audit_failure_503(client, env, monkeypatch):
    camp = _create(client, env)

    def boom(**_kw):
        raise AuditError("injected")

    monkeypatch.setattr(storage_supervisor, "record_event", boom)
    r = client.get(f"{BASE}/{camp['uuid']}/export.xlsx", headers=env["headers"])
    assert r.status_code == 503
    assert not r.headers["content-type"].startswith("application/vnd")


# ─── удаление ─────────────────────────────────────────────────────────────────

def test_delete_response_removes_consent(client, env):
    camp = _create(client, env)
    _submit(client, _token(camp))
    with SessionLocal() as db:
        resp = db.query(CampaignResponse).filter(
            CampaignResponse.campaign_id == _campaign_id(camp["uuid"])).one()
        resp_uuid, resp_id, consent_id = str(resp.uuid), resp.id, resp.consent_record_id
    url = f"{BASE}/{camp['uuid']}/responses/{resp_uuid}"
    assert client.delete(url, headers=env["headers"]).status_code == 204
    with SessionLocal() as db:
        assert db.get(CampaignResponse, resp_id) is None
        assert db.get(ConsentRecord, consent_id) is None
    assert _events("campaign_response_deleted", resp_id) == 1
    assert client.delete(url, headers=env["headers"]).status_code == 404


def test_delete_campaign_removes_everything(client, env):
    camp = _create(client, env)
    _submit(client, _token(camp))
    cid = _campaign_id(camp["uuid"])
    with SessionLocal() as db:
        consent_id = db.query(CampaignResponse.consent_record_id) \
            .filter(CampaignResponse.campaign_id == cid).scalar()
    assert client.delete(f"{BASE}/{camp['uuid']}", headers=env["headers"]).status_code == 204
    with SessionLocal() as db:
        assert db.get(TestCampaign, cid) is None
        assert db.query(CampaignResponse).filter(
            CampaignResponse.campaign_id == cid).count() == 0
        assert db.get(ConsentRecord, consent_id) is None
    assert _events("test_campaign_deleted", cid) == 1
    assert client.get(f"/api/public/campaigns/{_token(camp)}").status_code == 404


def test_delete_audit_failure_keeps_data(client, env, monkeypatch):
    camp = _create(client, env)
    _submit(client, _token(camp))
    cid = _campaign_id(camp["uuid"])

    def boom(**_kw):
        raise AuditError("injected")

    monkeypatch.setattr(storage_supervisor, "record_event", boom)
    r = client.delete(f"{BASE}/{camp['uuid']}", headers=env["headers"])
    assert r.status_code == 503
    with SessionLocal() as db:
        assert db.get(TestCampaign, cid) is not None
        assert db.query(CampaignResponse).filter(
            CampaignResponse.campaign_id == cid).count() == 1


# ─── список ───────────────────────────────────────────────────────────────────

def test_list_keyset_newest_first(client, env):
    created = [_create(client, env, title=f"integ list {i}")["uuid"] for i in range(3)]
    r = client.get(BASE, headers=env["headers"], params={"size": 2})
    page = r.json()
    mine = [c["uuid"] for c in page["items"]]
    assert mine == [created[2], created[1]] and page["has_more"] is True
    assert page["items"][0]["link_path"].startswith("/test/")
    r = client.get(BASE, headers=env["headers"], params={"size": 2, "before": mine[-1]})
    assert r.json()["items"][0]["uuid"] == created[0]


# ─── первичная обработка (экран результатов) ──────────────────────────────────

def _submit_with(client, token: str, name: str, yes: set, **fields) -> None:
    body = _payload(client, token, yes=yes, full_name=name, **fields)
    r = client.post(f"/api/public/campaigns/{token}/submit", json=body)
    assert r.status_code == 201, r.text


def test_results_levels_types_summary_and_filters(client, env):
    from app.tests.profiles import ito_sobchik as ito
    camp = _create(client, env)
    token = _token(camp)
    # «Неуравновешенный»: VIII и III на максимум; достоверно.
    unbalanced = set(ito.KEY["VIII"][0]) | set(ito.KEY["III"][0])
    _submit_with(client, token, "Участник Тип", unbalanced, gender="male",
                 faculty_code="law")
    # Недостоверно: L = 9.
    _submit_with(client, token, "Участник Ложь", set(ito.KEY["L"][0]))
    _submit_with(client, token, "Участник Норма", set())

    url = f"{BASE}/{camp['uuid']}/results"
    r = client.get(url, headers=env["headers"])
    assert r.status_code == 200, r.text
    _no_store(r)
    data = r.json()
    assert data["profile"] == "ito_sobchik" and data["total_all"] == 3
    assert [s["code"] for s in data["scales"]] == list(ito.EXPORT_SCALE_ORDER)
    assert len(data["type_names"]) == 6
    assert {f["code"] for f in data["faculties"]} == {"law", "accounting_finance"}
    by_name = {i["full_name"]: i for i in data["items"]}
    typed = by_name["Участник Тип"]
    assert typed["scores"]["VIII"] == 9 and typed["levels"]["VIII"] == "maladaptive"
    assert typed["types"] == ["Неуравновешенный"] and typed["is_valid"] is True
    assert typed["faculty_label"] == "Юридический факультет"
    assert by_name["Участник Ложь"]["is_valid"] is False
    assert by_name["Участник Ложь"]["levels"]["L"] == "invalid"
    s = data["summary"]
    assert (s["total"], s["valid"], s["invalid"], s["with_type"]) == (3, 2, 1, 1)
    assert {t["name"]: t["count"] for t in s["types"]}["Неуравновешенный"] == 1
    assert _events("campaign_results_read", _campaign_id(camp["uuid"])) == 1

    def names(params):
        res = client.get(url, headers=env["headers"], params=params).json()
        return sorted(i["full_name"] for i in res["items"]), res["summary"]["total"]

    assert names({"validity": "invalid"}) == (["Участник Ложь"], 1)
    assert names({"type": "Неуравновешенный"}) == (["Участник Тип"], 1)
    assert names({"type": "__none__"})[1] == 2
    assert names({"gender": "male", "faculty_code": "law"}) == (["Участник Тип"], 1)
    r = client.get(url, headers=env["headers"], params={"gender": "x"})
    assert r.status_code == 422


def test_results_empty_campaign_no_event(client, env):
    camp = _create(client, env)
    r = client.get(f"{BASE}/{camp['uuid']}/results", headers=env["headers"])
    assert r.status_code == 200
    assert r.json()["items"] == [] and r.json()["summary"]["total"] == 0
    assert _events("campaign_results_read", _campaign_id(camp["uuid"])) == 0


def test_results_audit_failure_503_without_names(client, env, monkeypatch):
    camp = _create(client, env)
    _submit(client, _token(camp), "Секретный Участник")

    def boom(**_kw):
        raise AuditError("injected")

    monkeypatch.setattr(storage_supervisor, "record_event", boom)
    r = client.get(f"{BASE}/{camp['uuid']}/results", headers=env["headers"])
    assert r.status_code == 503
    assert "Секретный" not in r.text


def test_results_forbidden_for_admin(client, env):
    camp = _create(client, env)
    headers, _ = _login(client, "admin")
    assert client.get(f"{BASE}/{camp['uuid']}/results", headers=headers).status_code == 403
