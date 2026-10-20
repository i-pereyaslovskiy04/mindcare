"""
Stage 8 — классификация actor в admin viewer.

Главный регресс, который здесь закрывается: FK всех трёх журналов объявлен
`ON DELETE SET NULL` (`app/db/models/audit.py`), поэтому `user_id IS NULL` НЕ
означает «действие совершил аноним» — после физического удаления аккаунта так
выглядят и `login`, и `logout`, и `password_change`. Класс обязан выводиться из
`ActorPolicy` конкретной спеки, а не из наличия id.

Второй инвариант: SQL-фильтр и проекция обязаны классифицировать строку
одинаково. В unit-слое проверяется, что оба пути используют одни и те же
множества `admin_policy` и что SQL-предикаты NULL-безопасны; совпадение
результатов на реальных строках проверяет integration-тест.
"""
from __future__ import annotations

import pytest
from sqlalchemy.dialects import postgresql

from app.audit import admin_policy as pol
from app.audit import admin_storage as storage
from app.db.models import AuditLog, AuthLog, DataChangeLog, User
from sqlalchemy.orm import aliased


def _classify(policy, key, actor_id, role, user_found=True):
    return pol.classify_actor(
        policy, key=key, actor_id=actor_id, role=role, user_found=user_found,
    )


# ── ON DELETE SET NULL: обнулённый actor ≠ аноним ─────────────────────────────

@pytest.mark.parametrize("event", ["login", "logout", "password_change",
                                   "registration_succeeded"])
def test_user_event_with_nulled_actor_is_unavailable_not_anonymous(event):
    """Аккаунт физически удалён → FK обнулил user_id. Это потеря сведений об
    акторе, а не анонимное действие."""
    assert _classify(pol.AUTH_POLICY, event, None, None) == pol.KIND_UNAVAILABLE


@pytest.mark.parametrize("event", ["failed_login", "registration_failed",
                                   "password_reset"])
def test_anonymous_only_event_with_null_actor_is_anonymous(event):
    assert _classify(pol.AUTH_POLICY, event, None, None) == pol.KIND_ANONYMOUS


@pytest.mark.parametrize("event", ["failed_login", "registration_failed"])
def test_anonymous_only_event_with_actor_id_is_contradiction(event):
    """ANONYMOUS_ONLY-событие не может нести actor id — строка противоречива."""
    assert _classify(pol.AUTH_POLICY, event, 42, None) == pol.KIND_UNAVAILABLE


def test_user_event_with_missing_users_row_is_unavailable():
    assert _classify(
        pol.AUTH_POLICY, "login", 42, None, user_found=False,
    ) == pol.KIND_UNAVAILABLE


def test_user_event_with_present_account_is_user():
    assert _classify(pol.AUTH_POLICY, "login", 42, None) == pol.KIND_USER


# ── Роль актора против allowed_actor_roles своей спеки ────────────────────────

def test_audit_event_with_role_outside_allowlist_is_unavailable():
    """`admin_role_add` разрешён только администратору. Строка с ролью
    `student` внутренне противоречива и не должна выдаваться за пользователя."""
    assert _classify(pol.AUDIT_POLICY, "admin_role_add", 42, "student") == (
        pol.KIND_UNAVAILABLE
    )
    assert _classify(pol.AUDIT_POLICY, "admin_role_add", 42, "admin") == pol.KIND_USER


def test_audit_event_without_role_is_unavailable():
    assert _classify(pol.AUDIT_POLICY, "admin_role_add", 42, None) == (
        pol.KIND_UNAVAILABLE
    )


def test_role_at_event_is_none_for_non_user_actor():
    assert pol.role_at_event(pol.AUDIT_POLICY, pol.KIND_UNAVAILABLE, "student") is None
    assert pol.role_at_event(pol.AUDIT_POLICY, pol.KIND_USER, "admin") == "admin"


def test_auth_log_never_reports_a_role():
    """В `auth_log` колонки роли нет — подставлять текущую нельзя."""
    assert pol.role_at_event(pol.AUTH_POLICY, pol.KIND_USER, "admin") is None


def test_auth_log_does_not_validate_role():
    """Роль в auth-строке отсутствует физически, поэтому её нечем проверять:
    классификация опирается только на политику события и наличие аккаунта."""
    assert _classify(pol.AUTH_POLICY, "login", 42, "student") == pol.KIND_USER


# ── SYSTEM ────────────────────────────────────────────────────────────────────

def test_system_event_with_correct_representation_is_system():
    assert _classify(
        pol.AUDIT_POLICY, "group_session_completed", None, "system",
    ) == pol.KIND_SYSTEM


@pytest.mark.parametrize("actor_id,role", [
    (None, None),          # роль потеряна
    (None, "admin"),       # роль не системная
    (42, "system"),        # у SYSTEM-события не может быть actor id
])
def test_system_event_with_broken_representation_is_unavailable(actor_id, role):
    assert _classify(
        pol.AUDIT_POLICY, "group_session_completed", actor_id, role,
    ) == pol.KIND_UNAVAILABLE


# ── Неизвестные ключи ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("policy,key", [
    (pol.AUDIT_POLICY, "no_such_event"),
    (pol.AUDIT_POLICY, "login"),            # AUTH-событие в audit-журнале
    (pol.AUTH_POLICY, "admin_role_add"),    # AUDIT-событие в auth-журнале
    (pol.DCL_POLICY, "session_notes"),      # таблица вне CHANGE_REGISTRY
    (pol.AUDIT_POLICY, None),
])
def test_unknown_key_is_unavailable(policy, key):
    assert _classify(policy, key, 42, "admin") == pol.KIND_UNAVAILABLE


