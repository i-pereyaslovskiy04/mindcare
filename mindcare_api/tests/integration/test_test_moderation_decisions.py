"""
ADR-016 (дополнение 2026-11-02) — решения модерации тестов по конкретному
состоянию: проверка состояния, смена статуса и success-аудит — одна транзакция
под FOR UPDATE; решение по устаревшему экрану (статус или updated_at иные)
→ 409 test_state_changed без изменений, без success-события и уведомления.

  * return → запоздалая публикация из очереди не становится «прямой»;
  * publish → повтор того же решения / return по устаревшему экрану — 409;
  * правка автора между загрузкой и решением → 409; правка автора после
    публикации — без мутации (TestNotEditable);
  * прямая публикация draft/needs_changes по свежему состоянию работает и не
    уведомляет; impersonation — 403; тело обязательно;
  * сбой аудита / commit — статус прежний, уведомления нет;
  * конкуренция publish/publish, publish/return, return/publish — одно решение.
"""
import threading
import uuid

import pytest
from sqlalchemy.orm import Session

import app.tests.notifications as notifications
import app.tests.service as service
import app.tests.storage as storage
from app.audit import AuditStorageError
from app.db.models import AuditLog
from app.db.models import Test as TestModel
from app.db.session import SessionLocal
from tests.integration.assignments_helpers import auth, user, uuid_of
from tests.integration.lock_helpers import (
    TIMEOUT, Gate, assert_no_deadlock_error, deadlock_count, run_in_thread,
    wait_for_lock_waiter,
)
from tests.integration.moderation_helpers import decision

BASE = "/api/admin/tests"


def _make(author_id, status):
    data = {
        "title": f"integ_DECISION {uuid.uuid4().hex[:6]}", "description": "d",
        "scoring": "sum", "time_limit_min": None, "is_active": True, "status": "published",
        "category_ids": [], "tag_uuids": [],
        "questions": [
            {"question_text": "Q1", "question_order": 1, "question_type": "single_choice",
             "is_required": True, "config": {},
             "options": [{"option_text": "нет", "option_order": 0, "value_score": 0},
                         {"option_text": "да", "option_order": 1, "value_score": 3}]},
        ],
        "interpretations": [],
    }
    test = storage.create_test(data, created_by=author_id, actor_role="admin")
    with SessionLocal() as db:
        db.query(TestModel).filter(TestModel.uuid == uuid.UUID(test["uuid"])).update(
            {"status": status})
        db.commit()
    return test["uuid"]


def _status(test_uuid):
    with SessionLocal() as db:
        return db.query(TestModel.status).filter(
            TestModel.uuid == uuid.UUID(test_uuid)).scalar()


def _events(test_uuid, *names):
    with SessionLocal() as db:
        tid = db.query(TestModel.id).filter(TestModel.uuid == uuid.UUID(test_uuid)).scalar()
        return [r.event_type for r in db.query(AuditLog).filter(
            AuditLog.entity_type == "test", AuditLog.entity_id == tid,
            AuditLog.event_type.in_(names)).order_by(AuditLog.id)]


@pytest.fixture
def actors(client):
    pid, ptoken = user(client, ["psychologist", "student"])
    sid, stoken = user(client, ["supervisor", "student"])
    sid2, stoken2 = user(client, ["supervisor", "student"])
    return {"pid": pid, "ptoken": ptoken, "sid": sid, "stoken": stoken,
            "sid2": sid2, "stoken2": stoken2}


@pytest.fixture
def notified(monkeypatch):
    calls = []
    real = notifications.notify_author

    def _spy(kind, **kw):
        calls.append(kind)
        return real(kind, **kw)

    monkeypatch.setattr(notifications, "notify_author", _spy)
    return calls


def _assert_state_changed(r, current):
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["code"] == "test_state_changed" and body["current_status"] == current


# ── устаревший экран и повтор ────────────────────────────────────────────────

