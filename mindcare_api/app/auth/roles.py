"""
Multi-role helpers (ADR-018) — ЧИСТЫЕ функции, без DB / FastAPI / HTTP.

Источник прав доступа — набор активных membership-ролей пользователя в
`user_roles`. Здесь только преобразования над списком имён ролей:

  - primary_role  — legacy/default/effective convenience: детерминированная
                    роль по глобальному приоритету (admin > supervisor >
                    psychologist > student). Возвращает None при отсутствии
                    ролей — НЕ маскирует пустой набор как "student".
  - effective_role — контекстно-зависимый выбор роли для конкретного
                    endpoint/кабинета: сначала ограничение по allowed, затем
                    предпочтение preferred (кабинет), иначе — по приоритету.

`primary_role` и `effective_role` — разные вещи: первый использует глобальный
приоритет, второй учитывает allowed/preferred текущего endpoint-а.

HTTP-guard (raise 403 при None) живёт в app/auth/deps.py, а не здесь: этот модуль
не должен зависеть от FastAPI. Порядок приоритета согласован с SQL-выражением
`_ROLE_PRIORITY` в app/users/storage.py.
"""

from typing import Iterable, Optional

# Глобальный приоритет ролей: чем левее — тем «главнее» (default cabinet, primary).
ROLE_PRIORITY: tuple[str, ...] = ("admin", "supervisor", "psychologist", "student")


def primary_role(role_names: Iterable[str]) -> Optional[str]:
    """
    Детерминированная primary/default роль по глобальному приоритету.

    Возвращает высшую по ROLE_PRIORITY роль из имеющихся или None, если набор
    пуст. НЕ возвращает "student" как fallback: отсутствие ролей — это
    отсутствие прав, а не роль студента.
    """
    names = set(role_names)
    for role in ROLE_PRIORITY:
        if role in names:
            return role
    return None


def effective_role(
    role_names: Iterable[str],
    *,
    allowed: Optional[Iterable[str]] = None,
    preferred: Optional[str] = None,
) -> Optional[str]:
    """
    Контекстная роль пользователя для конкретного endpoint/кабинета.

    Алгоритм:
      1. names = set(role_names) ∩ allowed   (если allowed задан; иначе — все);
      2. preferred возвращается ТОЛЬКО если preferred ∈ names
         (т.е. preferred ∈ (role_names ∩ allowed)) — предпочтение кабинета
         нельзя удовлетворить ролью, которой у пользователя нет ИЛИ которая не
         разрешена на данном endpoint;
      3. иначе — высшая по ROLE_PRIORITY роль из names;
      4. None, если names пусто.

    Никогда не расширяет доступ сверх membership: результат всегда ∈ role_names
    (и ∈ allowed, если allowed задан).
    """
    names = set(role_names)
    if allowed is not None:
        names &= set(allowed)

    if preferred is not None and preferred in names:
        return preferred

    for role in ROLE_PRIORITY:
        if role in names:
            return role
    return None
