"""
Задания психолога клиенту — весь SQLAlchemy и шифрование (ADR-033).

Хранение: assignments.text_enc — Fernet `enc:v1:` текста задания; автор и
получатель выводятся из therapy_engagements (psychologist_id / client_id).

Строгое сопровождение: status = 'active' AND ended_at IS NULL. Предикат
NULL-безопасен (status IS NOT NULL): строка сопровождения со status NULL не
попадает ни в «открытые», ни в «историю» одновременно.

Конкурентность (одна SessionLocal, один commit на мутацию):
  * строка сопровождения берётся SELECT … FOR SHARE (OF therapy_engagements).
    UPDATE therapy_engagements при закрытии/передаче (supervisor) ждёт commit
    мутации задания; если закрытие зафиксировано раньше, FOR SHARE после
    ожидания перечитывает свежую версию строки — мутация отклоняется. Цикла нет:
    supervisor-путь не трогает assignments, а здесь нет перехода FOR SHARE →
    UPDATE на ОДНОЙ строке (обновляется только assignments);
  * переход — условный UPDATE … WHERE status = 'active' RETURNING. Конкурирующие
    выполнение и отмена сериализуются блокировкой строки задания; проигравший
    видит 0 строк и перечитывает статус: тот же целевой → no-op, иной → конфликт.
    completed и cancelled никогда не перезаписывают друг друга;
  * материал при создании берётся FOR SHARE с публичным предикатом
    (is_published IS TRUE AND deleted_at IS NULL) — снятие с публикации
    параллельно с назначением не проскальзывает.

Аудит перехода — record_event(..., db=db) ATOMIC/RAISE в той же транзакции:
сбой аудита откатывает изменение (AuditError пробрасывается).

Keyset: порядок (created_at DESC, uuid DESC); курсор — значения последнего
элемента, сравнение (created_at, uuid) < курсора. Элемент-курсор не ищется,
поэтому его уход из выборки не создаёт пропусков.

Санитизация: любая неожиданная SQLAlchemyError/сбой шифрования/расшифровки →
rollback, в stderr — операция/фаза/класс, наружу AssignmentsStorageError (вне
except, from None): SQL, параметры и шифртекст не попадают в traceback.
"""
import sys
from typing import Optional

from sqlalchemy import and_, exists, func, insert, not_, or_, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import aliased

from app.assignments.errors import (
    AssignmentEngagementInactive,
    AssignmentFinalized,
    AssignmentNotAvailable,
    AssignmentsStorageError,
    MaterialUnavailable,
)
from app.audit import Actor, Outcome, Target, record_event
from app.audit.request_context import build_request_context
from app.core.encryption import decrypt_text, encrypt_text
from app.db.models import Article, Assignment as A, TherapyEngagement as TE, User
from app.db.session import SessionLocal

ENTITY_TYPE = "assignment"

_STRICT_ACTIVE = and_(
    TE.status.is_not(None), TE.status == "active", TE.ended_at.is_(None),
)
_OPEN = and_(A.status == "active", _STRICT_ACTIVE)
_PUBLIC_ARTICLE = and_(Article.is_published.is_(True), Article.deleted_at.is_(None))
_CLIENT_AVAILABLE = and_(User.deleted_at.is_(None), User.is_active.is_(True))
# Тот же предикат для выборки страницы, где User уже присоединён как психолог:
# клиент сопровождения существует и активен (коррелированный EXISTS по TE).
_ClientUser = aliased(User, name="client_user")
_ENGAGEMENT_CLIENT_AVAILABLE = exists().where(
    _ClientUser.id == TE.client_id,
    _ClientUser.deleted_at.is_(None),
    _ClientUser.is_active.is_(True),
)


class _Undecryptable(Exception):
    pass


# ── санитизация ───────────────────────────────────────────────────────────────

def _diag(operation: str, phase: str, error_class: str) -> None:
    # Только операция, фаза и класс: без SQL, параметров, id и str(exc).
    print(
        f"[ASSIGNMENTS] op={operation} phase={phase} error={error_class}",
        file=sys.stderr,
    )


def _failure(db, operation: str, phase: str, error_class: str) -> AssignmentsStorageError:
    """Откат + диагностика → безопасное исключение (вызывать ВНЕ except)."""
    try:
        db.rollback()
    except Exception as exc:   # noqa: BLE001 — rollback best-effort
        _diag(operation, "rollback", type(exc).__name__)
    _diag(operation, phase, error_class)
    return AssignmentsStorageError()


