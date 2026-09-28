"""
Test-only ускорение bcrypt (tests/conftest.py): стоимость снижена до 4 rounds.

Проверяем, что:
  - хеши приложения в тестах создаются с test-стоимостью (иначе набор снова
    станет ~1 час);
  - семантика hash/verify не изменилась;
  - проверка ранее созданных production-хешей (12 rounds) продолжает работать.
"""
import bcrypt

from app.auth.service import _hash, _verify

TEST_ROUNDS = 4

# Фиксированный production-хеш (12 rounds) пароля "SecurePass42!".
PROD_COST_HASH = "$2b$12$JaiPi1HFvW8WbQXAasFRb.q/aJeQZf5gph9wKY9XGckZQvIE5/YLe"


def _cost(hashed: str) -> int:
    # Формат bcrypt: $2b$<cost>$<salt+hash>
    return int(hashed.split("$")[2])


def test_app_hash_uses_test_rounds():
    assert _cost(_hash("SecurePass42!")) == TEST_ROUNDS


def test_gensalt_ignores_explicit_rounds_in_tests():
    assert bcrypt.gensalt(12).startswith(b"$2b$04$")


def test_hash_verify_semantics_unchanged():
    hashed = _hash("SecurePass42!")
    assert _verify("SecurePass42!", hashed)
    assert not _verify("WrongPass42!", hashed)


def test_production_cost_hash_still_verifies():
    assert _cost(PROD_COST_HASH) == 12
    assert _verify("SecurePass42!", PROD_COST_HASH)
    assert not _verify("WrongPass42!", PROD_COST_HASH)
