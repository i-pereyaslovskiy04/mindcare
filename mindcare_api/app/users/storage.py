"""
Работа с БД для модуля users: запросы, фильтры, пагинация.
Все SQLAlchemy-запросы изолированы здесь.
"""

import sys
import uuid as _uuid
from collections import defaultdict
from typing import Optional
from datetime import datetime, timezone

from sqlalchemy import or_, asc, desc, select, case as sa_case
from sqlalchemy.exc import IntegrityError

from app.core.normalization import normalize_email
from app.audit import (
    Actor, Operation, Outcome, Target, project_changed_fields,
    record_data_change, record_event,
)
from app.audit.request_context import build_request_context
from app.auth.roles import ROLE_PRIORITY as _ROLE_PRIORITY_ORDER, primary_role
from app.auth.storage import get_active_role_names
from app.db.session import SessionLocal
from app.db.models import (
    User, UserRole, Role, UserSession, UserLegalBasisRecord,
)
from app.users.errors import (
    ActorContextError, EmailAlreadyExistsError, InvalidUserRequestError,
    RoleConfigError, UserNotFoundError,
)

# Имена email-unique объектов схемы (перепроверены по Alembic: baseline
# af13ad7a133c → ix_users_email; e5a8f3c1d2b6 → ux_users_email_normalized).
# Только эти constraint_name считаются email-коллизией на flush; иные
# IntegrityError re-raise как есть (без анализа str/SQL).
_USERS_EMAIL_UNIQUE_CONSTRAINTS = frozenset({
    "ix_users_email", "ux_users_email_normalized",
})


def _is_users_email_unique_violation(exc: IntegrityError) -> bool:
    orig = getattr(exc, "orig", None)
    diag = getattr(orig, "diag", None)
    name = getattr(diag, "constraint_name", None)
    return name in _USERS_EMAIL_UNIQUE_CONSTRAINTS


def _commit_or_diag(db, flow: str) -> None:
    """Stage 5A-2 commit-phase: узкий try ТОЛЬКО вокруг db.commit(). Сбой commit
    → outcome ambiguous: безопасная диагностика (event/phase=commit/класс, без
    str(exc)/URL/email/UUID/ролей/SQL) и немедленный bare raise. НЕ в AuthError,
    НЕ record_secondary_failure. refresh/query/DTO — вне этого try."""
    try:
        db.commit()
    except Exception as exc:   # noqa: BLE001 — только commit-фаза
        print(
            f"[AUDIT] event={flow} phase=commit error={type(exc).__name__}",
            file=sys.stderr,
        )
        raise

_ROLE_PRIORITY = sa_case(
    (Role.name == "admin",        1),
    (Role.name == "supervisor",   2),
    (Role.name == "psychologist", 3),
    (Role.name == "student",      4),
    else_=5,
)

# Python-порядок для сортировки списков имён ролей (roles_before/after), тот же,
# что глобальный ROLE_PRIORITY (admin, supervisor, psychologist, student).
_ROLE_ORDER_INDEX = {name: i for i, name in enumerate(_ROLE_PRIORITY_ORDER)}


def _sorted_roles(names) -> list[str]:
    return sorted(
        set(names),
        key=lambda n: _ROLE_ORDER_INDEX.get(n, len(_ROLE_PRIORITY_ORDER)),
    )


ALLOWED_SORT_FIELDS = {"created_at", "email", "full_name", "last_login"}

# Служебные роли: их назначение требует документированного основания (legal basis).
STAFF_ROLES = {"psychologist", "supervisor", "admin"}


class RoleChangeError(ValueError):
    """
    Ошибка управления ролями через admin API с явным HTTP-статусом.

    Stage 5A-2: несёт обязательный стабильный `audit_code` (для durable failure-
    аудита; из allowlist admin_user_update_failed). Подкласс ValueError.
    """

    def __init__(self, message: str, status_code: int, audit_code: str):
        super().__init__(message)
        self.status_code = status_code
        self.audit_code = audit_code


