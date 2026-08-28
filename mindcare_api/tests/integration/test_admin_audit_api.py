"""
Stage 8 — gated integration read-only admin viewer журналов.

Запускается только через `scripts/isolated_test_db.py` на одноразовой
`mindcare_test_<random>` (fail-fast в `tests/integration/conftest.py`).

Изоляция строк — двухуровневая. Внутри прогона каждый тест получает СВОЙ
календарный день через `unique_day` и запрашивает ровно его. После теста
`purge_journal_rows` удаляет всё, что он записал в журналы: соседние тесты
проверяют СКВОЗНЫЕ инварианты по всем строкам БД (отсутствие значений ПДн в
`data_change_log`, счётчики `anonymize_old_ips`), и оставленные синтетические
строки ломали бы их.

Все ПДн в фикстурах синтетические.
"""
from __future__ import annotations

import itertools
import uuid as _uuid
from datetime import date, datetime, time, timedelta, timezone

import bcrypt
import pytest
from sqlalchemy import event, func, text

from app.auth import storage as auth_storage
from app.db.models import AuditLog, AuthLog, DataChangeLog, User
from app.db.session import SessionLocal, engine
from tests.integration.conftest import create_multi_role_user

PASSWORD = "SecurePass42!"
MOSCOW_TZ = timezone(timedelta(hours=3))

EVENTS_URL = "/api/admin/audit/events"
AUTH_URL = "/api/admin/audit/auth-events"
CHANGES_URL = "/api/admin/audit/data-changes"
OPTIONS_URL = "/api/admin/audit/options"

# Окно изоляции: дни отсчитываются назад от «сегодня», оставаясь внутри
# созданных миграцией месячных партиций.
_DAY_COUNTER = itertools.count(1)


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def unique_day():
    """Отдельный календарный день на тест — журналы между тестами не пересекаются."""
    offset = next(_DAY_COUNTER)
    return datetime.now(MOSCOW_TZ).date() - timedelta(days=offset)


@pytest.fixture(autouse=True)
def purge_journal_rows():
    """Удаляет строки журналов, созданные тестом (в т.ч. события просмотра).

    Append-only — свойство продакшена, а не одноразовой тестовой БД. Соседние
    тесты проверяют СКВОЗНЫЕ инварианты по всем строкам: что ни одна строка
    `data_change_log` для ПДн-таблиц не несёт значений и что
    `anonymize_old_ips()` затрагивает ровно свои probe-строки. Оставленные
    здесь синтетические строки ломали бы их, поэтому убираем за собой.

    Границей служит `id`: у партиционированных журналов это общая
    последовательность на parent, поэтому `id > snapshot` точно и не задевает
    чужие строки.
    """
    tables = (AuditLog, AuthLog, DataChangeLog)
    with SessionLocal() as db:
        before = {
            t.__tablename__: db.query(func.coalesce(func.max(t.id), 0)).scalar()
            for t in tables
        }
    yield
    with SessionLocal() as db:
        for t in tables:
            db.query(t).filter(t.id > before[t.__tablename__]).delete(
                synchronize_session=False,
            )
        db.commit()


def _leaf_values(payload) -> set:
    """Листовые значения JSON-поддерева — и как есть, и в строковом виде.

    Нужна именно точная проверка по значениям: подстрочный поиск внутреннего id
    в сериализованном ответе даёт ложные срабатывания на маленьких id (в
    одноразовой БД последовательность начинается с 1, а «3» встречается и в
    timestamp, и в UUID).
    """
    values: set = set()
    if isinstance(payload, dict):
        for item in payload.values():
            values |= _leaf_values(item)
    elif isinstance(payload, list):
        for item in payload:
            values |= _leaf_values(item)
    else:
        values.add(payload)
        values.add(str(payload))
    return values


def _at(day: date, hour: int = 12, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute), tzinfo=MOSCOW_TZ)


def _window(day: date) -> dict:
    return {"date_from": day.isoformat(), "date_to": day.isoformat()}


def _make_user(role: str, client) -> tuple[str, int]:
    suffix = _uuid.uuid4().hex[:10]
    email = f"integ_audview_{role}_{suffix}@example.com"
    user = auth_storage.save_user({
        "name": f"AudView {role.capitalize()} {_uuid.uuid4().hex[:6]}",
        "email": email,
        "hashed_password": bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode(),
        "role": role,
    })
    r = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["session_token"], int(user["id"])


