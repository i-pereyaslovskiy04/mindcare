"""
Storage session_notes: весь SQLAlchemy и шифрование content (Fernet enc:v1:).

ADR-035 (карточка клиента у психолога):
  * создание проверяет связи ДО вставки (_check_links): встреча и
    сопровождение принадлежат автору, при обеих связях клиент совпадает
    (прямой или через привязанную карточку). Отказ — NoteLinkInvalid;
  * обе правки (generic PATCH и client-scoped) пишут через ОДИН механизм
    _apply_note_update: строка заметки FOR UPDATE, CAS по version (если версия
    передана), diff со старыми значениями (content — после расшифровки:
    Fernet недетерминирован), version+1 при ЛЮБОМ реальном изменении
    редактируемого поля, настоящий no-op ничего не меняет и не пишет событие;
  * client-scoped чтение и правка видят заметку, только если КАЖДАЯ
    заполненная связь принадлежит психологу и этому клиенту
    (_relates_to_client) — противоречивые старые записи не выдаются и не
    расшифровываются, автоматически не исправляются.
"""
import sys
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import and_, desc, exists, or_, select
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import SessionLocal
from app.db.models import Appointment, SessionNote, TherapyEngagement, UnregisteredStudentCard
from app.core.encryption import decrypt_text, encrypt_text
from app.audit import Actor, Outcome, Target, record_event
from app.audit.request_context import build_request_context
from app.psychologist.client_scope import lock_client_scope


class NoteLinkInvalid(Exception):
    """Связь заметки чужая/несуществующая (access_denied) или несогласованная (link_mismatch)."""

    def __init__(self, failure_reason: str):
        super().__init__(failure_reason)
        self.failure_reason = failure_reason


class NoteVersionConflict(Exception):
    """Переданная version не совпадает с текущей — заметку изменили раньше."""
    failure_reason = "version_conflict"


class ClientScopeUnavailable(Exception):
    """Нет строгого активного сопровождения с клиентом / клиент отключён."""


class NotesStorageError(Exception):
    """Технический сбой client-scoped пути (без SQL, значений и шифртекста)."""


def _note_to_dict(note: SessionNote) -> dict:
    """Build response dict with decrypted content. Does NOT mutate the ORM object."""
    try:
        plaintext = decrypt_text(note.content)
    except (ValueError, RuntimeError) as exc:
        raise RuntimeError(f"Note decryption failed (id={note.id})") from exc

    return {
        "id":                    note.id,
        "uuid":                  str(note.uuid),
        "appointment_id":        note.appointment_id,
        "engagement_id":         note.engagement_id,
        "author_id":             note.author_id,
        "note_type":             note.note_type,
        "content":               plaintext,
        "is_shared_with_client": note.is_shared_with_client,
        "version":               note.version,
        "created_at":            note.created_at,
        "updated_at":            note.updated_at,
    }


def _note_to_meta_dict(note: SessionNote) -> dict:
    """
    Metadata-only dict: терапевтический content не включается и
    decrypt_text НЕ вызывается вообще (не падает на битых записях,
    не расшифровывает то, что роль не должна видеть).
    """
    return {
        "id":                    note.id,
        "uuid":                  str(note.uuid),
        "appointment_id":        note.appointment_id,
        "engagement_id":         note.engagement_id,
        "author_id":             note.author_id,
        "note_type":             note.note_type,
        "is_shared_with_client": note.is_shared_with_client,
        "version":               note.version,
        "created_at":            note.created_at,
        "updated_at":            note.updated_at,
        "content_available":     False,
    }


# ── связи заметки ────────────────────────────────────────────────────────────

def _appointment_client_id(db, appt) -> Optional[int]:
    """Клиент встречи: прямой client_id или пользователь привязанной карточки."""
    if appt.client_id is not None:
        return int(appt.client_id)
    if appt.unregistered_student_card_id is None:
        return None
    linked = db.execute(
        select(UnregisteredStudentCard.linked_user_id)
        .where(UnregisteredStudentCard.id == appt.unregistered_student_card_id)
    ).scalar()
    return int(linked) if linked is not None else None


def _check_links(db, author_id: int, appointment_id, engagement_id) -> None:
    """
    Generic create (ADR-035): встреча и сопровождение — автора; при обеих
    связях клиент совпадает. Чужое и несуществующее неразличимы (access_denied).
    Пара психолог↔клиент в этих строках неизменна — блокировка не нужна.
    """
    appt = None
    eng = None
    if appointment_id is not None:
        appt = db.get(Appointment, int(appointment_id))
        if appt is None or appt.psychologist_id != int(author_id):
            raise NoteLinkInvalid("access_denied")
    if engagement_id is not None:
        eng = db.get(TherapyEngagement, int(engagement_id))
        if eng is None or eng.psychologist_id != int(author_id):
            raise NoteLinkInvalid("access_denied")
    if appt is not None and eng is not None:
        if _appointment_client_id(db, appt) != int(eng.client_id):
            raise NoteLinkInvalid("link_mismatch")


