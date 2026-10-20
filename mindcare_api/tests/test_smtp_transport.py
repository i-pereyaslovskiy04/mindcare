"""
SMTP transport security tests (Stage 18d).

Covers:
  - Transport selection: SMTP vs SMTP_SSL
  - STARTTLS usage
  - SSL context security (no CERT_NONE, no check_hostname=False)
  - Conflict detection (SMTP_TLS + SMTP_SSL both True)
  - Plain SMTP warning
  - No set_debuglevel(1) in runtime path
  - Dev mode does not invoke SMTP at all

No real SMTP connections are made.
"""

import logging
import ssl
import pytest
from unittest.mock import MagicMock, patch


# ─── Patch targets ────────────────────────────────────────────────────────────

_SMTP      = "app.services._smtp.smtplib.SMTP"
_SMTP_SSL  = "app.services._smtp.smtplib.SMTP_SSL"
_SSL_CTX   = "app.services._smtp.ssl.create_default_context"
_SETTINGS  = "app.services._smtp.settings"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _mock_settings(*, tls=True, ssl_=False, user="u@ex.com",
                   password="secret", mode="smtp"):
    s = MagicMock()
    s.EMAIL_MODE    = mode
    s.SMTP_HOST     = "smtp.example.com"
    s.SMTP_PORT     = 587
    s.SMTP_USER     = user
    s.SMTP_PASSWORD = password
    s.SMTP_FROM     = "noreply@example.com"
    s.SMTP_TLS      = tls
    s.SMTP_SSL      = ssl_
    return s


def _make_conn():
    """Context-manager mock that returns itself from __enter__, like real SMTP."""
    m = MagicMock()
    m.__enter__ = MagicMock(return_value=m)
    m.__exit__  = MagicMock(return_value=False)
    return m


# ─── Import under test ────────────────────────────────────────────────────────

from app.services._smtp import _send_smtp, send_email  # noqa: E402


# ─── 1. STARTTLS (SMTP_TLS=True, SMTP_SSL=False) ─────────────────────────────

class TestStartTLS:
    def test_uses_smtp_not_smtp_ssl(self):
        conn = _make_conn()
        with patch(_SETTINGS, _mock_settings(tls=True, ssl_=False)), \
             patch(_SMTP, return_value=conn) as mock_plain, \
             patch(_SMTP_SSL) as mock_ssl, \
             patch(_SSL_CTX):
            _send_smtp("to@x.com", "S", "B", None)
        mock_plain.assert_called_once()
        mock_ssl.assert_not_called()

    def test_starttls_called(self):
        conn = _make_conn()
        mock_ctx = MagicMock()
        with patch(_SETTINGS, _mock_settings(tls=True, ssl_=False)), \
             patch(_SMTP, return_value=conn), \
             patch(_SSL_CTX, return_value=mock_ctx):
            _send_smtp("to@x.com", "S", "B", None)
        conn.starttls.assert_called_once_with(context=mock_ctx)

    def test_ssl_context_not_mutated(self):
        """SSL context must not have check_hostname or verify_mode disabled."""
        conn = _make_conn()
        real_ctx = ssl.create_default_context()
        with patch(_SETTINGS, _mock_settings(tls=True, ssl_=False)), \
             patch(_SMTP, return_value=conn), \
             patch(_SSL_CTX, return_value=real_ctx):
            _send_smtp("to@x.com", "S", "B", None)
        assert real_ctx.verify_mode == ssl.CERT_REQUIRED
        assert real_ctx.check_hostname is True

    def test_login_called_when_user_set(self):
        conn = _make_conn()
        s = _mock_settings(tls=True, ssl_=False, user="u@ex.com", password="pw")
        with patch(_SETTINGS, s), patch(_SMTP, return_value=conn), patch(_SSL_CTX):
            _send_smtp("to@x.com", "S", "B", None)
        conn.login.assert_called_once_with("u@ex.com", "pw")

    def test_login_skipped_when_no_user(self):
        conn = _make_conn()
        s = _mock_settings(tls=True, ssl_=False, user="")
        with patch(_SETTINGS, s), patch(_SMTP, return_value=conn), patch(_SSL_CTX):
            _send_smtp("to@x.com", "S", "B", None)
        conn.login.assert_not_called()

    def test_send_message_called(self):
        conn = _make_conn()
        with patch(_SETTINGS, _mock_settings(tls=True, ssl_=False)), \
             patch(_SMTP, return_value=conn), \
             patch(_SSL_CTX):
            _send_smtp("to@x.com", "S", "B", None)
        conn.send_message.assert_called_once()


# ─── 2. Implicit SSL (SMTP_TLS=False, SMTP_SSL=True) ─────────────────────────