@pytest.fixture
def admin(client):
    return _make_user("admin", client)


def _insert(rows):
    with SessionLocal() as db:
        for row in rows:
            db.add(row)
        db.commit()


def _audit(day, **kwargs):
    payload = dict(
        event_type="admin_role_add", user_id=None, user_role="admin",
        entity_type="user", entity_id=1, outcome="success",
        created_at=_at(day),
    )
    payload.update(kwargs)
    return AuditLog(**payload)


def _authlog(day, **kwargs):
    payload = dict(event="login", user_id=None, success=True, created_at=_at(day))
    payload.update(kwargs)
    return AuthLog(**payload)


def _change(day, **kwargs):
    payload = dict(
        actor_id=None, actor_role="admin", table_name="meeting_types",
        record_id=1, operation="UPDATE", changed_fields=["duration_minutes"],
        created_at=_at(day),
    )
    payload.update(kwargs)
    return DataChangeLog(**payload)


# ─── Доступ ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("url", [EVENTS_URL, AUTH_URL, CHANGES_URL, OPTIONS_URL])
def test_without_a_session_returns_401(client, url):
    assert client.get(url).status_code == 401


@pytest.mark.parametrize("role", ["student", "psychologist", "supervisor"])
@pytest.mark.parametrize("url", [EVENTS_URL, AUTH_URL, CHANGES_URL, OPTIONS_URL])
def test_non_admin_roles_are_forbidden(client, role, url):
    token, _ = _make_user(role, client)
    assert client.get(url, headers=_auth(token)).status_code == 403


@pytest.mark.parametrize("url", [EVENTS_URL, AUTH_URL, CHANGES_URL, OPTIONS_URL])
def test_admin_is_allowed(client, admin, url):
    token, _ = admin
    assert client.get(url, headers=_auth(token)).status_code == 200


@pytest.mark.parametrize("url", [EVENTS_URL, AUTH_URL, CHANGES_URL])
def test_multi_role_user_passes_by_admin_membership(client, url):
    """Пользователь admin+supervisor проходит именно по membership `admin`."""
    token, _, _ = create_multi_role_user(client, ["supervisor", "admin"])
    assert client.get(url, headers=_auth(token)).status_code == 200


def test_supervisor_only_multi_role_user_is_still_forbidden(client):
    token, _, _ = create_multi_role_user(client, ["supervisor", "psychologist"])
    assert client.get(EVENTS_URL, headers=_auth(token)).status_code == 403


# ─── Заголовки ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("url", [EVENTS_URL, AUTH_URL, CHANGES_URL])
def test_log_pages_are_never_cached(client, admin, url):
    token, _ = admin
    r = client.get(url, headers=_auth(token))
    assert r.headers["cache-control"] == "no-store, private"
    assert "etag" not in {k.lower() for k in r.headers}


# ─── Валидация запроса ────────────────────────────────────────────────────────

@pytest.mark.parametrize("params", [
    {"date_from": "2026-08-01"},
    {"date_to": "2026-08-01"},
    {"date_from": "2026-08-10", "date_to": "2026-08-01"},
    {"date_from": "2026-01-01", "date_to": "2026-08-01"},
    {"order": "sideways"},
    {"event_type": "no_such_event"},
    {"actor_kind": "robot"},
    {"entity_type": "appointment", "entity_id": 0},
    {"entity_type": "appointment", "entity_id": 2 ** 31},
    {"entity_type": "user", "entity_id": 5},
    # Целочисленный идентификатор без типа цели неоднозначен.
    {"entity_id": 5},
    {"page": 10_000, "size": 100},
])
def test_invalid_event_queries_are_rejected(client, admin, params):
    token, _ = admin
    assert client.get(EVENTS_URL, headers=_auth(token),
                      params=params).status_code == 422


@pytest.mark.parametrize("params", [
    {"operation": "INSERT"},
    {"operation": "DELETE"},
    {"table_name": "session_notes"},
    {"actor_kind": "system"},
    {"table_name": "users", "record_id": 5},
    {"record_id": 5},
])
def test_invalid_data_change_queries_are_rejected(client, admin, params):
    token, _ = admin
    assert client.get(CHANGES_URL, headers=_auth(token),
                      params=params).status_code == 422


