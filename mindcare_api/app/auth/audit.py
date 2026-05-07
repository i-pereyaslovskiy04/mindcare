"""
Auth event logging — один входной хелпер для всех auth-событий.
Используется только из routes.py (логи — инфраструктурная забота HTTP-слоя).
"""

from typing import Optional

from app.db.session import SessionLocal
from app.db.models import AuthLog


def log_auth_event(
    event: str,
    success: bool = True,
    user_id: Optional[int] = None,
    user_email: Optional[str] = None,
    failure_reason: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    session_id: Optional[str] = None,
) -> None:
    """
    Записывает auth-событие в auth_log. 
    
    Если запись падает (например, кончились партиции) — НЕ ломает основной 
    flow, просто пишет в stderr. По договорённости (вариант "мягкий") 
    логирование не должно блокировать логин.
    """
    try:
        with SessionLocal() as db:
            db.add(AuthLog(
                event=event,
                success=success,
                user_id=user_id,
                user_email=user_email,
                failure_reason=failure_reason,
                ip_address=ip_address,
                user_agent=user_agent,
                session_id=session_id,
            ))
            db.commit()
    except Exception as e:
        # Не роняем основной поток. Но в проде это должно попасть в мониторинг.
        import sys
        print(
            f"[AUDIT FAIL] failed to log {event} (success={success}): "
            f"{type(e).__name__}: {e}",
            file=sys.stderr,
        )