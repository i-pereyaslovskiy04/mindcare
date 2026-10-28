"""
Дополнение 2026-10-28 к ADR-034 — gated integration: уведомления и авторство
супервизора.

  * бейджи очередей: /api/review/articles/pending-count и
    /api/admin/tests/pending-count — только число, admin/supervisor, без аудита;
  * автор статьи / теста получает system-сообщение о решении по отправленному
    на проверку (без комментария статьи; причина возврата теста — только в
    сообщении); своё решение и прямая публикация черновика — без сообщения;
  * supervisor — автор своих статей: CRUD + публикация сам, без очереди;
    чужие статьи не видит, submit у него нет, психологу его API закрыт;
  * клиент получает system-сообщение о новом и об отменённом задании (без
    текста задания, один раз на задание).
"""
import uuid

import pytest

from app.core.encryption import decrypt_text
from app.db.models import Article, ChatConversation, ChatMessage, Test as TestModel
from app.db.session import SessionLocal
from app.tests import storage as tests_storage
from tests.integration.assignments_helpers import (
    SECRET, auth, blob, cancel, create_ok, engage, marks, rows_since, user, uuid_of,
)

COMMENT = "Комментарий-проверяющего-4b2e"
REASON = "Причина-возврата-теста-91c0"
PSYCH = "/api/psychologist/articles"
SUPER = "/api/supervisor/articles"
REVIEW = "/api/review/articles"


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    with SessionLocal() as db:
        db.query(Article).filter(Article.title.like("integ\\_ntf\\_%", escape="\\")).delete(
            synchronize_session=False)
        db.query(TestModel).filter(TestModel.title.like("integ\\_ntf\\_%", escape="\\")).delete(
            synchronize_session=False)
        db.commit()


def _title():
    return f"integ_ntf_{uuid.uuid4().hex[:8]}"


def _messages(recipient_id, prefix):
    """Расшифрованные system-сообщения получателя с event_key, начинающимся с prefix."""
    with SessionLocal() as db:
        rows = (
            db.query(ChatMessage)
            .join(ChatConversation, ChatConversation.id == ChatMessage.conversation_id)
            .filter(ChatConversation.recipient_id == recipient_id,
                    ChatMessage.event_key.like(f"{prefix}%"))
            .order_by(ChatMessage.id)
            .all()
        )
        return [decrypt_text(m.content) for m in rows]


def _events(m):
    return [(r.event_type, r.user_role) for r in rows_since(m)[0]
            if r.event_type != "system_conversation_created"]


@pytest.fixture
def actors(client):
    pid, ptoken = user(client, ["psychologist", "student"])
    sid, stoken = user(client, ["supervisor", "student"])
    return {"pid": pid, "ptoken": ptoken, "sid": sid, "stoken": stoken}


def _psych_article(client, token):
    r = client.post(PSYCH, headers=auth(token), json={"title": _title(), "content": "<p>x</p>"})
    assert r.status_code == 201, r.text
    return r.json()


def _count(client, url, token):
    r = client.get(url, headers=auth(token))
    assert r.status_code == 200, r.text
    return r.json()["count"]


# ── бейдж очереди статей ─────────────────────────────────────────────────────

def test_article_pending_count_follows_queue_without_audit(client, actors):
    a = actors
    _, admin = user(client, ["admin"])
    url = f"{REVIEW}/pending-count"
    before = _count(client, url, a["stoken"])
    art = _psych_article(client, a["ptoken"])
    assert _count(client, url, a["stoken"]) == before          # черновик не в очереди
    client.post(f"{PSYCH}/{art['uuid']}/submit", headers=auth(a["ptoken"]))

    m = marks()
    assert _count(client, url, a["stoken"]) == before + 1
    assert _count(client, url, admin) == before + 1
    assert _events(m) == []                                     # без аудита

    assert client.get(url, headers=auth(a["ptoken"])).status_code == 403
    client.post(f"{REVIEW}/{art['uuid']}/publish", headers=auth(a["stoken"]))
    assert _count(client, url, a["stoken"]) == before


# ── уведомление автора статьи ────────────────────────────────────────────────