def test_rejected_query_writes_no_access_event(client, admin, unique_day):
    token, _ = admin
    before = _count_access_events()
    client.get(EVENTS_URL, headers=_auth(token), params={"order": "sideways"})
    assert _count_access_events() == before


def _count_access_events() -> int:
    with SessionLocal() as db:
        return db.query(AuditLog).filter(
            AuditLog.event_type == "audit_logs_viewed",
        ).count()


# ─── Справочник ───────────────────────────────────────────────────────────────

def test_options_reflect_the_live_registry(client, admin):
    token, _ = admin
    body = client.get(OPTIONS_URL, headers=_auth(token)).json()

    assert body["operations"] == ["UPDATE"]
    assert body["actor_kinds"]["data_change_log"] == ["user", "unavailable"]
    assert len(body["audit_events"]) == 97
    assert len(body["auth_events"]) == 7
    assert body["limits"]["max_range_days"] == 90


def test_options_writes_no_access_event(client, admin):
    token, _ = admin
    before = _count_access_events()
    assert client.get(OPTIONS_URL, headers=_auth(token)).status_code == 200
    assert _count_access_events() == before


# ─── Классы актора: фильтр = проекция ────────────────────────────────────────

def test_nulled_actor_on_a_user_event_is_unavailable_not_anonymous(
    client, admin, unique_day,
):
    """FK объявлен ON DELETE SET NULL: после удаления аккаунта `login` теряет
    actor id, но анонимным действием не становится."""
    _insert([
        _authlog(unique_day, event="login", user_id=None),
        _authlog(unique_day, event="failed_login", user_id=None, success=False,
                 failure_reason="invalid_credentials"),
    ])
    token, _ = admin
    params = _window(unique_day)

    unavailable = client.get(AUTH_URL, headers=_auth(token),
                             params={**params, "actor_kind": "unavailable"}).json()
    anonymous = client.get(AUTH_URL, headers=_auth(token),
                           params={**params, "actor_kind": "anonymous"}).json()

    assert [i["event_code"] for i in unavailable["items"]] == ["login"]
    assert [i["event_code"] for i in anonymous["items"]] == ["failed_login"]
    assert unavailable["items"][0]["actor"]["kind"] == "unavailable"
    assert anonymous["items"][0]["actor"]["kind"] == "anonymous"


def test_role_outside_the_event_allowlist_is_only_reachable_as_unavailable(
    client, admin, unique_day,
):
    """`admin_role_add` с `user_role='student'` — противоречивая строка."""
    _, actor_id = _make_user("admin", client)
    _insert([_audit(unique_day, user_id=actor_id, user_role="student",
                    entity_id=actor_id)])
    token, _ = admin
    params = {**_window(unique_day), "event_type": "admin_role_add"}

    as_user = client.get(EVENTS_URL, headers=_auth(token),
                         params={**params, "actor_kind": "user"}).json()
    as_role = client.get(EVENTS_URL, headers=_auth(token),
                         params={**params, "actor_role": "student"}).json()
    as_unavailable = client.get(
        EVENTS_URL, headers=_auth(token),
        params={**params, "actor_kind": "unavailable"},
    ).json()

    assert as_user["total"] == 0
    assert as_unavailable["total"] == 1
    assert as_unavailable["items"][0]["actor"]["kind"] == "unavailable"
    assert as_unavailable["items"][0]["actor"]["role_at_event"] is None
    assert as_unavailable["items"][0]["actor"]["user_uuid"] is None
    # Фильтр по роли выбирает строку, но проекция всё равно её редактирует.
    assert as_role["total"] == 1
    assert as_role["items"][0]["actor"]["kind"] == "unavailable"


def test_every_row_is_reachable_by_exactly_one_actor_kind(
    client, admin, unique_day,
):
    """Разбиение по `actor_kind` обязано быть тотальным и непересекающимся."""
    _, actor_id = _make_user("admin", client)
    _insert([
        _audit(unique_day, user_id=actor_id, user_role="admin", entity_id=actor_id),
        _audit(unique_day, user_id=None, user_role="student"),
        _audit(unique_day, event_type="group_session_completed", user_id=None,
               user_role="system", entity_type="group_session", entity_id=3),
        _audit(unique_day, event_type="legacy_event_from_2019", user_id=None,
               user_role=None, entity_type=None, entity_id=None),
    ])
    token, _ = admin
    params = {**_window(unique_day), "include_access_events": "true"}

    total = client.get(EVENTS_URL, headers=_auth(token), params=params).json()["total"]
    seen = []
    for kind in ("user", "system", "unavailable"):
        body = client.get(EVENTS_URL, headers=_auth(token),
                          params={**params, "actor_kind": kind}).json()
        seen.extend(i["entry_id"] for i in body["items"])
        for item in body["items"]:
            assert item["actor"]["kind"] == kind

    assert len(seen) == len(set(seen)), "строка попала в два класса"
    assert len(seen) == total, "разбиение не покрывает все строки"


