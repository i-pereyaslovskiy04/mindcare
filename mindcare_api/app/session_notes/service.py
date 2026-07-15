"""
Access policy session_notes (Stage 25b, политика B) + multi-role (ADR-018):

  psychologist — create/list/get/update только свои заметки, с content;
  supervisor   — list: metadata-only (без decrypt);
                 get by id: content разрешён, КАЖДЫЙ такой read → audit_log;
  admin        — list и get: metadata-only, decrypt не вызывается вообще;
                 доступ к терапевтическому content админу не предоставляется
                 (возможный break-glass — отдельное compliance-решение);
  student      — 403 на уровне роутера (require_role).

Multi-role: у пользователя может быть несколько ролей одновременно. policy-ветка
и actor_role в audit выбираются НЕ по случайной primary роли, а через
`_resolve_notes_role`:
  - `X-Active-Role` (клиентская подсказка активного кабинета) валидируется по
    membership: должна быть среди policy-ролей пользователя, иначе 403 — не тихий
    fallback;
  - без подсказки при единственной policy-роли — она и используется;
  - без подсказки при нескольких policy-ролях — КОНСЕРВАТИВНЫЙ default (наименьшая
    экспозиция content: admin=metadata < psychologist=own < supervisor=all+audit);
    широкий supervisor-доступ берётся только по явному `X-Active-Role: supervisor`.
`effective_role` никогда не расширяет доступ сверх membership.

Plaintext content не логируется нигде; audit-хелпер принимает только id/метаданные.
"""

from typing import Optional

from app.session_notes import storage
from app.session_notes.audit import log_note_event


class NoteNotFound(Exception):
    pass


class NotesAccessError(Exception):
    """Невалидная/неразрешённая active-роль для session_notes → route мапит на 403."""


# Роли, у которых вообще есть policy-ветка на этом ресурсе.
NOTES_POLICY_ROLES = ("admin", "supervisor", "psychologist")

# Консервативный порядок по возрастанию экспозиции терапевтического content:
# admin (metadata-only) < psychologist (только свои) < supervisor (любые + audit).
# При нескольких policy-ролях без явной подсказки берём первую из этого порядка.
_NOTES_CONSERVATIVE_ORDER = ("admin", "psychologist", "supervisor")


def _resolve_notes_role(role_names, requested: Optional[str]) -> str:
    """
    Детерминированная acting-роль для session_notes из набора ролей пользователя.

    holder = роли пользователя ∩ NOTES_POLICY_ROLES. Пусто → 403 (не должно
    случаться после require_role). Если `requested` (X-Active-Role) задан — он
    обязан быть в holder, иначе 403. Иначе: единственная holder-роль, либо
    консервативный default при нескольких.
    """
    holder = [r for r in NOTES_POLICY_ROLES if r in set(role_names)]
    if not holder:
        raise NotesAccessError("Нет подходящей роли для доступа к заметкам")

    if requested is not None:
        if requested not in holder:
            raise NotesAccessError(
                "Указанная активная роль недоступна для этого действия"
            )
        return requested

    if len(holder) == 1:
        return holder[0]

    for role in _NOTES_CONSERVATIVE_ORDER:
        if role in holder:
            return role
    return holder[0]  # недостижимо: holder ⊆ NOTES_POLICY_ROLES


def create_note(
    data: dict,
    author_id: int,
    *,
    actor_role: str = "psychologist",
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    note = storage.create_note(
        author_id=author_id,
        appointment_id=data.get("appointment_id"),
        engagement_id=data.get("engagement_id"),
        note_type=data.get("note_type", "general"),
        content=data["content"],
        is_shared_with_client=data.get("is_shared_with_client", False),
    )
    log_note_event(
        "session_note_created",
        actor_id=author_id,
        actor_role=actor_role,
        note_id=note["id"],
        author_id=note["author_id"],
        engagement_id=note["engagement_id"],
        appointment_id=note["appointment_id"],
        ip=ip,
        user_agent=user_agent,
    )
    return note


def get_note(
    note_id: int,
    *,
    current_user: dict,
    requested_role: Optional[str] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    role = _resolve_notes_role(current_user.get("roles") or [], requested_role)

    if role == "admin":
        # Metadata-only: decrypt не вызывается, content недоступен
        note = storage.get_note_by_id(note_id, include_content=False)
    elif role == "supervisor":
        note = storage.get_note_by_id(note_id)
    else:
        # psychologist: только свои (чужая заметка неотличима от несуществующей)
        note = storage.get_note_by_id(note_id, author_id=current_user["id"])

    if not note:
        raise NoteNotFound()

    if role == "supervisor":
        # Staff-доступ к расшифрованному терапевтическому content — в audit
        log_note_event(
            "session_note_content_read",
            actor_id=int(current_user["id"]),
            actor_role=role,
            note_id=note["id"],
            author_id=note["author_id"],
            engagement_id=note["engagement_id"],
            appointment_id=note["appointment_id"],
            ip=ip,
            user_agent=user_agent,
        )

    return note


def list_notes(
    page:             int,
    size:             int,
    appointment_id:   Optional[int],
    engagement_id:    Optional[int],
    filter_author_id: Optional[int],
    *,
    current_user: dict,
    requested_role: Optional[str] = None,
) -> tuple[list[dict], int]:
    role = _resolve_notes_role(current_user.get("roles") or [], requested_role)

    if role in ("admin", "supervisor"):
        # Staff-список — metadata-only: без content и без decrypt.
        # Content для supervisor доступен только поштучно (GET by id, под audit).
        return storage.find_notes(
            page=page,
            size=size,
            author_id=filter_author_id,   # None = все; конкретный id = фильтр
            appointment_id=appointment_id,
            engagement_id=engagement_id,
            include_content=False,
        )

    # psychologist: всегда только свои, с content
    return storage.find_notes(
        page=page,
        size=size,
        author_id=current_user["id"],
        appointment_id=appointment_id,
        engagement_id=engagement_id,
    )


def update_note(
    note_id: int,
    data: dict,
    *,
    current_user: dict,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    note = storage.update_note(note_id, data, author_id=current_user["id"])
    if not note:
        raise NoteNotFound()
    # update — psychologist-only (require_role на роутере); actor действует как
    # psychologist, а не как случайная primary роль multi-role пользователя.
    actor_role = _resolve_notes_role(current_user.get("roles") or [], "psychologist")
    log_note_event(
        "session_note_updated",
        actor_id=int(current_user["id"]),
        actor_role=actor_role,
        note_id=note["id"],
        author_id=note["author_id"],
        engagement_id=note["engagement_id"],
        appointment_id=note["appointment_id"],
        ip=ip,
        user_agent=user_agent,
    )
    return note
