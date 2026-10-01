"""
Storage social login (Stage Social Auth 2B): весь SQLAlchemy — здесь.

Одноразовость state и ticket обеспечивает БД (атомарный UPDATE ... WHERE
consumed_at IS NULL ... RETURNING), а не память процесса — механизм работает
при нескольких воркерах и переживает рестарт. В БД только SHA-256 hash state
и ticket; PKCE verifier — только `enc:v1:` (CHECK).

Попутная очистка: при вставке нового запроса/ticket удаляются строки, истёкшие
больше часа назад (индексы по expires_at). Не lifespan и не планировщик.
"""
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from sqlalchemy import delete, func, select, update

from app.auth.storage import _user_to_dict, create_session_in_tx
from app.db.models import OAuthAuthRequest, OAuthPendingTicket, User, UserOAuthIdentity
from app.db.session import SessionLocal
from app.oauth.errors import OAuthLoginDenied, OAuthTicketInvalidError

_CLEANUP_GRACE = timedelta(hours=1)


def _cleanup_cutoff() -> datetime:
    return datetime.now(timezone.utc) - _CLEANUP_GRACE


# ── authorization requests (state + PKCE) ────────────────────────────────────

def create_login_request(
    *, state_hash: str, provider: str, code_verifier_enc: str,
    expires_at: datetime,
) -> None:
    """Новый анонимный login-запрос (intent=login, user_id NULL)."""
    with SessionLocal() as db:
        db.execute(
            delete(OAuthAuthRequest)
            .where(OAuthAuthRequest.expires_at < _cleanup_cutoff())
            .execution_options(synchronize_session=False)
        )
        db.add(OAuthAuthRequest(
            state_hash=state_hash,
            provider=provider,
            intent="login",
            code_verifier_enc=code_verifier_enc,
            user_id=None,
            expires_at=expires_at,
        ))
        db.commit()


def consume_auth_request(*, state_hash: str, provider: str) -> Optional[dict]:
    """
    Атомарно списывает запрос и СРАЗУ коммитит (до обмена с провайдером).

    Только одна транзакция получает строку: параллельный/повторный callback
    ждёт блокировку и затем видит consumed_at. None — запроса нет, он истёк,
    уже списан или выдан другому провайдеру.
    """
    with SessionLocal() as db:
        row = db.execute(
            update(OAuthAuthRequest)
            .where(
                OAuthAuthRequest.state_hash == state_hash,
                OAuthAuthRequest.provider == provider,
                OAuthAuthRequest.consumed_at.is_(None),
                OAuthAuthRequest.expires_at > func.now(),
            )
            .values(consumed_at=func.now())
            .returning(
                OAuthAuthRequest.intent,
                OAuthAuthRequest.code_verifier_enc,
                OAuthAuthRequest.user_id,
            )
            .execution_options(synchronize_session=False)
        ).first()
        db.commit()
    if row is None:
        return None
    return {
        "intent": row.intent,
        "code_verifier_enc": row.code_verifier_enc,
        "user_id": row.user_id,
    }


# ── identity lookup (callback, ранняя проверка) ──────────────────────────────

