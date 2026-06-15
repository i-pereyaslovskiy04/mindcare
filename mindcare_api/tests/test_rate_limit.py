"""
Unit tests for app.core.rate_limit (Stage 21).

Covers:
  - sliding window: under limit OK, over limit raises
  - window expiry frees the slot (controllable clock)
  - keys are independent (per action / per email / per IP)
  - email keys are normalized (case/whitespace variants share one bucket)
  - blocked attempt does not extend the block
  - keys never contain passwords/codes/tokens (key format assertions)
  - reset() clears state
  - enforce() skips missing dimensions
  - stale-key sweep removes abandoned keys

No HTTP, no DB.
"""

import pytest

from app.core import rate_limit
from app.core.rate_limit import (
    RULES,
    RateLimitExceeded,
    SlidingWindowRateLimiter,
)


class FakeClock:
    def __init__(self, start: float = 1000.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture(autouse=True)
def _clean_module_limiter():
    """Изолируем module-level singleton между тестами."""
    rate_limit.reset()
    yield
    rate_limit.reset()


# ─── 1. Sliding window basics ─────────────────────────────────────────────────

class TestSlidingWindow:
    def test_under_limit_ok(self):
        clock = FakeClock()
        lim = SlidingWindowRateLimiter(clock=clock)
        for _ in range(5):
            lim.check("k", limit=5, window_seconds=60)
        # 5 попыток при limit=5 проходят, 6-я — нет

    def test_over_limit_raises(self):
        clock = FakeClock()
        lim = SlidingWindowRateLimiter(clock=clock)
        for _ in range(5):
            lim.check("k", limit=5, window_seconds=60)
        with pytest.raises(RateLimitExceeded):
            lim.check("k", limit=5, window_seconds=60)

    def test_window_expiry_frees_slot(self):
        clock = FakeClock()
        lim = SlidingWindowRateLimiter(clock=clock)
        for _ in range(3):
            lim.check("k", limit=3, window_seconds=60)
        with pytest.raises(RateLimitExceeded):
            lim.check("k", limit=3, window_seconds=60)

        clock.advance(61)
        lim.check("k", limit=3, window_seconds=60)  # окно сдвинулось — снова можно

    def test_partial_expiry_sliding_not_fixed(self):
        """Окно скользящее: освобождаются только попытки старше window."""
        clock = FakeClock()
        lim = SlidingWindowRateLimiter(clock=clock)
        lim.check("k", limit=2, window_seconds=60)   # t=1000
        clock.advance(30)
        lim.check("k", limit=2, window_seconds=60)   # t=1030
        with pytest.raises(RateLimitExceeded):
            lim.check("k", limit=2, window_seconds=60)

        clock.advance(31)  # t=1061: первая попытка (t=1000) вышла из окна
        lim.check("k", limit=2, window_seconds=60)
        with pytest.raises(RateLimitExceeded):
            # вторая (t=1030) ещё в окне + только что добавленная = лимит
            lim.check("k", limit=2, window_seconds=60)

    def test_blocked_attempt_not_recorded(self):
        """Заблокированная попытка не продлевает блокировку."""
        clock = FakeClock()
        lim = SlidingWindowRateLimiter(clock=clock)
        for _ in range(3):
            lim.check("k", limit=3, window_seconds=60)

        # Долбим заблокированный ключ — это не должно сдвигать окно
        for _ in range(10):
            clock.advance(5)
            with pytest.raises(RateLimitExceeded):
                lim.check("k", limit=3, window_seconds=60)

        clock.advance(11)  # все 3 исходные попытки старше 60с
        lim.check("k", limit=3, window_seconds=60)

    def test_keys_independent(self):
        clock = FakeClock()
        lim = SlidingWindowRateLimiter(clock=clock)
        for _ in range(3):
            lim.check("a", limit=3, window_seconds=60)
        with pytest.raises(RateLimitExceeded):
            lim.check("a", limit=3, window_seconds=60)
        lim.check("b", limit=3, window_seconds=60)  # другой ключ не затронут

    def test_reset_clears_state(self):
        clock = FakeClock()
        lim = SlidingWindowRateLimiter(clock=clock)
        for _ in range(3):
            lim.check("k", limit=3, window_seconds=60)
        lim.reset()
        lim.check("k", limit=3, window_seconds=60)


# ─── 2. enforce(): ключи и нормализация ──────────────────────────────────────

class TestEnforce:
    def test_email_normalized_shared_bucket(self):
        """Разный регистр/пробелы одного email попадают в один bucket."""
        limit, _ = RULES["login:email"]
        variants = ["  User@Example.COM ", "user@example.com", "USER@example.com"]
        for i in range(limit):
            rate_limit.enforce("login", email=variants[i % len(variants)])
        with pytest.raises(RateLimitExceeded):
            rate_limit.enforce("login", email="user@EXAMPLE.com")

    def test_different_emails_independent(self):
        limit, _ = RULES["login:email"]
        for _ in range(limit):
            rate_limit.enforce("login", email="a@example.com")
        rate_limit.enforce("login", email="b@example.com")  # не заблокирован

    def test_ip_limit_enforced(self):
        limit, _ = RULES["login:ip"]
        for _ in range(limit):
            rate_limit.enforce("login", ip="10.0.0.1")
        with pytest.raises(RateLimitExceeded):
            rate_limit.enforce("login", ip="10.0.0.1")

    def test_different_ips_independent(self):
        limit, _ = RULES["login:ip"]
        for _ in range(limit):
            rate_limit.enforce("login", ip="10.0.0.1")
        rate_limit.enforce("login", ip="10.0.0.2")

    def test_missing_dimensions_skipped(self):
        """email=None / ip=None не бросают и не создают ключей."""
        rate_limit.enforce("login")
        rate_limit.enforce("login", email=None, ip=None)
        assert rate_limit._limiter._hits == {}

    def test_unknown_action_no_rules_noop(self):
        rate_limit.enforce("no_such_action", email="x@example.com", ip="1.2.3.4")
        assert rate_limit._limiter._hits == {}

    def test_actions_have_separate_buckets(self):
        limit, _ = RULES["reset_init:email"]
        for _ in range(limit):
            rate_limit.enforce("reset_init", email="a@example.com")
        with pytest.raises(RateLimitExceeded):
            rate_limit.enforce("reset_init", email="a@example.com")
        # login для того же email не затронут лимитом reset_init
        rate_limit.enforce("login", email="a@example.com")

    def test_keys_contain_no_secrets(self):
        """Ключи состоят только из action:dimension:value (email|ip)."""
        rate_limit.enforce("login", email="User@Example.com", ip="10.0.0.5")
        keys = set(rate_limit._limiter._hits.keys())
        assert keys == {"login:email:user@example.com", "login:ip:10.0.0.5"}


# ─── 3. Sweep устаревших ключей ──────────────────────────────────────────────

class TestSweep:
    def test_stale_keys_removed(self):
        clock = FakeClock()
        lim = SlidingWindowRateLimiter(clock=clock)
        lim.check("stale", limit=5, window_seconds=60)

        max_window = max(w for _, w in RULES.values())
        # Двигаем время за пределы и sweep-интервала, и максимального окна
        clock.advance(max_window + rate_limit._SWEEP_INTERVAL + 1)
        lim.check("fresh", limit=5, window_seconds=60)

        assert "stale" not in lim._hits
        assert "fresh" in lim._hits


# ─── 4. Конфигурация правил ──────────────────────────────────────────────────

class TestRules:
    def test_all_protected_actions_have_both_dimensions(self):
        for action in ("login", "register_init", "reset_init", "confirm"):
            assert f"{action}:email" in RULES
            assert f"{action}:ip" in RULES

    def test_ip_limits_not_stricter_than_email(self):
        """IP-лимит шире email-лимита: за NAT много пользователей."""
        for action in ("login", "register_init", "reset_init", "confirm"):
            email_limit, _ = RULES[f"{action}:email"]
            ip_limit, _ = RULES[f"{action}:ip"]
            assert ip_limit >= email_limit
