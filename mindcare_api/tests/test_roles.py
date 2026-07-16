"""
Unit-тесты чистых multi-role helpers (app/auth/roles.py) — без DB/FastAPI.

Покрывает:
  - primary_role: глобальный приоритет, пустой набор → None (НЕ 'student');
  - effective_role: ограничение по allowed, предпочтение preferred ТОЛЬКО если
    preferred ∈ (roles ∩ allowed), fallback по приоритету, None при пустом.
"""

from app.auth.roles import ROLE_PRIORITY, primary_role, effective_role


class TestPrimaryRole:
    def test_priority_order(self):
        assert primary_role(["student", "psychologist"]) == "psychologist"
        assert primary_role(["supervisor", "psychologist"]) == "supervisor"
        assert primary_role(["admin", "student"]) == "admin"
        assert primary_role(["admin", "supervisor", "psychologist"]) == "admin"

    def test_single(self):
        assert primary_role(["student"]) == "student"
        assert primary_role(["psychologist"]) == "psychologist"

    def test_empty_is_none_not_student(self):
        assert primary_role([]) is None
        assert primary_role(set()) is None

    def test_accepts_any_iterable(self):
        assert primary_role({"supervisor", "student"}) == "supervisor"

    def test_priority_constant_shape(self):
        assert ROLE_PRIORITY == (
            "admin", "supervisor", "psychologist", "student",
        )


class TestEffectiveRole:
    def test_no_allowed_uses_global_priority(self):
        assert effective_role(["supervisor", "psychologist"]) == "supervisor"

    def test_allowed_scoping(self):
        # admin отфильтрован allowed → берём supervisor.
        assert effective_role(
            ["admin", "supervisor"], allowed={"supervisor", "psychologist"}
        ) == "supervisor"

    def test_preferred_returned_when_in_roles_and_allowed(self):
        assert effective_role(
            ["admin", "supervisor"],
            allowed={"admin", "supervisor"},
            preferred="supervisor",
        ) == "supervisor"

    def test_preferred_ignored_when_not_held(self):
        # preferred psychologist пользователю не принадлежит → приоритет.
        assert effective_role(
            ["admin", "supervisor"],
            allowed={"admin", "supervisor"},
            preferred="psychologist",
        ) == "admin"

    def test_preferred_not_returned_when_not_in_allowed(self):
        # preferred есть у пользователя, но вне allowed данного endpoint-а →
        # не возвращаем preferred, берём высшую из (roles ∩ allowed).
        assert effective_role(
            ["admin", "psychologist"],
            allowed={"psychologist"},
            preferred="admin",
        ) == "psychologist"

    def test_empty_intersection_is_none(self):
        assert effective_role(["student"], allowed={"admin"}) is None
        assert effective_role([], allowed={"admin"}) is None
        assert effective_role([]) is None

    def test_never_exceeds_membership(self):
        # результат всегда ∈ role_names.
        result = effective_role(
            ["psychologist"], allowed={"admin", "psychologist"}, preferred="admin",
        )
        assert result == "psychologist"
