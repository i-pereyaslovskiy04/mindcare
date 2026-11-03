"""
Integration: staff-доступ к результатам психодиагностики (Этап E, ADR-016;
дополнение 2026-10-29 — карточка клиента у психолога).

Покрывает:
  - psychologist — список, деталь и ответы только при СТРОГОМ активном
    сопровождении с активным клиентом (клиент может иметь staff-роли); любой
    отказ — 404 + test_result_read_failed (access_denied), без content_read и
    без расшифровки ответов;
  - ответы: все типы, пропуск («Нет ответа»), медиа вопроса и выбранного
    варианта, порядок теста; value_score/config/id/ciphertext не отдаются;
  - исторический контракт: название — актуальное, баллы/интерпретации/ответы —
    сохранённые; снятие теста с публикации доступ не убирает;
  - больше 20 прохождений и повторы — пагинация с устойчивой сортировкой;
  - supervisor — «чистый» активный студент (список и деталь), ответов нет;
  - admin и impersonation — 403; X-Active-Role у multi-role;
  - fail-closed аудит (503 без содержимого), no-store, отсутствие значений в
    журналах и логах.

Требует disposable PostgreSQL (Stage 1 isolated runner).
"""
import logging
import uuid

import pytest
from sqlalchemy import text

import app.tests.service as tests_service
import app.tests.storage as tests_storage
from app.audit import AuditStorageError
from app.db.models import AuditLog, StudentAnswer
from app.db.models import Test as TestModel
from app.db.models import TestInterpretation as InterpretationModel
from app.db.session import SessionLocal
from tests.integration.assignments_helpers import (
    audit_since, blob, end_engagement, engage, marks, set_user, user, uuid_of,
)
from tests.integration.staff_results_helpers import (  # noqa: F401 (fixture)
    NO_STORE, OPT_MEDIA_URL, OTHER_OPT_MEDIA_URL, Q_MEDIA_URL, SECRET_TEXT, auth,
    content_reads, full_test, now, result_id, submit,
)

LIST = "/api/staff/test-results"


def _detail(client, token, r_uuid, role=None):
    headers = auth(token)
    if role:
        headers["X-Active-Role"] = role
    return client.get(f"{LIST}/{r_uuid}", headers=headers)


def _answers(client, token, r_uuid, role=None):
    headers = auth(token)
    if role:
        headers["X-Active-Role"] = role
    return client.get(f"{LIST}/{r_uuid}/answers", headers=headers)


def _list(client, token, client_uid, role=None, **params):
    headers = auth(token)
    if role:
        headers["X-Active-Role"] = role
    return client.get(LIST, headers=headers,
                      params={"student_uuid": uuid_of(client_uid), **params})


def _read_failures(m, actor_uid):
    rows = [r for r in audit_since(m) if r.event_type == "test_result_read_failed"]
    for r in rows:
        assert (r.user_id, r.user_role) == (actor_uid, "psychologist")
        assert r.outcome == "failure" and r.failure_reason_code == "access_denied"
        assert r.entity_type is None and r.log_metadata == {}
    return rows


@pytest.fixture
def scenario(client, full_test):
    """Клиент, психолог строгого сопровождения и одно прохождение всех типов."""
    admin_id, _ = user(client, ["admin"])
    sid, stoken = user(client, ["student"])
    pid, ptoken = user(client, ["psychologist", "student"])
    eng = engage(pid, sid)
    test = full_test(admin_id)
    r_uuid = submit(client, stoken, test)
    return {"sid": sid, "stoken": stoken, "pid": pid, "ptoken": ptoken, "eng": eng,
            "test": test, "r": r_uuid}


# ── ответы: все типы, пропуск, медиа, порядок ────────────────────────────────

