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
from sqlalchemy.exc import IntegrityError

from app.auth.otp_service import (
    MAX_ATTEMPTS, _utcnow as otp_utcnow, _verify_code as verify_otp_code,
    create_or_update_otp_in_tx,
)
from app.auth.storage import (
    RegistrationDataError, _assign_role, _user_to_dict, create_session_in_tx,
    required_consent_ids,
)
from app.db.models import (
    ConsentRecord, OAuthAuthRequest, OAuthPendingTicket, OtpVerification, User,
    UserOAuthIdentity,
)
from app.db.session import SessionLocal
from app.oauth.errors import (
    REGISTRATION_INTERNAL_MESSAGE, OAuthLoginDenied, OAuthRegistrationError,
    OAuthTicketInvalidError, email_exists_error, identity_linked_error,
)

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

    Возвращает {"session_token", "expires_at", "user", "provider"}; provider —
    из списанного ticket (для auth_log.auth_method). При доменном отказе тот же
    провайдер проставляется в OAuthLoginDenied.provider.
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
        except OAuthLoginDenied as denial:
            db.commit()   # фиксируем ТОЛЬКО списание ticket
            if denial.provider is None:
                denial.provider = row.provider   # провайдер — из строки ticket
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
            "provider": row.provider,
        }


# ── регистрация через провайдера (Stage Social Auth 4) ───────────────────────
#
# Миграции нет: используется kind='registration' фундамента 2A. Поля ticket
# `email` / `suggested_name` — email и имя из профиля провайдера, записанные
# callback'ом; клиент их не передаёт и изменить не может. Обычный allowlist
# доменов здесь НЕ применяется (ADR-027): email выбран не пользователем вручную,
# а подтверждён провайдером и затем OTP MindCare.

_EMAIL_CONSTRAINTS = frozenset({"ux_users_email_normalized", "ix_users_email"})
_IDENTITY_CONSTRAINTS = frozenset({
    "ux_user_oauth_identities_provider_subject",
    "ux_user_oauth_identities_user_provider",
})


def create_registration_ticket(
    *, ticket_hash: str, provider: str, subject: str, email: str,
    suggested_name: str, expires_at: datetime,
) -> None:
    """kind=registration: identity провайдера подтверждена, аккаунта ещё нет
    (user_id NULL); email (нормализованный) и имя — из профиля провайдера. Ни
    пользователь, ни identity, ни сессия здесь не создаются."""
    with SessionLocal() as db:
        db.execute(
            delete(OAuthPendingTicket)
            .where(OAuthPendingTicket.expires_at < _cleanup_cutoff())
            .execution_options(synchronize_session=False)
        )
        db.add(OAuthPendingTicket(
            ticket_hash=ticket_hash,
            kind="registration",
            provider=provider,
            provider_subject=subject,
            email=email,
            suggested_name=suggested_name,
            user_id=None,
            expires_at=expires_at,
        ))
        db.commit()


def _lock_registration_ticket(db, ticket_hash: str) -> OAuthPendingTicket:
    """Живой registration-ticket под FOR UPDATE: параллельный init/confirm того
    же ticket ждёт и затем видит уже изменённую строку. Ticket без email/имени
    (создан до Stage 4 hotfix) завершить нельзя — он невалиден."""
    ticket = db.execute(
        select(OAuthPendingTicket)
        .where(
            OAuthPendingTicket.ticket_hash == ticket_hash,
            OAuthPendingTicket.kind == "registration",
            OAuthPendingTicket.consumed_at.is_(None),
            OAuthPendingTicket.expires_at > func.now(),
        )
        .with_for_update()
    ).scalar_one_or_none()
    if ticket is None or ticket.email is None or ticket.suggested_name is None:
        raise OAuthTicketInvalidError()
    return ticket


def _identity_exists(db, provider: str, subject: str) -> bool:
    return db.execute(
        select(UserOAuthIdentity.id).where(
            UserOAuthIdentity.provider == provider,
            UserOAuthIdentity.provider_subject == subject,
        )
    ).first() is not None


def _email_taken(db, email: str) -> bool:
    """ЛЮБАЯ строка users, включая soft-deleted: уникальный индекс email полный,
    а реактивация/привязка существующего аккаунта здесь запрещена."""
    return db.execute(select(User.id).where(User.email == email)).first() is not None


