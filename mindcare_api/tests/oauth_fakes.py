"""
FakeProvider для тестов social login core (Stage Social Auth 2B).

Не тест-модуль (имя без `test_`) и не production-код: регистрируется только
фикстурами через app.oauth.providers и восстанавливается после теста. Имя —
разрешённое (`yandex`/`vk`), чтобы не трогать CHECK провайдера в БД.

Моделирует провайдера честно: authorize URL несёт state и PKCE challenge;
issue_code(state) «выдаёт» code, привязанный к challenge этого state;
resolve_identity проверяет, что предъявленный verifier даёт тот же challenge
(S256) — так тест доказывает, что сервис хранит и отдаёт правильный verifier.
"""
import secrets
from contextlib import contextmanager
from typing import Mapping, Optional
from urllib.parse import parse_qs, urlencode, urlparse

from app.oauth import providers
from app.oauth.providers.base import (
    ProviderCallback, ProviderIdentity, ProviderRejected, ProviderUnavailable,
)
from app.oauth.security import code_challenge_s256

FAKE_AUTHORIZE_URL = "https://oauth.fake-provider.invalid/authorize"


class FakeProvider:
    def __init__(self, name: str = "yandex", subject: Optional[str] = None):
        self.name = name
        self.subject = subject or f"integ_{secrets.token_hex(6)}"
        self.mode = "success"          # success | unavailable | rejected | crash | wrong_provider
        self.resolve_calls = 0
        self.last_redirect_uri: Optional[str] = None
        self._challenge_by_state: dict[str, str] = {}
        self._challenge_by_code: dict[str, str] = {}

    # ── OAuthProvider ────────────────────────────────────────────────────────
    def build_authorize_url(self, *, state: str, code_challenge: str, redirect_uri: str) -> str:
        self._challenge_by_state[state] = code_challenge
        self.last_redirect_uri = redirect_uri
        return FAKE_AUTHORIZE_URL + "?" + urlencode({
            "response_type": "code", "state": state,
            "code_challenge": code_challenge, "code_challenge_method": "S256",
            "redirect_uri": redirect_uri,
        })

    def parse_callback(self, query: Mapping[str, str]) -> ProviderCallback:
        return ProviderCallback(
            state=query.get("state") or None,
            code=query.get("code") or None,
            error=query.get("error") or None,
            extra={},
        )

    def resolve_identity(self, *, code, code_verifier, redirect_uri, extra) -> ProviderIdentity:
        self.resolve_calls += 1
        if self.mode == "unavailable":
            raise ProviderUnavailable()
        if self.mode == "rejected":
            raise ProviderRejected()
        if self.mode == "crash":
            raise RuntimeError("adapter bug")
        expected = self._challenge_by_code.get(code)
        if expected is None or code_challenge_s256(code_verifier) != expected:
            raise ProviderRejected()   # PKCE mismatch / неизвестный code
        provider = "vk" if self.mode == "wrong_provider" and self.name == "yandex" else self.name
        return ProviderIdentity(provider=provider, subject=self.subject)

    # ── helpers для тестов ───────────────────────────────────────────────────
    def issue_code(self, state: str) -> str:
        code = "fakecode_" + secrets.token_hex(8)
        self._challenge_by_code[code] = self._challenge_by_state[state]
        return code


def state_from_authorize_url(url: str) -> str:
    return parse_qs(urlparse(url).query)["state"][0]


def challenge_from_authorize_url(url: str) -> str:
    return parse_qs(urlparse(url).query)["code_challenge"][0]


@contextmanager
def registered(provider: FakeProvider):
    """Регистрирует провайдера и гарантированно восстанавливает реестр."""
    snapshot = providers.registered_providers()
    providers.register_provider(provider)
    try:
        yield provider
    finally:
        providers.restore_providers(snapshot)
