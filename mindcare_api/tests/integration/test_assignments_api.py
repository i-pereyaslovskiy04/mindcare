"""
ADR-033 — gated integration: задания психолога клиенту (сквозные сценарии).

  * создание → список клиента → выполнение → список психолога → повторное
    чтение (сохранение после «перезагрузки»), шифрование text_enc;
  * идемпотентность (повтор — no-op без события) и конфликт completed ↔ cancelled;
  * материал: опубликованный / снятый / удалённый / несуществующий, скрытое
    содержимое не раскрывается;
  * keyset-пагинация без пропусков при переходах open → history и create;
  * content_read — только для заданий возвращённой страницы;
  * Cache-Control: no-store, private на всех ответах (вкл. ошибки и 422);
  * failure-injection: сбой аудита → 503 + rollback, сбой commit → 500 без
    *_failed; сбой content_read → 503 без текстов.
"""
import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import event
from sqlalchemy.exc import OperationalError

import app.assignments.service as assignments_service
import app.assignments.storage as assignments_storage
from app.audit.contracts import AuditStorageError
from app.core.encryption import ENCRYPTION_PREFIX
from app.db.session import SessionLocal, engine
from tests.integration.assignments_helpers import (  # noqa: F401 — fixture articles
    NO_STORE, SECRET, articles, assert_failure_row, assert_success_row, audit_since,
    auth, cancel, client_url, complete, create, create_ok, end_engagement, engage,
    marks, my, row, rows_since, set_article, user,
)


@pytest.fixture
def pair(client):
    """Клиент (student) и психолог со строгим активным сопровождением."""
    sid, stoken = user(client, ["student"])
    pid, ptoken = user(client, ["psychologist", "student"])
    eng_id = engage(pid, sid)
    return {"sid": sid, "stoken": stoken, "pid": pid, "ptoken": ptoken, "eng": eng_id}


def _psych_list(client, p, **params):
    return client.get(client_url(p["sid"]), headers=auth(p["ptoken"]), params=params)


# ── сквозной сценарий ─────────────────────────────────────────────────────────

def test_full_flow_create_complete_and_persist(client, pair):
    p = pair
    due = (date.today() + timedelta(days=3)).isoformat()
    m = marks()
    r = create(client, p["ptoken"], p["sid"], text=f"  {SECRET}  ", due_date=due)
    assert r.status_code == 201 and r.headers["cache-control"] == NO_STORE
    body = r.json()
    assert body["status"] == "active" and body["changed"] is True
    assert "text" not in body                         # мутация без текста
    a_uuid = body["uuid"]

    stored = row(a_uuid)
    assert stored.text_enc.startswith(ENCRYPTION_PREFIX) and SECRET not in stored.text_enc
    assert stored.engagement_id == p["eng"] and stored.due_date.isoformat() == due
    rows = audit_since(m)
    (created,) = [r for r in rows if r.event_type.startswith("assignment")]
    # кроме создания — только system-беседа клиента для уведомления о задании
    assert {r.event_type for r in rows if r is not created} <= {"system_conversation_created"}
    assert_success_row(created, "assignment_created", p["pid"], "psychologist", a_uuid)

    # клиент видит задание (без content_read: свои данные)
    m = marks()
    r = my(client, p["stoken"])
    assert r.status_code == 200 and r.headers["cache-control"] == NO_STORE
    (item,) = r.json()["items"]
    assert item["text"] == SECRET and item["can_complete"] is True
    assert item["due_date"] == due and item["engagement_active"] is True
    assert item["psychologist_name"]
    assert audit_since(m) == []
    summary = client.get("/api/assignments/my/summary", headers=auth(p["stoken"])).json()
    assert summary == {"open_count": 1, "completed_count": 0, "total_count": 1}

    # выполнение
    m = marks()
    r = complete(client, p["stoken"], a_uuid)
    assert r.status_code == 200 and r.json()["status"] == "completed"
    assert r.json()["changed"] is True and r.json()["completed_at"]
    rows = audit_since(m)
    (done,) = [r for r in rows if r.event_type.startswith("assignment")]
    # кроме перехода — только создание system-беседы психолога для уведомления
    assert {r.event_type for r in rows if r is not done} <= {"system_conversation_created"}
    assert_success_row(done, "assignment_completed", p["sid"], "student", a_uuid)

    # «перезагрузка»: состояние читается заново из БД
    assert my(client, p["stoken"]).json()["items"] == []
    (hist,) = my(client, p["stoken"], view="history").json()["items"]
    assert hist["status"] == "completed" and hist["can_complete"] is False
    summary = client.get("/api/assignments/my/summary", headers=auth(p["stoken"])).json()
    assert summary == {"open_count": 0, "completed_count": 1, "total_count": 1}

    # психолог видит статус; чтение — под content_read
    m = marks()
    r = _psych_list(client, p)
    assert r.status_code == 200 and r.headers["cache-control"] == NO_STORE
    (pitem,) = r.json()["items"]
    assert pitem["status"] == "completed" and pitem["text"] == SECRET
    assert pitem["can_cancel"] is False
    (read,) = audit_since(m)
    assert_success_row(read, "assignment_content_read", p["pid"], "psychologist", a_uuid)


