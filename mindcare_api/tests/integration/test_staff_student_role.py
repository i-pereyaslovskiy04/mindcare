"""
Integration (isolated test DB): роль student для staff + изоляция.

Покрывает продуктовое решение «staff неявно получает роль student»:
  1. create_user(staff) выдаёт роль student в том же коммите;
  2. supervisor.get_students НЕ возвращает staff с ролью student, но возвращает
     чистого студента;
  3. users.find_users(role='student') исключает staff, но включает чистого
     студента.

Работаем со storage напрямую (каждая функция открывает собственную SessionLocal);
fixture `client` нужен только чтобы отработал lifespan-seed (роли в справочнике).
Все аккаунты — на integ_-префиксе, чтобы их удалил autouse cleanup_test_records.
"""

import uuid

import bcrypt

from app.auth.storage import get_active_role_names
from app.db.session import SessionLocal
from app.db.models import Role, User, UserRole
from app.users import storage as users_storage
from app.supervisor import storage as supervisor_storage


def _integ_email() -> str:
    return f"integ_{uuid.uuid4().hex[:12]}@donnu.ru"


def _password_hash() -> str:
    return bcrypt.hashpw(b"Passw0rd!123", bcrypt.gensalt()).decode()


def _make_admin_actor() -> int:
    """Прямой INSERT admin-актора для confirmed_by_user_id create_user."""
    with SessionLocal() as db:
        admin_role = db.query(Role).filter(Role.name == "admin").first()
        user = User(
            email=_integ_email(),
            full_name="Integ Actor",
            password_hash=_password_hash(),
            is_active=True,
        )
        db.add(user)
        db.flush()
        db.add(UserRole(user_id=user.id, role_id=admin_role.id))
        db.commit()
        return user.id


def _make_pure_student() -> int:
    """Прямой INSERT реального студента (только роль student)."""
    with SessionLocal() as db:
        student_role = db.query(Role).filter(Role.name == "student").first()
        user = User(
            email=_integ_email(),
            full_name="Integ Pure Student",
            password_hash=_password_hash(),
            is_active=True,
        )
        db.add(user)
        db.flush()
        db.add(UserRole(user_id=user.id, role_id=student_role.id))
        db.commit()
        return user.id


def _role_names(user_id: int) -> set[str]:
    with SessionLocal() as db:
        return set(get_active_role_names(db, user_id))


def test_create_user_grants_student_role(client):
    actor_id = _make_admin_actor()
    result = users_storage.create_user(
        email=_integ_email(),
        full_name="Integ Psychologist",
        password_hash=_password_hash(),
        roles=["psychologist"],
        basis_type="service_duty",
        basis_reference="Приказ № 1",
        confirmed_by_user_id=actor_id,
        actor_role="admin",
    )

    roles = _role_names(result["id"])
    assert "student" in roles, "staff-пользователь должен получить роль student"
    assert "psychologist" in roles
    # student — низший приоритет: primary остаётся staff-ролью.
    assert result["role"] == "psychologist"


def test_get_students_excludes_staff(client):
    actor_id = _make_admin_actor()
    staff = users_storage.create_user(
        email=_integ_email(),
        full_name="Integ Supervisor",
        password_hash=_password_hash(),
        roles=["supervisor"],
        basis_type="service_duty",
        basis_reference="Приказ № 2",
        confirmed_by_user_id=actor_id,
        actor_role="admin",
    )
    student_id = _make_pure_student()

    items, _total = supervisor_storage.get_students(page=1, size=100)
    ids = {it["id"] for it in items}

    assert student_id in ids, "реальный студент должен быть в списке"
    assert staff["id"] not in ids, "staff с ролью student не должен попадать в список"


def test_find_users_role_student_excludes_staff(client):
    actor_id = _make_admin_actor()
    staff = users_storage.create_user(
        email=_integ_email(),
        full_name="Integ Admin2",
        password_hash=_password_hash(),
        roles=["admin"],
        basis_type="service_duty",
        basis_reference="Приказ № 3",
        confirmed_by_user_id=actor_id,
        actor_role="admin",
    )
    student_id = _make_pure_student()

    items, _total = users_storage.find_users(page=1, size=200, role="student")
    ids = {it["id"] for it in items}

    assert student_id in ids, "реальный студент должен проходить фильтр ?role=student"
    assert staff["id"] not in ids, "staff не должен проходить фильтр ?role=student"