def find_users(
    page: int = 1,
    size: int = 20,
    search: Optional[str] = None,
    role: Optional[str] = None,
    is_active: Optional[bool] = None,
    sort: str = "created_at",
    order: str = "desc",
    include_deleted: bool = False,
) -> tuple[list[dict], int]:
    """
    Возвращает кортеж (items, total) для пагинированного списка юзеров.

    - items — список юзеров на текущей странице (в виде dict)
    - total — общее число юзеров с учётом фильтров (без пагинации)

    Применяет soft-delete фильтр: deleted_at IS NULL.
    Невалидные поля сортировки заменяются на 'created_at'.
    """
    if sort not in ALLOWED_SORT_FIELDS:
        sort = "created_at"

    now_dt = datetime.now(timezone.utc)
    # Просроченные user_roles (expires_at в прошлом) не считаются активными —
    # ни для отображаемой primary-роли, ни для фильтра по роли.
    _active_role = UserRole.expires_at.is_(None) | (UserRole.expires_at > now_dt)

    with SessionLocal() as db:
        # ── 1. Базовый запрос с коррелированным подзапросом роли ──
        role_subq = (
            select(Role.name)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == User.id)
            .where(_active_role)
            .order_by(_ROLE_PRIORITY)
            .limit(1)
            .correlate(User)
            .scalar_subquery()
        )
        query = db.query(User, role_subq.label("role_name"))
        if not include_deleted:
            query = query.filter(User.deleted_at.is_(None))

        # ── 2. Фильтры ──
        if search:
            pattern = f"%{search.strip()}%"
            query = query.filter(
                or_(
                    User.email.ilike(pattern),
                    User.full_name.ilike(pattern),
                )
            )

        if role:
            role_filter_subq = (
                select(UserRole.user_id)
                .join(Role, Role.id == UserRole.role_id)
                .where(Role.name == role)
                .where(_active_role)
            )
            query = query.filter(User.id.in_(role_filter_subq))

        if is_active is not None:
            query = query.filter(User.is_active == is_active)

        # ── 3. Общее количество (для пагинации) ──
        total = query.count()

        # ── 4. Сортировка ──
        sort_column = getattr(User, sort, User.created_at)
        direction = desc if order == "desc" else asc
        if include_deleted:
            query = query.order_by(User.deleted_at.is_(None).desc(), direction(sort_column))
        else:
            query = query.order_by(direction(sort_column))

        # ── 5. Пагинация (LIMIT/OFFSET) ──
        offset = (page - 1) * size
        results = query.offset(offset).limit(size).all()

        # ── 5b. Активные роли всех пользователей страницы одним запросом (не N+1) ──
        page_user_ids = [user.id for user, _ in results]
        roles_by_user: dict[int, list[str]] = defaultdict(list)
        if page_user_ids:
            role_rows = (
                db.query(UserRole.user_id, Role.name)
                .join(Role, Role.id == UserRole.role_id)
                .filter(UserRole.user_id.in_(page_user_ids))
                .filter(_active_role)
                .all()
            )
            for uid, name in role_rows:
                roles_by_user[uid].append(name)

        # ── 6. Маппинг в dict ──
        items = []
        for user, role_name in results:
            items.append({
                "id":         user.id,
                "uuid":       str(user.uuid),
                "email":      user.email,
                "full_name":  user.full_name,
                "roles":      _sorted_roles(roles_by_user.get(user.id, [])),
                # НЕ маскировать отсутствие активных ролей как "student":
                # role_name уже отфильтрован по _active_role и может быть None.
                "role":       role_name,
                "is_active":  user.is_active,
                "created_at": user.created_at,
                "last_login": user.last_login,
                "deleted_at": user.deleted_at,
            })

    return items, total


def get_user_by_uuid(uuid: str) -> Optional[dict]:
    """
    Возвращает dict с данными юзера (включая роли) или None если не найден.
    Применяет soft-delete фильтр: deleted_at IS NULL.

    `role` — primary_role(активные roles); None у пользователя без активных
    ролей (НЕ маскируется как "student"). Единственный источник активных
    ролей — get_active_role_names (тот же, что использует auth), без
    дублирующего SQL-подзапроса, который раньше не фильтровал expires_at.
    """
    try:
        uuid_obj = _uuid.UUID(uuid)
    except ValueError:
        return None

    with SessionLocal() as db:
        user = (
            db.query(User)
            .filter(User.uuid == uuid_obj)
            .filter(User.deleted_at.is_(None))
            .first()
        )
        if not user:
            return None
        roles = get_active_role_names(db, user.id)
        return {
            "id":         user.id,
            "uuid":       str(user.uuid),
            "email":      user.email,
            "full_name":  user.full_name,
            "phone":      user.phone,
            "roles":      roles,
            "role":       primary_role(roles),
            "is_active":  user.is_active,
            "created_at": user.created_at,
            "last_login": user.last_login,
        }


def _target_staff_from_roles(roles: list[str], current: set[str]) -> set[str]:
    """
    set-based путь (поле `roles`): целевой набор STAFF-ролей.

    `student` в `roles` запрещён (управляется вне admin role control) → 422.
    Существующая student-роль в `current` сохраняется ядром автоматически.
    """
    target = set(roles)
    if "student" in target:
        raise RoleChangeError(
            "Роль student не управляется через admin role control", 422,
            "role_policy_violation",
        )
    return target


