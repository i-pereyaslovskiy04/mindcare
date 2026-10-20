"""
Контакты пользователя — весь SQLAlchemy и шифрование (ADR-032).

Хранение: user_contacts (1:1 с users), contacts_enc = Fernet `enc:v1:` от
JSON-конверта {"v":1,"items":[{id,type,service,value,label}]}, version — счётчик
compare-and-set. Строка создаётся при первом СОХРАНЕНИИ; чтение пустого списка
ничего не пишет; «сохранить пустое поверх пустого» — no-op без строки.

Сохранение (одна SessionLocal, один commit):
  1. SELECT строки → расшифровка → если нормализованный список (с id и
     порядком) РАВЕН текущему — no-op (версия/updated_at/аудит не меняются,
     независимо от присланной версии: повтор после потерянного ответа безопасен);
  2. присланная версия ≠ текущей → ContactsVersionConflict;
  3. нет строки: INSERT … ON CONFLICT DO NOTHING RETURNING; есть строка:
     UPDATE … WHERE user_id AND version = :expected RETURNING (0 строк →
     конфликт: параллельное сохранение победило);
  4. record_event(profile_updated, fields=["contacts"], db=db) — ATOMIC/RAISE,
     тот же commit; сбой аудита откатывает запись.
Блокировка строки users не нужна: аудит-FK берёт лишь FOR KEY SHARE на неё
(ADR-028 операции контакты не трогают, цикла ожидания нет).

Санитизация: любая неожиданная SQLAlchemyError/сбой шифрования/расшифровки →
rollback, в stderr — операция/фаза/класс, наружу ContactsStorageError (вне
except, from None): SQL, параметры и шифртекст не попадают в traceback.
"""
import json
import sys
from typing import Optional

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError

from app.audit import Actor, Outcome, Target, record_event
from app.audit.request_context import build_request_context
from app.auth.roles import is_pure_student
from app.auth.storage import get_active_role_names
from app.core.encryption import decrypt_text, encrypt_text
from app.db.models import TherapyEngagement, User, UserContacts as UC
from app.db.session import SessionLocal
from app.user_contacts.errors import ContactsStorageError, ContactsVersionConflict

_ITEM_KEYS = ("id", "type", "service", "value", "label")
_ENVELOPE_VERSION = 1


class _Undecodable(Exception):
    pass


# ── санитизация ───────────────────────────────────────────────────────────────

def _diag(operation: str, phase: str, error_class: str) -> None:
    # Только операция, фаза и класс: без SQL, параметров, id и str(exc).
    print(
        f"[USER_CONTACTS] op={operation} phase={phase} error={error_class}",
        file=sys.stderr,
    )


def _failure(db, operation: str, phase: str, error_class: str) -> ContactsStorageError:
    """Откат + диагностика → безопасное исключение (вызывать ВНЕ except)."""
    try:
        db.rollback()
    except Exception as exc:   # noqa: BLE001 — rollback best-effort
        _diag(operation, "rollback", type(exc).__name__)
    _diag(operation, phase, error_class)
    return ContactsStorageError()


# ── шифрование ────────────────────────────────────────────────────────────────

def _encode(items: list) -> str:
    payload = {"v": _ENVELOPE_VERSION, "items": items}
    return encrypt_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def _decode(enc: str) -> list:
    items = None
    try:
        data = json.loads(decrypt_text(enc))
        if data.get("v") == _ENVELOPE_VERSION and isinstance(data.get("items"), list):
            items = [{key: raw.get(key) for key in _ITEM_KEYS} for raw in data["items"]]
    except Exception:   # noqa: BLE001 — класс не раскрываем, значения тоже
        items = None
    if items is None:
        raise _Undecodable()
    return items


# ── чтение ────────────────────────────────────────────────────────────────────

def read_snapshot(user_id: int) -> Optional[dict]:
    """{version, updated_at, items} или None (строки нет). Ничего не создаёт."""
    with SessionLocal() as db:
        error_class = None
        row = None
        items: list = []
        try:
            row = db.execute(
                select(UC.version, UC.updated_at, UC.contacts_enc)
                .where(UC.user_id == int(user_id))
            ).first()
            if row is not None:
                items = _decode(row.contacts_enc)
        except _Undecodable:
            error_class = "Undecodable"
        except SQLAlchemyError as exc:
            error_class = type(exc).__name__
        if error_class is not None:
            raise _failure(db, "read", "read", error_class) from None
    if row is None:
        return None
    return {"version": row.version, "updated_at": row.updated_at, "items": items}


# ── сохранение ────────────────────────────────────────────────────────────────

def _commit(db, operation: str) -> None:
    error_class = None
    try:
        db.commit()
    except SQLAlchemyError as exc:
        error_class = type(exc).__name__
    if error_class is not None:
        raise _failure(db, operation, "commit", error_class) from None