def test_repeat_complete_and_cancel_are_noops_without_events(client, pair):
    p = pair
    done_uuid = create_ok(client, p["ptoken"], p["sid"])
    assert complete(client, p["stoken"], done_uuid).status_code == 200
    m = marks()
    r = complete(client, p["stoken"], done_uuid)
    assert r.status_code == 200 and r.json()["changed"] is False
    assert audit_since(m) == []

    gone_uuid = create_ok(client, p["ptoken"], p["sid"])
    assert cancel(client, p["ptoken"], gone_uuid).json()["changed"] is True
    m = marks()
    r = cancel(client, p["ptoken"], gone_uuid)
    assert r.status_code == 200 and r.json()["changed"] is False
    assert audit_since(m) == []


def test_completed_and_cancelled_never_overwrite_each_other(client, pair):
    p = pair
    done_uuid = create_ok(client, p["ptoken"], p["sid"])
    assert complete(client, p["stoken"], done_uuid).status_code == 200
    m = marks()
    r = cancel(client, p["ptoken"], done_uuid)
    assert r.status_code == 409 and r.headers["cache-control"] == NO_STORE
    assert r.json() == {"detail": r.json()["detail"], "code": "assignment_finalized",
                        "current_status": "completed"}
    (fail,) = audit_since(m)
    assert_failure_row(fail, "assignment_cancel_failed", p["pid"], "psychologist",
                       "assignment_finalized")
    assert row(done_uuid).status == "completed"

    gone_uuid = create_ok(client, p["ptoken"], p["sid"])
    assert cancel(client, p["ptoken"], gone_uuid).status_code == 200
    m = marks()
    r = complete(client, p["stoken"], gone_uuid)
    assert r.status_code == 409 and r.json()["current_status"] == "cancelled"
    (fail,) = audit_since(m)
    assert_failure_row(fail, "assignment_complete_failed", p["sid"], "student",
                       "assignment_finalized")
    stored = row(gone_uuid)
    assert stored.status == "cancelled" and stored.completed_at is None


# ── материал ──────────────────────────────────────────────────────────────────

def test_material_lifecycle_hides_unpublished_content(client, pair, articles):
    p = pair
    art = articles(title="integ_article_visible")
    a_uuid = create_ok(client, p["ptoken"], p["sid"], article_uuid=art["uuid"])
    (item,) = my(client, p["stoken"]).json()["items"]
    assert item["material"] == {"uuid": art["uuid"], "title": "integ_article_visible"}
    assert item["material_unavailable"] is False

    # снят с публикации: задание сохраняется, материал не раскрывается
    set_article(art["id"], is_published=False, title="integ_article_hidden_draft")
    for r in (my(client, p["stoken"]), _psych_list(client, p)):
        (it,) = r.json()["items"]
        assert it["uuid"] == a_uuid
        assert it["material"] is None and it["material_unavailable"] is True
        assert "integ_article_hidden_draft" not in r.text and art["uuid"] not in r.text

    # удалён мягко — то же
    set_article(art["id"], is_published=True, deleted_at=_now())
    (it,) = my(client, p["stoken"]).json()["items"]
    assert it["material"] is None and it["material_unavailable"] is True