def test_psychologist_reads_answers_of_all_types_with_media(client, scenario):
    s = scenario
    m = marks()
    r = _answers(client, s["ptoken"], s["r"])
    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == NO_STORE
    body = r.json()
    assert body["result_uuid"] == s["r"] and body["order"] == "test_order"
    assert body["test_title"] == s["test"]["title"]
    items = body["items"]
    assert [i["position"] for i in items] == [1, 2, 3, 4, 5]
    assert [i["question_type"] for i in items] == [
        "single_choice", "multiple_choice", "scale", "free_text", "single_choice"]

    single = items[0]
    assert single["answered"] is True
    assert single["media"] == [{
        "uuid": single["media"][0]["uuid"], "url": Q_MEDIA_URL, "kind": "image",
        "caption": "Подпись картинки",
    }]
    assert [o["option_text"] for o in single["options"]] == ["Хорошо"]
    assert [md["url"] for md in single["options"][0]["media"]] == [OPT_MEDIA_URL]
    assert OTHER_OPT_MEDIA_URL not in r.text          # медиа невыбранного варианта
    assert "Плохо" not in r.text                      # текст невыбранного варианта

    multi = items[1]
    assert [o["option_text"] for o in multi["options"]] == ["Учёба", "Друзья"]  # option_order
    scale = items[2]
    assert (scale["scale_value"], scale["scale_min"], scale["scale_max"]) == (4, 1, 5)
    assert scale["options"] == []
    assert items[3]["free_text"] == SECRET_TEXT and items[3]["answered"] is True
    skipped = items[4]
    assert skipped["answered"] is False and skipped["options"] == []
    assert skipped["free_text"] is None and skipped["scale_value"] is None

    for forbidden in ("value_score", "config", "weight", "question_id", "option_id",
                      "enc:v1:", "time_spent"):
        assert forbidden not in r.text

    (event,) = audit_since(m)
    assert event.event_type == "test_result_content_read"
    assert (event.user_id, event.user_role) == (s["pid"], "psychologist")
    assert (event.entity_type, event.entity_id) == ("test_result", result_id(s["r"]))
    assert event.outcome == "success" and event.log_metadata == {}
    for leak in (SECRET_TEXT, Q_MEDIA_URL, "Хорошо"):
        assert leak not in blob(event)


def test_free_text_is_stored_encrypted(scenario):
    with SessionLocal() as db:
        encs = [a.free_text_answer_enc for a in db.query(StudentAnswer).filter(
            StudentAnswer.test_result_id == result_id(scenario["r"]),
            StudentAnswer.free_text_answer_enc.is_not(None))]
    assert len(encs) == 1 and encs[0].startswith("enc:v1:")
    assert SECRET_TEXT not in encs[0]


def test_psychologist_detail_and_list(client, scenario):
    s = scenario
    m = marks()
    r = _detail(client, s["ptoken"], s["r"])
    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == NO_STORE
    assert r.json()["total_score"] is not None
    (event,) = audit_since(m)
    assert event.event_type == "test_result_content_read" and event.user_role == "psychologist"

    m = marks()
    r = _list(client, s["ptoken"], s["sid"])
    assert r.status_code == 200 and r.headers["cache-control"] == NO_STORE
    (item,) = r.json()["items"]
    assert set(item) == {"uuid", "test_title", "submitted_at"}
    assert audit_since(m) == []                       # список — без события


# ── пагинация: больше 20 и повторы ───────────────────────────────────────────

def test_more_than_twenty_repeated_results_paginate_stably(client, scenario):
    s = scenario
    for _ in range(21):                               # +21 к первому = 22 повтора
        submit(client, s["stoken"], s["test"])
    first = _list(client, s["ptoken"], s["sid"], page=1, size=20).json()
    second = _list(client, s["ptoken"], s["sid"], page=2, size=20).json()
    assert first["total"] == second["total"] == 22
    assert len(first["items"]) == 20 and len(second["items"]) == 2
    uuids = [i["uuid"] for i in first["items"] + second["items"]]
    assert len(set(uuids)) == 22
    stamps = [i["submitted_at"] for i in first["items"] + second["items"]]
    assert stamps == sorted(stamps, reverse=True)
    again = _list(client, s["ptoken"], s["sid"], page=1, size=20).json()
    assert [i["uuid"] for i in again["items"]] == uuids[:20]   # устойчивый порядок


# ── исторический контракт ────────────────────────────────────────────────────

def test_history_keeps_stored_values_and_current_title(client, scenario):
    s = scenario
    before = _detail(client, s["ptoken"], s["r"]).json()
    answers_before = _answers(client, s["ptoken"], s["r"]).json()["items"]
    new_title = f"integ_RENAMED {uuid.uuid4().hex[:6]}"
    with SessionLocal() as db:
        t = db.query(TestModel).filter(TestModel.uuid == uuid.UUID(s["test"]["uuid"])).one()
        t.title = new_title
        t.is_active = False
        t.status = "draft"
        db.query(InterpretationModel).filter(InterpretationModel.test_id == t.id).update({
            "min_score": 0, "max_score": 1, "label": "Новая метка",
            "recommendation": "Новая рекомендация",
        })
        db.commit()

    after = _detail(client, s["ptoken"], s["r"])
    assert after.status_code == 200, after.text
    body = after.json()
    assert body["test_title"] == new_title                        # название — актуальное
    for key in ("total_score", "max_possible", "scoring_used", "recommendations", "scales"):
        assert body[key] == before[key]                           # сохранённое, без пересчёта
    assert "Новая рекомендация" not in after.text
    answers_after = _answers(client, s["ptoken"], s["r"]).json()
    assert answers_after["test_title"] == new_title
    assert answers_after["items"] == answers_before
    (item,) = _list(client, s["ptoken"], s["sid"]).json()["items"]
    assert item["test_title"] == new_title


