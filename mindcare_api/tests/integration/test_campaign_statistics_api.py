"""
Integration: GET /api/supervisor/campaigns/{uuid}/statistics (ТЗ редактора
методик, этап 2, §7).

Покрывает: меньше 5 участников — без распределений; с 5 — ответы по вопросам
и распределение баллов; фильтр; ФИО в ответе нет; событие
campaign_results_read до отдачи; сбой аудита — 503 без данных; доступ —
только супервизор; лист «Статистика по вопросам» в xlsx.
"""
import io

from openpyxl import load_workbook

from app.audit import AuditError
from app.campaigns import storage_supervisor
from tests.integration.test_campaign_supervisor_api import (  # noqa: F401  (fixture env)
    BASE, _campaign_id, _create, _events, _login, _submit, _token, env,
)

NAMES = ["Анна Первая", "Борис Второй", "Вера Третья", "Глеб Четвёртый", "Дина Пятая"]


def test_statistics_threshold_filters_and_audit(client, env):
    c = _create(client, env)
    cid, token = _campaign_id(c["uuid"]), _token(c)
    url = f"{BASE}/{c['uuid']}/statistics"
    for name in NAMES[:4]:
        _submit(client, token, name)
    r = client.get(url, headers=env["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 4 and body["too_few"] is True
    assert body["questions"] == [] and body["scales"] == []
    assert sum(d["count"] for d in body["by_day"]) == 4
    assert r.headers.get("cache-control") == "no-store, private"

    _submit(client, token, NAMES[4])
    before = _events("campaign_results_read", cid)
    r = client.get(url, headers=env["headers"])
    body = r.json()
    assert body["too_few"] is False and len(body["questions"]) == 91
    q1 = body["questions"][0]
    assert q1["answered"] == 5 and sum(o["count"] for o in q1["options"]) == 5
    assert {s["scale"] for s in body["scales"]} >= {"L", "F", "I"}
    assert _events("campaign_results_read", cid) == before + 1
    for name in NAMES:
        assert name not in r.text

    r = client.get(url, headers=env["headers"], params={"gender": "male"})
    assert r.json()["total"] == 0 and r.json()["too_few"] is True


def test_statistics_audit_failure_503(client, env, monkeypatch):
    c = _create(client, env)
    _submit(client, _token(c))

    def boom(*a, **k):
        raise AuditError("x")
    monkeypatch.setattr(storage_supervisor, "_record_read", boom)
    r = client.get(f"{BASE}/{c['uuid']}/statistics", headers=env["headers"])
    assert r.status_code == 503
    assert "by_day" not in r.text


def test_statistics_forbidden_for_psychologist(client, env):
    c = _create(client, env)
    headers, _ = _login(client, "psychologist")
    assert client.get(f"{BASE}/{c['uuid']}/statistics", headers=headers).status_code == 403


def test_export_has_question_stats_sheet(client, env):
    c = _create(client, env)
    _submit(client, _token(c))
    r = client.get(f"{BASE}/{c['uuid']}/export.xlsx", headers=env["headers"])
    assert r.status_code == 200
    wb = load_workbook(io.BytesIO(r.content), read_only=True)
    assert "Статистика по вопросам" in wb.sheetnames
