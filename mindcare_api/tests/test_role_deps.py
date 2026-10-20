"""
Unit-тесты dependency-слоя авторизации (app/auth/deps.py) — без БД, но НЕ pure:
импортируют FastAPI HTTPException и dependency factories require_role /
resolve_role_or_403 (потому и отдельный файл, а не test_roles.py, который
остаётся pure-only для app/auth/roles.py).

Фиксируют ADR-018 инвариант: явный `roles` (включая пустой `[]`) — источник
истины; legacy fallback на `role` допустим только при полном отсутствии ключа
`roles`. Пустое membership → 403, а не тихий откат на stale `role`.
"""

import pytest
from fastapi import HTTPException

from app.auth.deps import (
    _user_role_names,
    require_role,
    resolve_role_or_403,
)


class TestUserRoleNames:
    def test_explicit_empty_roles_beats_stale_legacy_role(self):
        # Ключ roles присутствует и пуст → источник истины; legacy role
        # ("admin") игнорируется, membership пусто.
        assert _user_role_names({"roles": [], "role": "admin"}) == []

    def test_legacy_fallback_only_when_roles_key_absent(self):
        assert _user_role_names({"role": "admin"}) == ["admin"]

    def test_multiple_explicit_membership_roles_returned_in_full(self):
        assert _user_role_names({"roles": ["admin", "supervisor"]}) == [
            "admin",
            "supervisor",
        ]


class TestRequireRoleExplicitEmpty:
    def test_rejects_empty_roles_with_stale_legacy_role(self):
        # require_role возвращает checker(current_user=...); membership пусто →
        # пересечение с allowed пусто → 403, несмотря на legacy role="admin".
        checker = require_role("admin")
        with pytest.raises(HTTPException) as exc:
            checker(current_user={"roles": [], "role": "admin"})
        assert exc.value.status_code == 403


class TestResolveRoleOr403ExplicitEmpty:
    def test_rejects_empty_roles_with_stale_legacy_role(self):
        with pytest.raises(HTTPException) as exc:
            resolve_role_or_403(
                {"roles": [], "role": "admin"},
                allowed={"admin"},
                preferred="admin",
            )
        assert exc.value.status_code == 403
