"""
Health-check (corrective pass 2026-11-02):

  * публичный GET /api/health без входа — только {"status": "ok"} (200); при
    недоступной БД — 503 {"status": "unavailable"}; ни ревизии, ни числа
    таблиц, ни текста исключения; no-store;
  * GET /api/admin/health — только admin: ревизия, head, таблицы; аноним 401,
    другие роли 403; при сбое — только класс исключения, без str(exc).
Скрипты запуска (start.ps1/start.sh) ждут HTTP 200 этого адреса — контракт
«200 = готов» сохранён.
"""
import app.db.init_db as init_db
from tests.integration.assignments_helpers import auth, user

SECRET = "postgresql://user:p4ss@db-host:5432/secretdb"


class _BrokenEngine:
    def connect(self):
        raise RuntimeError(SECRET)


def test_public_health_is_minimal(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
    assert "no-store" in r.headers["cache-control"]


def test_public_health_reports_503_without_details(client, monkeypatch):
    import app.db.session as session_mod
    monkeypatch.setattr(session_mod, "engine", _BrokenEngine())
    r = client.get("/api/health")
    assert r.status_code == 503
    assert r.json() == {"status": "unavailable"}
    assert SECRET not in r.text


def test_admin_health_is_admin_only(client):
    assert client.get("/api/admin/health").status_code == 401
    for roles in (["supervisor"], ["psychologist"], ["student"]):
        _, token = user(client, roles)
        assert client.get("/api/admin/health", headers=auth(token)).status_code == 403
    _, admin_token = user(client, ["admin"])
    r = client.get("/api/admin/health", headers=auth(admin_token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok" and body["revision_ok"] is True
    assert body["revision"] in body["head_revisions"] and body["tables"] > 0
    assert "no-store" in r.headers["cache-control"]


def test_admin_health_error_has_class_only(client, monkeypatch):
    _, admin_token = user(client, ["admin"])
    import app.db.session as session_mod
    monkeypatch.setattr(session_mod, "engine", _BrokenEngine())
    r = client.get("/api/admin/health", headers=auth(admin_token))
    monkeypatch.undo()
    assert r.status_code == 503
    assert r.json() == {"status": "error", "db": "unavailable", "error_class": "RuntimeError"}
    assert SECRET not in r.text


def test_ping_and_diagnostics_contract():
    assert init_db.ping() is True
    assert set(init_db.diagnostics()) == {
        "status", "db", "revision", "head_revisions", "revision_ok", "tables",
    }