def test_author_notified_on_publish_and_return_without_comment(client, actors):
    a = actors
    art = _psych_article(client, a["ptoken"])
    client.post(f"{PSYCH}/{art['uuid']}/submit", headers=auth(a["ptoken"]))
    r = client.post(f"{REVIEW}/{art['uuid']}/return", headers=auth(a["stoken"]),
                    json={"comment": COMMENT})
    assert r.status_code == 200
    (returned,) = _messages(a["pid"], f"article_returned:article:{art['uuid']}")
    assert art["title"] in returned and "доработку" in returned
    assert "/psychologist/materials#my-materials" in returned
    assert COMMENT not in returned                       # комментарий — только в «Мои материалы»

    # повторный цикл — новое сообщение (другой переход), публикация — своё
    client.post(f"{PSYCH}/{art['uuid']}/submit", headers=auth(a["ptoken"]))
    client.post(f"{REVIEW}/{art['uuid']}/return", headers=auth(a["stoken"]), json={})
    assert len(_messages(a["pid"], f"article_returned:article:{art['uuid']}")) == 2
    client.post(f"{PSYCH}/{art['uuid']}/submit", headers=auth(a["ptoken"]))
    assert client.post(f"{REVIEW}/{art['uuid']}/publish", headers=auth(a["stoken"])).status_code == 200
    (published,) = _messages(a["pid"], f"article_published:article:{art['uuid']}")
    assert art["title"] in published and "опубликован" in published
    # проверяющему ничего не приходит
    assert _messages(a["sid"], "article_") == []


def test_own_decision_is_not_notified(client):
    uid, token = user(client, ["psychologist", "supervisor", "student"])
    art = _psych_article(client, token)
    client.post(f"{PSYCH}/{art['uuid']}/submit", headers=auth(token))
    assert client.post(f"{REVIEW}/{art['uuid']}/publish", headers=auth(token)).status_code == 200
    assert _messages(uid, "article_") == []


def test_author_notification_failure_does_not_undo_publication(client, actors, monkeypatch):
    a = actors
    art = _psych_article(client, a["ptoken"])
    client.post(f"{PSYCH}/{art['uuid']}/submit", headers=auth(a["ptoken"]))

    def boom(*args, **kwargs):
        raise RuntimeError("chat down")

    import app.chat.storage as chat_storage
    monkeypatch.setattr(chat_storage, "create_system_message", boom)
    r = client.post(f"{REVIEW}/{art['uuid']}/publish", headers=auth(a["stoken"]))
    assert r.status_code == 200 and r.json()["status"] == "published"
    assert "_notify" not in r.json()
    monkeypatch.undo()
    assert _messages(a["pid"], "article_") == []


# ── supervisor — автор своих статей ───────────────────────────────────────────

def test_supervisor_creates_and_publishes_own_article(client, actors):
    a = actors
    m = marks()
    r = client.post(SUPER, headers=auth(a["stoken"]), json={"title": _title(), "content": "<p>s</p>"})
    assert r.status_code == 201 and r.json()["status"] == "draft"
    art = r.json()
    assert _events(m) == [("article_created", "supervisor")]
    assert client.get(f"/api/articles/{art['uuid']}").status_code == 404

    # не в очереди: публикует сам
    queue = client.get(REVIEW, headers=auth(a["stoken"]), params={"size": 100}).json()
    assert art["uuid"] not in [i["uuid"] for i in queue["items"]]
    m = marks()
    r = client.post(f"{SUPER}/{art['uuid']}/publish", headers=auth(a["stoken"]))
    assert r.status_code == 200 and r.json()["status"] == "published" and r.json()["is_published"]
    assert _events(m) == [("article_published", "supervisor")]
    assert client.get(f"/api/articles/{art['uuid']}").status_code == 200
    assert _messages(a["sid"], "article_") == []                # себе не уведомляет

    # повторная публикация — 409; правка опубликованной снимает её с публикации
    r = client.post(f"{SUPER}/{art['uuid']}/publish", headers=auth(a["stoken"]))
    assert r.status_code == 409 and r.json()["current_status"] == "published"
    m = marks()
    r = client.patch(f"{SUPER}/{art['uuid']}", headers=auth(a["stoken"]), json={"excerpt": "Новое"})
    assert r.status_code == 200 and r.json()["status"] == "draft"
    assert _events(m) == [("article_unpublished_for_edit", "supervisor"),
                          ("article_updated", "supervisor")]
    assert client.get(f"/api/articles/{art['uuid']}").status_code == 404

    m = marks()
    assert client.delete(f"{SUPER}/{art['uuid']}", headers=auth(a["stoken"])).status_code == 204
    assert _events(m) == [("article_deleted", "supervisor")]


