"""
Работа с БД для модуля users: запросы, фильтры, пагинация.
Все SQLAlchemy-запросы изолированы здесь.
"""

import uuid as _uuid
from collections import defaultdict
from typing import Optional
from datetime import datetime, timezone

from sqlalchemy import or_, asc, desc, select, case as sa_case

from app.core.normalization import normalize_email
from app.auth.roles import ROLE_PRIORITY as _ROLE_PRIORITY_ORDER, primary_role
from app.auth.storage import get_active_role_names
from app.db.session import SessionLocal
from app.db.models import (
    AuditLog, User, UserRole, Role, UserSession, UserLegalBasisRecord,
)

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

    Подкласс ValueError → существующая обработка `except ValueError` в service
    остаётся валидной, но service отдаёт предпочтение `status_code`.
    """

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


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
            "Роль student не управляется через admin role control", 422
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
            "У пользователя несколько активных ролей — используйте roles[]", 409
        )
    if role == "student":
        if current == {"student"}:
            return set()  # no-op: staff не меняем, student сохраняется
        raise RoleChangeError(
            "Роль student не назначается и не снимается через admin role control",
            422,
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
    Общее ядро set-based управления ролями (без commit; commit — у вызывающего).

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

    # Scalar-поля.
    if full_name is not None:
        stripped = full_name.strip()
        if len(stripped) < 2:
            raise RoleChangeError("ФИО должно содержать минимум 2 символа", 400)
        user.full_name = stripped
    if phone is not None:
        user.phone = phone.strip() or None
    if is_active is not None:
        user.is_active = is_active

    if target_staff is None:
        return

    added = target_staff - current
    removed = current_staff - target_staff

    # Self-admin guard (defense-in-depth, frontend лишь предотвращает ошибку в UI):
    # администратор не может снять у себя собственную активную роль admin. Работает
    # и для set-based roles[], и для legacy role adapter (оба вычисляют removed).
    # Другой админ может снять admin у другого пользователя (actor_id != user.id).
    if actor_id is not None and user.id == actor_id and "admin" in removed:
        raise RoleChangeError("Нельзя снять у себя роль администратора", 422)

    if not added and not removed:
        return  # no-op по ролям

    roles_after_set = (current - removed) | added
    if not roles_after_set:
        raise RoleChangeError(
            "Нельзя оставить пользователя без активных ролей", 422
        )

    # Назначение staff-роли доступно только тому, у кого уже есть staff-роль:
    # student→staff и bootstrap staff через PATCH запрещены (новые сотрудники —
    # через POST /api/admin/users).
    if added and not current_staff:
        raise RoleChangeError(
            "Назначение служебной роли доступно только пользователю, у которого "
            "уже есть служебная роль; новых сотрудников создавайте через "
            "POST /api/admin/users",
            422,
        )

    # Legal basis обязателен при добавлении staff-ролей.
    if added:
        if legal_basis_confirmed is not True:
            raise RoleChangeError(
                "Для назначения служебной роли необходимо подтвердить "
                "документированное основание (legal_basis_confirmed)", 400,
            )
        if not basis_type:
            raise RoleChangeError(
                "Необходимо указать basis_type для назначения служебной роли",
                400,
            )
        if not (basis_reference and basis_reference.strip()):
            raise RoleChangeError(
                "Необходимо указать basis_reference (документ-основание) "
                "для назначения служебной роли", 400,
            )

    roles_before = _sorted_roles(current)
    roles_after = _sorted_roles(roles_after_set)

    # Точечное удаление снятых staff-ролей.
    if removed:
        removed_role_ids = [
            r.id for r in db.query(Role).filter(Role.name.in_(removed)).all()
        ]
        if removed_role_ids:
            db.query(UserRole).filter(
                UserRole.user_id == user.id,
                UserRole.role_id.in_(removed_role_ids),
            ).delete(synchronize_session=False)

    # Добавление новых staff-ролей + запись основания на каждую.
    for role_name in _sorted_roles(added):
        role_obj = db.query(Role).filter(Role.name == role_name).first()
        if not role_obj:
            raise RoleChangeError(f"Роль '{role_name}' не найдена в БД", 400)
        # get_active_role_names уже исключил просроченные роли из `current`, но
        # строка user_roles(user_id, role_id) могла остаться в БД с истёкшим
        # expires_at (UniqueConstraint(user_id, role_id) не позволяет вставить
        # вторую). Реактивируем существующую строку вместо INSERT, если она есть.
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
            ip_address=ip,
            user_agent=user_agent,
            comment=legal_basis_comment,
            record_metadata={
                "action":       "role_add",
                "added_role":   role_name,
                "roles_before": roles_before,
                "roles_after":  roles_after,
            },
        ))

    # Audit операции над ролями (удаление staff-роли — audit без нового basis).
    if added and not removed:
        event = "admin_role_add"
    elif removed and not added:
        event = "admin_role_remove"
    else:
        event = "admin_role_update"
    db.add(AuditLog(
        user_id=user.id,
        user_role=actor_role,
        event_type=event,
        entity_type="user",
        entity_id=user.id,
        description=f"roles {roles_before} -> {roles_after}",
        log_metadata={
            "roles_before": roles_before,
            "roles_after":  roles_after,
            "added":        _sorted_roles(added),
            "removed":      _sorted_roles(removed),
        },
        ip_address=ip,
        user_agent=user_agent,
    ))


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

    Raises:
      ValueError        — юзер не найден / некорректный UUID (service → 404/400);
      RoleChangeError    — нарушение role-контракта (свой status_code: 400/409/422).
    """
    try:
        uuid_obj = _uuid.UUID(uuid)
    except ValueError:
        raise ValueError(f"Некорректный UUID: {uuid}")

    with SessionLocal() as db:
        user = (
            db.query(User)
            .filter(User.uuid == uuid_obj)
            .filter(User.deleted_at.is_(None))
            .first()
        )
        if not user:
            raise ValueError(f"Пользователь {uuid} не найден")

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

        db.commit()
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