# ── отказы психологу: единый 404, без content_read и расшифровки ─────────────

@pytest.fixture
def decrypt_calls(monkeypatch):
    calls = []
    real = tests_storage.decrypt_text

    def _spy(value):
        calls.append(value)
        return real(value)

    monkeypatch.setattr(tests_storage, "decrypt_text", _spy)
    return calls


def _assert_all_denied(client, s, token, actor_uid, decrypt_calls, *, list_too=True):
    m = marks()
    responses = [_detail(client, token, s["r"]), _answers(client, token, s["r"])]
    if list_too:
        responses.append(_list(client, token, s["sid"]))
    for r in responses:
        assert r.status_code == 404, r.text
        assert r.json() == {"detail": "Результаты клиента недоступны"}
        assert r.headers["cache-control"] == NO_STORE
        assert SECRET_TEXT not in r.text and "total_score" not in r.text
    assert len(_read_failures(m, actor_uid)) == len(responses)
    assert [x for x in audit_since(m) if x.event_type == "test_result_content_read"] == []
    assert decrypt_calls == []


def test_foreign_psychologist_is_denied(client, scenario, decrypt_calls):
    other_pid, other_token = user(client, ["psychologist", "student"])
    _assert_all_denied(client, scenario, other_token, other_pid, decrypt_calls)


def test_unknown_result_uuid_is_denied(client, scenario):
    s = scenario
    m = marks()
    r = _detail(client, s["ptoken"], uuid.uuid4())
    assert r.status_code == 404 and len(_read_failures(m, s["pid"])) == 1


@pytest.mark.parametrize("status", ["completed", "transferred", "cancelled"])
def test_ended_engagement_denies_everything(client, scenario, decrypt_calls, status):
    s = scenario
    end_engagement(s["eng"], status=status)
    _assert_all_denied(client, s, s["ptoken"], s["pid"], decrypt_calls)


def test_active_status_with_ended_at_is_not_strict(client, scenario, decrypt_calls):
    s = scenario
    with SessionLocal() as db:
        db.execute(text("UPDATE therapy_engagements SET ended_at = now() WHERE id = :id"),
                   {"id": s["eng"]})
        db.commit()
    _assert_all_denied(client, s, s["ptoken"], s["pid"], decrypt_calls)


@pytest.mark.parametrize("change", ["inactive", "deleted"])
def test_disabled_client_denies_everything(client, scenario, decrypt_calls, change):
    s = scenario
    if change == "inactive":
        set_user(s["sid"], is_active=False)
    else:
        set_user(s["sid"], deleted_at=now())
    _assert_all_denied(client, s, s["ptoken"], s["pid"], decrypt_calls)


def test_transfer_moves_access_to_new_psychologist(client, scenario):
    import app.supervisor.service as sup_service
    s = scenario
    sup_id, _ = user(client, ["supervisor", "student"])
    new_pid, new_token = user(client, ["psychologist", "student"])
    sup_service.transfer_psychologist(s["eng"], new_pid, None, sup_id, "supervisor")
    assert _detail(client, s["ptoken"], s["r"]).status_code == 404
    assert _answers(client, new_token, s["r"]).status_code == 200


# ── клиент со staff-ролью, multi-role, supervisor ────────────────────────────

def test_staff_role_client_is_visible_to_own_psychologist(client, full_test):
    admin_id, _ = user(client, ["admin"])
    sid, stoken = user(client, ["student", "psychologist"])      # клиент со staff-ролью
    pid, ptoken = user(client, ["psychologist", "student"])
    engage(pid, sid)
    r_uuid = submit(client, stoken, full_test(admin_id))
    assert _list(client, ptoken, sid).status_code == 200
    assert _detail(client, ptoken, r_uuid).status_code == 200
    assert _answers(client, ptoken, r_uuid).status_code == 200
    _, sup_token = user(client, ["supervisor"])
    assert _list(client, sup_token, sid).status_code == 404   # supervisor: только чистый студент
    assert _detail(client, sup_token, r_uuid).status_code == 404


def test_multi_role_actor_uses_x_active_role(client, scenario):
    s = scenario
    both_id, both_token = user(client, ["psychologist", "supervisor", "student"])
    # без сопровождения с этим клиентом: как психолог — 404, как супервизор — деталь да
    m = marks()
    assert _detail(client, both_token, s["r"]).status_code == 404   # консервативно psychologist
    assert len(_read_failures(m, both_id)) == 1
    r = _detail(client, both_token, s["r"], role="supervisor")
    assert r.status_code == 200
    assert content_reads(s["r"])[-1].user_role == "supervisor"
    m = marks()
    r = _answers(client, both_token, s["r"], role="supervisor")
    assert r.status_code == 403 and r.headers["cache-control"] == NO_STORE
    assert audit_since(m) == []
    assert _detail(client, both_token, s["r"], role="admin").status_code == 403