# ─── Target ───────────────────────────────────────────────────────────────────

def test_user_target_is_addressed_by_uuid_and_never_exposes_the_internal_id(
    client, admin, unique_day,
):
    _, actor_id = _make_user("admin", client)
    _, target_id = _make_user("student", client)
    with SessionLocal() as db:
        target_uuid = str(db.get(User, target_id).uuid)

    _insert([_audit(unique_day, user_id=actor_id, user_role="admin",
                    entity_type="user", entity_id=target_id)])
    token, _ = admin

    body = client.get(EVENTS_URL, headers=_auth(token), params={
        **_window(unique_day), "target_user_uuid": target_uuid,
        "entity_type": "user",
    }).json()

    assert body["total"] == 1
    item = body["items"][0]
    assert item["target"]["entity_type"] == "user"
    assert item["target"]["entity_ref"] is None
    assert item["target"]["user"]["user_uuid"] == target_uuid
    # Проверка точная, по листовым значениям: подстрочный поиск давал бы ложные
    # срабатывания на маленьких id (например «3» встречается в timestamp и UUID).
    assert target_id not in _leaf_values(item["target"])


def test_internal_user_id_cannot_be_resolved_to_a_uuid(
    client, admin, unique_day,
):
    """Ключевой security-инвариант: целочисленный идентификатор не должен быть
    рабочим ключом поиска по пользователям.

    Иначе перебор `entity_id` выдавал бы UUID и текущее ФИО из безопасной
    сводки цели — то есть `users.id` становился бы внешним идентификатором
    через чёрный ход.
    """
    _, actor_id = _make_user("admin", client)
    _, target_id = _make_user("student", client)
    with SessionLocal() as db:
        target_uuid = str(db.get(User, target_id).uuid)

    _insert([_audit(unique_day, user_id=actor_id, user_role="admin",
                    entity_type="user", entity_id=target_id)])
    token, _ = admin

    r = client.get(EVENTS_URL, headers=_auth(token), params={
        **_window(unique_day), "entity_id": target_id,
    })
    assert r.status_code == 422
    assert target_uuid not in r.text

    # И явная пара «user + внутренний id» тоже закрыта.
    paired = client.get(EVENTS_URL, headers=_auth(token), params={
        **_window(unique_day), "entity_type": "user", "entity_id": target_id,
    })
    assert paired.status_code == 422
    assert target_uuid not in paired.text


def test_record_id_without_table_name_is_rejected(client, admin, unique_day):
    _, target_id = _make_user("student", client)
    with SessionLocal() as db:
        target_uuid = str(db.get(User, target_id).uuid)

    _insert([_change(unique_day, table_name="users", record_id=target_id,
                     changed_fields=["full_name"])])
    token, _ = admin

    r = client.get(CHANGES_URL, headers=_auth(token), params={
        **_window(unique_day), "record_id": target_id,
    })
    assert r.status_code == 422
    assert target_uuid not in r.text


def test_typed_integer_reference_still_works(client, admin, unique_day):
    """Ограничение бьёт по неоднозначности, а не по самой возможности искать
    по техническому идентификатору."""
    _, actor_id = _make_user("supervisor", client)
    _insert([
        _audit(unique_day, event_type="meeting_type_created", user_id=actor_id,
               user_role="supervisor", entity_type="meeting_type", entity_id=4321),
        _change(unique_day, table_name="meeting_types", record_id=4321,
                actor_id=actor_id),
    ])
    token, _ = admin
    params = _window(unique_day)

    events = client.get(EVENTS_URL, headers=_auth(token), params={
        **params, "entity_type": "meeting_type", "entity_id": 4321,
    })
    changes = client.get(CHANGES_URL, headers=_auth(token), params={
        **params, "table_name": "meeting_types", "record_id": 4321,
    })

    assert events.status_code == 200
    assert changes.status_code == 200
    assert events.json()["total"] == 1
    assert changes.json()["total"] == 1
    assert events.json()["items"][0]["target"]["entity_ref"] == 4321
    assert changes.json()["items"][0]["record_id"] == 4321