def save_atomic(
    user_id: int,
    expected_version: int,
    items: list,
    *,
    actor_role: str,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    """
    Атомарно сохраняет нормализованный список. Возвращает
    {version, updated_at, items, changed}. Бросает ContactsVersionConflict;
    AuditError (сбой profile_updated) откатывает запись и пробрасывается.
    """
    user_id = int(user_id)
    with SessionLocal() as db:
        error_class = None
        row = None
        current: list = []
        try:
            row = db.execute(
                select(UC.version, UC.updated_at, UC.contacts_enc)
                .where(UC.user_id == user_id)
            ).first()
            if row is not None:
                current = _decode(row.contacts_enc)
        except _Undecodable:
            error_class = "Undecodable"
        except SQLAlchemyError as exc:
            error_class = type(exc).__name__
        if error_class is not None:
            raise _failure(db, "save", "read", error_class) from None

        current_version = row.version if row is not None else 0
        if items == current:
            return {
                "version": current_version,
                "updated_at": row.updated_at if row is not None else None,
                "items": current,
                "changed": False,
            }
        if expected_version != current_version:
            raise ContactsVersionConflict(current_version)

        encoded = None
        try:
            encoded = _encode(items)
        except Exception:   # noqa: BLE001
            error_class = "EncryptionError"
        if error_class is not None:
            raise _failure(db, "save", "encrypt", error_class) from None

        written = None
        try:
            if row is None:
                result = db.execute(
                    pg_insert(UC)
                    .values(user_id=user_id, contacts_enc=encoded, version=1)
                    .on_conflict_do_nothing(index_elements=[UC.user_id])
                    .returning(UC.version, UC.updated_at)
                )
            else:
                result = db.execute(
                    update(UC)
                    .where(UC.user_id == user_id, UC.version == expected_version)
                    .values(
                        contacts_enc=encoded,
                        version=UC.version + 1,
                        updated_at=func.now(),
                    )
                    .execution_options(synchronize_session=False)
                    .returning(UC.version, UC.updated_at)
                )
            written = result.first()
        except SQLAlchemyError as exc:
            error_class = type(exc).__name__
        if error_class is not None:
            raise _failure(db, "save", "write", error_class) from None

        if written is None:
            # Параллельное сохранение победило: сообщаем актуальную версию.
            latest = None
            try:
                db.rollback()
                latest = db.execute(
                    select(UC.version).where(UC.user_id == user_id)
                ).scalar()
            except SQLAlchemyError as exc:
                error_class = type(exc).__name__
            if error_class is not None:
                raise _failure(db, "save", "read", error_class) from None
            raise ContactsVersionConflict(latest or 0)

        record_event(
            event="profile_updated",
            actor=Actor.user(user_id, actor_role),
            target=Target("user", user_id),
            outcome=Outcome.SUCCESS,
            metadata={"fields": ["contacts"]},
            context=build_request_context(ip=ip, user_agent=user_agent),
            db=db,
        )
        _commit(db, "save")
        return {
            "version": written.version,
            "updated_at": written.updated_at,
            "items": items,
            "changed": True,
        }


# ── доступ сотрудника ─────────────────────────────────────────────────────────

def resolve_staff_grant(actor_id: int, roles, target_uuid) -> Optional[dict]:
    """
    Решение о доступе сотрудника к контактам цели (ADR-032), по membership roles[]:
      A) psychologist ∈ roles И строгое активное сопровождение с целью
         (status='active' AND ended_at IS NULL, client_id = цель) — цель любого
         типа, в т.ч. клиент со staff-ролью → acting_role='psychologist';
      B) supervisor ∈ roles И цель — чистый студент из списка супервизора
         → acting_role='supervisor'.
    Цель обязана быть не удалена и активна (NULL is_active = активна, ADR-028).
    Нет доступа / цели нет → None (один и тот же результат).
    Возвращает {target_id, acting_role, primary_phone}.
    """
    with SessionLocal() as db:
        error_class = None
        grant = None
        try:
            target = db.execute(
                select(User.id, User.phone, User.is_active, User.deleted_at)
                .where(User.uuid == target_uuid)
            ).first()
            if (
                target is not None
                and target.deleted_at is None
                and target.is_active is not False
            ):
                if "psychologist" in roles and db.execute(
                    select(TherapyEngagement.id).where(
                        TherapyEngagement.client_id == target.id,
                        TherapyEngagement.psychologist_id == int(actor_id),
                        TherapyEngagement.status == "active",
                        TherapyEngagement.ended_at.is_(None),
                    ).limit(1)
                ).first() is not None:
                    acting_role = "psychologist"
                elif "supervisor" in roles and is_pure_student(
                    get_active_role_names(db, target.id)
                ):
                    acting_role = "supervisor"
                else:
                    acting_role = None
                if acting_role is not None:
                    grant = {
                        "target_id": target.id,
                        "acting_role": acting_role,
                        "primary_phone": target.phone,
                    }
        except SQLAlchemyError as exc:
            error_class = type(exc).__name__
        if error_class is not None:
            raise _failure(db, "grant", "read", error_class) from None
    return grant
