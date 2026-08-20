"""
Stage 4B-2 — общий безопасный конструктор RequestContext для audit-writer'ов.

ip/user-agent приходят из клиента (untrusted). Строгая валидация facade
(`app.audit.validation.validate_context`) бросает AuditError на слишком длинном/
control-char User-Agent или непарсабельном IP — для ATOMIC-событий это RAISE, то
есть откат business mutation ПОСЛЕ успешного действия. Этот helper санитизирует
недоверенные значения ДО передачи facade: невалидное → None (в журнал не попадает),
исходное значение нигде не печатается. Строгую валидацию facade НЕ ослабляет —
лишь не даёт ей упасть на мусорном заголовке.

Модуль-лист: импортирует только stdlib + contracts (RequestContext), без routes/
service/storage/validation — во избежание циклов и дублирования. Принимает
примитивы (ip:str|None, user_agent:str|None) — тот слой, которым уже оперируют
storage-функции. X-Forwarded-For / X-Real-IP здесь НЕ читаются (trusted proxies —
отдельный этап).
"""
from __future__ import annotations

import ipaddress
from typing import Optional

from app.audit.contracts import RequestContext

# Синхронизировано с app/audit/validation.py::_UA_MAX (facade отвергает > 512).
_UA_MAX_LEN = 512


def _safe_user_agent(user_agent) -> Optional[str]:
    if not isinstance(user_agent, str):
        return None
    if len(user_agent) > _UA_MAX_LEN:
        return None
    if any(ord(c) < 32 or ord(c) == 127 for c in user_agent):
        return None
    return user_agent


def _safe_ip(ip) -> Optional[str]:
    if not isinstance(ip, str):
        return None
    try:
        ipaddress.ip_address(ip)
    except ValueError:
        return None
    return ip


def build_request_context(
    *,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
    session_id_hash: Optional[str] = None,
) -> RequestContext:
    """
    Строит RequestContext с санитизированными недоверенными ip/user_agent.

    session_id_hash пробрасывается без изменений (raw token сюда не передаётся) —
    его формирует caller (auth), для roles/supervisor/email он не применяется.
    """
    return RequestContext(
        ip_address=_safe_ip(ip),
        user_agent=_safe_user_agent(user_agent),
        session_id_hash=session_id_hash,
    )