@pytest.mark.parametrize("kind", ["unpublished", "deleted", "missing"])
def test_cannot_attach_unavailable_material(client, pair, articles, kind):
    p = pair
    if kind == "missing":
        article_uuid = str(uuid.uuid4())
    else:
        article_uuid = articles(published=(kind != "unpublished"),
                                deleted=(kind == "deleted"))["uuid"]
    m = marks()
    r = create(client, p["ptoken"], p["sid"], article_uuid=article_uuid)
    assert r.status_code == 422 and r.headers["cache-control"] == NO_STORE
    assert r.json()["code"] == "assignment_material_unavailable"
    assert SECRET not in r.text
    (fail,) = audit_since(m)
    assert_failure_row(fail, "assignment_create_failed", p["pid"], "psychologist",
                       "material_unavailable")
    assert my(client, p["stoken"]).json()["items"] == []


# ── валидация ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text, code", [("   ", "required"), ("x" * 4001, "too_long"),
                                        ("bad\u0000char", "invalid_characters")])
def test_semantic_validation_records_invalid_request(client, pair, text, code):
    p = pair
    m = marks()
    r = create(client, p["ptoken"], p["sid"], text=text)
    assert r.status_code == 422 and r.headers["cache-control"] == NO_STORE
    assert r.json()["errors"] == [{"field": "text", "code": code}]
    (fail,) = audit_since(m)
    assert_failure_row(fail, "assignment_create_failed", p["pid"], "psychologist",
                       "invalid_request")


def test_form_errors_are_sanitized_and_not_audited(client, pair):
    p = pair
    m = marks()
    r = client.post(client_url(p["sid"]), headers=auth(p["ptoken"]),
                    json={"text": SECRET, "due_date": SECRET, SECRET: 1})
    assert r.status_code == 422 and r.headers["cache-control"] == NO_STORE
    assert SECRET not in r.text
    assert audit_since(m) == []


def test_past_due_date_is_allowed_and_overdue_is_computed(client, pair):
    p = pair
    past = (date.today() - timedelta(days=5)).isoformat()
    create_ok(client, p["ptoken"], p["sid"], due_date=past)
    (item,) = my(client, p["stoken"]).json()["items"]
    assert item["due_date"] == past and item["is_overdue"] is True
    m = marks()
    my(client, p["stoken"])
    assert rows_since(m) == [[], [], []]              # GET ничего не пишет


# ── keyset-пагинация ──────────────────────────────────────────────────────────

def _collect(fetch):
    seen, before, pages = [], None, 0
    while True:
        params = {"size": 2}
        if before:
            params["before"] = before
        body = fetch(params).json()
        seen += [i["uuid"] for i in body["items"]]
        pages += 1
        if not body["has_more"]:
            assert body["next_cursor"] is None
            return seen, pages
        before = body["next_cursor"]


def test_open_pages_have_no_gaps_when_items_move_to_history(client, pair):
    p = pair
    uuids = [create_ok(client, p["ptoken"], p["sid"], text=f"{SECRET} {n}") for n in range(5)]
    expected = list(reversed(uuids))                 # новые сначала
    first = my(client, p["stoken"], size=2).json()
    assert [i["uuid"] for i in first["items"]] == expected[:2]
    assert first["total"] == 5 and first["has_more"] is True

    # между страницами: задание первой страницы выполнено, одно ещё отменено,
    # создано новое — следующая страница по курсору продолжает без пропусков.
    assert complete(client, p["stoken"], expected[0]).status_code == 200
    assert cancel(client, p["ptoken"], expected[1]).status_code == 200
    fresh = create_ok(client, p["ptoken"], p["sid"], text="новое")
    rest = []
    before = first["next_cursor"]
    while before:
        body = my(client, p["stoken"], size=2, before=before).json()
        rest += [i["uuid"] for i in body["items"]]
        before = body["next_cursor"]
    assert rest == expected[2:]
    assert fresh not in rest                          # новое — выше курсора: только после сброса

    # история догружается целиком
    history, _ = _collect(lambda params: my(client, p["stoken"], view="history", **params))
    assert history == [expected[0], expected[1]]     # тот же порядок: новые сначала


