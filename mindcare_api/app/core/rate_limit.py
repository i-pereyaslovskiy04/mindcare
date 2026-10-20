"""
In-memory sliding-window rate limiter for auth endpoints.

MVP LIMITATION: состояние хранится в памяти процесса. При нескольких
uvicorn-воркерах или нескольких инстансах каждый процесс считает лимиты
независимо (эффективный лимит = limit × N процессов). Для production
multi-worker/multi-instance заменить на Redis/shared storage — интерфейс
enforce() при этом сохраняется.

Ключи лимитера содержат только: имя действия, нормализованный email, IP и
(для social registration confirm) SHA-256 digest одноразового ticket.
Никогда не класть в ключ пароли, OTP-коды, токены или raw ticket.
"""

import re
import threading
import time

from app.core.normalization import normalize_email

_SHA256_HEX_RE = re.compile(r"[0-9a-f]{64}")

# Период фоновой зачистки устаревших ключей (сек) — защита от роста памяти
# на ключах, к которым больше не обращаются.
_SWEEP_INTERVAL = 300.0

# Правила: action:dimension -> (max_requests, window_seconds).
# Email-лимиты защищают конкретный аккаунт, IP-лимиты — от массовых атак.
# IP-лимиты сознательно мягче: студенты университета часто сидят за одним NAT.
RULES: dict[str, tuple[int, float]] = {
    "login:email":         (5,  300),   # 5 попыток / 5 мин
    "login:ip":            (30, 300),   # 30 попыток / 5 мин
    "register_init:email": (3,  900),   # 3 запроса / 15 мин (поверх RESEND_COOLDOWN)
    "register_init:ip":    (20, 900),   # 20 запросов / 15 мин
    "reset_init:email":    (3,  900),   # 3 запроса / 15 мин
    "reset_init:ip":       (20, 900),   # 20 запросов / 15 мин
    "confirm:email":       (10, 600),   # 10 попыток / 10 мин (поверх OTP MAX_ATTEMPTS)
    "confirm:ip":          (30, 600),   # 30 попыток / 10 мин
    # Social login (Stage Social Auth 2B). Только IP: email во входе через
    # провайдера не участвует. Replay-защита — в БД (state/ticket одноразовые),
    # здесь — лишь ограничение нагрузки: start пишет строку в БД, callback
    # вызывает провайдера, complete — атомарную транзакцию.
    "oauth_start:ip":      (20, 300),   # 20 стартов / 5 мин
    "oauth_callback:ip":   (30, 300),   # 30 callback / 5 мин
    "oauth_complete:ip":   (30, 300),   # 30 complete / 5 мин
    # Social registration (Stage Social Auth 4). init шлёт письмо на email из
    # ticket (клиент email не передаёт) — лимит по ticket вместо email: один
    # ticket = один адрес. Ключ ticket — ПОЛНЫЙ SHA-256 digest (raw ticket в
    # ключи/логи не попадает никогда).
    "oauth_registration_init:ip":        (20, 900),
    "oauth_registration_init:ticket":    (3,  900),
    # VK-1B. preview — только чтение. Выбор адреса (init с email): отдельные
    # лимиты, чтобы исправимые отказы не съедали квоту повторной отправки;
    # лимит по самому адресу — как у register_init — защищает чужой ящик.
    "oauth_registration_preview:ip":     (60, 300),
    "oauth_registration_preview:ticket": (20, 300),
    "oauth_registration_email:ip":       (20, 900),
    "oauth_registration_email:ticket":   (8,  900),
    "oauth_registration_email:email":    (3,  900),
    "oauth_registration_confirm:ip":     (30, 600),
    "oauth_registration_confirm:ticket": (10, 600),
}


class RateLimitExceeded(Exception):
    """Превышен лимит запросов. HTTP-слой переводит в 429."""


class SlidingWindowRateLimiter:
    """
    Потокобезопасный sliding-window лимитер.

    clock инжектируется для тестов (по умолчанию time.monotonic).
    """

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._lock = threading.Lock()
        self._hits: dict[str, list[float]] = {}
        self._last_sweep: float = clock()

    def check(self, key: str, limit: int, window_seconds: float) -> None:
        """
        Регистрирует попытку для key. Бросает RateLimitExceeded, если
        в скользящем окне window_seconds уже было >= limit попыток.
        Заблокированная попытка не записывается (не продлевает блокировку).
        """
        now = self._clock()
        cutoff = now - window_seconds

        with self._lock:
            self._maybe_sweep(now)

            hits = [t for t in self._hits.get(key, []) if t > cutoff]
            if len(hits) >= limit:
                self._hits[key] = hits
                raise RateLimitExceeded(key.split(":", 1)[0])
            hits.append(now)
            self._hits[key] = hits

    def reset(self) -> None:
        """Полный сброс состояния (для тестов)."""
        with self._lock:
            self._hits.clear()

    def _maybe_sweep(self, now: float) -> None:
        """Удаляет ключи, все попытки которых старше максимального окна."""
        if now - self._last_sweep < _SWEEP_INTERVAL:
            return
        self._last_sweep = now
        max_window = max(w for _, w in RULES.values())
        cutoff = now - max_window
        stale = [k for k, hits in self._hits.items() if not hits or hits[-1] <= cutoff]
        for k in stale:
            del self._hits[k]


# ─── Module-level singleton ───────────────────────────────────────────────────

_limiter = SlidingWindowRateLimiter()


def enforce(
    action: str, *, email: str | None = None, ip: str | None = None,
    ticket_digest: str | None = None,
) -> None:
    """
    Проверяет лимиты действия action по доступным измерениям.

    - email нормализуется через normalize_email до построения ключа;
    - отсутствующее измерение (None/пустое) пропускается;
    - порядок: сначала IP (защита от массовых атак), затем email, затем ticket;
    - ticket_digest — ТОЛЬКО SHA-256 hex от ticket (64 символа); иное значение
      отклоняется, чтобы raw ticket не мог стать ключом по ошибке вызывающего.

    Бросает RateLimitExceeded при превышении любого из лимитов.
    """
    if ip:
        rule = RULES.get(f"{action}:ip")
        if rule:
            _limiter.check(f"{action}:ip:{ip}", *rule)

    if email:
        rule = RULES.get(f"{action}:email")
        if rule:
            _limiter.check(f"{action}:email:{normalize_email(email)}", *rule)

    if ticket_digest:
        if not _SHA256_HEX_RE.fullmatch(ticket_digest):
            raise ValueError("ticket_digest must be a SHA-256 hex digest")
        rule = RULES.get(f"{action}:ticket")
        if rule:
            _limiter.check(f"{action}:ticket:{ticket_digest}", *rule)


def check(key: str, limit: int, window_seconds: float) -> None:
    """
    Прямая проверка произвольного ключа через общий module-level limiter
    (например, "chat_send:user:<id>"). Auth-логика enforce() не затрагивается.
    Бросает RateLimitExceeded при превышении.
    """
    _limiter.check(key, limit, window_seconds)


def reset() -> None:
    """Сброс всех счётчиков (используется тестами между кейсами)."""
    _limiter.reset()