def create_note(
    *,
    author_id:             int,
    appointment_id:        Optional[int],
    engagement_id:         Optional[int],
    note_type:             str,
    content:               str,
    is_shared_with_client: bool,
    actor_role:            str,
    ip:                    Optional[str] = None,
    user_agent:            Optional[str] = None,
) -> dict:
    """
    Создаёт заметку и пишет session_note_created в audit_log АТОМАРНО
    (ATOMIC/RAISE) — в той же транзакции до единственного commit. Сбой аудита
    откатывает заметку. author_id — единый идентификатор: SessionNote.author_id
    И actor id (Actor.user); отдельного actor_id нет. Связи проверяются до
    вставки (NoteLinkInvalid — заметка не создаётся).
    """
    if author_id is None or actor_role is None:
        raise RuntimeError(
            "session note create requires authenticated actor context "
            "(author_id and actor_role)"
        )
    safe_ctx = build_request_context(ip=ip, user_agent=user_agent)

    with SessionLocal() as db:
        if appointment_id is not None or engagement_id is not None:
            _check_links(db, author_id, appointment_id, engagement_id)
        note = SessionNote(
            author_id=author_id,
            appointment_id=appointment_id,
            engagement_id=engagement_id,
            note_type=note_type,
            content=encrypt_text(content),
            is_shared_with_client=is_shared_with_client,
        )
        db.add(note)
        db.flush()   # note.id до commit — нужен Target
        record_event(
            event="session_note_created",
            actor=Actor.user(int(author_id), actor_role),
            target=Target("session_note", note.id),
            outcome=Outcome.SUCCESS,
            metadata={},
            context=safe_ctx,
            db=db,
        )
        db.commit()
        db.refresh(note)
        return _note_to_dict(note)


def get_note_by_id(
    note_id: int,
    *,
    author_id: Optional[int] = None,
    include_content: bool = True,
) -> Optional[dict]:
    """
    Returns note dict or None. author_id scopes the query to own notes
    when provided. include_content=False возвращает metadata-only dict
    без вызова decrypt (permission-фильтры применяются до выборки).
    """
    with SessionLocal() as db:
        q = db.query(SessionNote).filter(SessionNote.id == note_id)
        if author_id is not None:
            q = q.filter(SessionNote.author_id == author_id)
        note = q.first()
        if not note:
            return None
        return _note_to_dict(note) if include_content else _note_to_meta_dict(note)


def find_notes(
    *,
    page:            int           = 1,
    size:            int           = 20,
    author_id:       Optional[int] = None,
    appointment_id:  Optional[int] = None,
    engagement_id:   Optional[int] = None,
    include_content: bool          = True,
) -> tuple[list[dict], int]:
    with SessionLocal() as db:
        q = db.query(SessionNote)
        if author_id is not None:
            q = q.filter(SessionNote.author_id == author_id)
        if appointment_id is not None:
            q = q.filter(SessionNote.appointment_id == appointment_id)
        if engagement_id is not None:
            q = q.filter(SessionNote.engagement_id == engagement_id)

        total = q.count()
        notes = (
            q.order_by(desc(SessionNote.created_at))
            .offset((page - 1) * size)
            .limit(size)
            .all()
        )
        mapper = _note_to_dict if include_content else _note_to_meta_dict
        items = [mapper(n) for n in notes]

    return items, total


# ── единый механизм правки (generic и client-scoped PATCH) ───────────────────

def _apply_note_update(
    db,
    note: SessionNote,
    changes: dict,
    *,
    expected_version: Optional[int],
    allow_shared: bool,
    author_id: int,
    actor_role: str,
    ip: Optional[str],
    user_agent: Optional[str],
) -> bool:
    """
    Строка заметки уже взята FOR UPDATE вызывающим. CAS: переданная версия
    обязана совпасть (иначе NoteVersionConflict без мутации и без события).
    Diff по редактируемым полям; реальное изменение → version+1, updated_at,
    session_note_updated (ATOMIC, тот же commit у вызывающего). Настоящий
    no-op → False без изменений и без события.
    """
    current_version = note.version or 1
    if expected_version is not None and int(expected_version) != current_version:
        raise NoteVersionConflict()

    changed = False
    new_content = changes.get("content")
    if new_content is not None and new_content != decrypt_text(note.content):
        note.content = encrypt_text(new_content)
        changed = True
    new_type = changes.get("note_type")
    if new_type is not None and new_type != note.note_type:
        note.note_type = new_type
        changed = True
    if allow_shared and "is_shared_with_client" in changes:
        shared = bool(changes["is_shared_with_client"])
        if shared != bool(note.is_shared_with_client):
            note.is_shared_with_client = shared
            changed = True
    if not changed:
        return False

    note.version = current_version + 1
    note.updated_at = datetime.now(timezone.utc)
    record_event(
        event="session_note_updated",
        actor=Actor.user(int(author_id), actor_role),
        target=Target("session_note", note.id),
        outcome=Outcome.SUCCESS,
        metadata={},
        context=build_request_context(ip=ip, user_agent=user_agent),
        db=db,
    )
    return True