def issue_registration_otp(ticket_hash: str) -> tuple[str, str]:
    """
    Init регистрации (и повторная отправка): OTP на email ИЗ TICKET.

      1. ticket (FOR UPDATE): registration, не списан, не истёк;
      2. identity уже привязана → ticket сжигается (commit), отказ;
      3. email уже занят (включая soft-deleted) → ticket сжигается (commit):
         email ticket не меняется, регистрация этим ticket невозможна;
      4. OTP (password_hash NULL) под cooldown — отказ без изменений;
      5. commit.

    Allowlist доменов не проверяется (ADR-027). Возвращает (plaintext-код,
    email) для отправки ПОСЛЕ commit — письмо уходит из service, вне транзакции.
    """
    with SessionLocal() as db:
        ticket = _lock_registration_ticket(db, ticket_hash)
        provider = ticket.provider
        email = ticket.email

        if _identity_exists(db, provider, ticket.provider_subject):
            ticket.consumed_at = datetime.now(timezone.utc)
            db.commit()
            raise identity_linked_error(provider)

        if _email_taken(db, email):
            ticket.consumed_at = datetime.now(timezone.utc)
            db.commit()
            raise email_exists_error(provider)

        cooldown = None
        try:
            code = create_or_update_otp_in_tx(
                db, email, ticket.suggested_name, None, lock=True,
            )
        except ValueError as exc:
            cooldown = str(exc)
        if cooldown is not None:
            raise OAuthRegistrationError("otp_cooldown", cooldown, 429, provider=provider)

        db.commit()
        return code, email


def _otp_error(audit_code: str, message: str, provider: str, email: str):
    return OAuthRegistrationError(
        audit_code, message, 400, audit_code=audit_code, provider=provider, email=email,
    )


def _conflict_from_integrity(exc: IntegrityError, provider: str, email: str):
    """Ожидаемая гонка на UNIQUE → фиксированный 409 без текста SQL. Иное
    нарушение целостности — не доменный отказ: возвращается None."""
    constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None) or ""
    if constraint in _EMAIL_CONSTRAINTS:
        return email_exists_error(provider, email, audited=True)
    if constraint in _IDENTITY_CONSTRAINTS:
        return identity_linked_error(provider, email, audited=True)
    return None


def _new_user(db, *, name: str, email: str) -> User:
    """Аккаунт без пароля: password_hash NULL, ни случайного пароля, ни заглушки."""
    user = User(full_name=name, email=email, password_hash=None)
    db.add(user)
    db.flush()   # нужен user.id; здесь же срабатывает UNIQUE email
    return user


def _add_consents(db, user_id: int, consent_ids: list, ip, user_agent) -> None:
    for consent_id in consent_ids:
        db.add(ConsentRecord(
            user_id=user_id, consent_id=consent_id, accepted=True,
            ip_address=ip, user_agent=user_agent,
        ))


def _new_identity(db, *, user_id: int, provider: str, subject: str, now) -> None:
    db.add(UserOAuthIdentity(
        user_id=user_id, provider=provider, provider_subject=subject,
        last_login_at=now,
    ))
    db.flush()   # UNIQUE (provider, subject) срабатывает до commit


