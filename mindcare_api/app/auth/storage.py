"""
PostgreSQL storage via SQLAlchemy ORM.

Сессии хранятся в user_sessions (таблица из SQL-схемы).
Роль пользователя берётся через JOIN user_roles → roles.
"""

import sys
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.core.normalization import normalize_email
from app.auth.roles import ROLE_PRIORITY, primary_role
from app.db.session import SessionLocal
from app.db.models import (
    User, UserRole, Role, UserSession, Consent, ConsentRecord, OtpVerification,
)
from app.auth.security import generate_session_token, hash_session_token
from app.auth.errors import (
    OtpExpiredError, OtpInvalidError, ProfileActorContextError,
)
# OTP-хелперы переиспользуются для атомарного confirm (один пакет app.auth,
# цикла импортов нет: otp_service не импортирует storage).
from app.auth.otp_service import _verify_code, MAX_ATTEMPTS, _utcnow
from app.core.config import SESSION_EXPIRE_DAYS
from app.audit import Actor, Outcome, Target, record_event
from app.audit.request_context import build_request_context


class RegistrationDataError(RuntimeError):
    """
    Отсутствуют обязательные seed/reference данные (роль или consent-политика)
    при подтверждении регистрации. Подкласс RuntimeError → существующие
    проверки `pytest.raises(RuntimeError)` остаются валидными; service-слой
    может отлавливать этот тип отдельно и мапить на HTTP 500.
    """