def update_note(
    note_id:   int,
    data:      dict,
    *,
    author_id:  int,
    actor_role: str,
    ip:         Optional[str] = None,
    user_agent: Optional[str] = None,
) -> Optional[dict]:
    """
    Generic PATCH (только автор). data — поля exclude_unset; необязательный
    data["version"] включает CAS (409 NoteVersionConflict). Без version —
    сохранённый режим last-write-wins: блокировка строки сериализует записи,
    но от потери изменений не защищает. Чужая/несуществующая заметка → None
    (до какой-либо мутации/аудита). Пишет через _apply_note_update.
    """
    if author_id is None or actor_role is None:
        raise RuntimeError(
            "session note update requires authenticated actor context "
            "(author_id and actor_role)"
        )

    with SessionLocal() as db:
        note = (
            db.query(SessionNote)
            .filter(SessionNote.id == note_id, SessionNote.author_id == author_id)
            .populate_existing()
            .with_for_update()
            .first()
        )
        if not note:
            return None
        changed = _apply_note_update(
            db, note, data,
            expected_version=data.get("version"),
            allow_shared=True,
            author_id=author_id, actor_role=actor_role,
            ip=ip, user_agent=user_agent,
        )
        if changed:
            db.commit()
            db.refresh(note)
        return _note_to_dict(note)


# ── client-scoped путь карточки клиента (ADR-035) ────────────────────────────

def _diag(operation: str, phase: str, error_class: str) -> None:
    print(f"[SESSION_NOTES] op={operation} phase={phase} error={error_class}", file=sys.stderr)


def _relates_to_client(author_id: int, client_id: int):
    """
    Заметка автора относится к клиенту, только если КАЖДАЯ заполненная связь
    принадлежит этому психологу и этому клиенту (и хотя бы одна заполнена).
    OR по одной подходящей связи не пропускает противоречивую запись.
    """
    linked_cards = select(UnregisteredStudentCard.id).where(
        UnregisteredStudentCard.linked_user_id == client_id,
    )
    engagement_ok = exists().where(
        TherapyEngagement.id == SessionNote.engagement_id,
        TherapyEngagement.psychologist_id == author_id,
        TherapyEngagement.client_id == client_id,
    )
    appointment_ok = exists().where(
        Appointment.id == SessionNote.appointment_id,
        Appointment.psychologist_id == author_id,
        or_(
            Appointment.client_id == client_id,
            Appointment.unregistered_student_card_id.in_(linked_cards),
        ),
    )
    return and_(
        SessionNote.author_id == author_id,
        or_(SessionNote.engagement_id.is_not(None), SessionNote.appointment_id.is_not(None)),
        or_(SessionNote.engagement_id.is_(None), engagement_ok),
        or_(SessionNote.appointment_id.is_(None), appointment_ok),
    )


def _client_note_dto(db, note: SessionNote) -> dict:
    appointment = None
    if note.appointment_id is not None:
        row = db.execute(
            select(Appointment.uuid, Appointment.starts_at)
            .where(Appointment.id == note.appointment_id)
        ).first()
        if row is not None:
            appointment = {"uuid": str(row.uuid), "starts_at": row.starts_at}
    return {
        "uuid":        str(note.uuid),
        "note_type":   note.note_type,
        "content":     decrypt_text(note.content),
        "version":     note.version or 1,
        "created_at":  note.created_at,
        "updated_at":  note.updated_at,
        "appointment": appointment,
    }


def _guarded(operation: str, db, fn):
    """Неожиданная SQLAlchemyError / сбой расшифровки → rollback, санитизированная ошибка."""
    error_class = None
    phase = "db"
    out = None
    try:
        out = fn()
    except SQLAlchemyError as exc:
        error_class = type(exc).__name__
    except (ValueError, RuntimeError) as exc:   # encryption: битый/чужой шифртекст
        error_class, phase = type(exc).__name__, "crypto"
    if error_class is not None:
        try:
            db.rollback()
        except Exception as exc:   # noqa: BLE001 — rollback best-effort
            _diag(operation, "rollback", type(exc).__name__)
        _diag(operation, phase, error_class)
        raise NotesStorageError() from None
    return out