def test_corrupted_target_is_excluded_from_every_target_filter(
    client, admin, unique_day,
):
    """`admin_role_add` над `article` — противоречие. Такая строка не должна
    попадать в целевой фильтр и затем показываться с пустым target."""
    _, actor_id = _make_user("admin", client)
    _, target_id = _make_user("student", client)
    with SessionLocal() as db:
        target_uuid = str(db.get(User, target_id).uuid)

    _insert([_audit(unique_day, user_id=actor_id, user_role="admin",
                    entity_type="article", entity_id=target_id)])
    token, _ = admin
    params = _window(unique_day)

    by_uuid = client.get(EVENTS_URL, headers=_auth(token), params={
        **params, "target_user_uuid": target_uuid, "entity_type": "user",
    }).json()
    by_entity_type = client.get(EVENTS_URL, headers=_auth(token), params={
        **params, "entity_type": "user",
    }).json()
    # Ключевой регресс: плоского `event_type IN <все REQUIRED>` было бы мало —
    # нужна дизъюнкция «тип цели согласован со своим событием».
    by_typed_entity_id = client.get(EVENTS_URL, headers=_auth(token), params={
        **params, "entity_type": "article", "entity_id": target_id,
    }).json()

    assert by_uuid["total"] == 0
    assert by_entity_type["total"] == 0
    assert by_typed_entity_id["total"] == 0

    # Без целевого фильтра строка видна, но её target отредактирован.
    everything = client.get(EVENTS_URL, headers=_auth(token), params=params).json()
    assert everything["total"] == 1
    assert everything["items"][0]["target"] is None
    assert everything["items"][0]["details_redacted"] is True


def test_non_user_target_exposes_a_technical_reference(client, admin, unique_day):
    _, actor_id = _make_user("supervisor", client)
    _insert([_audit(unique_day, event_type="meeting_type_created",
                    user_id=actor_id, user_role="supervisor",
                    entity_type="meeting_type", entity_id=1234)])
    token, _ = admin

    body = client.get(EVENTS_URL, headers=_auth(token), params={
        **_window(unique_day), "entity_type": "meeting_type",
    }).json()
    assert body["items"][0]["target"]["entity_ref"] == 1234


# ─── Порядок, границы партиций, пагинация ────────────────────────────────────

def test_rows_from_two_adjacent_month_partitions_come_in_one_page(client, admin):
    """Партиции месячные — запрос обязан идти к parent и склеивать их."""
    end_of_month = date(2026, 6, 30)
    start_of_next = date(2026, 7, 1)
    _insert([
        _audit(end_of_month, entity_id=1),
        _audit(start_of_next, entity_id=2),
    ])
    token, _ = admin

    body = client.get(EVENTS_URL, headers=_auth(token), params={
        "date_from": end_of_month.isoformat(), "date_to": start_of_next.isoformat(),
        "entity_type": "user", "size": 100,
    }).json()
    assert body["total"] >= 2

    days = {i["occurred_at"][:10] for i in body["items"]}
    assert {"2026-06-30", "2026-07-01"} <= days


def test_identical_timestamps_have_a_stable_tie_break_by_id(
    client, admin, unique_day,
):
    moment = _at(unique_day, 9, 30)
    _insert([_audit(unique_day, created_at=moment, entity_id=n) for n in (1, 2, 3)])
    token, _ = admin

    desc = client.get(EVENTS_URL, headers=_auth(token), params={
        **_window(unique_day), "order": "desc",
    }).json()
    asc = client.get(EVENTS_URL, headers=_auth(token), params={
        **_window(unique_day), "order": "asc",
    }).json()

    desc_ids = [int(i["entry_id"]) for i in desc["items"]]
    asc_ids = [int(i["entry_id"]) for i in asc["items"]]
    assert desc_ids == sorted(desc_ids, reverse=True)
    assert asc_ids == sorted(asc_ids)
    assert desc_ids == list(reversed(asc_ids))


