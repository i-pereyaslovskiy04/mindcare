from app.core.security import hash_password

# Хардкод пользователей. Ключ — email.
USERS: dict[str, dict] = {
    "patient@test.com": {
        "id": 1,
        "email": "patient@test.com",
        "password_hash": hash_password("patient123"),
        "role": "patient",
        "name": "Иван Петров",
    },
    "psychologist@test.com": {
        "id": 2,
        "email": "psychologist@test.com",
        "password_hash": hash_password("psycho123"),
        "role": "psychologist",
        "name": "Мария Иванова",
        "specialization": "Когнитивно-поведенческая терапия",
    },
    "admin@test.com": {
        "id": 3,
        "email": "admin@test.com",
        "password_hash": hash_password("admin123"),
        "role": "admin",
        "name": "Администратор",
    },
}


def get_user_by_email(email: str) -> dict | None:
    return USERS.get(email)


def get_user_by_id(user_id: int) -> dict | None:
    return next((u for u in USERS.values() if u["id"] == user_id), None)


def create_user(email: str, password: str, name: str, role: str = "patient") -> dict:
    if email in USERS:
        raise ValueError("Пользователь с таким email уже существует")
    new_id = max(u["id"] for u in USERS.values()) + 1
    user = {
        "id": new_id,
        "email": email,
        "password_hash": hash_password(password),
        "role": role,
        "name": name,
    }
    USERS[email] = user
    return user
