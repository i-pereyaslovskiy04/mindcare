"""
Tests for app/core/encryption.py.

Covers:
  - encrypt/decrypt roundtrip (including Cyrillic text)
  - enc:v1: prefix is always present in ciphertext
  - ciphertext does not contain plaintext
  - is_encrypted() for encrypted/plain/None values
  - decrypt raises ValueError on plaintext (no fallback)
  - encrypt raises RuntimeError when DATA_ENCRYPTION_KEY is not set
  - decrypt raises ValueError when wrong key used (wrong-key / corrupted token)

Important: encryption module keeps a lazy _fernet cache. Each test that needs
a specific key must reset the cache (set _fernet = None) so _get_fernet() picks
up the monkeypatched settings value on the next call.
"""

import pytest
from cryptography.fernet import Fernet

import app.core.encryption as enc_mod
from app.core.encryption import (
    ENCRYPTION_PREFIX,
    decrypt_text,
    encrypt_text,
    is_encrypted,
)


@pytest.fixture(autouse=True)
def reset_fernet_cache():
    """Reset the lazy _fernet cache before every test."""
    enc_mod._fernet = None
    yield
    enc_mod._fernet = None


@pytest.fixture()
def valid_key(monkeypatch) -> str:
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(enc_mod.settings, "DATA_ENCRYPTION_KEY", key)
    return key


# ──────────────────────────────────────────────────────────────────────────────
# 2.1  Roundtrip
# ──────────────────────────────────────────────────────────────────────────────

class TestRoundtrip:
    PLAINTEXT_ASCII    = "Test note Stage 13d encryption check"
    PLAINTEXT_CYRILLIC = "Проверка шифрования MindCare — тревога, сессия, заметка."

    def test_ascii_roundtrip(self, valid_key):
        ct = encrypt_text(self.PLAINTEXT_ASCII)
        assert decrypt_text(ct) == self.PLAINTEXT_ASCII

    def test_cyrillic_roundtrip(self, valid_key):
        ct = encrypt_text(self.PLAINTEXT_CYRILLIC)
        assert decrypt_text(ct) == self.PLAINTEXT_CYRILLIC

    def test_ciphertext_has_enc_prefix(self, valid_key):
        ct = encrypt_text(self.PLAINTEXT_ASCII)
        assert ct.startswith(ENCRYPTION_PREFIX)

    def test_ciphertext_does_not_contain_plaintext(self, valid_key):
        ct = encrypt_text(self.PLAINTEXT_ASCII)
        assert self.PLAINTEXT_ASCII not in ct

    def test_ciphertext_does_not_contain_cyrillic_plaintext(self, valid_key):
        ct = encrypt_text(self.PLAINTEXT_CYRILLIC)
        # The Cyrillic string should not appear literally in the ciphertext
        assert "тревога" not in ct

    def test_empty_string_encrypts_and_decrypts(self, valid_key):
        # Empty string is valid plaintext (min_length validation is in schema, not here)
        ct = encrypt_text("")
        assert decrypt_text(ct) == ""

    def test_encrypt_is_nondeterministic(self, valid_key):
        # Fernet includes a timestamp + random IV, so two encryptions differ
        ct1 = encrypt_text(self.PLAINTEXT_ASCII)
        ct2 = encrypt_text(self.PLAINTEXT_ASCII)
        assert ct1 != ct2


# ──────────────────────────────────────────────────────────────────────────────
# 2.2  is_encrypted
# ──────────────────────────────────────────────────────────────────────────────

class TestIsEncrypted:
    def test_encrypted_value_returns_true(self, valid_key):
        ct = encrypt_text("some text")
        assert is_encrypted(ct) is True

    def test_plaintext_returns_false(self):
        assert is_encrypted("plaintext string") is False

    def test_none_returns_false(self):
        assert is_encrypted(None) is False

    def test_empty_string_returns_false(self):
        assert is_encrypted("") is False

    def test_partial_prefix_returns_false(self):
        assert is_encrypted("enc:v1") is False   # no trailing colon

    def test_full_prefix_only_returns_true(self):
        # A bare prefix with no token still reports as "looks encrypted"
        # (actual decrypt would fail — that's separate)
        assert is_encrypted("enc:v1:") is True


# ──────────────────────────────────────────────────────────────────────────────
# 2.3  Plaintext fallback отсутствует
# ──────────────────────────────────────────────────────────────────────────────

class TestNoPlaintextFallback:
    def test_decrypt_plaintext_raises_valueerror(self, valid_key):
        with pytest.raises(ValueError, match="not encrypted"):
            decrypt_text("this is plaintext")

    def test_decrypt_empty_raises_valueerror(self, valid_key):
        with pytest.raises(ValueError):
            decrypt_text("")

    def test_decrypt_none_raises_valueerror(self, valid_key):
        with pytest.raises(ValueError):
            decrypt_text(None)


# ──────────────────────────────────────────────────────────────────────────────
# 2.4  Missing key
# ──────────────────────────────────────────────────────────────────────────────

class TestMissingKey:
    def test_encrypt_raises_runtimeerror_when_no_key(self, monkeypatch):
        monkeypatch.setattr(enc_mod.settings, "DATA_ENCRYPTION_KEY", None)
        with pytest.raises(RuntimeError, match="DATA_ENCRYPTION_KEY"):
            encrypt_text("some text")

    def test_decrypt_raises_runtimeerror_when_no_key(self, monkeypatch):
        monkeypatch.setattr(enc_mod.settings, "DATA_ENCRYPTION_KEY", None)
        with pytest.raises(RuntimeError, match="DATA_ENCRYPTION_KEY"):
            decrypt_text(f"{ENCRYPTION_PREFIX}sometoken")


# ──────────────────────────────────────────────────────────────────────────────
# 2.5  Wrong key / corrupted token
# ──────────────────────────────────────────────────────────────────────────────

class TestWrongKeyOrCorrupted:
    def test_wrong_key_raises_valueerror(self, monkeypatch):
        key1 = Fernet.generate_key().decode()
        key2 = Fernet.generate_key().decode()

        # Encrypt with key1
        monkeypatch.setattr(enc_mod.settings, "DATA_ENCRYPTION_KEY", key1)
        enc_mod._fernet = None
        ciphertext = encrypt_text("sensitive note")

        # Reset cache and switch to key2
        enc_mod._fernet = None
        monkeypatch.setattr(enc_mod.settings, "DATA_ENCRYPTION_KEY", key2)

        with pytest.raises(ValueError, match="invalid key or corrupted"):
            decrypt_text(ciphertext)

    def test_corrupted_token_raises_valueerror(self, valid_key):
        ct = encrypt_text("note text")
        corrupted = ct[:-5] + "XXXXX"
        with pytest.raises(ValueError, match="invalid key or corrupted"):
            decrypt_text(corrupted)

    def test_truncated_token_raises_valueerror(self, valid_key):
        ct = encrypt_text("note text")
        truncated = ct[:len(ENCRYPTION_PREFIX) + 10]
        with pytest.raises(ValueError, match="invalid key or corrupted"):
            decrypt_text(truncated)