def test_supervisor_reads_pure_student_detail_but_not_answers(client, scenario):
    s = scenario
    sup_id, sup_token = user(client, ["supervisor", "student"])
    m = marks()
    r = _detail(client, sup_token, s["r"])
    assert r.status_code == 200 and r.headers["cache-control"] == NO_STORE
    (event,) = audit_since(m)
    assert (event.user_id, event.user_role) == (sup_id, "supervisor")
    assert _answers(client, sup_token, s["r"]).status_code == 403
    (item,) = _list(client, sup_token, s["sid"]).json()["items"]
    assert set(item) == {"uuid", "test_title", "submitted_at"}


def test_supervisor_detail_of_staff_self_test_is_not_found(client, full_test):
    admin_id, _ = user(client, ["admin"])
    staff_id, staff_token = user(client, ["psychologist", "student"])
    r_uuid = submit(client, staff_token, full_test(admin_id))
    _, sup_token = user(client, ["supervisor"])
    m = marks()
    r = _detail(client, sup_token, r_uuid)
    assert r.status_code == 404 and "total_score" not in r.text
    assert audit_since(m) == []


def test_supervisor_detail_of_disabled_student_is_not_found(client, scenario):
    s = scenario
    set_user(s["sid"], is_active=False)
    _, sup_token = user(client, ["supervisor"])
    assert _detail(client, sup_token, s["r"]).status_code == 404


# ── admin, impersonation ─────────────────────────────────────────────────────

def test_admin_has_no_access(client, scenario):
    _, admin_token = user(client, ["admin"])
    for r in (_detail(client, admin_token, scenario["r"]),
              _answers(client, admin_token, scenario["r"]),
              _list(client, admin_token, scenario["sid"])):
        assert r.status_code == 403 and r.headers["cache-control"] == NO_STORE


def test_impersonation_is_forbidden(client, scenario):
    s = scenario
    _, admin_token = user(client, ["admin"])
    r = client.post(f"/api/admin/users/{uuid_of(s['pid'])}/impersonate",
                    headers=auth(admin_token))
    assert r.status_code == 200, r.text
    as_psych = r.json()["session_token"]
    m = marks()
    for resp in (_detail(client, as_psych, s["r"]), _answers(client, as_psych, s["r"]),
                 _list(client, as_psych, s["sid"])):
        assert resp.status_code == 403 and resp.headers["cache-control"] == NO_STORE
        assert SECRET_TEXT not in resp.text
    assert [x for x in audit_since(m) if x.event_type.startswith("test_result")] == []


# ── fail-closed аудит ────────────────────────────────────────────────────────

def test_audit_failure_returns_503_without_content(client, scenario, monkeypatch):
    s = scenario

    def _boom(**kwargs):
        raise AuditStorageError("audit storage failure")

    monkeypatch.setattr(tests_service, "record_event", _boom)
    for r in (_detail(client, s["ptoken"], s["r"]), _answers(client, s["ptoken"], s["r"])):
        assert r.status_code == 503, r.text
        assert r.headers["cache-control"] == NO_STORE
        assert SECRET_TEXT not in r.text and "total_score" not in r.text
        assert "Хорошо" not in r.text
    monkeypatch.undo()
    assert content_reads(s["r"]) == []


def test_invalid_uuid_is_422_without_echo(client, scenario):
    r = client.get(f"{LIST}/not-a-uuid-{SECRET_TEXT}", headers=auth(scenario["ptoken"]))
    assert r.status_code == 422 and r.headers["cache-control"] == NO_STORE
    assert SECRET_TEXT not in r.text


# ── утечки в журналы и логи ──────────────────────────────────────────────────

def test_values_never_reach_journals_or_logs(client, scenario, caplog, capsys):
    caplog.set_level(logging.DEBUG)
    s = scenario
    other_pid, other_token = user(client, ["psychologist", "student"])
    m = marks()
    _answers(client, s["ptoken"], s["r"])
    _detail(client, s["ptoken"], s["r"])
    _answers(client, other_token, s["r"])
    out = capsys.readouterr()
    for leak in (SECRET_TEXT, "Хорошо", Q_MEDIA_URL):
        assert leak not in caplog.text and leak not in out.out and leak not in out.err
    with SessionLocal() as db:
        rows = db.query(AuditLog).filter(AuditLog.id > m[0]).all()
        for row in rows:
            assert SECRET_TEXT not in blob(row) and Q_MEDIA_URL not in blob(row)