def complete_registration_atomic(
    ticket_hash: str,
    code: str,
    *,
    required_consent_types: list,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    """
    Атомарное подтверждение регистрации через провайдера: одна сессия, один
    финальный commit.

    Согласие MindCare (consent gate) проверяет service ДО вызова: без него
    сюда не доходит.

      1. ticket (FOR UPDATE): registration, не списан, не истёк, с email/именем;
      2. identity уже существует → ticket сжигается, отказ;
      3. email свободен, включая soft-deleted → иначе ticket сжигается, отказ
         (до OTP: reset-OTP существующего пользователя здесь не трогается);
      4. OTP по email ticket (FOR UPDATE): password_hash IS NULL (иначе это код
         другого потока), не истёк, попытки, код;
      5. id обязательных согласий;
      6. User (password_hash NULL) → роль student → consent_records →
         UserOAuthIdentity (last_login_at) → удаление OTP → ticket.consumed_at
         → сессия → last_login;
      7. commit.

    Allowlist доменов не проверяется (ADR-027): email — от провайдера,
    подтверждён этим OTP.

    Семантика:
      * неверный/истёкший код → commit ТОЛЬКО счётчика попыток (или удаления
        OTP); ticket остаётся годным, аккаунт не создаётся;
      * identity/email уже существуют → ticket сожжён навсегда (commit);
      * нет роли/политики → rollback: ticket и OTP целы;
      * гонка на UNIQUE → rollback всего, фиксированный 409;
      * технический сбой (БД, вставка сессии, commit) → rollback всего и
        исключение как есть — он НЕ превращается в «неверный код».

    Имя и email берутся ТОЛЬКО из ticket (не из записи OTP). Возвращает
    {"session_token", "expires_at", "user", "provider"}.
    """
    with SessionLocal() as db:
        ticket = _lock_registration_ticket(db, ticket_hash)

        provider = ticket.provider
        subject = ticket.provider_subject
        email = ticket.email
        name = ticket.suggested_name

        if _identity_exists(db, provider, subject):
            ticket.consumed_at = datetime.now(timezone.utc)
            db.commit()
            raise identity_linked_error(provider, email, audited=True)

        # Email занят → ticket уже не завершится. Проверка ДО OTP:
        # запись OTP для существующего пользователя — это reset-OTP чужого
        # потока, её попытки здесь трогать нельзя.
        if _email_taken(db, email):
            ticket.consumed_at = datetime.now(timezone.utc)
            db.commit()
            raise email_exists_error(provider, email, audited=True)

        # ── OTP ─────────────────────────────────────────────────────────────
        record = db.execute(
            select(OtpVerification)
            .where(OtpVerification.email == email)
            .with_for_update()
        ).scalars().first()
        # Запись с хешем пароля — код обычной регистрации: чужому потоку попытки
        # не сжигаем и код не проверяем.
        if record is None or record.password_hash is not None:
            raise _otp_error(
                "otp_invalid", "Код не найден или уже использован. Запросите новый код.",
                provider, email,
            )
        if otp_utcnow() > record.expires_at:
            db.delete(record)
            db.commit()
            raise _otp_error(
                "otp_expired", "Срок действия кода истёк. Запросите новый код.",
                provider, email,
            )
        if record.attempts >= MAX_ATTEMPTS:
            db.delete(record)
            db.commit()
            raise _otp_error(
                "otp_invalid", "Превышено число попыток. Запросите новый код.",
                provider, email,
            )
        if not verify_otp_code(code, record.code):
            record.attempts += 1
            remaining = MAX_ATTEMPTS - record.attempts
            if remaining <= 0:
                db.delete(record)
                db.commit()
                raise _otp_error(
                    "otp_invalid", "Неверный код. Попытки исчерпаны. Запросите новый код.",
                    provider, email,
                )
            db.commit()
            raise _otp_error(
                "otp_invalid", f"Неверный код. Осталось попыток: {remaining}",
                provider, email,
            )

        # ── OTP верный. Дальше — core UoW без промежуточных commit. ─────────
        # Повторная проверка email (READ COMMITTED: свежий снимок после
        # ожидания FOR UPDATE на OTP); окончательно гонку решает UNIQUE ниже.
        if _email_taken(db, email):
            ticket.consumed_at = datetime.now(timezone.utc)
            db.commit()
            raise email_exists_error(provider, email, audited=True)

        conflict = None
        seed_missing = False
        try:
            consent_ids = required_consent_ids(db, required_consent_types)
            now = datetime.now(timezone.utc)
            user = _new_user(db, name=name, email=email)
            _assign_role(db, user.id, "student")
            _add_consents(db, user.id, consent_ids, ip, user_agent)
            _new_identity(db, user_id=user.id, provider=provider, subject=subject, now=now)
            db.delete(record)
            ticket.consumed_at = now
            token, expires_at = create_session_in_tx(
                db, user.id, ip=ip, user_agent=user_agent,
            )
            user.last_login = now
            db.commit()
        except RegistrationDataError:
            db.rollback()
            seed_missing = True
        except IntegrityError as exc:
            db.rollback()
            conflict = _conflict_from_integrity(exc, provider, email)
            if conflict is None:
                raise
        if seed_missing:
            raise OAuthRegistrationError(
                "internal_error", REGISTRATION_INTERNAL_MESSAGE, 500,
                audit_code="internal_error", provider=provider, email=email,
            )
        if conflict is not None:
            raise conflict

        db.refresh(user)
        return {
            "session_token": token,
            "expires_at": expires_at,
            "user": _user_to_dict(user, db),
            "provider": provider,
        }
