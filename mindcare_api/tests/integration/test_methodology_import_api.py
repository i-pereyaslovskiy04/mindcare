"""
ADR-037, этап 5: шаблон xlsx, выгрузка и импорт методики.

  - шаблон скачивается admin/supervisor и психологом, no-store;
  - ИТО: выгрузка → импорт → идентичные вопросы, ключ, пороги и правила;
    импорт — всегда черновик, событие test_imported; dry_run ничего не создаёт;
  - ошибки — с адресом лист/строка/колонка, без содержимого ячеек;
  - не xlsx / больше 2 МБ — 422 / 413; психолог выгружает только своё.

Требует disposable PostgreSQL (Stage 1 isolated runner).
"""
import io
import uuid

import pytest
from openpyxl import load_workbook

from app.db.models import AuditLog
from app.db.models import Test as TestModel
from app.db.session import SessionLocal
from app.tests.profiles.ito_seed import ensure_ito_test
from tests.integration.assignments_helpers import user
from tests.integration.staff_results_helpers import auth

ADMIN = "/api/admin/tests"
PSY = "/api/psychologist/tests"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@pytest.fixture
def created():
    uuids = []
    yield uuids
    with SessionLocal() as db:
        for u in uuids:
            t = db.query(TestModel).filter(TestModel.uuid == uuid.UUID(u)).first()
            if t is not None:
                db.delete(t)
        db.commit()


def _upload(client, token, base, content, dry_run=False):
    return client.post(f"{base}/import", headers=auth(token),
                       params={"dry_run": str(dry_run).lower()},
                       files={"file": ("m.xlsx", content, XLSX)})


def _structure(test):
    return [(q["question_order"], q["question_text"], q["question_type"],
             (q["config"] or {}).get("scale"),
             [(o["option_text"], o["value_score"]) for o in q["options"]])
            for q in sorted(test["questions"], key=lambda q: q["question_order"])]


def _interps(test):
    return sorted((i["scale_name"] or "", i["min_score"], i["max_score"], i["label"])
                  for i in test["interpretations"])


@pytest.mark.parametrize("roles, base", [(["supervisor"], ADMIN), (["psychologist"], PSY)])
def test_template_download(client, roles, base):
    _, token = user(client, roles)
    r = client.get(f"{base}/methodology-template.xlsx", headers=auth(token))
    assert r.status_code == 200
    assert r.headers["content-type"].startswith(XLSX)
    assert "no-store" in r.headers["cache-control"]
    wb = load_workbook(io.BytesIO(r.content), read_only=True)
    assert {"Методика", "Вопросы", "Ключ", "Шкалы", "Уровни", "Типы"} <= set(wb.sheetnames)


def test_ito_roundtrip(client, created):
    _, token = user(client, ["admin"])
    with SessionLocal() as db:
        ito, _ = ensure_ito_test(db)
        db.commit()
        ito_uuid = str(ito.uuid)
    source = client.get(f"{ADMIN}/{ito_uuid}", headers=auth(token)).json()
    r = client.get(f"{ADMIN}/{ito_uuid}/methodology.xlsx", headers=auth(token))
    assert r.status_code == 200, r.text
    content = r.content

    with SessionLocal() as db:
        before = db.query(TestModel).count()
    dry = _upload(client, token, ADMIN, content, dry_run=True)
    assert dry.status_code == 200, dry.text
    report = dry.json()
    assert report["ok"] is True and report["errors"] == [] and report["warnings"] == []
    assert report["summary"]["questions"] == 91 and report["summary"]["types"] == 6
    with SessionLocal() as db:
        assert db.query(TestModel).count() == before        # dry_run не создаёт

    r = _upload(client, token, ADMIN, content)
    assert r.status_code == 201, r.text
    new_uuid = r.json()["test_uuid"]
    created.append(new_uuid)
    imported = client.get(f"{ADMIN}/{new_uuid}", headers=auth(token)).json()
    assert imported["status"] == "draft"
    assert imported["campaign_only"] is True
    assert _structure(imported) == _structure(source)
    assert _interps(imported) == _interps(source)
    assert imported["scoring_rules"] == source["scoring_rules"]
    assert imported["lineage_uuid"] != source["lineage_uuid"]   # новая методика
    with SessionLocal() as db:
        tid = db.query(TestModel.id).filter(TestModel.uuid == uuid.UUID(new_uuid)).scalar()
        events = [e.event_type for e in db.query(AuditLog).filter(
            AuditLog.entity_type == "test", AuditLog.entity_id == tid)]
        assert events == ["test_imported"]
        assert db.query(AuditLog).filter(AuditLog.entity_type == "test",
                                         AuditLog.entity_id == tid).one().log_metadata == {}