def _commit(db, operation: str) -> None:
    error_class = None
    try:
        db.commit()
    except SQLAlchemyError as exc:
        error_class = type(exc).__name__
    if error_class is not None:
        raise _failure(db, operation, "commit", error_class) from None


def _decrypt(enc: str) -> str:
    text = None
    failed = False
    try:
        text = decrypt_text(enc)
    except Exception:   # noqa: BLE001 — класс не раскрываем, значения тоже
        failed = True
    if failed:
        raise _Undecryptable()   # вне except: без __context__ со значениями
    return text


# ── чтение списков ────────────────────────────────────────────────────────────

_LIST_COLUMNS = (
    A.id, A.uuid, A.text_enc, A.status, A.due_date,
    A.created_at, A.completed_at, A.cancelled_at, A.article_id,
    Article.uuid.label("article_uuid"),
    Article.title.label("article_title"),
    Article.is_published.label("article_published"),
    Article.deleted_at.label("article_deleted_at"),
    TE.status.label("eng_status"),
    TE.ended_at.label("eng_ended_at"),
    User.full_name.label("psychologist_name"),
)


def _row_dict(row) -> dict:
    """Строка выборки → dict с расшифрованным текстом. Скрытый материал не раскрывается."""
    material = None
    material_unavailable = False
    if row.article_id is not None:
        if row.article_published is True and row.article_deleted_at is None:
            material = {"uuid": row.article_uuid, "title": row.article_title}
        else:
            material_unavailable = True
    return {
        "id":                   row.id,
        "uuid":                 row.uuid,
        "text":                 _decrypt(row.text_enc),
        "status":               row.status,
        "due_date":             row.due_date,
        "created_at":           row.created_at,
        "completed_at":         row.completed_at,
        "cancelled_at":         row.cancelled_at,
        "engagement_active":    row.eng_status == "active" and row.eng_ended_at is None,
        "psychologist_name":    row.psychologist_name or "",
        "material":             material,
        "material_unavailable": material_unavailable,
    }


def _page(db, scope: list, cursor: Optional[tuple], size: int) -> dict:
    base = (
        select(*_LIST_COLUMNS)
        .select_from(A)
        .join(TE, TE.id == A.engagement_id)
        .outerjoin(User, User.id == TE.psychologist_id)
        .outerjoin(Article, Article.id == A.article_id)
        .where(*scope)
    )
    if cursor is not None:
        created_at, uuid_value = cursor
        base = base.where(or_(
            A.created_at < created_at,
            and_(A.created_at == created_at, A.uuid < uuid_value),
        ))
    rows = db.execute(
        base.order_by(A.created_at.desc(), A.uuid.desc()).limit(size + 1)
    ).all()
    total = db.execute(
        select(func.count(A.id))
        .select_from(A)
        .join(TE, TE.id == A.engagement_id)
        .where(*scope)
    ).scalar() or 0
    has_more = len(rows) > size
    rows = rows[:size]
    return {
        "rows": [_row_dict(r) for r in rows],
        "has_more": has_more,
        "total": int(total),
    }


def list_client_page(client_id: int, view: str, cursor: Optional[tuple], size: int) -> dict:
    """
    Собственные задания клиента по всем его сопровождениям.
    view='open' — active при строго активном сопровождении; 'history' — остальное.
    """
    scope = [TE.client_id == int(client_id), _OPEN if view == "open" else not_(_OPEN)]
    with SessionLocal() as db:
        error_class = None
        page = None
        try:
            page = _page(db, scope, cursor, size)
        except _Undecryptable:
            error_class = "Undecryptable"
        except SQLAlchemyError as exc:
            error_class = type(exc).__name__
        if error_class is not None:
            raise _failure(db, "list_my", "read", error_class) from None
    return page


