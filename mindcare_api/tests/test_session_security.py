"""
Unit tests for session token helpers (Stage 22b).

Covers app/auth/security.py:
  - generate_session_token format
  - hash_session_token determinism, length, output format
  - hash differs from input; different tokens -> different hashes

No HTTP, no DB.
"""

import hashlib
import re

from app.auth.security import generate_session_token, hash_session_token

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class TestGenerateSessionToken:
    def test_returns_urlsafe_token(self):
        token = generate_session_token()
        assert len(token) == 43
        assert re.fullmatch(r"[A-Za-z0-9_-]{43}", token)

    def test_tokens_unique(self):
        assert generate_session_token() != generate_session_token()


class TestHashSessionToken:
    def test_deterministic(self):
        token = "some-opaque-token-value"
        assert hash_session_token(token) == hash_session_token(token)

    def test_returns_64_hex_chars(self):
        h = hash_session_token(generate_session_token())
        assert _HEX64.fullmatch(h)

    def test_not_equal_to_input(self):
        token = generate_session_token()
        assert hash_session_token(token) != token

    def test_different_tokens_different_hashes(self):
        assert (
            hash_session_token(generate_session_token())
            != hash_session_token(generate_session_token())
        )

    def test_matches_sha256_hexdigest(self):
        """Хеш — ровно SHA-256 hexdigest без соли: lookup воспроизводим."""
        token = "fixed-token"
        expected = hashlib.sha256(token.encode("utf-8")).hexdigest()
        assert hash_session_token(token) == expected

    def test_raw_token_never_looks_like_hash(self):
        """
        Raw token (43 urlsafe chars) и hash (64 hex chars) различимы по длине —
        это используется в будущем maintenance-cleanup старых строк.
        """
        token = generate_session_token()
        assert len(token) != 64
        assert len(hash_session_token(token)) == 64
