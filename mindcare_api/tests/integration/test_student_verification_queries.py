"""
ADR-029 — gated integration: минимизация SELECT в
app/student_verification/storage.py по ФАКТИЧЕСКИ выполняемым запросам
(SQLAlchemy event before_cursor_execute на engine).

  * список и история — только метаданные: ни ticket_number_enc, ни
    rejection_reason_enc, ни auth-полей users;
  * собственный статус — без номера; пояснение отказа читается отдельным
    запросом и только для rejected;
  * карточка — ciphertext номера/пояснения в одном запросе, без auth-полей;
  * подача и решение — SELECT без ciphertext и auth-полей;
  * точное число SELECT доказывает отсутствие скрытой lazy-загрузки в DTO;
  * API-контракты (поля DTO, пагинация, поиск) прежние.
"""
import uuid as _uuid
from contextlib import contextmanager

import pytest
from sqlalchemy import event

import app.student_verification.storage as sv_storage
from app.db.session import engine
from tests.integration.conftest import create_multi_role_user, create_test_user

CIPHERTEXT = ("ticket_number_enc", "rejection_reason_enc")
AUTH_FIELDS = ("password_hash", "deactivation_reason_enc", "ui_theme_palette",
               "last_login", "phone")


@contextmanager
def _selects():
    statements = []

    def _listener(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", _listener)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", _listener)


def _assert_no(statements, *names):
    for stmt in statements:
        for name in names:
            assert name not in stmt, (name, stmt)


def _student(tag="q"):
    email = f"integ_svq_{tag}_{_uuid.uuid4().hex[:8]}@example.com"
    return int(create_test_user(email)["id"]), email


@pytest.fixture
def data(client):
    """Две заявки одного пользователя (rejected → pending) + pending другого."""
    _, sup, _ = create_multi_role_user(client, ["supervisor", "student"])
    a, a_email = _student("a")
    b, _ = _student("b")
    first = sv_storage.submit_atomic(a, faculty_code="law", ticket_number="000111")
    sv_storage.decide_atomic(_uuid.UUID(first["uuid"]), decision="reject",
                             reviewer_id=sup, reason="Не читается")
    second = sv_storage.submit_atomic(a, faculty_code="history", ticket_number="000222")
    other = sv_storage.submit_atomic(b, faculty_code="law", ticket_number="000333")
    return {"sup": sup, "a": a, "a_email": a_email, "b": b,
            "first": first, "second": second, "other": other}


def test_list_selects_only_metadata_and_keeps_contract(data):
    with _selects() as stmts:
        items, total = sv_storage.list_requests(status=None, page=1, size=100)
    assert len(stmts) == 2                       # count + страница, без lazy-load
    _assert_no(stmts, *CIPHERTEXT, *AUTH_FIELDS)

    mine = {i["uuid"]: i for i in items}
    assert total >= 3
    rejected = mine[data["first"]["uuid"]]
    assert set(rejected) == {"id", "uuid", "user_id", "status", "faculty_code",
                             "submitted_at", "reviewed_at", "reviewed_by",
                             "student", "reviewer"}
    assert rejected["status"] == "rejected" and rejected["reviewer"]["full_name"]
    assert set(rejected["student"]) == {"uuid", "full_name", "email", "is_active"}
    assert mine[data["second"]["uuid"]]["reviewer"] is None


def test_list_search_and_pagination_select_only_metadata(data):
    with _selects() as stmts:
        found, total = sv_storage.list_requests(
            status=None, page=1, size=100, search=data["a_email"],
        )
        page1, total_pending = sv_storage.list_requests(status="pending", page=1, size=1)
        page2, _ = sv_storage.list_requests(status="pending", page=2, size=1)
    assert len(stmts) == 6
    _assert_no(stmts, *CIPHERTEXT, *AUTH_FIELDS)
    assert {i["uuid"] for i in found} == {data["first"]["uuid"], data["second"]["uuid"]}
    assert total == 2
    assert total_pending >= 2 and len(page1) == 1 and len(page2) == 1
    assert page1[0]["uuid"] != page2[0]["uuid"]


def test_own_status_reads_reason_only_when_rejected(data):
    with _selects() as pending_stmts:
        latest = sv_storage.get_latest_for_user(data["b"])
    assert latest["status"] == "pending" and latest["rejection_reason_enc"] is None
    assert len(pending_stmts) == 1
    _assert_no(pending_stmts, *CIPHERTEXT, *AUTH_FIELDS)

    # Последняя заявка a — pending; отклонённую делаем последней для проверки.
    sv_storage.decide_atomic(_uuid.UUID(data["second"]["uuid"]), decision="reject",
                             reviewer_id=data["sup"], reason="Повторно")
    with _selects() as rejected_stmts:
        latest = sv_storage.get_latest_for_user(data["a"])
    assert latest["status"] == "rejected"
    assert latest["rejection_reason_enc"].startswith("enc:v1:")
    assert len(rejected_stmts) == 2
    _assert_no(rejected_stmts[:1], *CIPHERTEXT)
    assert "rejection_reason_enc" in rejected_stmts[1]
    _assert_no(rejected_stmts, "ticket_number_enc", *AUTH_FIELDS)


def test_card_selects_ciphertext_once_and_no_auth_fields(data):
    with _selects() as stmts:
        card = sv_storage.get_card(_uuid.UUID(data["second"]["uuid"]))
    assert len(stmts) == 2                       # карточка + история
    assert "ticket_number_enc" in stmts[0] and "rejection_reason_enc" in stmts[0]
    _assert_no(stmts[1:], *CIPHERTEXT)          # история — только метаданные
    _assert_no(stmts, *AUTH_FIELDS)
    assert card["ticket_number_enc"].startswith("enc:v1:")
    assert [h["uuid"] for h in card["history"]] == [data["first"]["uuid"]]
    assert set(card["history"][0]) == {"uuid", "status", "faculty_code",
                                       "submitted_at", "reviewed_at"}


def test_submit_and_decide_select_no_ciphertext_or_auth_fields(client):
    _, sup, _ = create_multi_role_user(client, ["supervisor", "student"])
    uid, _ = _student("w")
    with _selects() as submit_stmts:
        req = sv_storage.submit_atomic(uid, faculty_code="law", ticket_number="000444")
    with _selects() as decide_stmts:
        row, changed = sv_storage.decide_atomic(
            _uuid.UUID(req["uuid"]), decision="reject", reviewer_id=sup, reason="Нет",
        )
    assert changed is True and row["status"] == "rejected"
    _assert_no(submit_stmts + decide_stmts, *CIPHERTEXT, *AUTH_FIELDS)
    assert any("FOR UPDATE" in s for s in submit_stmts)
    assert sum("FOR UPDATE" in s for s in decide_stmts) == 3   # 2 users + заявка
