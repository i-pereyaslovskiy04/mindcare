"""
User.email нормализуется на уровне ORM-модели (@validates) — без БД.

Страховка для будущих путей записи, которые забудут normalize_email():
иначе ненормализованный email не нашёлся бы при логине (поиск — точное
сравнение с normalize_email(input)). DB-уровень (CHECK) — в
tests/integration/test_users_email_normalized_check.py.
"""
from app.db.models import User


def test_constructor_normalizes_email():
    user = User(email="  Ivan.Petrov@DonNU.ru ")
    assert user.email == "ivan.petrov@donnu.ru"


def test_assignment_normalizes_email():
    user = User(email="a@donnu.ru")
    user.email = "NEW.Address@DONNU.RU\t"
    assert user.email == "new.address@donnu.ru"


def test_already_normalized_email_unchanged():
    assert User(email="ivan@donnu.ru").email == "ivan@donnu.ru"


def test_none_is_left_for_not_null_constraint():
    assert User(email=None).email is None


def test_db_check_constraint_declared_on_model():
    names = {c.name for c in User.__table__.constraints}
    assert "ck_users_email_normalized" in names