def _target_staff_from_legacy_role(role: str, current: set[str]) -> set[str]:
    """
    Legacy single-`role` compatibility adapter (без replace-all).

    - multi-role пользователь → 409 (использовать `roles[]`);
    - `role == "student"`: разрешён только no-op (current == {student});
      иначе 422 (student не назначается/не снимается через admin role control);
    - staff `role`: возвращает {role} как целевой staff-набор. student-only →
      staff и bootstrap staff через PATCH отклоняются ядром (added при пустом
      current_staff → 422).
    """
    if len(current) > 1:
        raise RoleChangeError(
            "У пользователя несколько активных ролей — используйте roles[]", 409,
            "role_policy_violation",
        )
    if role == "student":
        if current == {"student"}:
            return set()  # no-op: staff не меняем, student сохраняется
        raise RoleChangeError(
            "Роль student не назначается и не снимается через admin role control",
            422, "role_policy_violation",
        )
    return {role}


def _apply_role_and_scalar_changes(
    db,
    user,
    *,
    current_roles: list[str],
    target_staff: Optional[set],
    full_name: Optional[str],
    phone: Optional[str],
    is_active: Optional[bool],
    legal_basis_confirmed: Optional[bool],
    basis_type: Optional[str],
    basis_reference: Optional[str],
    legal_basis_comment: Optional[str],
    confirmed_by_user_id: Optional[int],
    actor_id: Optional[int],
    actor_role: Optional[str],
    ip: Optional[str],
    user_agent: Optional[str],
) -> None:
    """
    Общее ядро set-based управления ролями и scalar-полей (без commit; commit —
    у вызывающего). Stage 4B-4: validate-then-mutate — все проверки, способные
    отклонить запрос (включая существование actor-контекста и added-ролей),
    выполняются ДО какой-либо мутации ORM; audit (admin_user_updated/
    admin_role_*) стейджится в этой же транзакции, ПОСЛЕ мутации, строго
    ПЕРЕД возвратом (commit — у вызывающего update_user).

    target_staff:
      - None → роли не трогаем (только scalar-поля);
      - set  → желаемый набор STAFF-ролей; student-роль пользователя сохраняется
               неизменной.

    Инвариант: НЕ удаляем весь user_roles ради одной роли — только точечный diff
    (add для added, delete для removed). Назначение staff-роли требует legal
    basis (одна запись на каждую добавленную роль); удаление staff-роли пишет
    audit, но не создаёт новый legal basis и не трогает старые записи.
    """
    current = set(current_roles)
    current_staff = current & STAFF_ROLES

    # ── (a) Нормализовать proposed scalar-значения в ЛОКАЛЬНЫЕ переменные, БЕЗ
    #        мутации ORM. Формат-валидация (400-уровень) не зависит от actor
    #        context и не должна дожидаться guard'а ниже.
    new_full_name = None
    if full_name is not None:
        new_full_name = full_name.strip()
        if len(new_full_name) < 2:
            raise RoleChangeError(
                "ФИО должно содержать минимум 2 символа", 400, "invalid_request",
            )
    new_phone = (phone.strip() or None) if phone is not None else None

    # ── (b)+(c) Scalar diff — сравнение НОРМАЛИЗОВАННЫХ proposed значений с
    #            текущими, ДО какой-либо мутации ORM. Stage 5A-1: is_active
    #            ВЫВЕДЕН из scalar_changed — его переход описывается отдельными
    #            lifecycle-событиями (admin_user_activated/deactivated), а
    #            admin_user_updated пишется только при изменении full_name/phone.
    #
    #            Stage 6-C: тот же diff теперь даёт ТОЧНЫЙ НАБОР ИМЁН полей —
    #            он нужен data_change_log. Семантика scalar_changed не меняется:
    #            это по-прежнему «есть ли реальный diff по full_name/phone».
    changed_scalar_fields: set = set()
    if full_name is not None and new_full_name != user.full_name:
        changed_scalar_fields.add("full_name")
    if phone is not None and new_phone != user.phone:
        changed_scalar_fields.add("phone")
    scalar_changed = bool(changed_scalar_fields)
    is_active_changed = is_active is not None and is_active != user.is_active
    deactivating = is_active_changed and is_active is False

    # ── (d) Role diff — до мутации.
    added: set = set()
    removed: set = set()
    if target_staff is not None:
        added = target_staff - current
        removed = current_staff - target_staff

    # ── (e) Fail-closed actor guard — ДО любой мутации ORM/ролей, если хоть
    #        один вид реального diff присутствует. Отсутствие actor_id/
    #        actor_role здесь — internal wiring-баг вызывающего кода (не
    #        пользовательский ввод и не system actor). RuntimeError не
    #        ловится service.update_user → HTTP 500; guard стоит до
    #        self-admin guard, остальных validations и любых мутаций (scalar/
    #        UserRole/UserLegalBasisRecord/AuditLog) — транзакция вызывающего
    #        откатывается без частичных изменений. Сообщение фиксированное,
    #        без ПДн/UUID/email/ролей target.
    if (scalar_changed or is_active_changed or added or removed) and (
        actor_id is None or actor_role is None
    ):
        raise ActorContextError(
            "user update requires authenticated actor context "
            "(actor_id and actor_role)"
        )

    # Self-admin guard (defense-in-depth, frontend лишь предотвращает ошибку в UI):
    # администратор не может снять у себя собственную активную роль admin. Работает
    # и для set-based roles[], и для legacy role adapter (оба вычисляют removed).
    # Другой админ может снять admin у другого пользователя (actor_id != user.id).
    if actor_id is not None and user.id == actor_id and "admin" in removed:
        raise RoleChangeError(
            "Нельзя снять у себя роль администратора", 422,
            "self_admin_protected",
        )

    # ── Истинный no-op: ни scalar, ни is_active, ни role — выходим ДО дальнейших
    #    validations/мутаций/audit.
    if (
        not scalar_changed
        and not is_active_changed
        and (target_staff is None or (not added and not removed))
    ):
        return

    # ── (f) Оставшиеся role-validations, способные ОТКЛОНИТЬ весь PATCH
    #        (400/422) — включая существование Role-строк для added. Всё это —
    #        read-only фаза, без единого db.add/db.delete/setattr на user.
    roles_after_set = None
    role_by_name: dict = {}
    removed_role_ids: list = []
    if target_staff is not None and (added or removed):
        roles_after_set = (current - removed) | added
        if not roles_after_set:
            raise RoleChangeError(
                "Нельзя оставить пользователя без активных ролей", 422,
                "role_policy_violation",
            )

        # Назначение staff-роли доступно только тому, у кого уже есть
        # staff-роль: student→staff и bootstrap staff через PATCH запрещены
        # (новые сотрудники — через POST /api/admin/users).
        if added and not current_staff:
            raise RoleChangeError(
                "Назначение служебной роли доступно только пользователю, у "
                "которого уже есть служебная роль; новых сотрудников "
                "создавайте через POST /api/admin/users",
                422, "role_policy_violation",
            )

        # Legal basis обязателен при добавлении staff-ролей.
        if added:
            if legal_basis_confirmed is not True:
                raise RoleChangeError(
                    "Для назначения служебной роли необходимо подтвердить "
                    "документированное основание (legal_basis_confirmed)", 400,
                    "legal_basis_required",
                )
            if not basis_type:
                raise RoleChangeError(
                    "Необходимо указать basis_type для назначения служебной "
                    "роли", 400, "legal_basis_required",
                )
            if not (basis_reference and basis_reference.strip()):
                raise RoleChangeError(
                    "Необходимо указать basis_reference (документ-основание) "
                    "для назначения служебной роли", 400, "legal_basis_required",
                )

            # Существование Role для ВСЕХ added — здесь, до какой-либо
            # мутации (раньше проверялось внутри цикла мутации, ПОСЛЕ scalar
            # setattr и удаления removed — Stage 4B-4 corrective pass).
            # Отсутствие Role в seed/БД — configuration/internal failure
            # (RoleConfigError → internal_error), НЕ пользовательский invalid_role.
            role_objs = db.query(Role).filter(Role.name.in_(added)).all()
            role_by_name = {r.name: r for r in role_objs}
            missing = sorted(added - role_by_name.keys())
            if missing:
                raise RoleConfigError("required staff role missing in seed/DB")

        # removed_role_ids — тоже чистое чтение (SELECT), не мутация; готовим
        # заранее, чтобы фаза (g) не содержала ничего, что могло бы отклонить
        # запрос.
        if removed:
            removed_role_ids = [
                r.id for r in db.query(Role).filter(Role.name.in_(removed)).all()
            ]

    # ── Единый sanitized context — ОДИН вызов на функцию, переиспользуется и
    #    для UserLegalBasisRecord, и для обеих audit-строк. Строится ПОСЛЕ
    #    всех отклоняющих validations (включая role-existence check выше).
    safe_ctx = build_request_context(ip=ip, user_agent=user_agent)

    # ── Stage 6-C: публичная проекция journal'а — ДО любой мутации ORM.
    #    Поле, неизвестное CHANGE_REGISTRY, роняет операцию здесь (fail-closed),
    #    пока ни один setattr ещё не выполнен. old snapshot НЕ снимается и
    #    values НЕ строятся: full_name и phone объявлены name-only, поэтому
    #    ФИО и телефон физически не могут попасть в old_values/new_values.
    dcl_fields: list = []
    if scalar_changed:
        dcl_fields = project_changed_fields("users", changed_scalar_fields)

    # ── (g) Применить мутации — ТОЛЬКО теперь, когда ВСЕ validations прошли
    #        (включая существование added-ролей). С этой точки и до конца
    #        функции не остаётся ни одной проверки, способной бросить
    #        RoleChangeError/ValueError.
    if full_name is not None:
        user.full_name = new_full_name
    if phone is not None:
        user.phone = new_phone
    if is_active is not None:
        user.is_active = is_active

    # Stage 5A-1: отзыв активных сессий ТОЛЬКО при реальном переходе True→False,
    # в той же транзакции ДО record_event и commit. Сбой аудита/commit откатывает
    # is_active и отзыв сессий вместе. Активация/no-op/прочие поля сессии не трогают.
    if deactivating:
        db.query(UserSession).filter(
            UserSession.user_id == user.id,
            ~UserSession.is_revoked,
        ).update({"is_revoked": True}, synchronize_session=False)

    roles_before = roles_after = None
    if target_staff is not None and (added or removed):
        roles_before = _sorted_roles(current)
        roles_after = _sorted_roles(roles_after_set)

        # Точечное удаление снятых staff-ролей.
        if removed_role_ids:
            db.query(UserRole).filter(
                UserRole.user_id == user.id,
                UserRole.role_id.in_(removed_role_ids),
            ).delete(synchronize_session=False)

        # Добавление новых staff-ролей + запись основания на каждую.
        for role_name in _sorted_roles(added):
            role_obj = role_by_name[role_name]   # гарантированно существует (шаг f)
            # get_active_role_names уже исключил просроченные роли из `current`,
            # но строка user_roles(user_id, role_id) могла остаться в БД с
            # истёкшим expires_at (UniqueConstraint не позволяет вставить
            # вторую). Реактивируем существующую строку вместо INSERT.
            existing_ur = (
                db.query(UserRole)
                .filter(UserRole.user_id == user.id, UserRole.role_id == role_obj.id)
                .first()
            )
            if existing_ur is not None:
                existing_ur.expires_at = None
            else:
                db.add(UserRole(user_id=user.id, role_id=role_obj.id))
            db.add(UserLegalBasisRecord(
                user_id=user.id,
                basis_type=basis_type,
                basis_source="admin_ui",
                basis_reference=basis_reference.strip(),
                confirmed_by_user_id=confirmed_by_user_id,
                ip_address=safe_ctx.ip_address,   # sanitized, не raw ip
                user_agent=safe_ctx.user_agent,    # sanitized, не raw user_agent
                comment=legal_basis_comment,
                record_metadata={
                    "action":       "role_add",
                    "added_role":   role_name,
                    "roles_before": roles_before,
                    "roles_after":  roles_after,
                },
            ))

    # ── (h) Stage audit rows — success record_event ТОЛЬКО теперь, после того
    #        как ВСЕ отклоняющие validations уже прошли и мутации применены.
    #        Порядок: scalar раньше role (естественный порядок кода).
    if scalar_changed:
        record_event(
            event="admin_user_updated",
            actor=Actor.user(actor_id, actor_role),
            target=Target("user", user.id),
            outcome=Outcome.SUCCESS,
            metadata={},
            context=safe_ctx,
            db=db,
        )
        # Stage 6-C: field-level журнал рядом с тем же paired_event, в ТОЙ ЖЕ
        # транзакции (SessionLocal и commit — у update_user). values=None
        # всегда: full_name/phone — name-only, значения ПДн не копируются.
        # is_active и роли сюда не попадают — они вне changed_scalar_fields.
        record_data_change(
            table="users",
            record_id=user.id,
            operation=Operation.UPDATE,
            actor=Actor.user(actor_id, actor_role),
            changed_fields=dcl_fields,
            values=None,
            context=safe_ctx,
            db=db,
        )
    # Stage 5A-1: отдельное lifecycle-событие для перехода is_active (не дублируется
    # в admin_user_updated). Ровно одно на реальный переход; direction по deactivating.
    if is_active_changed:
        record_event(
            event="admin_user_deactivated" if deactivating else "admin_user_activated",
            actor=Actor.user(actor_id, actor_role),
            target=Target("user", user.id),
            outcome=Outcome.SUCCESS,
            metadata={},
            context=safe_ctx,
            db=db,
        )
    if target_staff is not None and (added or removed):
        event = "admin_role_add" if added and not removed else (
            "admin_role_remove" if removed and not added else "admin_role_update"
        )
        # ATOMIC audit через единый facade: та же caller-транзакция (db=db),
        # facade только db.add (без commit/rollback/close). actor=действующий
        # админ, target=пользователь, чьи роли меняются (Stage 3 semantics
        # сохранены). description не пишется (facade), metadata — role-diff.
        record_event(
            event=event,
            actor=Actor.user(actor_id, actor_role),
            target=Target("user", user.id),
            outcome=Outcome.SUCCESS,
            metadata={
                "roles_before": roles_before,
                "roles_after":  roles_after,
                "added":        _sorted_roles(added),
                "removed":      _sorted_roles(removed),
            },
            context=safe_ctx,
            db=db,
        )