def find_identity_user(*, provider: str, subject: str) -> Optional[dict]:
    """
    Привязанная identity → {"user_id", "user"}; user=None, если аккаунт
    soft-deleted. None — identity не найдена. Только чтение: авторитетная
    проверка выполняется в complete_login_atomic.
    """
    with SessionLocal() as db:
        identity = db.execute(
            select(UserOAuthIdentity).where(
                UserOAuthIdentity.provider == provider,
                UserOAuthIdentity.provider_subject == subject,
            )
        ).scalar_one_or_none()
        if identity is None:
            return None
        user = db.execute(
            select(User).where(
                User.id == identity.user_id, User.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        return {
            "user_id": identity.user_id,
            "user": _user_to_dict(user, db) if user is not None else None,
        }


# ── pending tickets ──────────────────────────────────────────────────────────

def create_login_ticket(
    *, ticket_hash: str, provider: str, subject: str, user_id: int,
    expires_at: datetime,
) -> None:
    """kind=login ticket. provider_subject сохраняется: complete проверяет,
    что identity всё ещё существует и принадлежит тому же пользователю."""
    with SessionLocal() as db:
        db.execute(
            delete(OAuthPendingTicket)
            .where(OAuthPendingTicket.expires_at < _cleanup_cutoff())
            .execution_options(synchronize_session=False)
        )
        db.add(OAuthPendingTicket(
            ticket_hash=ticket_hash,
            kind="login",
            provider=provider,
            provider_subject=subject,
            user_id=user_id,
            expires_at=expires_at,
        ))
        db.commit()


def complete_login_atomic(
    ticket_hash: str,
    *,
    check_user: Callable[[dict], None],
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    """
    Атомарный обмен login-ticket на обычную MindCare-сессию.

    Одна транзакция:
      1. списать ticket (UPDATE ... RETURNING; блокирует строку — параллельный
         complete ждёт и затем получает 0 строк);
      2. identity (provider, subject, user_id) — FOR SHARE: удалённая или
         переназначенная identity → отказ;
      3. пользователь (не soft-deleted) — FOR SHARE;
      4. check_user(user_dict) — ensure_user_can_start_session + чистый студент;
      5. create_session_in_tx + last_login_at/last_login;
      6. один commit: ticket + сессия.

    Семантика сбоев:
      * ticket невалиден → OAuthTicketInvalidError, ничего не изменено;
      * ДОМЕННЫЙ отказ (OAuthLoginDenied) → commit одного списания (ticket
        сожжён навсегда, сессии нет), затем исключение пробрасывается;
      * ТЕХНИЧЕСКИЙ сбой (БД, вставка сессии) → rollback при выходе из with:
        ticket снова годен до TTL, сессии нет. Один ticket → максимум одна сессия.

    Возвращает {"session_token", "expires_at", "user"}.
    """
    with SessionLocal() as db:
        row = db.execute(
            update(OAuthPendingTicket)
            .where(
                OAuthPendingTicket.ticket_hash == ticket_hash,
                OAuthPendingTicket.kind == "login",
                OAuthPendingTicket.consumed_at.is_(None),
                OAuthPendingTicket.expires_at > func.now(),
            )
            .values(consumed_at=func.now())
            .returning(
                OAuthPendingTicket.user_id,
                OAuthPendingTicket.provider,
                OAuthPendingTicket.provider_subject,
            )
            .execution_options(synchronize_session=False)
        ).first()
        if row is None:
            raise OAuthTicketInvalidError()

        try:
            identity = db.execute(
                select(UserOAuthIdentity)
                .where(
                    UserOAuthIdentity.provider == row.provider,
                    UserOAuthIdentity.provider_subject == row.provider_subject,
                    UserOAuthIdentity.user_id == row.user_id,
                )
                .with_for_update(read=True)
            ).scalar_one_or_none()
            if identity is None:
                raise OAuthLoginDenied("oauth_identity_unknown")

            user = db.execute(
                select(User)
                .where(User.id == row.user_id, User.deleted_at.is_(None))
                .with_for_update(read=True)
            ).scalar_one_or_none()
            if user is None:
                # soft-delete выставляет и is_active=false — тот же исход.
                raise OAuthLoginDenied("account_disabled")

            user_dict = _user_to_dict(user, db)
            check_user(user_dict)
        except OAuthLoginDenied:
            db.commit()   # фиксируем ТОЛЬКО списание ticket
            raise

        token, expires_at = create_session_in_tx(
            db, user.id, ip=ip, user_agent=user_agent,
        )
        now = datetime.now(timezone.utc)
        identity.last_login_at = now
        user.last_login = now
        db.commit()
        return {
            "session_token": token,
            "expires_at": expires_at,
            "user": user_dict,
        }