def client_summary(client_id: int) -> dict:
    with SessionLocal() as db:
        error_class = None
        row = None
        try:
            row = db.execute(
                select(
                    func.count(A.id).filter(_OPEN).label("open_count"),
                    func.count(A.id).filter(A.status == "completed").label("completed_count"),
                    func.count(A.id).label("total_count"),
                )
                .select_from(A)
                .join(TE, TE.id == A.engagement_id)
                .where(TE.client_id == int(client_id))
            ).one()
        except SQLAlchemyError as exc:
            error_class = type(exc).__name__
        if error_class is not None:
            raise _failure(db, "summary", "read", error_class) from None
    return {
        "open_count": int(row.open_count or 0),
        "completed_count": int(row.completed_count or 0),
        "total_count": int(row.total_count or 0),
    }


def _notify_party(db, engagement_id: int) -> dict:
    """Получатель post-commit уведомления клиента и имя психолога (без текста задания)."""
    psych = aliased(User, name="notify_psychologist")
    row = db.execute(
        select(TE.client_id, psych.full_name)
        .join(psych, psych.id == TE.psychologist_id)
        .where(TE.id == engagement_id)
    ).first()
    return {"client_id": int(row.client_id), "psychologist_name": row.full_name or ""}


def _psychologist_engagement_query(psychologist_id: int, client_uuid):
    """Строгое сопровождение (actor → клиент); клиент существует и активен."""
    return (
        select(TE.id)
        .join(User, User.id == TE.client_id)
        .where(
            User.uuid == client_uuid,
            _CLIENT_AVAILABLE,
            TE.psychologist_id == int(psychologist_id),
            _STRICT_ACTIVE,
        )
    )


def list_psychologist_page(
    psychologist_id: int, client_uuid, cursor: Optional[tuple], size: int,
) -> Optional[dict]:
    """
    Задания ТЕКУЩЕГО строгого сопровождения психолога с клиентом.
    Нет сопровождения / клиента / права → None (один и тот же результат).
    Задания прежних сопровождений сюда не попадают: новый психолог их не видит.

    Право держится на всём получении содержимого: проверка берёт FOR SHARE
    OF therapy_engagements, users — строку сопровождения И строку клиента — в
    той же транзакции, что и выборка страницы. При READ COMMITTED без
    блокировки close/transfer сопровождения или отключение клиента (ADR-028:
    users FOR UPDATE → UPDATE is_active/deactivated_at) могли бы
    зафиксироваться между проверкой и выборкой, и психолог без права прочитал
    бы тексты. Теперь эти UPDATE ждут конца чтения, а изменение, зафиксированное
    раньше, FOR SHARE видит после ожидания (свежая версия строки) → None.
    Выборка страницы дополнительно повторяет предикат права — строгое
    сопровождение этого психолога и активный клиент (защита в глубину).

    Цикла блокировок нет: здесь только разделяемые блокировки двух строк без
    последующих UPDATE; supervisor-путь (UPDATE therapy_engagements) не берёт
    users, а отключение (users FOR UPDATE, UPDATE users/user_sessions) не трогает
    therapy_engagements — ни один путь не держит одну из строк эксклюзивно,
    ожидая другую. Блокировки снимаются при закрытии сессии — до записи
    content_read.
    """
    psychologist_id = int(psychologist_id)
    with SessionLocal() as db:
        error_class = None
        page = None
        try:
            engagement_id = db.execute(
                _psychologist_engagement_query(psychologist_id, client_uuid)
                .limit(1)
                .with_for_update(read=True, of=(TE, User))
            ).scalar()
            if engagement_id is not None:
                page = _page(db, [
                    A.engagement_id == engagement_id,
                    TE.psychologist_id == psychologist_id,
                    _STRICT_ACTIVE,
                    _ENGAGEMENT_CLIENT_AVAILABLE,
                ], cursor, size)
        except _Undecryptable:
            error_class = "Undecryptable"
        except SQLAlchemyError as exc:
            error_class = type(exc).__name__
        if error_class is not None:
            raise _failure(db, "list_client", "read", error_class) from None
    return page


# ── мутации ───────────────────────────────────────────────────────────────────

_MUTATION_COLUMNS = (A.id, A.uuid, A.status, A.created_at, A.completed_at, A.cancelled_at)


def _mutation_dict(row, changed: bool) -> dict:
    return {
        "id":           row.id,
        "uuid":         row.uuid,
        "status":       row.status,
        "created_at":   row.created_at,
        "completed_at": row.completed_at,
        "cancelled_at": row.cancelled_at,
        "changed":      changed,
    }