def test_stale_publish_after_return_is_not_direct_publication(client, actors, notified):
    a = actors
    t = _make(a["pid"], "in_review")
    seen = decision(t)                       # оба проверяющих видят in_review
    r = client.post(f"{BASE}/{t}/return", headers=auth(a["stoken"]), json={**seen, "reason": "x"})
    assert r.status_code == 200, r.text
    r = client.post(f"{BASE}/{t}/publish", headers=auth(a["stoken2"]), json=seen)
    _assert_state_changed(r, "needs_changes")
    assert _status(t) == "needs_changes"
    assert _events(t, "test_published", "test_returned_for_changes") == ["test_returned_for_changes"]
    assert notified == ["returned"]


def test_repeat_and_stale_return_after_publish(client, actors, notified):
    a = actors
    t = _make(a["pid"], "in_review")
    seen = decision(t)
    assert client.post(f"{BASE}/{t}/publish", headers=auth(a["stoken"]), json=seen).status_code == 200
    _assert_state_changed(client.post(f"{BASE}/{t}/publish", headers=auth(a["stoken"]), json=seen),
                          "published")
    _assert_state_changed(client.post(f"{BASE}/{t}/return", headers=auth(a["stoken2"]), json=seen),
                          "published")
    assert _status(t) == "published"
    assert _events(t, "test_published", "test_returned_for_changes") == ["test_published"]
    assert notified == ["published"]


def test_author_edit_between_load_and_decision(client, actors, notified):
    a = actors
    t = _make(a["pid"], "draft")
    seen = decision(t)                                  # экран проверяющего
    r = client.patch(f"/api/psychologist/tests/{t}", headers=auth(a["ptoken"]),
                     json={"title": "integ_DECISION правка автора"})
    assert r.status_code == 200, r.text
    _assert_state_changed(client.post(f"{BASE}/{t}/publish", headers=auth(a["stoken"]), json=seen),
                          "draft")
    assert _status(t) == "draft" and _events(t, "test_published") == []
    # по свежему состоянию — намеренная прямая публикация, без уведомления
    r = client.post(f"{BASE}/{t}/publish", headers=auth(a["stoken"]), json=decision(t))
    assert r.status_code == 200 and _status(t) == "published"
    assert notified == []


def test_direct_publication_of_needs_changes(client, actors, notified):
    a = actors
    t = _make(a["pid"], "needs_changes")
    r = client.post(f"{BASE}/{t}/publish", headers=auth(a["stoken"]), json=decision(t))
    assert r.status_code == 200 and _status(t) == "published"
    assert notified == []


def test_author_edit_after_status_changed_does_not_apply(actors, monkeypatch):
    a = actors
    t = _make(a["pid"], "draft")
    real_gate = service._own_updatable_test

    def gate_then_publish(test_uuid, actor_id):
        found = real_gate(test_uuid, actor_id)           # автор видит draft
        with SessionLocal() as db:                       # проверяющий публикует
            db.query(TestModel).filter(TestModel.uuid == uuid.UUID(test_uuid)).update(
                {"status": "published"})
            db.commit()
        return found

    monkeypatch.setattr(service, "_own_updatable_test", gate_then_publish)
    with pytest.raises(service.TestNotEditable):
        service.update_my_test(t, {"title": "integ_DECISION поздняя правка"}, actor_id=a["pid"])
    with SessionLocal() as db:
        row = db.query(TestModel).filter(TestModel.uuid == uuid.UUID(t)).one()
        assert row.status == "published" and "поздняя" not in row.title


