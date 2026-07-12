"""
PostgreSQL storage via SQLAlchemy ORM.

Сессии хранятся в user_sessions (таблица из SQL-схемы).
Роль пользователя берётся через JOIN user_roles → roles.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from app.core.normalization import normalize_email
from app.db.session import SessionLocal
from app.db.models import (
    User, UserRole, Role, UserSession, Consent, ConsentRecord, OtpVerification,
)
from app.auth.security import generate_session_token, hash_session_token
# OTP-хелперы переиспользуются для атомарного confirm (один пакет app.auth,
# цикла импортов нет: otp_service не импортирует storage).
from app.auth.otp_service import _verify_code, MAX_ATTEMPTS, _utcnow
from app.core.config import SESSION_EXPIRE_DAYS


class RegistrationDataError(RuntimeError):
    """
    Отсутствуют обязательные seed/reference данные (роль или consent-политика)
    при подтверждении регистрации. Подкласс RuntimeError → существующие
    проверки `pytest.raises(RuntimeError)` остаются валидными; service-слой
    может отлавливать этот тип отдельно и мапить на HTTP 500.
    """


class UserNotFoundError(RuntimeError):
    """
    Пользователь не найден при атомарной операции с паролем
    (change_password_atomic / password_reset_confirm_atomic).
    Service-слой мапит на HTTP 404.
    """


class InvalidCurrentPasswordError(RuntimeError):
    """
    Текущий пароль не совпал при change_password_atomic.
    Service-слой мапит на HTTP 400. Проверка выполняется ВНУТРИ
    транзакции (callback), поэтому ни password_hash, ни сессии не меняются.
    """


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def _get_primary_role(db, user_id: int) -> str:
    """Первая активная роль пользователя, по умолчанию — 'student'."""
    ur = (
        db.query(UserRole)
        .join(Role, UserRole.role_id == Role.id)
        .filter(UserRole.user_id == user_id)
        .filter(
            UserRole.expires_at.is_(None)
            | (UserRole.expires_at > datetime.now(timezone.utc))
        )
        .first()
    )
    return ur.role.name if ur else "student"


def _user_to_dict(user: User, db) -> dict:
    return {
        "id":              str(user.id),
        "name":            user.full_name,
        "email":           user.email,
        "hashed_password": user.password_hash,
        "role":            _get_primary_role(db, user.id),
        "is_active":       user.is_active,
    }


def _assign_role(db, user_id: int, role_name: str = "student") -> None:
    """
    Назначает роль пользователю.

    Роль обязана существовать в справочнике `roles`. Если её нет — это
    проблема seed/reference data: бросаем RuntimeError, чтобы не создать
    пользователя без реальной записи `user_roles` (раньше роль молча
    пропускалась, а `_get_primary_role` маскировал это дефолтом "student").
    Исключение поднимается до commit в `save_user`, поэтому INSERT
    пользователя откатывается вместе с транзакцией.
    """
    role = db.query(Role).filter(Role.name == role_name).first()
    if role is None:
        raise RegistrationDataError(
            f"Role '{role_name}' not found in roles table — "
            "check seed/reference data"
        )
    db.add(UserRole(user_id=user_id, role_id=role.id))


# ---------------------------------------------------------------------------
# Пользователи
# ---------------------------------------------------------------------------

def find_user_by_email(email: str) -> Optional[dict]:
    with SessionLocal() as db:
        user = (
            db.query(User)
            .filter(
                User.email == normalize_email(email),
                User.deleted_at.is_(None),
            )
            .first()
        )
        return _user_to_dict(user, db) if user else None


def find_user_by_id(user_id: str) -> Optional[dict]:
    with SessionLocal() as db:
        user = (
            db.query(User)
            .filter(
                User.id == int(user_id),
                User.deleted_at.is_(None),
            )
            .first()
        )
        return _user_to_dict(user, db) if user else None


def _profile_to_dict(user: User, db) -> dict:
    return {
        "id":               str(user.id),
        "email":            user.email,
        "full_name":        user.full_name,
        "phone":            user.phone,
        "role":             _get_primary_role(db, user.id),
        "ui_theme_palette": user.ui_theme_palette,
        "ui_theme_mode":    user.ui_theme_mode,
    }


def get_profile(user_id: str) -> Optional[dict]:
    """Self-profile текущего пользователя (без password_hash)."""
    with SessionLocal() as db:
        user = (
            db.query(User)
            .filter(
                User.id == int(user_id),
                User.deleted_at.is_(None),
            )
            .first()
        )
        return _profile_to_dict(user, db) if user else None


ALLOWED_PROFILE_FIELDS = ("full_name", "phone", "ui_theme_palette", "ui_theme_mode")


def update_profile_atomic(user_id: str, updates: dict) -> dict:
    """Атомарно обновляет разрешённые self-поля текущего пользователя.
    Один SessionLocal + один commit.

    updates — только реально переданные поля (exclude_unset): отсутствие ключа
    = не менять, значение None = сбросить. Ключи вне ALLOWED_PROFILE_FIELDS
    игнорируются (defense-in-depth: схема их и так не пропустит).
    """
    with SessionLocal() as db:
        user = (
            db.query(User)
            .filter(
                User.id == int(user_id),
                User.deleted_at.is_(None),
            )
            .first()
        )
        if user is None:
            raise UserNotFoundError("User not found")
        for field, value in updates.items():
            if field in ALLOWED_PROFILE_FIELDS:
                setattr(user, field, value)
        user.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(user)
        return _profile_to_dict(user, db)


def save_user(user: dict) -> dict:
    with SessionLocal() as db:
        db_user = User(
            full_name=user["name"],
            email=normalize_email(user["email"]),
            password_hash=user["hashed_password"],
        )
        db.add(db_user)
        db.flush()  # нужен id до commit — для user_roles в той же транзакции
        _assign_role(db, db_user.id, user.get("role", "student"))
        db.commit()
        db.refresh(db_user)
        return _user_to_dict(db_user, db)


def reactivate_user(
    email: str,
    name: str,
    password_hash: str,
) -> Optional[dict]:
    """
    Реактивирует мягко-удалённого пользователя вместо создания нового.
    Возвращает dict если такой удалённый юзер найден, иначе None.
    Роль, uuid и id остаются прежними — обновляются только имя, пароль и статус.
    """
    with SessionLocal() as db:
        user = (
            db.query(User)
            .filter(
                User.email == normalize_email(email),
                User.deleted_at.isnot(None),
            )
            .first()
        )
        if not user:
            return None
        user.deleted_at = None
        user.is_active = True
        user.full_name = name
        user.password_hash = password_hash
        db.commit()
        db.refresh(user)
        return _user_to_dict(user, db)


def get_active_consent_id(policy_type: str) -> Optional[int]:
    """Возвращает id последней версии согласия данного типа."""
    with SessionLocal() as db:
        consent = (
            db.query(Consent)
            .filter(Consent.policy_type == policy_type)
            .order_by(Consent.version.desc())
            .first()
        )
        return consent.id if consent else None


def save_consent_record(
    user_id: int,
    consent_id: int,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> None:
    """Записывает факт согласия пользователя."""
    with SessionLocal() as db:
        db.add(ConsentRecord(
            user_id=user_id,
            consent_id=consent_id,
            accepted=True,
            ip_address=ip,
            user_agent=user_agent,
        ))
        db.commit()


def register_confirm_atomic(
    email: str,
    code: str,
    required_consent_types: list[str],
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    """
    Атомарное подтверждение self-registration (Stage 31m-fix-b2).

    В ОДНОЙ сессии и ОДНОМ финальном commit:
      1. validate OTP (без удаления, если код верный);
      2. убедиться, что все обязательные consent-политики существуют;
      3. создать нового или реактивировать soft-deleted пользователя;
      4. назначить роль student (для нового пользователя);
      5. создать все обязательные consent_records (с ip/user_agent);
      6. consume (delete) OTP;
      7. commit.

    Любой сбой core-шага (2–6) поднимает исключение до commit → транзакция
    откатывается целиком: пользователь, user_roles и consent_records не
    сохраняются даже частично, а OTP НЕ потребляется (повторная попытка
    возможна тем же кодом).

    OTP failure-пути (не найден / истёк / превышены попытки / неверный код)
    сохраняют текущую политику attempts: для них выполняется отдельный commit
    (пользователь при этом не создаётся).

    Бросает:
      ValueError            — проблема OTP (service → HTTP 400);
      RegistrationDataError — нет роли student или consent-политики (→ HTTP 500).

    SMTP/email и welcome-уведомление СЮДА не входят (письмо отправляется на
    init-шаге; welcome — soft-fail после commit на уровне service).
    """
    email = normalize_email(email)
    now = _utcnow()

    with SessionLocal() as db:
        # ── 1. OTP validation ───────────────────────────────────────────────
        record = (
            db.query(OtpVerification)
            .filter(OtpVerification.email == email)
            .first()
        )
        if not record:
            raise ValueError("Код не найден или уже использован")

        if now > record.expires_at:
            db.delete(record)
            db.commit()
            raise ValueError("Срок действия кода истёк. Начните регистрацию заново")

        if record.attempts >= MAX_ATTEMPTS:
            db.delete(record)
            db.commit()
            raise ValueError("Превышено число попыток. Начните регистрацию заново")

        if not _verify_code(code, record.code):
            record.attempts += 1
            remaining = MAX_ATTEMPTS - record.attempts
            if remaining <= 0:
                db.delete(record)
                db.commit()
                raise ValueError(
                    "Неверный код. Попытки исчерпаны. Начните регистрацию заново"
                )
            db.commit()
            raise ValueError(f"Неверный код. Осталось попыток: {remaining}")

        # ── OTP верный. Дальше — core UoW без промежуточных commit. ──────────
        name = record.name
        password_hash = record.password_hash

        # 2. Обязательные consent-политики обязаны существовать (seed data).
        consent_ids: list[int] = []
        for policy_type in required_consent_types:
            consent = (
                db.query(Consent)
                .filter(Consent.policy_type == policy_type)
                .order_by(Consent.version.desc())
                .first()
            )
            if consent is None:
                raise RegistrationDataError(
                    f"Политика '{policy_type}' не найдена в БД."
                    " Обратитесь к администратору."
                )
            consent_ids.append(consent.id)

        # 3. Создать нового или реактивировать soft-deleted пользователя.
        user = (
            db.query(User)
            .filter(
                User.email == email,
                User.deleted_at.isnot(None),
            )
            .first()
        )
        if user is not None:
            # Реактивация: id/uuid/роль сохраняются (как в reactivate_user).
            user.deleted_at = None
            user.is_active = True
            user.full_name = name
            user.password_hash = password_hash
            db.flush()
        else:
            user = User(
                full_name=name,
                email=email,
                password_hash=password_hash,
            )
            db.add(user)
            db.flush()                      # нужен user.id до user_roles/consents
            _assign_role(db, user.id, "student")  # RegistrationDataError если нет роли

        # 4. Обязательные consent_records (с request-контекстом).
        for cid in consent_ids:
            db.add(ConsentRecord(
                user_id=user.id,
                consent_id=cid,
                accepted=True,
                ip_address=ip,
                user_agent=user_agent,
            ))

        # 5. Потребить OTP в той же транзакции.
        db.delete(record)

        # 6. Единственный финальный commit — атомарно.
        db.commit()
        db.refresh(user)
        return _user_to_dict(user, db)


def update_last_login(user_id: str) -> None:
    with SessionLocal() as db:
        db.query(User).filter(User.id == int(user_id)).update(
            {"last_login": datetime.now(timezone.utc)},
            synchronize_session=False,
        )
        db.commit()


def update_user_password(user_id: str, password_hash: str) -> None:
    with SessionLocal() as db:
        db.query(User).filter(User.id == int(user_id)).update(
            {
                "password_hash": password_hash,
                "updated_at": datetime.now(timezone.utc),
            },
            synchronize_session=False,
        )
        db.commit()


def _revoke_all_user_sessions_in_session(db, user_id: int) -> None:
    """
    Отзывает все сессии пользователя ВНУТРИ переданной сессии (без commit).

    Выделено отдельным хелпером, чтобы атомарные UoW-функции переиспользовали
    одну логику отзыва и чтобы failure-injection тесты могли точечно подменить
    этот шаг (проверка rollback при сбое именно на отзыве сессий).
    """
    db.query(UserSession).filter(
        UserSession.user_id == user_id
    ).update({"is_revoked": True}, synchronize_session=False)


def _consume_otp(db, record) -> None:
    """
    Удаляет OTP-запись ВНУТРИ переданной сессии (без commit).

    Отдельный хелпер — чтобы потребление OTP было явным последним шагом UoW
    и чтобы failure-injection тесты могли проверить сценарий «сбой после
    обновления пароля, но до фиксации потребления OTP» (rollback всего).
    """
    db.delete(record)


def change_password_atomic(
    user_id: str,
    verify_current,
    new_password_hash: str,
) -> dict:
    """
    Атомарная смена пароля авторизованного пользователя (Stage 31m-fix-b3).

    В ОДНОЙ сессии и ОДНОМ финальном commit:
      1. найти пользователя (не soft-deleted);
      2. проверить текущий пароль через callback verify_current(stored_hash);
      3. обновить password_hash;
      4. отозвать ВСЕ сессии пользователя;
      5. commit.

    verify_current — функция (stored_hash: str) -> bool; bcrypt-проверка
    выполняется внутри транзакции, но до UPDATE строка не блокируется
    (plain SELECT в PostgreSQL не держит row lock), поэтому медленный bcrypt
    не удерживает блокировку. new_password_hash вычисляется ВНЕ транзакции.

    Если verify_current(...) → False, бросается InvalidCurrentPasswordError
    ДО любых изменений: пароль и сессии не трогаются. Сбой на шаге отзыва
    сессий поднимает исключение до commit → транзакция откатывается целиком,
    password_hash остаётся прежним (не частичный успех).

    Бросает:
      UserNotFoundError           — пользователь не найден (→ HTTP 404);
      InvalidCurrentPasswordError — неверный текущий пароль (→ HTTP 400).

    Возвращает dict пользователя (для post-commit soft-fail уведомления).
    """
    with SessionLocal() as db:
        user = (
            db.query(User)
            .filter(User.id == int(user_id), User.deleted_at.is_(None))
            .first()
        )
        if user is None:
            raise UserNotFoundError("Пользователь не найден")

        if not verify_current(user.password_hash):
            raise InvalidCurrentPasswordError("Неверный текущий пароль")

        user.password_hash = new_password_hash
        user.updated_at = datetime.now(timezone.utc)
        _revoke_all_user_sessions_in_session(db, user.id)

        db.commit()
        db.refresh(user)
        return _user_to_dict(user, db)


def password_reset_confirm_atomic(
    email: str,
    code: str,
    new_password_hash: str,
) -> dict:
    """
    Атомарное подтверждение сброса пароля по OTP (Stage 31m-fix-b3).

    В ОДНОЙ сессии и ОДНОМ финальном commit (после успешной OTP-валидации):
      1. validate OTP (без удаления, если код верный);
      2. найти пользователя (не soft-deleted);
      3. обновить password_hash;
      4. отозвать ВСЕ сессии пользователя;
      5. consume (delete) OTP;
      6. commit.

    OTP потребляется ТОЛЬКО вместе с успешным обновлением пароля и отзывом
    сессий — одним commit. Любой сбой core-шага (2–5) поднимает исключение
    до commit → rollback: пароль не меняется, сессии не отзываются, OTP НЕ
    теряется (повторная попытка возможна тем же кодом, пока он не истёк).

    OTP failure-пути (не найден / истёк / превышены попытки / неверный код)
    сохраняют текущую политику attempts: для них выполняется отдельный commit,
    пароль при этом не трогается.

    new_password_hash вычисляется ВНЕ транзакции (на service-слое).

    Бросает:
      ValueError        — проблема OTP (service → HTTP 400);
      UserNotFoundError — OTP верный, но пользователь не найден (→ HTTP 404);
                          OTP при этом НЕ потребляется (rollback).
    """
    email = normalize_email(email)
    now = _utcnow()

    with SessionLocal() as db:
        # ── 1. OTP validation (зеркалит verify_otp / register_confirm_atomic) ──
        record = (
            db.query(OtpVerification)
            .filter(OtpVerification.email == email)
            .first()
        )
        if not record:
            raise ValueError("Код не найден или уже использован")

        if now > record.expires_at:
            db.delete(record)
            db.commit()
            raise ValueError("Срок действия кода истёк. Запросите код заново")

        if record.attempts >= MAX_ATTEMPTS:
            db.delete(record)
            db.commit()
            raise ValueError("Превышено число попыток. Запросите код заново")

        if not _verify_code(code, record.code):
            record.attempts += 1
            remaining = MAX_ATTEMPTS - record.attempts
            if remaining <= 0:
                db.delete(record)
                db.commit()
                raise ValueError(
                    "Неверный код. Попытки исчерпаны. Запросите код заново"
                )
            db.commit()
            raise ValueError(f"Неверный код. Осталось попыток: {remaining}")

        # ── OTP верный. Дальше — core UoW без промежуточных commit. ──────────
        user = (
            db.query(User)
            .filter(User.email == email, User.deleted_at.is_(None))
            .first()
        )
        if user is None:
            # OTP валиден, но пользователя нет (например, удалён между init и
            # confirm): откатываемся, OTP сохраняется (commit не выполняется).
            raise UserNotFoundError("Пользователь не найден")

        user.password_hash = new_password_hash
        user.updated_at = datetime.now(timezone.utc)
        _revoke_all_user_sessions_in_session(db, user.id)

        # Потребить OTP в той же транзакции — последним шагом перед commit.
        _consume_otp(db, record)

        db.commit()
        db.refresh(user)
        return _user_to_dict(user, db)


# ---------------------------------------------------------------------------
# Сессии (заменяют JWT refresh-токены)
# ---------------------------------------------------------------------------

# Debounce для last_active (Stage 26): обновляем не чаще раза в 5 минут.
# touch_session вызывается на КАЖДОМ авторизованном запросе — без debounce
# каждый GET порождает UPDATE по user_sessions (write amplification,
# критично перед Chat MVP polling). Точность last_active — до 5 минут.
TOUCH_SESSION_DEBOUNCE_SECONDS = 300

def create_session(
    user_id: str,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
    expire_days: int = SESSION_EXPIRE_DAYS,
) -> tuple[str, datetime]:
    """
    Создаёт сессию в БД. Возвращает (session_token, expires_at).

    Клиенту возвращается raw token; в user_sessions.id хранится только
    SHA-256 hash — значение из дампа БД нельзя использовать как Bearer.
    """
    token = generate_session_token()
    expires_at = datetime.now(timezone.utc) + timedelta(days=expire_days)

    with SessionLocal() as db:
        db.add(UserSession(
            id=hash_session_token(token),
            user_id=int(user_id),
            ip_address=ip,
            user_agent=user_agent,
            expires_at=expires_at,
        ))
        db.commit()

    return token, expires_at


def find_session(token: str) -> Optional[dict]:
    """Ищет активную (не отозванную, не просроченную) сессию по hash от
    raw token клиента. Возвращает {'user_id': str, 'expires_at': datetime}
    или None. Plaintext-сессии, созданные до перехода на hashing,
    намеренно не находятся (dual-read fallback отсутствует)."""
    with SessionLocal() as db:
        session = (
            db.query(UserSession)
            .filter(
                UserSession.id == hash_session_token(token),
                ~UserSession.is_revoked,
                UserSession.expires_at > datetime.now(timezone.utc),
            )
            .first()
        )
        if not session:
            return None
        return {
            "user_id":    str(session.user_id),
            "expires_at": session.expires_at,
        }


def revoke_session(token: str) -> None:
    """Отзывает одну сессию (logout). Принимает raw token, ищет по hash."""
    with SessionLocal() as db:
        db.query(UserSession).filter(
            UserSession.id == hash_session_token(token)
        ).update({"is_revoked": True}, synchronize_session=False)
        db.commit()


def revoke_all_user_sessions(user_id: str) -> None:
    """
    Отзывает все сессии пользователя в отдельной транзакции.

    Оставлено для не-атомарных flows; атомарные UoW (change_password_atomic,
    password_reset_confirm_atomic) отзывают сессии внутри своей транзакции
    через _revoke_all_user_sessions_in_session, без отдельного commit.
    """
    with SessionLocal() as db:
        _revoke_all_user_sessions_in_session(db, int(user_id))
        db.commit()


def touch_session(token: str) -> None:
    """
    Обновляет last_active для сессии. Принимает raw token, ищет по hash.

    Debounce: UPDATE выполняется только если last_active отсутствует или
    старше TOUCH_SESSION_DEBOUNCE_SECONDS — свежие сессии не трогаются
    (условие в самом UPDATE, без отдельного SELECT — атомарно).

    Revoked/expired сессии намеренно не «оживляются»: их last_active
    не обновляется. Валидацию сессии это не затрагивает — она выполняется
    в find_session на каждом запросе, как раньше.
    """
    now = datetime.now(timezone.utc)
    threshold = now - timedelta(seconds=TOUCH_SESSION_DEBOUNCE_SECONDS)

    with SessionLocal() as db:
        db.query(UserSession).filter(
            UserSession.id == hash_session_token(token),
            ~UserSession.is_revoked,
            UserSession.expires_at > now,
            (UserSession.last_active.is_(None))
            | (UserSession.last_active <= threshold),
        ).update(
            {"last_active": now},
            synchronize_session=False,
        )
        db.commit()