class SelfReactivationNotAllowedError(RegistrationDataError):
    """
    Stage 5A-1 (security): попытка публичной self-registration реактивировать
    soft-deleted аккаунт, активные роли которого НЕ равны строго {"student"}
    (staff-роль, пустой набор или student+staff). Подкласс RegistrationDataError
    → уже существующий `except storage.RegistrationDataError` в service мапит его
    в безопасный generic ответ (HTTP 500, audit_code="internal_error") БЕЗ
    раскрытия существования аккаунта и его ролей. Сообщение исключения намеренно
    фиксированное и НЕ содержит email/id/UUID/названий ролей.
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

_ROLE_PRIORITY_INDEX = {name: i for i, name in enumerate(ROLE_PRIORITY)}


def get_active_role_names(db, user_id: int) -> list[str]:
    """
    Все активные (непросроченные) роли пользователя из user_roles.

    Просроченные роли (expires_at в прошлом) исключаются. Результат упорядочен
    по глобальному приоритету ROLE_PRIORITY (admin, supervisor, psychologist,
    student), чтобы primary_role/effective_role были детерминированы, а сам
    список читался предсказуемо.
    """
    rows = (
        db.query(Role.name)
        .join(UserRole, UserRole.role_id == Role.id)
        .filter(UserRole.user_id == user_id)
        .filter(
            UserRole.expires_at.is_(None)
            | (UserRole.expires_at > datetime.now(timezone.utc))
        )
        .all()
    )
    names = {r[0] for r in rows}
    return sorted(names, key=lambda n: _ROLE_PRIORITY_INDEX.get(n, len(ROLE_PRIORITY)))


def _get_primary_role(db, user_id: int) -> Optional[str]:
    """
    Детерминированная primary/default роль (глобальный приоритет) или None.

    НЕ маскирует отсутствие ролей как 'student' — пустой набор возвращает None
    (пользователь без активных ролей не проходит require_role).
    """
    return primary_role(get_active_role_names(db, user_id))


def _user_to_dict(user: User, db) -> dict:
    roles = get_active_role_names(db, user.id)
    return {
        "id":              str(user.id),
        "name":            user.full_name,
        "email":           user.email,
        "hashed_password": user.password_hash,
        "roles":           roles,
        "role":            primary_role(roles),
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
    roles = get_active_role_names(db, user.id)
    return {
        "id":               str(user.id),
        "email":            user.email,
        "full_name":        user.full_name,
        "phone":            user.phone,
        "roles":            roles,
        "role":             primary_role(roles),
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
# Подмножество ALLOWED_PROFILE_FIELDS, реальное изменение которого пишет
# compliance-audit profile_updated (registry metadata enum — только эти два).
AUDITED_PROFILE_FIELDS = frozenset({"full_name", "phone"})


def update_profile_atomic(
    user_id: str,
    updates: dict,
    *,
    actor_role: Optional[str] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    """Атомарно обновляет разрешённые self-поля текущего пользователя.
    Один SessionLocal + один commit.

    updates — только реально переданные поля (exclude_unset): отсутствие ключа
    = не менять, значение None = сбросить. Ключи вне ALLOWED_PROFILE_FIELDS
    игнорируются (defense-in-depth: схема их и так не пропустит).

    Настоящий no-op (Stage 4B-4): мутируются и попадают в `updated_at` ТОЛЬКО
    реально изменившиеся поля (сравнение со значением в БД, не факт
    присутствия в `updates`). `profile_updated` (record_event) пишется только
    если реально изменилось хотя бы одно поле из AUDITED_PROFILE_FIELDS
    (full_name/phone) — theme-only изменение мутирует/бампает updated_at, но
    не порождает compliance-audit запись. Значения full_name/phone нигде не
    логируются — только их имена.

    Raises:
        ProfileActorContextError: нет authenticated actor context (fail-closed,
            wiring-баг; precommit → service мапит в 500/internal_error).
        UserNotFoundError: пользователь не найден (precommit → 404).
    """
    # Fail-closed actor guard — ДО открытия сессии, ДО любых setattr/updated_at.
    if actor_role is None:
        raise ProfileActorContextError(
            "profile update requires authenticated actor context (actor_role)"
        )

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

        # Настоящий diff по ВСЕМ разрешённым полям (включая тему) — до
        # какой-либо мутации ORM.
        changed_all_fields = []
        changed_audited_fields = []
        for field, value in updates.items():
            if field not in ALLOWED_PROFILE_FIELDS:
                continue
            if value != getattr(user, field):
                changed_all_fields.append(field)
                if field in AUDITED_PROFILE_FIELDS:
                    changed_audited_fields.append(field)

        # Мутация — только реально изменившихся полей.
        for field in changed_all_fields:
            setattr(user, field, updates[field])

        # updated_at — только если хоть что-то реально изменилось.
        if changed_all_fields:
            user.updated_at = datetime.now(timezone.utc)

        # profile_updated — только если изменилось хотя бы одно аудируемое
        # поле; ATOMIC/RAISE, в той же транзакции, до commit.
        if changed_audited_fields:
            record_event(
                event="profile_updated",
                actor=Actor.user(int(user_id), actor_role),
                target=Target("user", int(user_id)),
                outcome=Outcome.SUCCESS,
                metadata={"fields": sorted(changed_audited_fields)},
                context=build_request_context(ip=ip, user_agent=user_agent),
                db=db,
            )

        # Stage 5A-2 commit-phase: узкий try ТОЛЬКО вокруг commit (ambiguous
        # outcome). refresh/DTO — вне try; профильный failure на этих шагах не
        # пишется.
        try:
            db.commit()
        except Exception as exc:   # noqa: BLE001 — только commit-фаза
            print(
                "[AUDIT] event=self_profile_update phase=commit "
                f"error={type(exc).__name__}",
                file=sys.stderr,
            )
            raise
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
            raise OtpInvalidError("Код не найден или уже использован")

        if now > record.expires_at:
            db.delete(record)
            db.commit()
            raise OtpExpiredError("Срок действия кода истёк. Начните регистрацию заново")

        if record.attempts >= MAX_ATTEMPTS:
            db.delete(record)
            db.commit()
            raise OtpInvalidError("Превышено число попыток. Начните регистрацию заново")

        if not _verify_code(code, record.code):
            record.attempts += 1
            remaining = MAX_ATTEMPTS - record.attempts
            if remaining <= 0:
                db.delete(record)
                db.commit()
                raise OtpInvalidError(
                    "Неверный код. Попытки исчерпаны. Начните регистрацию заново"
                )
            db.commit()
            raise OtpInvalidError(f"Неверный код. Осталось попыток: {remaining}")

        # ── OTP верный. Дальше — core UoW без промежуточных commit. ──────────
        # Authoritative проверка домена ВНУТРИ транзакции, до создания/реактивации
        # пользователя и до consume OTP. FOR SHARE удерживает разрешённый домен до
        # commit. Отклонение (домен не в активном allowlist, в т.ч. отключён между
        # init и confirm) поднимает EmailDomainNotAllowedError до commit → rollback,
        # OTP НЕ потребляется. Применяется и к реактивации soft-deleted аккаунта.
        from app.email_domains.storage import assert_email_domain_allowed_in_tx
        assert_email_domain_allowed_in_tx(db, email)

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
            # Stage 5A-1 (security): публичная self-registration может
            # реактивировать ТОЛЬКО чистый student-аккаунт. Проверяем реальные
            # активные роли ДО любой мутации/flush/audit/consume OTP. Staff-роль,
            # пустой набор или student+staff → fail closed (typed internal
            # precommit error, generic ответ без раскрытия ролей/существования).
            active_roles = set(get_active_role_names(db, user.id))
            if active_roles != {"student"}:
                raise SelfReactivationNotAllowedError(
                    "self-reactivation is not permitted for this account"
                )
            # Реактивация: id/uuid/роль сохраняются (как в reactivate_user).
            user.deleted_at = None
            user.is_active = True
            user.full_name = name
            user.password_hash = password_hash
            db.flush()
            # Stage 5A-1: entity-привязанное lifecycle-событие восстановления
            # soft-deleted аккаунта. Actor = сам восстановленный student, target =
            # этот же аккаунт. ATOMIC (db=db) в той же транзакции до единственного
            # commit — сбой аудита откатывает реактивацию/consent/consume OTP.
            # Только reactivation-ветка; новая регистрация его НЕ пишет. ПДн
            # (email/ФИО/OTP/hash/consent) в audit не попадают: metadata={}.
            record_event(
                event="user_reactivated",
                actor=Actor.user(user.id, "student"),
                target=Target("user", user.id),
                outcome=Outcome.SUCCESS,
                metadata={},
                context=build_request_context(ip=ip, user_agent=user_agent),
                db=db,
            )
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
            raise OtpInvalidError("Код не найден или уже использован")

        if now > record.expires_at:
            db.delete(record)
            db.commit()
            raise OtpExpiredError("Срок действия кода истёк. Запросите код заново")

        if record.attempts >= MAX_ATTEMPTS:
            db.delete(record)
            db.commit()
            raise OtpInvalidError("Превышено число попыток. Запросите код заново")

        if not _verify_code(code, record.code):
            record.attempts += 1
            remaining = MAX_ATTEMPTS - record.attempts
            if remaining <= 0:
                db.delete(record)
                db.commit()
                raise OtpInvalidError(
                    "Неверный код. Попытки исчерпаны. Запросите код заново"
                )
            db.commit()
            raise OtpInvalidError(f"Неверный код. Осталось попыток: {remaining}")

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
    expire_days: float = SESSION_EXPIRE_DAYS,
    impersonator_user_id: Optional[int] = None,
) -> tuple[str, datetime]:
    """
    Создаёт сессию в БД. Возвращает (session_token, expires_at).

    Клиенту возвращается raw token; в user_sessions.id хранится только
    SHA-256 hash — значение из дампа БД нельзя использовать как Bearer.

    impersonator_user_id (ADR-025): если задан — это impersonation-сессия,
    созданная администратором от имени user_id. Отметка серверная, для
    атрибуции; сам токен по правам эквивалентен обычной сессии user_id.
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
            impersonator_user_id=impersonator_user_id,
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
            "user_id":              str(session.user_id),
            "expires_at":           session.expires_at,
            "impersonator_user_id": session.impersonator_user_id,
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
