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

Существующие ненормализованные email приводятся к lower(trim(email)) ДО
добавления CHECK, чтобы миграция не останавливала деплой. Коллизий быть не
может: уникальный ux_users_email_normalized (e5a8f3c1d2b6) уже гарантирует,
что двух строк с одинаковым lower(trim(email)) нет. Для таких пользователей
это исправление, а не поломка: до него их логин не находил.
Изменение идёт мимо data_change_log (DDL-миграция); печатается только
количество строк, без адресов (ПДн).

Downgrade снимает только CHECK; нормализация данных необратима (и не нужна
к откату — приложение всегда работало с нормализованной формой).

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
    fixed = conn.execute(sa.text(
        "UPDATE users SET email = lower(trim(email)) "
        "WHERE email <> lower(trim(email))"
    )).rowcount
    if fixed:
        print(f"[INFO] f3b8d1e6a4c2: normalized email for {fixed} user(s)")

    op.create_check_constraint(
        "ck_users_email_normalized",
        "users",
        "email = lower(trim(email))",
    )


def downgrade() -> None:
    op.drop_constraint("ck_users_email_normalized", "users", type_="check")