def test_pagination_is_server_side_and_total_is_filter_aware(
    client, admin, unique_day,
):
    _insert([_audit(unique_day, created_at=_at(unique_day, 8, n), entity_id=n + 1)
             for n in range(5)])
    token, _ = admin
    params = _window(unique_day)

    first = client.get(EVENTS_URL, headers=_auth(token),
                       params={**params, "page": 1, "size": 2}).json()
    second = client.get(EVENTS_URL, headers=_auth(token),
                        params={**params, "page": 2, "size": 2}).json()

    assert first["total"] == second["total"] == 5
    assert (first["page"], first["size"]) == (1, 2)
    assert len(first["items"]) == len(second["items"]) == 2
    assert {i["entry_id"] for i in first["items"]}.isdisjoint(
        i["entry_id"] for i in second["items"]
    )


# ─── Событие просмотра ────────────────────────────────────────────────────────

def test_one_request_records_exactly_one_access_event(client, admin):
    token, _ = admin
    before = _count_access_events()
    client.get(EVENTS_URL, headers=_auth(token))
    assert _count_access_events() == before + 1


def test_access_event_is_absent_from_its_own_response(client, admin):
    token, _ = admin
    body = client.get(EVENTS_URL, headers=_auth(token),
                      params={"include_access_events": "true"}).json()
    recorded = _count_access_events()
    # Событие записано ПОСЛЕ выборки, поэтому в ответ попасть не могло.
    shown = sum(1 for i in body["items"] if i["event_code"] == "audit_logs_viewed")
    assert shown < recorded


def test_default_feed_hides_access_events_and_filters_reveal_them(client, admin):
    token, _ = admin
    client.get(EVENTS_URL, headers=_auth(token))     # породить хотя бы одно

    default = client.get(EVENTS_URL, headers=_auth(token), params={"size": 100}).json()
    assert all(i["event_code"] != "audit_logs_viewed" for i in default["items"])

    explicit = client.get(EVENTS_URL, headers=_auth(token), params={
        "event_type": "audit_logs_viewed", "size": 100,
    }).json()
    assert explicit["total"] >= 1
    assert all(i["event_code"] == "audit_logs_viewed" for i in explicit["items"])

    opted_in = client.get(EVENTS_URL, headers=_auth(token), params={
        "include_access_events": "true", "size": 100,
    }).json()
    assert opted_in["total"] >= explicit["total"]


def test_access_event_metadata_carries_names_only(client, admin):
    token, _ = admin
    client.get(AUTH_URL, headers=_auth(token), params={"success": False})

    with SessionLocal() as db:
        row = (
            db.query(AuditLog)
            .filter(AuditLog.event_type == "audit_logs_viewed")
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .first()
        )
    assert row.log_metadata["journal"] == "auth_log"
    # success=False обязан считаться применённым фильтром.
    assert set(row.log_metadata["filter_keys"]) == {"date_range", "success"}
    assert row.entity_type is None and row.entity_id is None
    assert row.outcome == "success" and row.failure_reason_code is None


def test_audit_write_failure_suppresses_the_payload(client, admin, monkeypatch):
    from app.audit import admin_service as svc
    from app.audit.contracts import AuditStorageError

    def _boom(**kwargs):
        raise AuditStorageError("sanitised")

    monkeypatch.setattr(svc, "record_event", _boom)
    token, _ = admin

    r = client.get(EVENTS_URL, headers=_auth(token))
    assert r.status_code == 503
    body = r.json()
    assert "items" not in body
    assert "sanitised" not in r.text


# ─── Утечки ───────────────────────────────────────────────────────────────────

