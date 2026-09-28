"""
users.email хранится только нормализованным (migration f3b8d1e6a4c2).

  - ORM-путь нормализует сам (@validates) — в БД попадает lower(trim(email));
  - запись в обход ORM (raw SQL INSERT/UPDATE) с ненормализованным email
    отклоняется CHECK ck_users_email_normalized и ничего не меняет.

Все email — с префиксом integ_ (после нормализации), их удаляет
autouse-фикстура cleanup_test_records.
"""
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db.models import User
from app.db.session import SessionLocal

CHECK_NAME = "ck_users_email_normalized"


def _local() -> str:
    return f"integ_{uuid.uuid4().hex[:12]}"


def _stored_email(user_id: int) -> str:
    with SessionLocal() as db:
        return db.execute(
            text("SELECT email FROM users WHERE id = :id"), {"id": user_id}
        ).scalar()


def _raw_insert(email: str) -> int:
    with SessionLocal() as db:
        user_id = db.execute(
            text(
                "INSERT INTO users (uuid, full_name, email, password_hash) "
                "VALUES (:u, 'Integration Raw', :e, 'x') RETURNING id"
            ),
            {"u": str(uuid.uuid4()), "e": email},
        ).scalar()
        db.commit()
        return user_id


def _violated_constraint(exc: IntegrityError):
    return getattr(getattr(exc.orig, "diag", None), "constraint_name", None)


def test_check_constraint_exists_in_db(client):
    with SessionLocal() as db:
        definition = db.execute(text(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conrelid = 'users'::regclass AND conname = :n"
        ), {"n": CHECK_NAME}).scalar()
    # PostgreSQL отдаёт каноническую форму:
    # CHECK (((email)::text = lower(TRIM(BOTH FROM email))))
    assert definition is not None
    assert "lower(TRIM(BOTH FROM email))" in definition


def test_orm_insert_stores_normalized_email(client):
    local = _local()
    with SessionLocal() as db:
        user = User(
            email=f"  {local.upper()}@DonNU.ru ",
            full_name="Integration ORM",
            password_hash="x",
        )
        db.add(user)
        db.commit()
        user_id = user.id
    assert _stored_email(user_id) == f"{local}@donnu.ru"


def test_orm_update_stores_normalized_email(client):
    local = _local()
    user_id = _raw_insert(f"{local}@donnu.ru")
    with SessionLocal() as db:
        user = db.get(User, user_id)
        user.email = f"{local.upper()}@EXAMPLE.COM "
        db.commit()
    assert _stored_email(user_id) == f"{local}@example.com"


@pytest.mark.parametrize("template", [
    "{local}@DonNU.ru",      # регистр
    " {local}@donnu.ru",     # пробел в начале
    "{local}@donnu.ru ",     # пробел в конце
])
def test_raw_insert_non_normalized_email_rejected(client, template):
    email = template.format(local=_local())
    with pytest.raises(IntegrityError) as exc_info:
        _raw_insert(email)
    assert _violated_constraint(exc_info.value) == CHECK_NAME
    with SessionLocal() as db:
        found = db.execute(
            text("SELECT COUNT(*) FROM users WHERE lower(trim(email)) = :e"),
            {"e": email.strip().lower()},
        ).scalar()
    assert found == 0


def test_raw_update_to_non_normalized_email_rejected(client):
    local = _local()
    user_id = _raw_insert(f"{local}@donnu.ru")
    with SessionLocal() as db:
        with pytest.raises(IntegrityError) as exc_info:
            db.execute(
                text("UPDATE users SET email = :e WHERE id = :id"),
                {"e": f"{local.upper()}@donnu.ru", "id": user_id},
            )
            db.commit()
        db.rollback()
    assert _violated_constraint(exc_info.value) == CHECK_NAME
    assert _stored_email(user_id) == f"{local}@donnu.ru"