def soft_delete_user(uuid: str) -> bool:
    """
    Мягкое удаление юзера — выставляет deleted_at, не удаляет физически.
    Возвращает True если юзер найден и помечен удалённым, False если не найден.
    Также отзывает все активные сессии юзера.
    """
    try:
        uuid_obj = _uuid.UUID(uuid)
    except ValueError:
        return False

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

        db.commit()
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
    Всё в одной транзакции: если запись основания падает — пользователь не
    создаётся (rollback).

    Возвращает dict с `roles` (sorted) и `role` = primary_role(roles).

    Raises ValueError при duplicate email, пустом/невалидном наборе ролей,
    отсутствии роли в БД, либо пустом/whitespace-only basis_reference.
    """
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

    with SessionLocal() as db:
        # Authoritative in-tx проверка домена (FOR SHARE) до создания User.
        # EmailDomainNotAllowedError (не ValueError) пробрасывается наружу и
        # мапится в 422 в users.service.create_user (отдельным except раньше
        # существующего ValueError→409).
        from app.email_domains.storage import assert_email_domain_allowed_in_tx
        assert_email_domain_allowed_in_tx(db, email)

        existing = (
            db.query(User)
            .filter(User.email == normalize_email(email))
            .filter(User.deleted_at.is_(None))
            .first()
        )
        if existing:
            raise ValueError(f"Пользователь с email {email} уже существует")

        # Все роли обязаны существовать в справочнике (один запрос).
        role_objs = db.query(Role).filter(Role.name.in_(deduped)).all()
        by_name = {r.name: r for r in role_objs}
        missing = [r for r in deduped if r not in by_name]
        if missing:
            raise ValueError(f"Роли не найдены в БД: {missing}")

        new_user = User(
            email=normalize_email(email),
            full_name=full_name.strip(),
            password_hash=password_hash,
            phone=phone.strip() or None if phone else None,
            is_active=True,
        )
        db.add(new_user)
        db.flush()  # получаем id до commit — нужен для user_roles и legal basis

        for role_name in sorted_roles:
            db.add(UserRole(user_id=new_user.id, role_id=by_name[role_name].id))
            db.add(UserLegalBasisRecord(
                user_id=new_user.id,
                basis_type=basis_type,
                basis_source="admin_ui",
                basis_reference=stripped_basis_reference,
                confirmed_by_user_id=confirmed_by_user_id,
                ip_address=ip,
                user_agent=user_agent,
                comment=legal_basis_comment,
                record_metadata={
                    "action":       "user_create",
                    "created_role": role_name,
                    "roles_after":  sorted_roles,
                },
            ))
        db.commit()
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