def list_client_notes(
    author_id: int, client_uuid, cursor: Optional[tuple], size: int,
) -> dict:
    """
    Свои заметки психолога о клиенте (строгое активное сопровождение, область
    FOR SHARE на всё чтение). Keyset (created_at DESC, uuid DESC). Предикат
    согласованности — в SQL, до выборки content: противоречивые записи не
    расшифровываются. Нет области → ClientScopeUnavailable.
    """
    author_id = int(author_id)
    with SessionLocal() as db:
        def _read():
            scope = lock_client_scope(db, author_id, client_uuid=client_uuid)
            if scope is None:
                return None
            q = db.query(SessionNote).filter(_relates_to_client(author_id, scope[1]))
            if cursor is not None:
                created_at, note_uuid = cursor
                q = q.filter(or_(
                    SessionNote.created_at < created_at,
                    and_(SessionNote.created_at == created_at, SessionNote.uuid < note_uuid),
                ))
            notes = (
                q.order_by(SessionNote.created_at.desc(), SessionNote.uuid.desc())
                .limit(size + 1)
                .all()
            )
            has_more = len(notes) > size
            return {
                "items": [_client_note_dto(db, n) for n in notes[:size]],
                "has_more": has_more,
            }

        page = _guarded("list_client", db, _read)
    if page is None:
        raise ClientScopeUnavailable()
    return page


def create_client_note(
    author_id: int,
    client_uuid,
    *,
    content: str,
    note_type: str,
    appointment_uuid,
    actor_role: str,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    """
    Заметка о клиенте из карточки: engagement_id — текущее строгое
    сопровождение (FOR SHARE), appointment_uuid — любая неудалённая встреча
    этого психолога с этим клиентом (прямая или по привязанной карточке),
    проверяется в БД независимо от пагинации UI. is_shared_with_client=false.
    session_note_created — ATOMIC, один commit.
    """
    author_id = int(author_id)
    with SessionLocal() as db:
        scope = _guarded("create_client", db,
                         lambda: lock_client_scope(db, author_id, client_uuid=client_uuid))
        if scope is None:
            raise ClientScopeUnavailable()
        engagement_id, client_id = scope
        appointment_id = None
        if appointment_uuid is not None:
            linked_cards = select(UnregisteredStudentCard.id).where(
                UnregisteredStudentCard.linked_user_id == client_id,
            )
            appointment_id = _guarded("create_client", db, lambda: db.execute(
                select(Appointment.id).where(
                    Appointment.uuid == appointment_uuid,
                    Appointment.psychologist_id == author_id,
                    Appointment.deleted_at.is_(None),
                    or_(
                        Appointment.client_id == client_id,
                        Appointment.unregistered_student_card_id.in_(linked_cards),
                    ),
                )
            ).scalar())
            if appointment_id is None:
                raise NoteLinkInvalid("access_denied")
        note = SessionNote(
            author_id=author_id,
            appointment_id=appointment_id,
            engagement_id=engagement_id,
            note_type=note_type,
            content=encrypt_text(content),
            is_shared_with_client=False,
        )
        db.add(note)
        db.flush()
        record_event(
            event="session_note_created",
            actor=Actor.user(author_id, actor_role),
            target=Target("session_note", note.id),
            outcome=Outcome.SUCCESS,
            metadata={},
            context=build_request_context(ip=ip, user_agent=user_agent),
            db=db,
        )
        db.commit()
        db.refresh(note)
        return _guarded("create_client", db, lambda: _client_note_dto(db, note))


def update_client_note(
    author_id: int,
    client_uuid,
    note_uuid,
    changes: dict,
    *,
    expected_version: int,
    actor_role: str,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> Optional[dict]:
    """
    Client-scoped PATCH: область FOR SHARE, заметка FOR UPDATE по предикату
    согласованности (своя и относящаяся к клиенту), затем тот же
    _apply_note_update (CAS обязателен). Нет области → ClientScopeUnavailable;
    нет заметки / противоречивая → None.
    """
    author_id = int(author_id)
    with SessionLocal() as db:
        scope = _guarded("update_client", db,
                         lambda: lock_client_scope(db, author_id, client_uuid=client_uuid))
        if scope is None:
            raise ClientScopeUnavailable()
        note = _guarded("update_client", db, lambda: (
            db.query(SessionNote)
            .filter(SessionNote.uuid == note_uuid, _relates_to_client(author_id, scope[1]))
            .populate_existing()
            .with_for_update(of=SessionNote)
            .first()
        ))
        if note is None:
            return None
        changed = _apply_note_update(
            db, note, changes,
            expected_version=expected_version,
            allow_shared=False,
            author_id=author_id, actor_role=actor_role,
            ip=ip, user_agent=user_agent,
        )
        if changed:
            db.commit()
            db.refresh(note)
        dto = _guarded("update_client", db, lambda: _client_note_dto(db, note))
        dto["changed"] = changed
        return dto