def test_supervisor_author_api_boundaries(client, actors):
    a = actors
    psych_art = _psych_article(client, a["ptoken"])
    # чужая статья — 404 во всех операциях своего API
    assert client.get(f"{SUPER}/{psych_art['uuid']}", headers=auth(a["stoken"])).status_code == 404
    assert client.post(f"{SUPER}/{psych_art['uuid']}/publish",
                       headers=auth(a["stoken"])).status_code == 404
    assert psych_art["uuid"] not in [i["uuid"] for i in
                                     client.get(SUPER, headers=auth(a["stoken"])).json()["items"]]
    # submit у супервизора нет, психологу API супервизора закрыт
    own = client.post(SUPER, headers=auth(a["stoken"]), json={"title": _title()}).json()
    assert client.post(f"{SUPER}/{own['uuid']}/submit",
                       headers=auth(a["stoken"])).status_code in (404, 405)
    assert client.get(SUPER, headers=auth(a["ptoken"])).status_code == 403
    assert client.post(f"{PSYCH}/{psych_art['uuid']}/publish",
                       headers=auth(a["ptoken"])).status_code in (404, 405)
    # impersonation — 403
    _, admin = user(client, ["admin"])
    imp = client.post(f"/api/admin/users/{uuid_of(a['sid'])}/impersonate",
                      headers=auth(admin)).json()["session_token"]
    assert client.get(SUPER, headers=auth(imp)).status_code == 403


# ── тесты: бейдж и уведомление автора ────────────────────────────────────────

def _psych_test(author_id, status):
    data = {
        "title": _title(), "description": "d", "scoring": "sum",
        "time_limit_min": None, "is_active": True, "status": "published",
        "category_ids": [], "tag_uuids": [],
        "questions": [
            {"question_text": "Q1", "question_order": 1, "question_type": "single_choice",
             "is_required": True, "config": {},
             "options": [{"option_text": "нет", "option_order": 0, "value_score": 0},
                         {"option_text": "да", "option_order": 1, "value_score": 3}]},
        ],
        "interpretations": [],
    }
    test = tests_storage.create_test(data, created_by=author_id, actor_role="admin")
    with SessionLocal() as db:
        db.query(TestModel).filter(TestModel.uuid == uuid.UUID(test["uuid"])).update(
            {"status": status})
        db.commit()
    return test


def test_tests_pending_count_and_author_notifications(client, actors):
    a = actors
    url = "/api/admin/tests/pending-count"
    before = _count(client, url, a["stoken"])
    t1 = _psych_test(a["pid"], "in_review")
    t2 = _psych_test(a["pid"], "in_review")
    m = marks()
    assert _count(client, url, a["stoken"]) == before + 2
    assert _events(m) == []
    assert client.get(url, headers=auth(a["ptoken"])).status_code == 403

    r = client.post(f"/api/admin/tests/{t1['uuid']}/publish", headers=auth(a["stoken"]))
    assert r.status_code == 200
    (published,) = _messages(a["pid"], f"test_published:test:{t1['uuid']}")
    assert t1["title"] in published and "/psychologist/tests" in published

    r = client.post(f"/api/admin/tests/{t2['uuid']}/return", headers=auth(a["stoken"]),
                    json={"reason": REASON})
    assert r.status_code == 200 and REASON not in r.text
    (returned,) = _messages(a["pid"], f"test_returned:test:{t2['uuid']}")
    assert t2["title"] in returned and REASON in returned
    assert all(REASON not in blob(row) for logs in rows_since(m) for row in logs)
    assert _count(client, url, a["stoken"]) == before


def test_direct_publication_of_draft_is_not_notified(client, actors):
    a = actors
    t = _psych_test(a["pid"], "draft")
    assert client.post(f"/api/admin/tests/{t['uuid']}/publish",
                       headers=auth(a["stoken"])).status_code == 200
    assert _messages(a["pid"], "test_") == []


# ── задания: уведомления клиента ─────────────────────────────────────────────

def test_client_notified_about_new_and_cancelled_assignment(client):
    sid, stoken = user(client, ["student"])
    pid, ptoken = user(client, ["psychologist", "student"])
    engage(pid, sid)

    a_uuid = create_ok(client, ptoken, sid)
    (created,) = _messages(sid, f"assignment_created:assignment:{a_uuid}")
    assert created.startswith("Новое задание от психолога") and "/student/tasks" in created
    assert SECRET not in created
    assert _messages(pid, "assignment_created") == []

    assert cancel(client, ptoken, a_uuid).status_code == 200
    (cancelled,) = _messages(sid, f"assignment_cancelled:assignment:{a_uuid}")
    assert "отменено" in cancelled and SECRET not in cancelled
    # повтор отмены (no-op) — без дубля
    assert cancel(client, ptoken, a_uuid).json()["changed"] is False
    assert len(_messages(sid, f"assignment_cancelled:assignment:{a_uuid}")) == 1