def test_body_required_and_impersonation_forbidden(client, actors):
    a = actors
    t = _make(a["pid"], "in_review")
    assert client.post(f"{BASE}/{t}/publish", headers=auth(a["stoken"])).status_code == 422
    r = client.post(f"{BASE}/{t}/return", headers=auth(a["stoken"]),
                    json={**decision(t), "reason": "x" * 2001})
    assert r.status_code == 422
    _, admin_token = user(client, ["admin"])
    as_sup = client.post(f"/api/admin/users/{uuid_of(a['sid'])}/impersonate",
                         headers=auth(admin_token)).json()["session_token"]
    for path in ("publish", "return"):
        r = client.post(f"{BASE}/{t}/{path}", headers=auth(as_sup), json=decision(t))
        assert r.status_code == 403, r.text
    assert _status(t) == "in_review"


# ── сбой аудита и commit ─────────────────────────────────────────────────────

def _publish(a, t, seen):
    return service.publish_test(
        t, actor_id=a["sid"], actor_role="supervisor",
        expected_status=seen[0], expected_updated_at=seen[1],
    )


def _seen(t):
    with SessionLocal() as db:
        row = db.query(TestModel.status, TestModel.updated_at).filter(
            TestModel.uuid == uuid.UUID(t)).one()
        return row.status, row.updated_at


def test_audit_failure_keeps_status_and_sends_nothing(actors, monkeypatch, notified):
    a = actors
    t = _make(a["pid"], "in_review")

    def _boom(**kwargs):
        raise AuditStorageError("audit storage failure")

    monkeypatch.setattr(storage, "record_event", _boom)
    with pytest.raises(AuditStorageError):
        _publish(a, t, _seen(t))
    monkeypatch.undo()
    assert _status(t) == "in_review" and notified == []


def test_commit_failure_keeps_status_and_sends_nothing(actors, monkeypatch, notified):
    a = actors
    t = _make(a["pid"], "in_review")
    seen = _seen(t)

    def _boom(self):
        raise RuntimeError("commit failure")

    monkeypatch.setattr(Session, "commit", _boom)
    with pytest.raises(RuntimeError):
        _publish(a, t, seen)
    monkeypatch.undo()
    assert _status(t) == "in_review" and notified == []


# ── конкуренция: одно решение по одной версии проверки ───────────────────────

def _return(a, t, seen, actor="sid2"):
    return service.return_for_changes(
        t, actor_id=a[actor], actor_role="supervisor",
        expected_status=seen[0], expected_updated_at=seen[1], reason="r",
    )


@pytest.mark.parametrize("first, second, winner", [
    ("publish", "publish", "published"),
    ("publish", "return", "published"),
    ("return", "publish", "needs_changes"),
])
def test_concurrent_decisions_one_wins(actors, monkeypatch, notified, first, second, winner):
    a = actors
    t = _make(a["pid"], "in_review")
    seen = _seen(t)
    ops = {"publish": lambda: _publish(a, t, seen), "return": lambda: _return(a, t, seen)}
    gate = Gate()
    monkeypatch.setattr(service, "_validate_transition", gate.wrap(service._validate_transition))
    deadlocks = deadlock_count()

    one = run_in_thread(ops[first])
    gate.wait_reached()                 # первое решение держит строку теста
    two = run_in_thread(ops[second])
    wait_for_lock_waiter()              # второе ждёт блокировку
    gate.release.set()
    r1, r2 = one.join(), two.join()
    assert_no_deadlock_error(r1, r2)
    assert r1[0] == "ok", r1
    assert r2[0] == "error" and isinstance(r2[1], service.TestStateChanged), r2
    assert r2[1].current_status == winner
    assert _status(t) == winner
    events = _events(t, "test_published", "test_returned_for_changes")
    assert len(events) == 1
    assert notified == ["published" if winner == "published" else "returned"]
    assert deadlock_count() == deadlocks


# ── конкуренция: автор/проверяющий меняют саму запись (не решение по очереди) ─
#
# Эти гонки — про update_my_test/delete_my_test/submit_for_review/publish_test,
# а не про два решения модерации по одному снимку (выше). Решение здесь может
# провалиться СРАЗУ под блокировкой строки — до какого-либо audit-события
# (например, нелегальный переход submit на published-тесте) — поэтому Gate.wrap
# (пауза ДО вызова обёрнутой функции) не годится: если первым идёт именно такой
# провал, обёрнутая функция может быть не вызвана вовсе, и `reached` не сигналит.
# Гейт здесь стоит на самой блокировке строки (`storage._lock_test`) — паузит
# ПОСЛЕ её взятия (блокировка уже реально держится в Postgres).

