"""
SQLAlchemy-запросы для модуля супервизора.

Чтение (SELECT) + одна транзакционная операция создания студента
(create_student): остальные write-операции (assign/transfer/close) — в service.py.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import aliased

from app.audit import Actor, Outcome, Target, record_event
from app.core.normalization import normalize_email
from app.db.session import SessionLocal
from app.db.models import (
    Consent,
    ConsentRecord,
    PsychologistProfile,
    Role,
    TherapyEngagement,
    User,
    UserRole,
)


class StudentCreateError(Exception):
    """Ошибка создания студента на уровне storage.

    code маппится в HTTP-статус в service.create_student
    (duplicate_email/psychologist_not_found/not_a_psychologist/
    psychologist_inactive/consent_policy_missing/student_role_missing).
    """

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def get_students(
    search: Optional[str] = None,
    page: int = 1,
    size: int = 20,
) -> tuple[list[dict], int]:
    """
    Возвращает (items, total) — студентов с их текущим активным engagement.
    """
    with SessionLocal() as db:
        PsychUser = aliased(User)

        base_filter = [
            Role.name == "student",
            User.is_active.is_(True),
            User.deleted_at.is_(None),
        ]
        if search:
            pattern = f"%{search.strip()}%"
            base_filter.append(
                or_(User.email.ilike(pattern), User.full_name.ilike(pattern))
            )

        # Отдельный count (без лишних outer join — быстрее)
        total = (
            db.query(func.count(User.id))
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .filter(*base_filter)
            .scalar()
        ) or 0

        results = (
            db.query(User, TherapyEngagement, PsychUser)
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .filter(*base_filter)
            .outerjoin(
                TherapyEngagement,
                and_(
                    TherapyEngagement.client_id == User.id,
                    TherapyEngagement.status == "active",
                    TherapyEngagement.ended_at.is_(None),
                ),
            )
            .outerjoin(PsychUser, PsychUser.id == TherapyEngagement.psychologist_id)
            .order_by(User.full_name)
            .offset((page - 1) * size)
            .limit(size)
            .all()
        )

        items = []
        for student, engagement, psy in results:
            current_engagement = None
            if engagement:
                current_engagement = {
                    "id":     engagement.id,
                    "status": engagement.status,
                    "psychologist": {
                        "id":        psy.id,
                        "uuid":      str(psy.uuid),
                        "full_name": psy.full_name,
                        "email":     psy.email,
                    } if psy else None,
                }
            items.append({
                "id":                 student.id,
                "uuid":               str(student.uuid),
                "full_name":          student.full_name,
                "email":              student.email,
                "current_engagement": current_engagement,
            })

        return items, total


def get_psychologists(
    search: Optional[str] = None,
    page: int = 1,
    size: int = 100,
) -> tuple[list[dict], int]:
    """
    Возвращает (items, total) — психологов с полем is_accepting из profiles.
    """
    with SessionLocal() as db:
        base_filter = [
            Role.name == "psychologist",
            User.is_active.is_(True),
            User.deleted_at.is_(None),
        ]
        if search:
            pattern = f"%{search.strip()}%"
            base_filter.append(
                or_(User.email.ilike(pattern), User.full_name.ilike(pattern))
            )

        total = (
            db.query(func.count(User.id))
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .filter(*base_filter)
            .scalar()
        ) or 0

        results = (
            db.query(User, PsychologistProfile)
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .filter(*base_filter)
            .outerjoin(PsychologistProfile, PsychologistProfile.user_id == User.id)
            .order_by(User.full_name)
            .offset((page - 1) * size)
            .limit(size)
            .all()
        )

        items = []
        for user, profile in results:
            items.append({
                "id":           user.id,
                "uuid":         str(user.uuid),
                "full_name":    user.full_name,
                "email":        user.email,
                "is_accepting": profile.is_accepting if profile else None,
            })

        return items, total


def get_engagements(
    status: Optional[str] = None,
    student_search: Optional[str] = None,
    psychologist_search: Optional[str] = None,
    page: int = 1,
    size: int = 20,
) -> tuple[list[dict], int]:
    """
    Возвращает (items, total) — список всех связок с фильтрами.
    """
    with SessionLocal() as db:
        ClientUser = aliased(User, name="client_user")
        PsychUser  = aliased(User, name="psy_user")

        q = (
            db.query(TherapyEngagement, ClientUser, PsychUser)
            .join(ClientUser, ClientUser.id == TherapyEngagement.client_id)
            .join(PsychUser,  PsychUser.id  == TherapyEngagement.psychologist_id)
            .filter(
                ClientUser.deleted_at.is_(None),
                PsychUser.deleted_at.is_(None),
            )
        )

        if status:
            q = q.filter(TherapyEngagement.status == status)
        if student_search:
            pattern = f"%{student_search.strip()}%"
            q = q.filter(
                or_(ClientUser.email.ilike(pattern), ClientUser.full_name.ilike(pattern))
            )
        if psychologist_search:
            pattern = f"%{psychologist_search.strip()}%"
            q = q.filter(
                or_(PsychUser.email.ilike(pattern), PsychUser.full_name.ilike(pattern))
            )

        total = q.with_entities(func.count(TherapyEngagement.id)).scalar() or 0

        results = (
            q.order_by(TherapyEngagement.started_at.desc())
            .offset((page - 1) * size)
            .limit(size)
            .all()
        )

        items = []
        for eng, client, psy in results:
            items.append({
                "id":              eng.id,
                "status":          eng.status,
                "primary_concern": eng.primary_concern,
                "started_at":      eng.started_at,
                "ended_at":        eng.ended_at,
                "transfer_reason": eng.transfer_reason,
                "client": {
                    "id":        client.id,
                    "uuid":      str(client.uuid),
                    "full_name": client.full_name,
                    "email":     client.email,
                },
                "psychologist": {
                    "id":        psy.id,
                    "uuid":      str(psy.uuid),
                    "full_name": psy.full_name,
                    "email":     psy.email,
                },
            })

        return items, total


# ── Создание зарегистрированного студента (admin/supervisor) ───────────────────

def create_student(
    *,
    email: str,
    full_name: str,
    password_hash: str,
    phone: Optional[str],
    psychologist_id: Optional[int],
    primary_concern: Optional[str],
    actor_id: int,
    actor_role: str,
    ip: Optional[str],
    user_agent: Optional[str],
    required_consent_types: list[str],
) -> dict:
    """
    Атомарно создаёт полноценный аккаунт студента (admin/supervisor).

    В ОДНОЙ сессии и ОДНОМ commit:
      1. проверка уникальности email;
      2. (если задан psychologist_id) валидация психолога — существует,
         не удалён, роль psychologist, is_active=True;
      3. User(role=student, is_active=True) + UserRole(student);
      4. ConsentRecord на каждую обязательную политику — личное согласие
         субъекта, получено очно (accepted=True; ip/user_agent — контекст
         запроса staff, в котором согласие внесено);
      5. (если задан psychologist_id) active TherapyEngagement;
      6. AuditLog supervisor_create_student (+ supervisor_assign_psychologist).

    AuditLog обязателен В ЭТОЙ транзакции (ConsentRecord не хранит actor) и НЕ
    swallow'ится: его сбой откатывает всю запись. Любой сбой шага поднимает
    исключение до commit → полный rollback (нет студента без согласия/
    назначения/аудита). ПДн/пароль не логируются.

    Raises StudentCreateError(code). Возвращает dict с данными студента,
    engagement (или None) и psychologist_name (для post-commit уведомления).
    """
    email_norm = normalize_email(email)
    now = datetime.now(timezone.utc)

    with SessionLocal() as db:
        # 0. Authoritative in-tx проверка домена (FOR SHARE) до создания User.
        # supervisor.storage не импортирует SupervisorError (service-слой):
        # EmailDomainNotAllowedError преобразуется в StudentCreateError с кодом,
        # который service мапит в 422.
        from app.email_domains.errors import EmailDomainNotAllowedError
        from app.email_domains.storage import assert_email_domain_allowed_in_tx
        try:
            assert_email_domain_allowed_in_tx(db, email)
        except EmailDomainNotAllowedError as exc:
            raise StudentCreateError("email_domain_not_allowed", str(exc))

        # 1. Уникальность email среди не удалённых пользователей.
        exists = (
            db.query(User.id)
            .filter(User.email == email_norm, User.deleted_at.is_(None))
            .first()
        )
        if exists:
            raise StudentCreateError(
                "duplicate_email",
                f"Пользователь с email {email} уже существует",
            )

        # 2. Валидация психолога (если назначаем) — в той же сессии.
        psych_name = None
        if psychologist_id is not None:
            psy = (
                db.query(User)
                .filter(
                    User.id == psychologist_id, User.deleted_at.is_(None)
                )
                .first()
            )
            if psy is None:
                raise StudentCreateError(
                    "psychologist_not_found",
                    f"Психолог id={psychologist_id} не найден",
                )
            has_role = (
                db.query(UserRole.user_id)
                .join(Role, Role.id == UserRole.role_id)
                .filter(
                    UserRole.user_id == psychologist_id,
                    Role.name == "psychologist",
                )
                .first()
            )
            if not has_role:
                raise StudentCreateError(
                    "not_a_psychologist",
                    f"Пользователь id={psychologist_id} не является психологом",
                )
            if not psy.is_active:
                raise StudentCreateError(
                    "psychologist_inactive",
                    f"Психолог id={psychologist_id} неактивен",
                )
            psych_name = psy.full_name or psy.email

        # 3. Обязательные consent-политики обязаны существовать (seed data).
        consent_ids: list[int] = []
        for policy_type in required_consent_types:
            consent = (
                db.query(Consent)
                .filter(Consent.policy_type == policy_type)
                .order_by(Consent.version.desc())
                .first()
            )
            if consent is None:
                raise StudentCreateError(
                    "consent_policy_missing",
                    f"Политика '{policy_type}' не найдена в БД",
                )
            consent_ids.append(consent.id)

        student_role = (
            db.query(Role).filter(Role.name == "student").first()
        )
        if student_role is None:
            raise StudentCreateError(
                "student_role_missing", "Роль 'student' не найдена в БД"
            )

        # 4. User + роль student.
        new_user = User(
            email=email_norm,
            full_name=full_name.strip(),
            password_hash=password_hash,
            phone=(phone.strip() or None) if phone else None,
            is_active=True,
        )
        db.add(new_user)
        db.flush()  # нужен new_user.id для ролей/consents/engagement

        db.add(UserRole(user_id=new_user.id, role_id=student_role.id))

        # 5. Личное согласие субъекта (получено очно).
        for cid in consent_ids:
            db.add(ConsentRecord(
                user_id=new_user.id,
                consent_id=cid,
                accepted=True,
                ip_address=ip,
                user_agent=user_agent,
            ))

        # 6. (опц.) активная связь студент↔психолог.
        engagement_dict = None
        engagement_id = None
        if psychologist_id is not None:
            engagement = TherapyEngagement(
                client_id=new_user.id,
                psychologist_id=psychologist_id,
                status="active",
                primary_concern=primary_concern,
                started_at=now,
                ended_at=None,
            )
            db.add(engagement)
            db.flush()
            engagement_id = engagement.id
            engagement_dict = {
                "id":              engagement.id,
                "status":          engagement.status,
                "primary_concern": engagement.primary_concern,
                "started_at":      engagement.started_at,
                "ended_at":        engagement.ended_at,
                "transfer_reason": engagement.transfer_reason,
                "client_id":       engagement.client_id,
                "psychologist_id": engagement.psychologist_id,
            }

        # 7. Аудит — обязателен в ЭТОЙ транзакции через единый facade (db=db;
        # facade только db.add, без commit/rollback/close). metadata пуста,
        # description не пишется, ПДн/имена/пароль не логируются. Сбой аудита
        # не проглатывается — откатывает всю запись. actor уже int (route _actor).
        record_event(
            event="supervisor_create_student",
            actor=Actor.user(int(actor_id), actor_role),
            target=Target("user", new_user.id),
            outcome=Outcome.SUCCESS,
            context=None,
            db=db,
        )
        if engagement_id is not None:
            record_event(
                event="supervisor_assign_psychologist",
                actor=Actor.user(int(actor_id), actor_role),
                target=Target("therapy_engagement", engagement_id),
                outcome=Outcome.SUCCESS,
                context=None,
                db=db,
            )

        db.commit()
        db.refresh(new_user)

        return {
            "id":                new_user.id,
            "uuid":              str(new_user.uuid),
            "email":             new_user.email,
            "full_name":         new_user.full_name,
            "role":              "student",
            "is_active":         new_user.is_active,
            "created_at":        new_user.created_at,
            "engagement":        engagement_dict,
            "psychologist_name": psych_name,
        }
