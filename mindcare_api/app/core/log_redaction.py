"""
Маскировка query у OAuth callback в access log uvicorn (Stage Social Auth 2B).

URL callback несёт authorization code и state. uvicorn пишет access-строку
`'%s - "%s %s HTTP/%s" %d'`, где третий аргумент — путь ВМЕСТЕ с query
(protocols/utils.get_path_with_query_string). Фильтр на логгере
`uvicorn.access` заменяет query ТОЛЬКО у /api/auth/oauth/{provider}/callback
на `?<redacted>`; остальные записи не трогает и ни одну не отбрасывает.

uvicorn настраивает логирование до импорта приложения (Config.__init__ →
configure_logging, затем load), поэтому фильтр, добавленный при импорте
app.main, сохраняется; при --reload/--workers каждый процесс повторяет этот
порядок. Перед публичным HTTPS-деплоем то же самое нужно обеспечить на
reverse proxy/TLS-терминаторе (его access log пишет URI сам).
"""
import logging
import re

_CALLBACK_TARGET_RE = re.compile(r"^(/api/auth/oauth/[^/?#]+/callback)\?.*$", re.DOTALL)
REDACTED_QUERY = "?<redacted>"
ACCESS_LOGGER_NAME = "uvicorn.access"


def redact_request_target(target: str) -> str:
    """Путь callback с query → путь + '?<redacted>'; иное — без изменений."""
    match = _CALLBACK_TARGET_RE.match(target)
    if match is None:
        return target
    return match.group(1) + REDACTED_QUERY


class OAuthCallbackQueryRedactor(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            args = record.args
            if isinstance(args, tuple) and len(args) >= 3 and isinstance(args[2], str):
                redacted = redact_request_target(args[2])
                if redacted is not args[2]:
                    record.args = args[:2] + (redacted,) + args[3:]
        except Exception:   # noqa: BLE001 — фильтр никогда не ломает логирование
            pass
        return True


def install_access_log_redaction(logger_name: str = ACCESS_LOGGER_NAME) -> None:
    """Идемпотентно вешает фильтр на логгер (повторный импорт не дублирует)."""
    logger = logging.getLogger(logger_name)
    if not any(isinstance(f, OAuthCallbackQueryRedactor) for f in logger.filters):
        logger.addFilter(OAuthCallbackQueryRedactor())