def _lock_gate(monkeypatch):
    real = storage._lock_test
    reached, release = threading.Event(), threading.Event()
    state_lock, used = threading.Lock(), {"flag": False}

    def _wrapper(*args, **kwargs):
        result = real(*args, **kwargs)
        with state_lock:
            first = not used["flag"]
            used["flag"] = True
        if first:
            reached.set()
            if not release.wait(TIMEOUT):
                raise AssertionError("gate was never released")
        return result

    monkeypatch.setattr(storage, "_lock_test", _wrapper)
    return reached, release


def _race(monkeypatch, ops, first, second):
    reached, release = _lock_gate(monkeypatch)
    deadlocks = deadlock_count()
    one = run_in_thread(ops[first])
    assert reached.wait(TIMEOUT), "первый поток не дошёл до гейта"
    two = run_in_thread(ops[second])
    wait_for_lock_waiter()
    release.set()
    r1, r2 = one.join(), two.join()
    assert_no_deadlock_error(r1, r2)
    assert deadlock_count() == deadlocks
    return r1, r2


def _update_title(a, t, title):
    return service.update_my_test(
        t, {"title": title}, actor_id=a["pid"], actor_role="psychologist",
    )


def _submit(a, t):
    return service.submit_for_review(t, actor_id=a["pid"], actor_role="psychologist")


def _delete(a, t):
    return service.delete_my_test(t, actor_id=a["pid"], actor_role="psychologist")


def _title(test_uuid):
    with SessionLocal() as db:
        return db.query(TestModel.title).filter(
            TestModel.uuid == uuid.UUID(test_uuid)).scalar()


@pytest.mark.parametrize("first, second", [("update", "submit"), ("submit", "update")])
def test_concurrent_update_and_submit_on_published_test(actors, monkeypatch, notified, first, second):
    """Автор правит СВОЙ published-тест (правка published снимает публикацию,
    F2.1) одновременно с отправкой этого же теста на проверку. submit не несёт
    CAS-токена (это действие автора «из текущего статуса», а не решение по
    снимку очереди) — его исход зависит от того, что РЕАЛЬНО под блокировкой."""
    a = actors
    t = _make(a["pid"], "published")
    title = "integ_DECISION правка опубликованного"
    ops = {"update": lambda: _update_title(a, t, title), "submit": lambda: _submit(a, t)}
    r1, r2 = _race(monkeypatch, ops, first, second)

    if first == "update":
        # update коммитится первым: published → draft (+ unpublish) в одной
        # транзакции с правкой title; submit видит СВЕЖИЙ draft под той же
        # блокировкой и легально уходит в in_review — обе операции успешны.
        assert r1[0] == "ok" and r2[0] == "ok", (r1, r2)
        assert _status(t) == "in_review"
        assert _title(t) == title
        assert _events(
            t, "test_unpublished_for_edit", "test_updated", "test_submitted_for_review",
        ) == ["test_unpublished_for_edit", "test_updated", "test_submitted_for_review"]
    else:
        # submit коммитится первым, но видит ЕЩЁ "published" (unpublish пока не
        # случился) — у published нет перехода в in_review → отказ без мутации
        # и без события. update затем проходит по своему CAS (expected_status
        # "published" не изменился) и снимает публикацию как обычно.
        assert r1[0] == "error" and isinstance(r1[1], service.TestTransitionError), r1
        assert r2[0] == "ok", r2
        assert _status(t) == "draft"
        assert _title(t) == title
        assert _events(
            t, "test_unpublished_for_edit", "test_updated", "test_submitted_for_review",
        ) == ["test_unpublished_for_edit", "test_updated"]
    assert notified == []