def test_hostile_legacy_rows_do_not_leak(client, admin, unique_day):
    markers = {
        "description": "Синтетический plaintext контента сессии",
        "ua": "Mozilla/5.0 (SyntheticProbe)",
        "url": "/api/admin/users?token=synthetic-leak-token",
        "session": "f" * 64,
        "ip": "203.0.113.42",
        "reason": "Traceback: synthetic exception text",
        "old": "Синтетическое ФИО из old_values",
    }
    _insert([
        _audit(
            unique_day, event_type="legacy_event_from_2019", user_id=None,
            user_role=None, entity_type=None, entity_id=None,
            description=markers["description"], user_agent=markers["ua"],
            request_url=markers["url"], session_id=markers["session"],
            ip_address=markers["ip"],
            log_metadata={"password": "synthetic", "note": markers["description"]},
        ),
        _authlog(
            unique_day, event="failed_login", user_id=None, success=False,
            failure_reason=markers["reason"], ip_address=markers["ip"],
            user_agent=markers["ua"], session_id=markers["session"],
            mfa_method="totp",
        ),
        _change(
            unique_day, table_name="users", record_id=1,
            changed_fields=["full_name"], ip_address=markers["ip"],
            old_values={"full_name": markers["old"]},
            new_values={"full_name": markers["old"]},
        ),
    ])
    token, _ = admin
    params = _window(unique_day)

    payload = "".join(
        client.get(url, headers=_auth(token), params=params).text
        for url in (EVENTS_URL, AUTH_URL, CHANGES_URL)
    )
    for name, marker in markers.items():
        assert marker not in payload, f"утечка {name}"


def test_data_change_values_are_never_returned(client, admin, unique_day):
    _insert([_change(unique_day, table_name="meeting_types", record_id=7,
                     changed_fields=["duration_minutes"],
                     old_values={"duration_minutes": 30},
                     new_values={"duration_minutes": 60})])
    token, _ = admin

    body = client.get(CHANGES_URL, headers=_auth(token),
                      params=_window(unique_day)).json()
    item = body["items"][0]
    assert item["changed_fields"] == ["duration_minutes"]
    assert "old_values" not in item and "new_values" not in item
    assert "30" not in str(item) and "60" not in str(item)


def test_legacy_operation_outside_the_table_contract_is_redacted(
    client, admin, unique_day,
):
    _insert([_change(unique_day, table_name="meeting_types", operation="INSERT")])
    token, _ = admin

    item = client.get(CHANGES_URL, headers=_auth(token),
                      params=_window(unique_day)).json()["items"][0]
    assert item["operation"] is None
    assert item["details_redacted"] is True


# ─── Производительность и изоляция контента ──────────────────────────────────

def test_query_count_does_not_grow_with_page_size(client, admin, unique_day):
    """Отсутствие N+1: число SQL-запросов не зависит от размера страницы."""
    _insert([_audit(unique_day, created_at=_at(unique_day, 7, n), entity_id=n + 1)
             for n in range(20)])
    token, _ = admin

    def _count(size):
        seen = []

        def _hook(conn, cursor, statement, params, context, executemany):
            seen.append(statement)

        event.listen(engine, "before_cursor_execute", _hook)
        try:
            r = client.get(EVENTS_URL, headers=_auth(token),
                           params={**_window(unique_day), "size": size})
            assert r.status_code == 200
        finally:
            event.remove(engine, "before_cursor_execute", _hook)
        return len(seen)

    small, large = _count(1), _count(20)
    assert small == large, f"{small} → {large}: похоже на N+1"


def test_viewer_never_decrypts_therapeutic_content(client, admin, monkeypatch):
    from app.core import encryption

    def _boom(ciphertext):
        raise AssertionError("viewer не должен расшифровывать контент")

    monkeypatch.setattr(encryption, "decrypt_text", _boom)
    token, _ = admin
    for url in (EVENTS_URL, AUTH_URL, CHANGES_URL, OPTIONS_URL):
        assert client.get(url, headers=_auth(token)).status_code == 200


def test_queries_are_bounded_by_the_period(client, admin, unique_day):
    """Фильтр по created_at присутствует всегда — без него partition pruning
    невозможен, а окно стало бы неограниченным."""
    long_ago = date(2026, 2, 15)
    _insert([_audit(long_ago, entity_id=1)])
    token, _ = admin

    inside = client.get(EVENTS_URL, headers=_auth(token), params={
        "date_from": long_ago.isoformat(), "date_to": long_ago.isoformat(),
    }).json()
    outside = client.get(EVENTS_URL, headers=_auth(token),
                         params=_window(unique_day)).json()

    assert inside["total"] >= 1
    assert all(i["occurred_at"][:10] != long_ago.isoformat()
               for i in outside["items"])


def test_new_indexes_exist_on_the_partitioned_parents():
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT indexname FROM pg_indexes "
            "WHERE indexname IN "
            "('idx_audit_created', 'idx_auth_created', 'idx_dcl_created')"
        )).fetchall()
    assert {r[0] for r in rows} == {
        "idx_audit_created", "idx_auth_created", "idx_dcl_created",
    }