def update_user(
    uuid: str,
    full_name: Optional[str] = None,
    phone: Optional[str] = None,
    is_active: Optional[bool] = None,
    role: Optional[str] = None,
    *,
    roles: Optional[list[str]] = None,
    legal_basis_confirmed: Optional[bool] = None,
    basis_type: Optional[str] = None,
    basis_reference: Optional[str] = None,
    legal_basis_comment: Optional[str] = None,
    confirmed_by_user_id: Optional[int] = None,
    actor_id: Optional[int] = None,
    actor_role: Optional[str] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    """
    Обновляет scalar-поля и/или роли юзера (multi-role, set-based; ADR-018).

    Управление ролями — ТОЛЬКО staff (`psychologist`/`supervisor`/`admin`) и
    без destructive replace-all:
      - `roles` (target staff set) — основной set-based путь;
      - legacy `role` (single) — compatibility adapter поверх того же ядра
        (multi-role → 409; student — только no-op).
    `student`-роль read-only: не добавляется, не снимается, не конвертируется.

    Raises (Stage 5A-2, typed precommit):
      InvalidUserRequestError — malformed UUID (service → 400/invalid_request);
      UserNotFoundError       — юзер не найден (service → 404/user_not_found);
      RoleChangeError         — нарушение role-контракта (audit_code + status);
      RoleConfigError         — отсутствует Role в seed/БД (→ internal_error);
      ActorContextError       — нет actor context (→ internal_error).
    """
    try:
        uuid_obj = _uuid.UUID(uuid)
    except ValueError:
        raise InvalidUserRequestError("Некорректный идентификатор пользователя")

    with SessionLocal() as db:
        user = (
            db.query(User)
            .filter(User.uuid == uuid_obj)
            .filter(User.deleted_at.is_(None))
            .first()
        )
        if not user:
            raise UserNotFoundError("Пользователь не найден")

        current_roles = get_active_role_names(db, user.id)
        current = set(current_roles)

        if roles is not None:
            target_staff: Optional[set] = _target_staff_from_roles(roles, current)
        elif role is not None:
            target_staff = _target_staff_from_legacy_role(role, current)
        else:
            target_staff = None  # только scalar-поля

        _apply_role_and_scalar_changes(
            db, user,
            current_roles=current_roles,
            target_staff=target_staff,
            full_name=full_name,
            phone=phone,
            is_active=is_active,
            legal_basis_confirmed=legal_basis_confirmed,
            basis_type=basis_type,
            basis_reference=basis_reference,
            legal_basis_comment=legal_basis_comment,
            confirmed_by_user_id=confirmed_by_user_id,
            actor_id=actor_id,
            actor_role=actor_role,
            ip=ip,
            user_agent=user_agent,
        )

        _commit_or_diag(db, "admin_user_update")
        db.refresh(user)

        roles_out = get_active_role_names(db, user.id)
        return {
            "id":         user.id,
            "uuid":       str(user.uuid),
            "email":      user.email,
            "full_name":  user.full_name,
            "phone":      user.phone,
            "roles":      roles_out,
            # НЕ маскировать отсутствие активных ролей как "student".
            "role":       primary_role(roles_out),
            "is_active":  user.is_active,
            "created_at": user.created_at,
            "last_login": user.last_login,
        }


def soft_delete_user(
    uuid: str,
    *,
    actor_id: Optional[int] = None,
    actor_role: Optional[str] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> bool:
    """
    Мягкое удаление юзера — выставляет deleted_at, не удаляет физически.
    Возвращает True если юзер найден и помечен удалённым, False если не найден.
    Также отзывает все активные сессии юзера.

    Raises:
        ActorContextError: нет authenticated actor context (→ internal_error).
    """
    # malformed UUID → not-found контракт (service → 404/user_not_found).
    try:
        uuid_obj = _uuid.UUID(uuid)
    except ValueError:
        return False

    # Fail-closed actor guard — ДО открытия сессии/поиска пользователя.
    # Мягкое удаление — всегда привилегированное действие; отсутствие
    # actor-контекста здесь — internal wiring-баг, не пользовательский ввод.
    if actor_id is None or actor_role is None:
        raise ActorContextError(
            "user delete requires authenticated actor context "
            "(actor_id and actor_role)"
        )

    with SessionLocal() as db:
        user = (
            db.query(User)
            .filter(User.uuid == uuid_obj)
            .filter(User.deleted_at.is_(None))
            .first()
        )
        if not user:
            return False

        now = datetime.now(timezone.utc)
        user.deleted_at = now
        user.is_active = False

        db.query(UserSession).filter(
            UserSession.user_id == user.id,
            ~UserSession.is_revoked,
        ).update({"is_revoked": True}, synchronize_session=False)

        # ATOMIC audit через единый facade: та же caller-транзакция (db=db),
        # facade только db.add. metadata={} (registry не допускает ключей).
        # Сбой аудита откатывает soft-delete и отзыв сессий целиком.
        record_event(
            event="admin_user_deleted",
            actor=Actor.user(actor_id, actor_role),
            target=Target("user", user.id),
            outcome=Outcome.SUCCESS,
            metadata={},
            context=build_request_context(ip=ip, user_agent=user_agent),
            db=db,
        )

        _commit_or_diag(db, "admin_user_delete")
        return True


def create_user(
    email: str,
    full_name: str,
    password_hash: str,
    roles: list[str],
    phone: Optional[str] = None,
    *,
    basis_type: str = "service_duty",
    basis_reference: Optional[str] = None,
    legal_basis_comment: Optional[str] = None,
    confirmed_by_user_id: Optional[int] = None,
    actor_role: Optional[str] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    """
    Создаёт нового пользователя с набором служебных (staff) ролей.

    Используется только из админских эндпоинтов (multi-role create; single role —
    частный случай списка из одной роли). Публичная регистрация — через
    auth/storage.save_user; student через admin API не создаётся.

    Defense-in-depth (не полагаемся на схему): dedupe с сохранением порядка,
    только staff-роли (psychologist/supervisor/admin), набор не пуст, все роли
    существуют в БД, basis_reference непустой после strip. На каждую уникальную
    роль — ровно одна UserRole и одна UserLegalBasisRecord (документированное
    основание организации, НЕ consent_records) с обрезанным basis_reference.
    Всё в одной транзакции: если запись основания или audit-запись падает —
    пользователь не создаётся (rollback).

    `confirmed_by_user_id` — ЕДИНСТВЕННЫЙ actor identifier (уже существовал для
    legal basis); используется и как actor audit-события `admin_user_created`
    (Stage 4B-4) — не дублируется отдельным `actor_id`, чтобы исключить
    расхождение между «кто подтвердил legal basis» и «кто actor аудита».

    Возвращает dict с `roles` (sorted) и `role` = primary_role(roles).

    Raises:
        ValueError: duplicate email, пустой/невалидный набор ролей, отсутствие
            роли в БД, либо пустой/whitespace-only basis_reference.
        RuntimeError: отсутствует authenticated actor context (fail-closed,
            wiring-баг вызывающего кода, не пользовательский ввод).
    """
    # Fail-closed actor guard — ДО какой-либо валидации/мутации. Создание
    # staff-пользователя — всегда привилегированное действие; отсутствие
    # actor-контекста здесь означает internal wiring-баг вызывающего кода, не
    # отсутствие пользовательского ввода. Сообщение фиксированное, без ПДн.
    if confirmed_by_user_id is None or actor_role is None:
        raise ActorContextError(
            "user create requires authenticated actor context "
            "(confirmed_by_user_id and actor_role)"
        )

    # ── Нормализация и валидация набора ролей ──
    deduped = list(dict.fromkeys(roles))       # dedupe, порядок сохранён
    if not deduped:
        raise ValueError("Не указано ни одной роли для создания пользователя")
    invalid = [r for r in deduped if r not in STAFF_ROLES]
    if invalid:
        raise ValueError(
            f"Через admin API назначаются только служебные роли "
            f"(psychologist/supervisor/admin); недопустимо: {invalid}"
        )
    sorted_roles = _sorted_roles(deduped)

    # Defense-in-depth: не полагаемся на то, что basis_reference уже провалидирован
    # схемой (AdminUserCreate) — storage самостоятельно отвергает пустое/whitespace
    # значение до создания User.
    if not basis_reference or not basis_reference.strip():
        raise ValueError(
            "Необходимо указать basis_reference (документ-основание) для "
            "создания служебной учётной записи"
        )
    stripped_basis_reference = basis_reference.strip()

    # Единый sanitized context — один вызов на функцию, переиспользуется и для
    # UserLegalBasisRecord, и для admin_user_created record_event (не два
    # независимых источника истины для одного и того же raw ip/user_agent).
    safe_ctx = build_request_context(ip=ip, user_agent=user_agent)

    with SessionLocal() as db:
        # Authoritative in-tx проверка домена (FOR SHARE) до создания User.
        # EmailDomainNotAllowedError (не ValueError) пробрасывается наружу и
        # мапится в 422 в users.service.create_user (отдельным except раньше
        # существующего ValueError→409).
        from app.email_domains.storage import assert_email_domain_allowed_in_tx
        assert_email_domain_allowed_in_tx(db, email)

        # Stage 5A-2: authoritative duplicate-check среди ВСЕХ User (включая
        # soft-deleted) — soft-deleted staff публично/через admin create НЕ
        # реактивируется. Найдено → typed EmailAlreadyExistsError до мутации.
        existing = (
            db.query(User)
            .filter(User.email == normalize_email(email))
            .first()
        )
        if existing:
            raise EmailAlreadyExistsError(
                "Пользователь с таким email уже существует"
            )

        # Все роли обязаны существовать в справочнике (один запрос).
        # Отсутствие Role — configuration/internal failure (RoleConfigError →
        # internal_error), НЕ пользовательский invalid_role.
        role_objs = db.query(Role).filter(Role.name.in_(deduped)).all()
        by_name = {r.name: r for r in role_objs}
        missing = [r for r in deduped if r not in by_name]
        if missing:
            raise RoleConfigError("required staff role missing in seed/DB")

        new_user = User(
            email=normalize_email(email),
            full_name=full_name.strip(),
            password_hash=password_hash,
            phone=phone.strip() or None if phone else None,
            is_active=True,
        )
        db.add(new_user)
        # Узкий try ТОЛЬКО вокруг business INSERT+flush. IntegrityError по
        # email-unique (гонка) → EmailAlreadyExistsError ТОЛЬКО при известном
        # constraint_name (без анализа str/SQL); иной IntegrityError re-raise
        # как есть (не AuthError, не *_failed). Precommit → rollback-confirmed.
        try:
            db.flush()  # id до commit — нужен для user_roles и legal basis
        except IntegrityError as exc:
            db.rollback()
            if _is_users_email_unique_violation(exc):
                raise EmailAlreadyExistsError(
                    "Пользователь с таким email уже существует"
                )
            raise

        for role_name in sorted_roles:
            db.add(UserRole(user_id=new_user.id, role_id=by_name[role_name].id))
            db.add(UserLegalBasisRecord(
                user_id=new_user.id,
                basis_type=basis_type,
                basis_source="admin_ui",
                basis_reference=stripped_basis_reference,
                confirmed_by_user_id=confirmed_by_user_id,
                ip_address=safe_ctx.ip_address,   # sanitized, не raw ip
                user_agent=safe_ctx.user_agent,    # sanitized, не raw user_agent
                comment=legal_basis_comment,
                record_metadata={
                    "action":       "user_create",
                    "created_role": role_name,
                    "roles_after":  sorted_roles,
                },
            ))

        # ATOMIC audit через единый facade: та же caller-транзакция (db=db),
        # facade только db.add (без commit/rollback/close). actor=admin,
        # создавший пользователя (тот же confirmed_by_user_id, что и в legal
        # basis выше — см. docstring), target=новый пользователь. metadata={}
        # (registry не допускает ключей для этого события). Сбой аудита
        # откатывает создание пользователя целиком (ATOMIC/RAISE).
        record_event(
            event="admin_user_created",
            actor=Actor.user(confirmed_by_user_id, actor_role),
            target=Target("user", new_user.id),
            outcome=Outcome.SUCCESS,
            metadata={},
            context=safe_ctx,
            db=db,
        )

        _commit_or_diag(db, "admin_user_create")
        db.refresh(new_user)

        return {
            "id":         new_user.id,
            "uuid":       str(new_user.uuid),
            "email":      new_user.email,
            "full_name":  new_user.full_name,
            "roles":      sorted_roles,
            "role":       primary_role(sorted_roles),
            "is_active":  new_user.is_active,
            "created_at": new_user.created_at,
        }