@pytest.mark.parametrize("first, second", [("delete", "submit"), ("submit", "delete")])
def test_concurrent_delete_and_submit(actors, monkeypatch, notified, first, second):
    """Автор удаляет СВОЙ draft-тест одновременно с его же отправкой на
    проверку (например, два открытых окна). Обе операции читают статус без
    блокировки ДО гонки — выигрывает та, что первой взяла FOR UPDATE."""
    a = actors
    t = _make(a["pid"], "draft")
    ops = {"delete": lambda: _delete(a, t), "submit": lambda: _submit(a, t)}
    r1, r2 = _race(monkeypatch, ops, first, second)

    if first == "delete":
        # удаление коммитится первым (deleted_at) — submit затем не находит
        # строку (WHERE deleted_at IS NULL) и получает «Тест не найден».
        assert r1[0] == "ok", r1
        assert r2[0] == "error" and isinstance(r2[1], ValueError), r2
        with SessionLocal() as db:
            row = db.query(TestModel.deleted_at, TestModel.status).filter(
                TestModel.uuid == uuid.UUID(t)).one()
            assert row.deleted_at is not None and row.status == "draft"
        assert _events(t, "test_deleted", "test_submitted_for_review") == ["test_deleted"]
    else:
        # submit коммитится первым (draft → in_review) — удаление затем видит
        # под блокировкой статус, расходящийся с его собственным CAS ("draft"
        # ожидался), и отказывает без мутации: in_review автору удалить и так
        # нельзя, но отказывает именно версия строки, а не повторная проверка
        # editable-статуса (та прошла раньше, по тому же "draft").
        assert r1[0] == "ok", r1
        assert r2[0] == "error" and isinstance(r2[1], service.TestNotEditable), r2
        assert _status(t) == "in_review"
        with SessionLocal() as db:
            assert db.query(TestModel.deleted_at).filter(
                TestModel.uuid == uuid.UUID(t)).scalar() is None
        assert _events(
            t, "test_deleted", "test_submitted_for_review",
        ) == ["test_submitted_for_review"]
    assert notified == []


@pytest.mark.parametrize("first, second", [("update", "publish"), ("publish", "update")])
def test_concurrent_update_and_direct_publish(actors, monkeypatch, notified, first, second):
    """Автор правит метаданные своего draft-теста одновременно с намеренной
    прямой публикацией этого же draft супервизором. Правка не меняет статус,
    но ВСЕГДА двигает `updated_at` (токен версии) — поэтому даже «безопасная»
    правка делает ранее увиденный снимок публикации устаревшим."""
    a = actors
    t = _make(a["pid"], "draft")
    title = "integ_DECISION правка черновика"
    seen = _seen(t)
    ops = {"update": lambda: _update_title(a, t, title), "publish": lambda: _publish(a, t, seen)}
    r1, r2 = _race(monkeypatch, ops, first, second)

    if first == "update":
        # update коммитится первым: статус остаётся draft, но updated_at
        # меняется. publish по старому снимку (status=draft совпадает, а
        # updated_at — уже нет) получает 409 test_state_changed, хотя статус
        # внешне тот же самый.
        assert r1[0] == "ok", r1
        assert r2[0] == "error" and isinstance(r2[1], service.TestStateChanged), r2
        assert r2[1].current_status == "draft"
        assert _status(t) == "draft"
        assert _title(t) == title
        assert _events(t, "test_published", "test_updated") == ["test_updated"]
    else:
        # publish коммитится первым (draft → published); update по своему CAS
        # видит, что статус уже не draft, и отказывает без мутации.
        assert r1[0] == "ok", r1
        assert r2[0] == "error" and isinstance(r2[1], service.TestNotEditable), r2
        assert _status(t) == "published"
        assert _title(t) != title
        assert _events(t, "test_published", "test_updated") == ["test_published"]
    assert notified == []