# ── data_change_log ───────────────────────────────────────────────────────────

def test_data_change_actor_follows_table_spec():
    assert _classify(pol.DCL_POLICY, "users", 42, "admin") == pol.KIND_USER
    # meeting_types доступны supervisor/admin, но не студенту.
    assert _classify(pol.DCL_POLICY, "meeting_types", 42, "student") == (
        pol.KIND_UNAVAILABLE
    )
    assert _classify(pol.DCL_POLICY, "meeting_types", 42, "supervisor") == (
        pol.KIND_USER
    )


def test_data_change_system_kind_is_not_producible_today():
    """Все четыре TableSpec объявлены USER_REQUIRED, поэтому `system` не может
    возникнуть — и не должен предлагаться как значение фильтра."""
    assert pol.KIND_SYSTEM not in pol.DCL_POLICY.kinds
    assert pol.DCL_POLICY.kinds == (pol.KIND_USER, pol.KIND_UNAVAILABLE)


# ── Достижимость и замкнутость ────────────────────────────────────────────────

@pytest.mark.parametrize("journal", pol.JOURNALS)
def test_classifier_never_returns_a_kind_outside_declared_set(journal):
    policy = pol.POLICY_BY_JOURNAL[journal]
    keys = sorted(policy.all_names)[:12] + ["definitely_not_a_key", None]
    roles = [None, "admin", "student", "system", "root"]

    produced = set()
    for key in keys:
        for actor_id in (None, 42):
            for role in roles:
                for found in (True, False):
                    produced.add(_classify(policy, key, actor_id, role, found))

    assert produced <= set(policy.kinds), (
        f"{journal}: классификатор вернул класс вне объявленного набора"
    )
    assert pol.KIND_UNAVAILABLE in produced


def test_roleset_grouping_loses_nothing():
    """SQL строится по `names_by_roleset`, проекция — по `roles_by_name`.
    Группировка обязана быть точным разбиением, иначе фильтр потеряет события."""
    for policy in pol.POLICY_BY_JOURNAL.values():
        flattened = {}
        for roles, names in policy.names_by_roleset.items():
            for name in names:
                assert name not in flattened, "имя попало в две группы"
                flattened[name] = roles
        assert flattened == dict(policy.roles_by_name)


# ── SQL-предикаты ─────────────────────────────────────────────────────────────

def _sql(expr) -> str:
    return str(expr.compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True},
    )).lower()


def _audit_predicates():
    actor = aliased(User)
    return storage.actor_kind_predicates(
        pol.AUDIT_POLICY,
        key_col=AuditLog.event_type, id_col=AuditLog.user_id,
        role_col=AuditLog.user_role, joined_id_col=actor.id,
    )


def _auth_predicates():
    actor = aliased(User)
    return storage.actor_kind_predicates(
        pol.AUTH_POLICY,
        key_col=AuthLog.event, id_col=AuthLog.user_id, joined_id_col=actor.id,
    )


def _dcl_predicates():
    actor = aliased(User)
    return storage.actor_kind_predicates(
        pol.DCL_POLICY,
        key_col=DataChangeLog.table_name, id_col=DataChangeLog.actor_id,
        role_col=DataChangeLog.actor_role, joined_id_col=actor.id,
    )


@pytest.mark.parametrize("build", [_audit_predicates, _auth_predicates, _dcl_predicates])
def test_predicates_cover_every_kind_constant(build):
    predicates = build()
    assert set(predicates) == {
        pol.KIND_USER, pol.KIND_SYSTEM, pol.KIND_ANONYMOUS, pol.KIND_UNAVAILABLE,
    }


@pytest.mark.parametrize("build,kind", [
    (_audit_predicates, pol.KIND_USER),
    (_audit_predicates, pol.KIND_SYSTEM),
    (_auth_predicates, pol.KIND_USER),
    (_auth_predicates, pol.KIND_ANONYMOUS),
    (_dcl_predicates, pol.KIND_USER),
])
def test_positive_predicates_are_null_free(build, kind):
    """SQL трёхзначен: без `coalesce` предикат с NULL-ролью дал бы NULL, и
    `NOT(...)` тоже NULL — строка молча выпала бы из `unavailable`."""
    assert "coalesce" in _sql(build()[kind])


@pytest.mark.parametrize("build", [_audit_predicates, _auth_predicates, _dcl_predicates])
def test_unavailable_is_the_complement_of_the_other_kinds(build):
    sql = _sql(build()[pol.KIND_UNAVAILABLE])
    assert sql.startswith("not ")


def test_audit_user_predicate_constrains_role_per_event():
    """Роль обязана проверяться внутри SQL, иначе фильтр `actor_kind=user`
    вернул бы противоречивые строки, которые проекция помечает `unavailable`."""
    sql = _sql(_audit_predicates()[pol.KIND_USER])
    assert "user_role" in sql
    assert "'admin_role_add'" in sql


def test_auth_user_predicate_does_not_reference_a_role_column():
    sql = _sql(_auth_predicates()[pol.KIND_USER])
    assert "role" not in sql


def test_role_aware_policy_requires_a_role_column():
    """Забытая колонка роли должна ронять построение запроса, а не тихо
    выключать проверку allowlist."""
    actor = aliased(User)
    with pytest.raises(ValueError):
        storage.actor_kind_predicates(
            pol.AUDIT_POLICY,
            key_col=AuditLog.event_type, id_col=AuditLog.user_id,
            joined_id_col=actor.id,
        )
