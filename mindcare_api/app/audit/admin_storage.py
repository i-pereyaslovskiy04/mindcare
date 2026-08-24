"""
Stage 8 — SQL read-only admin viewer журналов. Весь SQLAlchemy — здесь.

Инварианты слоя:

  * колонки перечисляются ЯВНО. Запрещённые поля физически не попадают в
    результат: `audit_log.description / ip_address / user_agent / session_id /
    request_url / request_method`, `auth_log.ip_address / user_agent /
    session_id / mfa_method`, `data_change_log.old_values / new_values /
    ip_address`. Не «не показываем», а «не выбираем»;
  * `.label()` обязателен: actor-alias и target-alias — оба `User`, у обоих есть
    `uuid` / `full_name` / `email` / `deleted_at`, и без меток ключи Row были бы
    неоднозначны. `AuditLog.log_metadata` тоже лейблится — в БД колонка
    называется `metadata`;
  * фильтр по `created_at` присутствует ВСЕГДА, поэтому PostgreSQL отсекает
    ненужные месячные партиции (запрос идёт к partitioned parent);
  * actor-join включён и в count-запрос: предикаты `user` / `unavailable`
    ссылаются на `A.id`. Join по первичному ключу, строки не размножаются,
    поэтому `count()` остаётся точным;
  * UUID никогда не превращается в наружный internal id: он резолвится
    scalar-подзапросом внутри того же SQL. Несуществующий UUID даёт пустую
    страницу, а не 404 — иначе endpoint стал бы оракулом существования аккаунта.

Классификация actor и допустимость target берутся из `admin_policy` — того же
модуля, которым пользуется проекция DTO. Дублировать эти множества здесь нельзя.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import and_, asc, desc, false, func, not_, or_, select
from sqlalchemy.orm import aliased

from app.db.models import AuditLog, AuthLog, DataChangeLog, User
from app.db.session import SessionLocal

from app.audit import admin_policy as pol
from app.audit.contracts import SYSTEM_ROLE


# ── Общие кирпичи ─────────────────────────────────────────────────────────────

def _user_id_subq(user_uuid: UUID):
    """UUID → внутренний id ВНУТРИ SQL. Наружу id не выходит ни при каком исходе.

    Нет такого пользователя → подзапрос даёт NULL → сравнение даёт NULL →
    строка не проходит фильтр. Ровно то поведение, которое нужно: пустая
    страница без сигнала «такого аккаунта не существует».
    """
    return select(User.id).where(User.uuid == user_uuid).scalar_subquery()


def _sane(expr):
    """Делает предикат NULL-free.

    SQL трёхзначен: `role = 'system'` при `role IS NULL` даёт NULL, `NOT(NULL)`
    — тоже NULL, и строка молча выпала бы из класса `unavailable`, нарушив
    тождество «фильтр = проекция». `coalesce(expr, false)` закрывает это одним
    приёмом вместо ручных `IS NOT NULL` на каждую колонку.
    """
    return func.coalesce(expr, false())


def actor_kind_predicates(
    policy, *, key_col, id_col, joined_id_col, role_col=None,
) -> dict:
    """Предикаты классов актора — зеркало `admin_policy.classify_actor`.

    `unavailable` определяется как отрицание объединения трёх остальных: это
    единственный способ гарантировать, что разбиение тотально и непересекающееся
    (неизвестное имя события, обнулённый FK, отсутствующий User и роль вне
    allowlist попадают туда автоматически, без отдельного перечисления).
    """
    needs_role = policy.role_aware or bool(policy.system_names)
    if needs_role and role_col is None:
        raise ValueError(f"{policy.journal}: role column is required")

    if not policy.user_names:
        user_core = false()
    elif policy.role_aware:
        # Группировка по одинаковому набору ролей: несколько веток OR вместо
        # одной на каждое из 87 событий.
        user_core = or_(*[
            and_(key_col.in_(sorted(names)), role_col.in_(sorted(roles)))
            for roles, names in policy.names_by_roleset.items()
        ])
    else:
        # auth_log роль не хранит — проверять её нечем и не нужно.
        user_core = key_col.in_(sorted(policy.user_names))

    p_user = _sane(and_(id_col.isnot(None), joined_id_col.isnot(None), user_core))
    p_anon = (
        _sane(and_(key_col.in_(sorted(policy.anon_names)), id_col.is_(None)))
        if policy.anon_names else false()
    )
    p_system = (
        _sane(and_(
            key_col.in_(sorted(policy.system_names)),
            id_col.is_(None),
            role_col == SYSTEM_ROLE,
        ))
        if policy.system_names else false()
    )

    return {
        pol.KIND_USER: p_user,
        pol.KIND_ANONYMOUS: p_anon,
        pol.KIND_SYSTEM: p_system,
        pol.KIND_UNAVAILABLE: not_(or_(p_user, p_anon, p_system)),
    }


def _semantic_target():
    """«Тип цели согласован со своим событием» — дизъюнкция по всем типам.

    Плоского `event_type IN <все target-REQUIRED события>` недостаточно:
    повреждённая строка (`admin_role_add` + `entity_type='article'`) прошла бы
    такой фильтр и затем показалась бы с пустым target.
    """
    return or_(*[
        and_(AuditLog.entity_type == entity_type,
             AuditLog.event_type.in_(sorted(names)))
        for entity_type, names in pol.EVENTS_BY_ENTITY_TYPE.items()
    ])


def _ordered(query, created_col, id_col, order: str):
    direction = desc if order == "desc" else asc
    return query.order_by(direction(created_col), direction(id_col))


def _paged(query, page: int, size: int):
    return query.offset((page - 1) * size).limit(size)


# ── audit_log ─────────────────────────────────────────────────────────────────

def list_audit_events(
    *,
    start: datetime,
    end: datetime,
    order: str,
    page: int,
    size: int,
    actor_uuid: Optional[UUID] = None,
    actor_kind: Optional[str] = None,
    actor_role: Optional[str] = None,
    event_type: Optional[str] = None,
    outcome: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    target_user_uuid: Optional[UUID] = None,
    exclude_access_events: bool = True,
) -> tuple[list, int]:
    actor = aliased(User)
    target = aliased(User)

    kinds = actor_kind_predicates(
        pol.AUDIT_POLICY,
        key_col=AuditLog.event_type,
        id_col=AuditLog.user_id,
        role_col=AuditLog.user_role,
        joined_id_col=actor.id,
    )

    conditions = [AuditLog.created_at >= start, AuditLog.created_at < end]
    if actor_uuid is not None:
        conditions.append(AuditLog.user_id == _user_id_subq(actor_uuid))
    if actor_kind is not None:
        conditions.append(kinds[actor_kind])
    if actor_role is not None:
        conditions.append(AuditLog.user_role == actor_role)
    if event_type is not None:
        conditions.append(AuditLog.event_type == event_type)
    if outcome is not None:
        conditions.append(AuditLog.outcome == outcome)
    if entity_type is not None:
        conditions.append(and_(
            AuditLog.entity_type == entity_type,
            AuditLog.event_type.in_(
                sorted(pol.EVENTS_BY_ENTITY_TYPE.get(entity_type, frozenset()))
            ),
        ))
    if entity_id is not None:
        # Сервис не пропускает entity_id без entity_type, поэтому ветка выше уже
        # сузила выборку. `_semantic_target()` остаётся defense-in-depth на
        # случай прямого вызова storage в обход валидации.
        conditions.append(and_(AuditLog.entity_id == entity_id, _semantic_target()))
    if target_user_uuid is not None:
        conditions.append(and_(
            AuditLog.entity_type == pol.USER_ENTITY_TYPE,
            AuditLog.entity_id == _user_id_subq(target_user_uuid),
            AuditLog.event_type.in_(sorted(pol.USER_TARGET_EVENTS)),
        ))
    if exclude_access_events:
        conditions.append(AuditLog.event_type != pol.ACCESS_EVENT)

    with SessionLocal() as db:
        total = (
            db.query(func.count())
            .select_from(AuditLog)
            .outerjoin(actor, actor.id == AuditLog.user_id)
            .filter(*conditions)
            .scalar()
        )

        query = (
            db.query(
                AuditLog.id.label("entry_id"),
                AuditLog.created_at.label("occurred_at"),
                AuditLog.event_type.label("event_type"),
                AuditLog.user_id.label("actor_id"),
                AuditLog.user_role.label("actor_role"),
                AuditLog.entity_type.label("entity_type"),
                AuditLog.entity_id.label("entity_id"),
                AuditLog.outcome.label("outcome"),
                AuditLog.failure_reason_code.label("failure_code"),
                AuditLog.log_metadata.label("raw_metadata"),
                actor.id.label("actor_row_id"),
                actor.uuid.label("actor_user_uuid"),
                actor.full_name.label("actor_full_name"),
                actor.email.label("actor_email"),
                actor.deleted_at.label("actor_deleted_at"),
                target.uuid.label("target_user_uuid"),
                target.full_name.label("target_full_name"),
                target.email.label("target_email"),
                target.deleted_at.label("target_deleted_at"),
            )
            .select_from(AuditLog)
            .outerjoin(actor, actor.id == AuditLog.user_id)
            .outerjoin(target, and_(
                AuditLog.entity_type == pol.USER_ENTITY_TYPE,
                target.id == AuditLog.entity_id,
            ))
            .filter(*conditions)
        )
        query = _ordered(query, AuditLog.created_at, AuditLog.id, order)
        rows = _paged(query, page, size).all()

    return rows, int(total or 0)


# ── auth_log ──────────────────────────────────────────────────────────────────

def list_auth_events(
    *,
    start: datetime,
    end: datetime,
    order: str,
    page: int,
    size: int,
    actor_uuid: Optional[UUID] = None,
    actor_kind: Optional[str] = None,
    event: Optional[str] = None,
    success: Optional[bool] = None,
) -> tuple[list, int]:
    actor = aliased(User)

    kinds = actor_kind_predicates(
        pol.AUTH_POLICY,
        key_col=AuthLog.event,
        id_col=AuthLog.user_id,
        joined_id_col=actor.id,
        # role_col не передаётся: колонки роли в auth_log НЕТ. Хелпер сам
        # потребует её, если политика журнала когда-либо станет role-aware
        # или получит SYSTEM-события.
    )

    conditions = [AuthLog.created_at >= start, AuthLog.created_at < end]
    if actor_uuid is not None:
        conditions.append(AuthLog.user_id == _user_id_subq(actor_uuid))
    if actor_kind is not None:
        conditions.append(kinds[actor_kind])
    if event is not None:
        conditions.append(AuthLog.event == event)
    if success is not None:
        conditions.append(AuthLog.success.is_(success))

    with SessionLocal() as db:
        total = (
            db.query(func.count())
            .select_from(AuthLog)
            .outerjoin(actor, actor.id == AuthLog.user_id)
            .filter(*conditions)
            .scalar()
        )

        query = (
            db.query(
                AuthLog.id.label("entry_id"),
                AuthLog.created_at.label("occurred_at"),
                AuthLog.event.label("event"),
                AuthLog.user_id.label("actor_id"),
                AuthLog.user_email.label("event_email"),
                AuthLog.success.label("success"),
                AuthLog.failure_reason.label("failure_reason"),
                actor.id.label("actor_row_id"),
                actor.uuid.label("actor_user_uuid"),
                actor.full_name.label("actor_full_name"),
                actor.email.label("actor_email"),
                actor.deleted_at.label("actor_deleted_at"),
            )
            .select_from(AuthLog)
            .outerjoin(actor, actor.id == AuthLog.user_id)
            .filter(*conditions)
        )
        query = _ordered(query, AuthLog.created_at, AuthLog.id, order)
        rows = _paged(query, page, size).all()

    return rows, int(total or 0)


# ── data_change_log ───────────────────────────────────────────────────────────

def list_data_changes(
    *,
    start: datetime,
    end: datetime,
    order: str,
    page: int,
    size: int,
    actor_uuid: Optional[UUID] = None,
    actor_kind: Optional[str] = None,
    actor_role: Optional[str] = None,
    table_name: Optional[str] = None,
    operation: Optional[str] = None,
    record_id: Optional[int] = None,
    target_user_uuid: Optional[UUID] = None,
) -> tuple[list, int]:
    actor = aliased(User)
    target = aliased(User)

    kinds = actor_kind_predicates(
        pol.DCL_POLICY,
        key_col=DataChangeLog.table_name,
        id_col=DataChangeLog.actor_id,
        role_col=DataChangeLog.actor_role,
        joined_id_col=actor.id,
    )

    conditions = [DataChangeLog.created_at >= start, DataChangeLog.created_at < end]
    if actor_uuid is not None:
        conditions.append(DataChangeLog.actor_id == _user_id_subq(actor_uuid))
    if actor_kind is not None:
        conditions.append(kinds[actor_kind])
    if actor_role is not None:
        conditions.append(DataChangeLog.actor_role == actor_role)
    if table_name is not None:
        conditions.append(DataChangeLog.table_name == table_name)
    if operation is not None:
        conditions.append(DataChangeLog.operation == operation)
    if record_id is not None:
        # Строка неизвестной таблицы не имеет осмысленного record_id — её нельзя
        # отдавать по точечному фильтру и затем показывать с record_id=null.
        conditions.append(and_(
            DataChangeLog.record_id == record_id,
            DataChangeLog.table_name.in_(sorted(pol.CHANGE_TABLE_NAMES)),
        ))
    if target_user_uuid is not None:
        conditions.append(and_(
            DataChangeLog.table_name == pol.USERS_TABLE,
            DataChangeLog.record_id == _user_id_subq(target_user_uuid),
        ))

    with SessionLocal() as db:
        total = (
            db.query(func.count())
            .select_from(DataChangeLog)
            .outerjoin(actor, actor.id == DataChangeLog.actor_id)
            .filter(*conditions)
            .scalar()
        )

        query = (
            db.query(
                DataChangeLog.id.label("entry_id"),
                DataChangeLog.created_at.label("occurred_at"),
                DataChangeLog.actor_id.label("actor_id"),
                DataChangeLog.actor_role.label("actor_role"),
                DataChangeLog.table_name.label("table_name"),
                DataChangeLog.record_id.label("record_id"),
                DataChangeLog.operation.label("operation"),
                DataChangeLog.changed_fields.label("changed_fields"),
                actor.id.label("actor_row_id"),
                actor.uuid.label("actor_user_uuid"),
                actor.full_name.label("actor_full_name"),
                actor.email.label("actor_email"),
                actor.deleted_at.label("actor_deleted_at"),
                target.uuid.label("target_user_uuid"),
                target.full_name.label("target_full_name"),
                target.email.label("target_email"),
                target.deleted_at.label("target_deleted_at"),
            )
            .select_from(DataChangeLog)
            .outerjoin(actor, actor.id == DataChangeLog.actor_id)
            .outerjoin(target, and_(
                DataChangeLog.table_name == pol.USERS_TABLE,
                target.id == DataChangeLog.record_id,
            ))
            .filter(*conditions)
        )
        query = _ordered(query, DataChangeLog.created_at, DataChangeLog.id, order)
        rows = _paged(query, page, size).all()

    return rows, int(total or 0)


# ── Батч-резолв внутренних id в UUID ──────────────────────────────────────────

def resolve_user_uuids(user_ids) -> dict:
    """`users.id` → `users.uuid` одним запросом на страницу.

    Нужен исключительно для DTO-политики metadata (`linked_user_id` →
    `linked_user_uuid`): внутренний id обязан быть заменён на UUID до выхода
    наружу. Один SQL на страницу, а не на строку — иначе получился бы N+1.
    """
    ids = {int(uid) for uid in user_ids if uid is not None}
    if not ids:
        return {}
    with SessionLocal() as db:
        rows = db.query(User.id, User.uuid).filter(User.id.in_(sorted(ids))).all()
    return {row.id: row.uuid for row in rows}