class TestImplicitSSL:
    def test_uses_smtp_ssl_not_plain(self):
        conn = _make_conn()
        with patch(_SETTINGS, _mock_settings(tls=False, ssl_=True)), \
             patch(_SMTP_SSL, return_value=conn) as mock_ssl, \
             patch(_SMTP) as mock_plain, \
             patch(_SSL_CTX):
            _send_smtp("to@x.com", "S", "B", None)
        mock_ssl.assert_called_once()
        mock_plain.assert_not_called()

    def test_smtp_ssl_receives_default_context(self):
        conn = _make_conn()
        mock_ctx = MagicMock()
        with patch(_SETTINGS, _mock_settings(tls=False, ssl_=True)), \
             patch(_SMTP_SSL, return_value=conn) as mock_ssl_cls, \
             patch(_SSL_CTX, return_value=mock_ctx):
            _send_smtp("to@x.com", "S", "B", None)
        _, kwargs = mock_ssl_cls.call_args
        assert kwargs.get("context") is mock_ctx

    def test_starttls_not_called(self):
        conn = _make_conn()
        with patch(_SETTINGS, _mock_settings(tls=False, ssl_=True)), \
             patch(_SMTP_SSL, return_value=conn), \
             patch(_SSL_CTX):
            _send_smtp("to@x.com", "S", "B", None)
        conn.starttls.assert_not_called()

    def test_send_message_called(self):
        conn = _make_conn()
        with patch(_SETTINGS, _mock_settings(tls=False, ssl_=True)), \
             patch(_SMTP_SSL, return_value=conn), \
             patch(_SSL_CTX):
            _send_smtp("to@x.com", "S", "B", None)
        conn.send_message.assert_called_once()


# ─── 3. Conflict: SMTP_TLS=True and SMTP_SSL=True ────────────────────────────

class TestConflict:
    def test_raises_runtime_error(self):
        with patch(_SETTINGS, _mock_settings(tls=True, ssl_=True)):
            with pytest.raises(RuntimeError, match="cannot both be enabled"):
                _send_smtp("to@x.com", "S", "B", None)

    def test_no_smtp_connection_attempted(self):
        with patch(_SETTINGS, _mock_settings(tls=True, ssl_=True)), \
             patch(_SMTP) as mock_plain, \
             patch(_SMTP_SSL) as mock_ssl:
            with pytest.raises(RuntimeError):
                _send_smtp("to@x.com", "S", "B", None)
        mock_plain.assert_not_called()
        mock_ssl.assert_not_called()


# ─── 4. Plain SMTP (SMTP_TLS=False, SMTP_SSL=False) ──────────────────────────

class TestPlainSMTP:
    def test_uses_plain_smtp(self):
        conn = _make_conn()
        with patch(_SETTINGS, _mock_settings(tls=False, ssl_=False)), \
             patch(_SMTP, return_value=conn) as mock_plain, \
             patch(_SMTP_SSL) as mock_ssl:
            _send_smtp("to@x.com", "S", "B", None)
        mock_plain.assert_called_once()
        mock_ssl.assert_not_called()

    def test_starttls_not_called(self):
        conn = _make_conn()
        with patch(_SETTINGS, _mock_settings(tls=False, ssl_=False)), \
             patch(_SMTP, return_value=conn):
            _send_smtp("to@x.com", "S", "B", None)
        conn.starttls.assert_not_called()

    def test_warning_logged(self, caplog):
        conn = _make_conn()
        with caplog.at_level(logging.WARNING), \
             patch(_SETTINGS, _mock_settings(tls=False, ssl_=False)), \
             patch(_SMTP, return_value=conn):
            _send_smtp("to@x.com", "S", "B", None)
        assert any("without TLS" in r.message for r in caplog.records)

    def test_send_message_called(self):
        conn = _make_conn()
        with patch(_SETTINGS, _mock_settings(tls=False, ssl_=False)), \
             patch(_SMTP, return_value=conn):
            _send_smtp("to@x.com", "S", "B", None)
        conn.send_message.assert_called_once()


# ─── 5. No set_debuglevel in runtime path ────────────────────────────────────

class TestNoDebugLevel:
    def test_not_called_starttls(self):
        conn = _make_conn()
        with patch(_SETTINGS, _mock_settings(tls=True, ssl_=False)), \
             patch(_SMTP, return_value=conn), \
             patch(_SSL_CTX):
            _send_smtp("to@x.com", "S", "B", None)
        conn.set_debuglevel.assert_not_called()

    def test_not_called_ssl(self):
        conn = _make_conn()
        with patch(_SETTINGS, _mock_settings(tls=False, ssl_=True)), \
             patch(_SMTP_SSL, return_value=conn), \
             patch(_SSL_CTX):
            _send_smtp("to@x.com", "S", "B", None)
        conn.set_debuglevel.assert_not_called()

    def test_not_called_plain(self):
        conn = _make_conn()
        with patch(_SETTINGS, _mock_settings(tls=False, ssl_=False)), \
             patch(_SMTP, return_value=conn):
            _send_smtp("to@x.com", "S", "B", None)
        conn.set_debuglevel.assert_not_called()


# ─── 6. Dev mode does not use SMTP ───────────────────────────────────────────

class TestDevMode:
    def test_smtp_not_called(self):
        with patch(_SETTINGS, _mock_settings(mode="dev")), \
             patch(_SMTP) as mock_plain, \
             patch(_SMTP_SSL) as mock_ssl:
            send_email("to@x.com", "S", "B", None)
        mock_plain.assert_not_called()
        mock_ssl.assert_not_called()

    def test_prints_to_stdout(self, capsys):
        with patch(_SETTINGS, _mock_settings(mode="dev")):
            send_email("to@x.com", "Subject-dev", "Body", None)
        out = capsys.readouterr().out
        assert "to@x.com" in out
        assert "Subject-dev" in out