def test_errors_have_address_without_cell_values(client):
    _, token = user(client, ["supervisor"])
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Методика"
    ws.append(["Поле", "Значение"])
    ws.append(["Название", "Секретная-метка-xyz"])
    opts = wb.create_sheet("Варианты ответа")
    opts.append(["Порядок", "Текст"])
    opts.append([1, "Да"])
    opts.append([2, "Нет"])
    qs = wb.create_sheet("Вопросы")
    qs.append(["№", "Текст"])
    qs.append([1, "Вопрос"])
    qs.append([3, "Пропуск номера"])
    key = wb.create_sheet("Ключ")
    key.append(["Шкала", "№", "Вариант", "Балл"])
    key.append(["A", 9, 1, 1])
    buf = io.BytesIO()
    wb.save(buf)
    r = _upload(client, token, ADMIN, buf.getvalue(), dry_run=True)
    assert r.status_code == 200
    errors = r.json()["errors"]
    assert {"sheet": "Вопросы", "row": 3, "column": "A",
            "message": "номера должны идти подряд: ожидалось 2"} in errors
    assert any(e["sheet"] == "Ключ" and e["row"] == 2 and e["column"] == "B" for e in errors)
    assert "Секретная-метка-xyz" not in r.text
    r = _upload(client, token, ADMIN, buf.getvalue())
    assert r.status_code == 422 and r.json()["ok"] is False


def test_bad_files(client):
    _, token = user(client, ["admin"])
    r = _upload(client, token, ADMIN, b"not a zip at all", dry_run=True)
    assert r.status_code == 422 and r.json()["detail"] == "Это не файл xlsx"
    r = _upload(client, token, ADMIN, b"PK\x03\x04" + b"0" * (2 * 1024 * 1024 + 10))
    assert r.status_code == 413


def test_psychologist_import_and_own_export(client, created):
    _, ptoken = user(client, ["psychologist"])
    _, other = user(client, ["psychologist"])
    _, atoken = user(client, ["admin"])
    with SessionLocal() as db:
        ito, _ = ensure_ito_test(db)
        db.commit()
        ito_uuid = str(ito.uuid)
    content = client.get(f"{ADMIN}/{ito_uuid}/methodology.xlsx", headers=auth(atoken)).content
    r = _upload(client, ptoken, PSY, content)
    assert r.status_code == 201, r.text
    mine = r.json()["test_uuid"]
    created.append(mine)
    got = client.get(f"{PSY}/{mine}", headers=auth(ptoken)).json()
    assert got["status"] == "draft"
    assert client.get(f"{PSY}/{mine}/methodology.xlsx", headers=auth(ptoken)).status_code == 200
    assert client.get(f"{PSY}/{mine}/methodology.xlsx", headers=auth(other)).status_code == 404
    assert client.get(f"{PSY}/{ito_uuid}/methodology.xlsx", headers=auth(ptoken)).status_code == 404


def test_export_not_representable(client, created):
    _, token = user(client, ["admin"])
    r = client.post(ADMIN, headers=auth(token), json={
        "title": f"integ_IMP {uuid.uuid4().hex[:6]}", "status": "draft",
        "questions": [{"question_text": "Оцените", "question_order": 1,
                       "question_type": "scale", "is_required": True,
                       "config": {"min": 0, "max": 5}, "options": []}]})
    assert r.status_code == 201, r.text
    created.append(r.json()["uuid"])
    r = client.get(f"{ADMIN}/{r.json()['uuid']}/methodology.xlsx", headers=auth(token))
    assert r.status_code == 422