def test_psychologist_pages_without_gaps_and_audit_only_returned_page(client, pair):
    p = pair
    uuids = [create_ok(client, p["ptoken"], p["sid"]) for _ in range(5)]
    expected = list(reversed(uuids))
    m = marks()
    first = _psych_list(client, p, size=2)
    body = first.json()
    assert [i["uuid"] for i in body["items"]] == expected[:2]
    reads = [r for r in audit_since(m) if r.event_type == "assignment_content_read"]
    assert sorted(r.entity_id for r in reads) == sorted(row(u).id for u in expected[:2])

    # отмена и создание между страницами не сдвигают курсор
    assert cancel(client, p["ptoken"], expected[0]).status_code == 200
    create_ok(client, p["ptoken"], p["sid"])
    m = marks()
    second = _psych_list(client, p, size=2, before=body["next_cursor"]).json()
    assert [i["uuid"] for i in second["items"]] == expected[2:4]
    reads = [r for r in audit_since(m) if r.event_type == "assignment_content_read"]
    assert sorted(r.entity_id for r in reads) == sorted(row(u).id for u in expected[2:4])


def test_broken_cursor_is_sanitized_422(client, pair):
    p = pair
    for r in (my(client, p["stoken"], before="%%%garbage"),
              _psych_list(client, p, before="bm90LWEtY3Vyc29y")):
        assert r.status_code == 422 and r.headers["cache-control"] == NO_STORE
        assert r.json()["errors"] == [{"field": "before", "code": "invalid_cursor"}]


# ── Cache-Control на ошибках ──────────────────────────────────────────────────

def test_no_store_on_auth_errors_and_not_found(client, pair):
    p = pair
    responses = [
        client.get("/api/assignments/my"),                                      # 401
        client.get("/api/assignments/my", headers=auth(p["ptoken"] + "x")),     # 401
        client.get(client_url(p["sid"]), headers=auth(p["stoken"])),           # 403 роль
        complete(client, p["stoken"], uuid.uuid4()),                            # 404
        cancel(client, p["ptoken"], "not-a-uuid"),                              # 422
        client.get("/api/assignments/my/summary", headers=auth(p["stoken"])),  # 200
    ]
    assert [r.status_code for r in responses] == [401, 401, 403, 404, 422, 200]
    for r in responses:
        assert r.headers["cache-control"] == NO_STORE, r.status_code


# ── failure-injection ─────────────────────────────────────────────────────────

def _boom(**kwargs):
    raise AuditStorageError("audit storage failure")


def test_audit_failure_on_create_rolls_back(client, pair, monkeypatch):
    p = pair
    monkeypatch.setattr(assignments_storage, "record_event", _boom)
    m = marks()
    r = create(client, p["ptoken"], p["sid"])
    assert r.status_code == 503 and r.headers["cache-control"] == NO_STORE
    assert SECRET not in r.text
    monkeypatch.undo()
    assert my(client, p["stoken"]).json()["items"] == []
    assert audit_since(m) == []                       # ни success, ни ложного failure


@pytest.mark.parametrize("action", ["complete", "cancel"])
def test_audit_failure_on_transition_rolls_back(client, pair, monkeypatch, action):
    p = pair
    a_uuid = create_ok(client, p["ptoken"], p["sid"])
    monkeypatch.setattr(assignments_storage, "record_event", _boom)
    m = marks()
    r = (complete(client, p["stoken"], a_uuid) if action == "complete"
         else cancel(client, p["ptoken"], a_uuid))
    assert r.status_code == 503 and r.headers["cache-control"] == NO_STORE
    stored = row(a_uuid)
    assert stored.status == "active"
    assert stored.completed_at is None and stored.cancelled_at is None
    assert audit_since(m) == []


