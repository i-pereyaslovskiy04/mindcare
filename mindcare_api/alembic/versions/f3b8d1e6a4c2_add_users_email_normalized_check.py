"""add_users_email_normalized_check

users.email хранится только в нормализованной форме: CHECK
ck_users_email_normalized (email = lower(trim(email))).

Зачем: поиск пользователя (login, password reset, admin/supervisor create)
делает точное сравнение User.email == normalize_email(input). Ненормализованная
строка в БД (например, "Ivan@donnu.ru") не нашлась бы — аккаунт существует,
но войти/сбросить пароль нельзя. ux_users_email_normalized защищает только от
дублей, но не от такой записи.

ORM-путь нормализует сам (@validates в app/db/models/auth.py User); этот CHECK
ловит запись в обход ORM (raw SQL, bulk update, ручной psql).

Pre-check: при наличии ненормализованных email миграция падает с понятной
ошибкой ДО DDL — данные нужно исправить вручную (возможны коллизии с уже
существующими нормализованными адресами, автоматически их не сливаем).

Revision ID: f3b8d1e6a4c2
Revises: a1c2e3f4b5d6
Create Date: 2026-09-28
"""
from alembic import op
import sqlalchemy as sa


revision = "f3b8d1e6a4c2"
down_revision = "a1c2e3f4b5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_context().connection
    bad = conn.execute(sa.text(
        "SELECT COUNT(*) FROM users WHERE email <> lower(trim(email))"
    )).scalar()
    if bad:
        # Без самих адресов (ПДн) — только количество и запрос для поиска.
        raise RuntimeError(
            f"Cannot add ck_users_email_normalized: {bad} user(s) have "
            "non-normalized email. Find them with: SELECT id FROM users "
            "WHERE email <> lower(trim(email)); fix manually, then re-run."
        )

    op.create_check_constraint(
        "ck_users_email_normalized",
        "users",
        "email = lower(trim(email))",
    )


def downgrade() -> None:
    op.drop_constraint("ck_users_email_normalized", "users", type_="check")