def create_atomic(
    psychologist_id: int,
    client_uuid,
    text: str,
    due_date,
    article_uuid,
    *,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    """
    Создаёт задание в строгом сопровождении psychologist → клиент.
    Бросает AssignmentNotAvailable / MaterialUnavailable; AuditError (сбой
    assignment_created) откатывает запись и пробрасывается.
    """
    psychologist_id = int(psychologist_id)
    with SessionLocal() as db:
        error_class = None
        engagement_id = None
        article_id = None
        party = None
        try:
            engagement_id = db.execute(
                _psychologist_engagement_query(psychologist_id, client_uuid)
                .limit(1)
                .with_for_update(read=True, of=TE)
            ).scalar()
            if engagement_id is not None and article_uuid is not None:
                article_id = db.execute(
                    select(Article.id)
                    .where(Article.uuid == article_uuid, _PUBLIC_ARTICLE)
                    .with_for_update(read=True)
                ).scalar()
        except SQLAlchemyError as exc:
            error_class = type(exc).__name__
        if error_class is not None:
            raise _failure(db, "create", "read", error_class) from None

        if engagement_id is None:
            raise AssignmentNotAvailable()
        if article_uuid is not None and article_id is None:
            raise MaterialUnavailable()

        encoded = None
        try:
            encoded = encrypt_text(text)
        except Exception:   # noqa: BLE001
            error_class = "EncryptionError"
        if error_class is not None:
            raise _failure(db, "create", "encrypt", error_class) from None

        written = None
        try:
            written = db.execute(
                insert(A)
                .values(
                    engagement_id=engagement_id,
                    text_enc=encoded,
                    due_date=due_date,
                    article_id=article_id,
                    status="active",
                )
                .returning(*_MUTATION_COLUMNS)
            ).first()
            party = _notify_party(db, engagement_id)
        except SQLAlchemyError as exc:
            error_class = type(exc).__name__
        if error_class is not None:
            raise _failure(db, "create", "write", error_class) from None

        record_event(
            event="assignment_created",
            actor=Actor.user(psychologist_id, "psychologist"),
            target=Target(ENTITY_TYPE, written.id),
            outcome=Outcome.SUCCESS,
            metadata={},
            context=build_request_context(ip=ip, user_agent=user_agent),
            db=db,
        )
        _commit(db, "create")
        result = _mutation_dict(written, changed=True)
        result["notify"] = party
        return result


def _transition(
    db,
    assignment_id: int,
    *,
    target_status: str,
    stamp_column,
) -> Optional[object]:
    """Условный UPDATE active → target_status. None — строка уже не active."""
    return db.execute(
        update(A)
        .where(A.id == assignment_id, A.status == "active")
        .values({
            A.status: target_status,
            stamp_column: func.now(),
            A.updated_at: func.now(),
        })
        .execution_options(synchronize_session=False)
        .returning(*_MUTATION_COLUMNS)
    ).first()


def _current(db, assignment_id: int):
    return db.execute(select(*_MUTATION_COLUMNS).where(A.id == assignment_id)).first()


def complete_atomic(
    client_id: int,
    assignment_uuid,
    *,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    """
    Клиент отмечает своё активное задание выполненным.
    При реальном переходе результат содержит "notify" (id психолога и имя
    клиента) для post-commit уведомления; у no-op его нет.
    Порядок проверок после FOR SHARE сопровождения: уже completed → no-op;
    cancelled → AssignmentFinalized; сопровождение не строго активно →
    AssignmentEngagementInactive. Чужое / несуществующее → AssignmentNotAvailable.
    """
    client_id = int(client_id)
    with SessionLocal() as db:
        error_class = None
        ref = None
        engagement = None
        current = None
        try:
            ref = db.execute(
                select(
                    A.id, A.engagement_id, TE.psychologist_id,
                    User.full_name.label("client_name"),
                )
                .join(TE, TE.id == A.engagement_id)
                .join(User, User.id == TE.client_id)
                .where(A.uuid == assignment_uuid, TE.client_id == client_id)
            ).first()
            if ref is not None:
                engagement = db.execute(
                    select(TE.status, TE.ended_at)
                    .where(TE.id == ref.engagement_id)
                    .with_for_update(read=True)
                ).first()
                current = _current(db, ref.id)
        except SQLAlchemyError as exc:
            error_class = type(exc).__name__
        if error_class is not None:
            raise _failure(db, "complete", "read", error_class) from None

        if ref is None or current is None:
            raise AssignmentNotAvailable()
        if current.status == "completed":
            return _mutation_dict(current, changed=False)
        if current.status == "cancelled":
            raise AssignmentFinalized("cancelled")
        if not (
            engagement is not None
            and engagement.status == "active"
            and engagement.ended_at is None
        ):
            raise AssignmentEngagementInactive()

        written = None
        latest = None
        try:
            written = _transition(
                db, ref.id,
                target_status="completed", stamp_column=A.completed_at,
            )
            if written is None:
                latest = _current(db, ref.id)
        except SQLAlchemyError as exc:
            error_class = type(exc).__name__
        if error_class is not None:
            raise _failure(db, "complete", "write", error_class) from None

        if written is None:
            # Конкурирующий переход зафиксирован раньше.
            if latest is not None and latest.status == "completed":
                return _mutation_dict(latest, changed=False)
            raise AssignmentFinalized(latest.status if latest is not None else "cancelled")

        record_event(
            event="assignment_completed",
            actor=Actor.user(client_id, "student"),
            target=Target(ENTITY_TYPE, written.id),
            outcome=Outcome.SUCCESS,
            metadata={},
            context=build_request_context(ip=ip, user_agent=user_agent),
            db=db,
        )
        _commit(db, "complete")
        result = _mutation_dict(written, changed=True)
        # Только для post-commit уведомления психолога (service убирает из ответа).
        result["notify"] = {
            "psychologist_id": int(ref.psychologist_id),
            "client_name": ref.client_name or "",
        }
        return result


def cancel_atomic(
    psychologist_id: int,
    assignment_uuid,
    *,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    """
    Психолог отменяет активное задание СВОЕГО строго активного сопровождения
    (клиент существует и активен). Нет права (в т.ч. сопровождение завершено или
    передано) → AssignmentNotAvailable. Уже cancelled → no-op; completed →
    AssignmentFinalized.
    """
    psychologist_id = int(psychologist_id)
    with SessionLocal() as db:
        error_class = None
        ref = None
        granted = None
        current = None
        party = None
        try:
            ref = db.execute(
                select(A.id, A.engagement_id)
                .join(TE, TE.id == A.engagement_id)
                .where(A.uuid == assignment_uuid, TE.psychologist_id == psychologist_id)
            ).first()
            if ref is not None:
                granted = db.execute(
                    select(TE.id)
                    .join(User, User.id == TE.client_id)
                    .where(
                        TE.id == ref.engagement_id,
                        TE.psychologist_id == psychologist_id,
                        _STRICT_ACTIVE,
                        _CLIENT_AVAILABLE,
                    )
                    .with_for_update(read=True, of=TE)
                ).scalar()
                if granted is not None:
                    current = _current(db, ref.id)
        except SQLAlchemyError as exc:
            error_class = type(exc).__name__
        if error_class is not None:
            raise _failure(db, "cancel", "read", error_class) from None

        if ref is None or granted is None or current is None:
            raise AssignmentNotAvailable()
        if current.status == "cancelled":
            return _mutation_dict(current, changed=False)
        if current.status == "completed":
            raise AssignmentFinalized("completed")

        written = None
        latest = None
        try:
            written = _transition(
                db, ref.id,
                target_status="cancelled", stamp_column=A.cancelled_at,
            )
            if written is None:
                latest = _current(db, ref.id)
            else:
                party = _notify_party(db, ref.engagement_id)
        except SQLAlchemyError as exc:
            error_class = type(exc).__name__
        if error_class is not None:
            raise _failure(db, "cancel", "write", error_class) from None

        if written is None:
            if latest is not None and latest.status == "cancelled":
                return _mutation_dict(latest, changed=False)
            raise AssignmentFinalized(latest.status if latest is not None else "completed")

        record_event(
            event="assignment_cancelled",
            actor=Actor.user(psychologist_id, "psychologist"),
            target=Target(ENTITY_TYPE, written.id),
            outcome=Outcome.SUCCESS,
            metadata={},
            context=build_request_context(ip=ip, user_agent=user_agent),
            db=db,
        )
        _commit(db, "cancel")
        result = _mutation_dict(written, changed=True)
        result["notify"] = party
        return result