def test_content_read_audit_failure_returns_no_texts(client, pair, monkeypatch):
    p = pair
    create_ok(client, p["ptoken"], p["sid"])
    monkeypatch.setattr(assignments_service, "record_event", _boom)
    r = _psych_list(client, p)
    assert r.status_code == 503 and r.headers["cache-control"] == NO_STORE
    assert SECRET not in r.text and "items" not in r.text


def test_commit_failure_is_500_without_business_failure_event(client, pair, capsys):
    p = pair
    a_uuid = create_ok(client, p["ptoken"], p["sid"])
    state = {"wrote": False}

    def _mark(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("UPDATE ASSIGNMENTS"):
            state["wrote"] = True

    def _fail_commit(session):
        if state["wrote"]:
            state["wrote"] = False
            raise OperationalError("COMMIT /* SQL-MARKER */", {"t": SECRET}, Exception("driver"))

    event.listen(engine, "before_cursor_execute", _mark)
    event.listen(SessionLocal.class_, "before_commit", _fail_commit)
    m = marks()
    try:
        r = complete(client, p["stoken"], a_uuid)
    finally:
        event.remove(engine, "before_cursor_execute", _mark)
        event.remove(SessionLocal.class_, "before_commit", _fail_commit)
    assert r.status_code == 500 and r.headers["cache-control"] == NO_STORE
    assert r.json() == {"detail": "Внутренняя ошибка"}
    err = capsys.readouterr().err
    assert "op=complete phase=commit error=OperationalError" in err
    assert "SQL-MARKER" not in err and SECRET not in err
    assert row(a_uuid).status == "active"
    assert audit_since(m) == []                       # неоднозначный commit — без *_failed


def test_ended_engagement_history_stays_readable_for_client(client, pair):
    p = pair
    a_uuid = create_ok(client, p["ptoken"], p["sid"])
    end_engagement(p["eng"])
    assert my(client, p["stoken"]).json()["items"] == []
    (item,) = my(client, p["stoken"], view="history").json()["items"]
    assert item["uuid"] == a_uuid and item["status"] == "active"
    assert item["engagement_active"] is False and item["can_complete"] is False
    assert item["text"] == SECRET


def _now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)


# ── уведомление психолога о выполнении ───────────────────────────────────────

def _system_messages(event_key):
    from app.core.encryption import decrypt_text
    from app.db.models import ChatConversation, ChatMessage
    with SessionLocal() as db:
        rows = (
            db.query(ChatMessage, ChatConversation)
            .join(ChatConversation, ChatConversation.id == ChatMessage.conversation_id)
            .filter(ChatMessage.event_key == event_key)
            .all()
        )
        return [(conv.recipient_id, decrypt_text(msg.content)) for msg, conv in rows]


def test_completion_notifies_psychologist_once_without_task_text(client, pair):
    p = pair
    a_uuid = create_ok(client, p["ptoken"], p["sid"])
    key = assignments_service.completed_event_key(a_uuid)
    assert _system_messages(key) == []

    assert complete(client, p["stoken"], a_uuid).status_code == 200
    ((recipient, text),) = _system_messages(key)
    assert recipient == p["pid"]
    assert text.startswith("Задание выполнено. Клиент: ") and SECRET not in text

    # повтор (no-op) — без дубля
    assert complete(client, p["stoken"], a_uuid).json()["changed"] is False
    assert len(_system_messages(key)) == 1


def test_notification_failure_does_not_undo_completion(client, pair, monkeypatch):
    p = pair
    a_uuid = create_ok(client, p["ptoken"], p["sid"])

    def boom(*a, **k):
        raise RuntimeError("chat down")

    import app.chat.storage as chat_storage
    monkeypatch.setattr(chat_storage, "create_system_message", boom)
    r = complete(client, p["stoken"], a_uuid)
    assert r.status_code == 200 and r.json()["status"] == "completed"
    assert row(a_uuid).status == "completed"
    assert _system_messages(assignments_service.completed_event_key(a_uuid)) == []
