"""
Создание административного пользователя.

Использование (из mindcare_api/):
    python scripts/create_admin.py

Скрипт интерактивно запросит email, имя и пароль, создаст:
- запись в users с ролью admin
- запись в user_roles
- запись в user_legal_basis_records (документированное основание, ФЗ-152)

ВАЖНО: скрипт НЕ создаёт consent_records — это личное согласие субъекта,
которое нельзя записывать за пользователя. Основание создания учётной
записи фиксируется как legal basis (basis_type=bootstrap).

Если пользователь с таким email уже существует — скрипт спросит, добавить
ли роль admin к существующему юзеру (для случаев когда обычный студент
становится админом).
"""
print("[DEBUG] Скрипт стартовал")
import sys
import getpass
from pathlib import Path

# Делаем app/ импортируемым из scripts/
# scripts/create_admin.py живёт в scripts/, app/ живёт рядом.
# Поэтому добавляем родителя scripts/ (то есть mindcare_api/) в sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.auth import storage, service
from app.core.normalization import normalize_email
from app.db.session import SessionLocal
from app.db.models import UserRole, Role, UserLegalBasisRecord


def prompt_user_data() -> dict:
    """Запрашивает у разработчика данные нового админа."""
    print("\n=== Создание администратора ===\n")

    email = normalize_email(input("Email: "))
    if not email or "@" not in email:
        print("[ERROR] Невалидный email")
        sys.exit(1)

    name = input("ФИО: ").strip()
    if len(name) < 2:
        print("[ERROR] ФИО должно быть минимум 2 символа")
        sys.exit(1)

    # getpass прячет пароль при вводе (не показывает в терминале)
    password = getpass.getpass("Пароль (минимум 8 символов): ")
    if len(password) < 8:
        print("[ERROR] Пароль слишком короткий")
        sys.exit(1)

    password_confirm = getpass.getpass("Повторите пароль: ")
    if password != password_confirm:
        print("[ERROR] Пароли не совпадают")
        sys.exit(1)

    return {"email": email, "name": name, "password": password}


def add_admin_role_to_existing_user(email: str) -> bool:
    """Проверяет существует ли юзер. Если да — спрашивает добавить ли роль admin."""
    user = storage.find_user_by_email(email)
    if not user:
        return False

    print(f"\n[!] Пользователь с email {email} уже существует:")
    print(f"    ID:   {user['id']}")
    print(f"    Имя:  {user['name']}")
    print(f"    Роль: {user['role']}")

    if user["role"] == "admin":
        print("\n[INFO] Пользователь уже админ. Ничего делать не нужно.")
        sys.exit(0)

    answer = input("\nДобавить роль admin этому пользователю? [y/N]: ").strip().lower()
    if answer != "y":
        print("Отменено.")
        sys.exit(0)

    with SessionLocal() as db:
        admin_role = db.query(Role).filter(Role.name == "admin").first()
        if not admin_role:
            print("[ERROR] Роль 'admin' не найдена в БД. Применены ли seed-миграции?")
            sys.exit(1)

        # Проверка нет ли уже такой связи (на случай гонки)
        existing = (
            db.query(UserRole)
            .filter(UserRole.user_id == int(user["id"]),
                    UserRole.role_id == admin_role.id)
            .first()
        )
        if existing:
            print("[INFO] Роль уже назначена.")
            sys.exit(0)

        db.add(UserRole(user_id=int(user["id"]), role_id=admin_role.id))
        # Роль admin — это смена основания обработки ПДн (студент → сотрудник).
        # Фиксируем legal basis record в той же транзакции.
        db.add(UserLegalBasisRecord(
            user_id=int(user["id"]),
            basis_type="role_change",
            basis_source="bootstrap_script",
            confirmed_by_user_id=None,
            user_agent="bootstrap-script",
            comment="Admin role granted to existing user via bootstrap script",
        ))
        db.commit()

    # Гарантируем неявную роль student и этому staff-аккаунту (идемпотентно).
    ensure_student_role(int(user["id"]))

    print(f"[OK] Роль admin добавлена пользователю {email}")
    return True


def save_legal_basis_for_user(user_id: int) -> None:
    """
    Записывает документированное основание для bootstrap-админа.

    НЕ создаёт consent_records: личное согласие нельзя записывать
    за пользователя. Основание учётной записи bootstrap-админа —
    служебное (развёртывание системы).
    """
    with SessionLocal() as db:
        db.add(UserLegalBasisRecord(
            user_id=user_id,
            basis_type="bootstrap",
            basis_source="bootstrap_script",
            confirmed_by_user_id=None,   # bootstrap, актора-админа ещё нет
            ip_address=None,             # не было HTTP-запроса
            user_agent="bootstrap-script",
            comment="Bootstrap admin account created during deployment/setup",
        ))
        db.commit()


def ensure_student_role(user_id: int) -> None:
    """
    Идемпотентно выдаёт пользователю роль student (не дублирует, реактивирует
    просроченную). Продуктовое решение: каждый staff-пользователь неявно
    получает роль student для доступа к кабинету студента — так же, как это
    делает users.storage.create_user для admin-created staff и backfill-скрипт
    для существующих. Иначе новый bootstrap-админ остался бы без student, а
    backfill одноразовый и повторно не запускается. Legal basis для student НЕ
    пишется (это не staff-роль).
    """
    with SessionLocal() as db:
        student_role = db.query(Role).filter(Role.name == "student").first()
        if not student_role:
            print("[WARN] Роль 'student' не найдена — пропускаю выдачу student.")
            return
        existing = (
            db.query(UserRole)
            .filter(UserRole.user_id == user_id,
                    UserRole.role_id == student_role.id)
            .first()
        )
        if existing is not None:
            existing.expires_at = None
        else:
            db.add(UserRole(user_id=user_id, role_id=student_role.id))
        db.commit()


def create_new_admin(data: dict) -> None:
    """Создаёт нового админа с нуля."""
    user = storage.save_user({
        "name":            data["name"],
        "email":           data["email"],
        "hashed_password": service._hash(data["password"]),
        "role":            "admin",
    })

    save_legal_basis_for_user(int(user["id"]))
    ensure_student_role(int(user["id"]))

    print(f"\n[OK] Администратор создан:")
    print(f"     ID:    {user['id']}")
    print(f"     Email: {user['email']}")
    print(f"     Роль:  {user['role']}")


def main():
    data = prompt_user_data()

    # Если юзер с таким email уже есть — обработали и вышли
    if add_admin_role_to_existing_user(data["email"]):
        return

    # Иначе создаём нового
    create_new_admin(data)


if __name__ == "__main__":
    main()