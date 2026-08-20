"""
Fixtures for API/integration tests (tests/integration/).

Prerequisites (Stage 1 — isolated test DB):
  - Запускать ТОЛЬКО через isolated runner (scripts/isolated_test_db.py) или
    с явными ENV=test и TEST_DATABASE_URL на одноразовую mindcare_test_<random>.
    Прямой прогон против dev-БД невозможен: см. fail-fast ниже.
  - Схема применяется runner'ом через `alembic upgrade head`; seed — в lifespan
    TestClient (init_db). EMAIL_MODE=dev — реальные письма не шлются.

These fixtures are scoped to tests/integration/ only and do NOT affect the
unit tests in tests/  (test_change_password, test_encryption, test_normalization).
"""

import os
import re
import uuid
from unittest.mock import patch

import bcrypt
import pytest
from sqlalchemy.engine import make_url
from starlette.testclient import TestClient

# ── Fail-fast: integration только на изолированной test-БД ────────────────────
# Выполняется ДО import app.main / app.db.session (engine связывается на импорте).
# Root tests/conftest.py уже выставил DATABASE_URL (test URL или sentinel).
if os.environ.get("MINDCARE_UNIT_ONLY") == "1":
    raise RuntimeError("Integration-тесты недоступны в unit-only режиме.")
if os.environ.get("ENV") != "test":
    raise RuntimeError("Integration-тесты требуют ENV=test и isolated test DB.")
if not os.environ.get("TEST_DATABASE_URL"):
    raise RuntimeError("Integration-тесты требуют TEST_DATABASE_URL (test DB).")
_active_db = make_url(os.environ.get("DATABASE_URL", "")).database or ""
if not re.match(r"^mindcare_test_[a-z0-9]+$", _active_db):
    raise RuntimeError(
        "DATABASE_URL integration-тестов не является isolated test DB "
        "(ожидается mindcare_test_<random>)."
    )

from app.main import app
from app.auth import storage as auth_storage
from app.db.session import SessionLocal
from app.db.models import (
    AllowedEmailDomain, Appointment, ChatAttachment, ChatConversation,
    ChatMessage, ConsentRecord, DiaryEntry, GroupSession,
    GroupSessionRegistration, MeetingType, OtpVerification, Role,
    TherapyEngagement, UnregisteredStudentCard, User, UserRole,
)

# Литеральный test-префикс "integ_" (или "integ-" для доменов, где "_"
# недопустим в hostname). Экранируем "_" как SQL LIKE wildcard (matches any
# single char) через escape="\\", иначе "integ_%" случайно матчит "integX...".
_INTEG_PREFIX_LIKE = r"integ\_%"
_INTEG_LIKE_ESCAPE = "\\"

# Test-домены (allowed_email_domains), созданные тестами, обязаны начинаться
# с этого префикса — см. reset_email_domains ниже. Домен не может содержать
# "_", поэтому используем дефис (уже принятая конвенция в существующих тестах:
# test_allowed_email_domains_api.py, test_email_domain_policy.py,
# test_allowed_email_domains_concurrency.py).
TEST_DOMAIN_PREFIX = "integ-"


# ─── HTTP client ──────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def client():
    """
    Session-scoped TestClient backed by the real dev PostgreSQL DB.
    Runs the FastAPI lifespan (init_db + seed) exactly once per test session.
    """
    # client=("127.0.0.1", 50000) provides a valid inet address for DB columns.
    # Default "testclient" is not a valid inet value and causes DataError.
    with TestClient(app, client=("127.0.0.1", 50000)) as c:
        yield c


# ─── Test email ───────────────────────────────────────────────────────────────

# Разрешённый seeded-домен для тестов, которые создают аккаунты через guarded-пути
# (register/confirm, POST /api/admin/users, POST /api/supervisor/students). Домен
# email-allowlist политика проверяет именно на этих путях, поэтому создавать новые
# аккаунты нужно на активном домене из seed (migration c7f1a9e4d2b8).
ALLOWED_TEST_DOMAIN = "donnu.ru"

# example.com в allowlist НЕ входит (foreign): используется для сценариев уже
# существующих пользователей (login/reset) через auth_storage.save_user, который
# domain-политику НЕ проходит (он не в runtime creation-пути).
FOREIGN_TEST_DOMAIN = "example.com"


@pytest.fixture
def test_email():
    """
    Unique per-test email на РАЗРЕШЁННОМ домене (donnu.ru) — годится для тестов,
    создающих новые аккаунты через guarded-эндпоинты. Cleanup удаляет все
    integ_*-записи независимо от домена.
    """
    return f"integ_{uuid.uuid4().hex[:12]}@{ALLOWED_TEST_DOMAIN}"


@pytest.fixture
def foreign_test_email():
    """
    Unique per-test email на НЕразрешённом домене (example.com) — для проверки,
    что политика отклоняет создание, и для foreign login/reset существующих
    аккаунтов, заводимых напрямую через save_user.
    """
    return f"integ_{uuid.uuid4().hex[:12]}@{FOREIGN_TEST_DOMAIN}"


# ─── Email / OTP interception ─────────────────────────────────────────────────

@pytest.fixture
def capture_emails():
    """
    Patches app.services._smtp.send_email and captures OTP codes by recipient.

    Yields a dict: { to_address: [code, ...] }

    The key is the pre-normalization address passed to send_email (i.e. the
    address the service received from the request body after pydantic parsed it,
    but before storage normalized it).  Use capture_emails[init_email][-1] to
    get the most recently sent code.
    """
    sent: dict[str, list[str]] = {}

    def _fake(to: str, subject: str, body: str, html: str | None = None) -> None:
        match = re.search(r"Ваш код: (\d{6})", body)
        if match:
            sent.setdefault(to, []).append(match.group(1))

    # email_service.py does `from app.services._smtp import send_email`,
    # so we must patch the imported name in that module, not the source.
    with patch("app.services.email_service.send_email", side_effect=_fake):
        yield sent


# ─── Rate limiter isolation ───────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """
    Сбрасывает in-memory rate limiter перед каждым тестом.

    Все integration-тесты ходят через один TestClient с одним IP (127.0.0.1),
    поэтому без сброса IP-лимиты auth-эндпоинтов срабатывали бы на сумме
    запросов всей сессии, а не одного теста.
    """
    from app.core import rate_limit
    rate_limit.reset()
    yield


# ─── DB cleanup ───────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def cleanup_test_records():
    """
    Deletes all integ_*-prefixed test records from the dev DB after each test.

    "integ_" — reserved literal prefix for ALL test-created records (emails on
    any domain: donnu.ru allowed / example.com foreign — see test_email /
    foreign_test_email above; meeting type names; unregistered-card full
    names). LIKE patterns escape "_" (SQL LIKE wildcard for "any single char")
    via escape="\\" so "integ_%" matches only the literal prefix, not
    "integX...".

    Cleanup order respects FK constraints:
      1. chat_messages → chat_conversations → therapy_engagements
         (chat FKs — ON DELETE RESTRICT: иначе cascade-удаление engagement
          при удалении user заблокируется беседой)
      2. consent_records (ondelete=SET NULL — must delete explicitly)
      3. users            (cascades user_roles, user_sessions, profiles, etc.)
      4. otp_verifications (no FK to users — standalone)
    """
    yield
    with SessionLocal() as db:
        ids = [
            row.id
            for row in db.query(User.id)
            .filter(User.email.like(_INTEG_PREFIX_LIKE, escape=_INTEG_LIKE_ESCAPE))
            .all()
        ]
        if ids:
            eng_ids = [
                row.id
                for row in db.query(TherapyEngagement.id).filter(
                    TherapyEngagement.client_id.in_(ids)
                    | TherapyEngagement.psychologist_id.in_(ids)
                ).all()
            ]
            # Беседы integ-пользователей: system (по recipient_id) + engagement (по eng_ids).
            conv_ids = set(
                row.id
                for row in db.query(ChatConversation.id).filter(
                    ChatConversation.recipient_id.in_(ids)
                ).all()
            )
            if eng_ids:
                conv_ids |= set(
                    row.id
                    for row in db.query(ChatConversation.id).filter(
                        ChatConversation.engagement_id.in_(eng_ids)
                    ).all()
                )
            conv_ids = list(conv_ids)
            if conv_ids:
                # chat_attachments FK → chat_messages (RESTRICT): удалять до messages.
                db.query(ChatAttachment).filter(
                    ChatAttachment.conversation_id.in_(conv_ids)
                ).delete(synchronize_session=False)
                db.query(ChatMessage).filter(
                    ChatMessage.conversation_id.in_(conv_ids)
                ).delete(synchronize_session=False)
                db.query(ChatConversation).filter(
                    ChatConversation.id.in_(conv_ids)
                ).delete(synchronize_session=False)
            if eng_ids:
                db.query(TherapyEngagement).filter(
                    TherapyEngagement.id.in_(eng_ids)
                ).delete(synchronize_session=False)
            db.query(DiaryEntry).filter(
                DiaryEntry.student_id.in_(ids)
            ).delete(synchronize_session=False)
            db.query(ConsentRecord).filter(
                ConsentRecord.user_id.in_(ids)
            ).delete(synchronize_session=False)
            db.query(User).filter(
                User.id.in_(ids)
            ).delete(synchronize_session=False)
        db.query(OtpVerification).filter(
            OtpVerification.email.like(_INTEG_PREFIX_LIKE, escape=_INTEG_LIKE_ESCAPE)
        ).delete(synchronize_session=False)

        # Тестовые meeting types и их групповые занятия (префикс integ_).
        # group_sessions.meeting_type_id — ON DELETE RESTRICT, поэтому
        # сначала удаляем сессии (и их регистрации), затем сами типы.
        mt_ids = [
            row.id
            for row in db.query(MeetingType.id)
            .filter(
                MeetingType.name.like(_INTEG_PREFIX_LIKE, escape=_INTEG_LIKE_ESCAPE)
            )
            .all()
        ]
        if mt_ids:
            gs_ids = [
                row.id
                for row in db.query(GroupSession.id)
                .filter(GroupSession.meeting_type_id.in_(mt_ids))
                .all()
            ]
            if gs_ids:
                db.query(GroupSessionRegistration).filter(
                    GroupSessionRegistration.group_session_id.in_(gs_ids)
                ).delete(synchronize_session=False)
                db.query(GroupSession).filter(
                    GroupSession.id.in_(gs_ids)
                ).delete(synchronize_session=False)
            db.query(MeetingType).filter(
                MeetingType.id.in_(mt_ids)
            ).delete(synchronize_session=False)

        # Тестовые карточки незарегистрированных студентов (full_name LIKE 'integ_%').
        # appointments по карточке (FK RESTRICT) удаляем первыми; обычно их уже
        # снёс CASCADE при удалении психолога, но подстрахуемся явным удалением.
        card_ids = [
            row.id
            for row in db.query(UnregisteredStudentCard.id)
            .filter(
                UnregisteredStudentCard.full_name.like(
                    _INTEG_PREFIX_LIKE, escape=_INTEG_LIKE_ESCAPE
                )
            )
            .all()
        ]
        if card_ids:
            db.query(Appointment).filter(
                Appointment.unregistered_student_card_id.in_(card_ids)
            ).delete(synchronize_session=False)
            db.query(UnregisteredStudentCard).filter(
                UnregisteredStudentCard.id.in_(card_ids)
            ).delete(synchronize_session=False)
        db.commit()


# ─── Email allowlist isolation ────────────────────────────────────────────────

@pytest.fixture
def reset_email_domains():
    """
    Изолирует изменения allowed_email_domains, сделанные тестом (snapshot/restore).

    Snapshot ДО теста: id, domain, is_active, comment, updated_at ВСЕХ
    существующих строк — не только seed-набора, но и любых уже присутствующих
    в dev-БД admin-доменов (не хардкодим список; поэтому фикстура не может
    случайно затереть ручные изменения администратора dev-окружения).

    Teardown:
      - удаляет только строки, ОТСУТСТВОВАВШИЕ в snapshot И начинающиеся с
        TEST_DOMAIN_PREFIX ("integ-") — т.е. заведомо созданные этим тестом.
        Двойное условие (новая строка + префикс) — защита от случайного
        удаления домена, добавленного вручную кем-то ещё во время прогона;
      - восстанавливает is_active/comment/updated_at КАЖДОЙ строки, БЫВШЕЙ в
        snapshot, к её исходным значениям — включая пользовательские
        admin-домены dev-БД, не только seed;
      - НЕ удаляет и не меняет новые строки без TEST_DOMAIN_PREFIX (не
        созданы этим тестом — оставляем как есть).

    audit_log (append-only) не чистится — это ожидаемо.
    """
    with SessionLocal() as db:
        before = {
            row.id: {
                "is_active": row.is_active,
                "comment": row.comment,
                "updated_at": row.updated_at,
            }
            for row in db.query(AllowedEmailDomain).all()
        }

    yield

    with SessionLocal() as db:
        current_ids = {
            row.id for row in db.query(AllowedEmailDomain.id).all()
        }
        new_ids = current_ids - before.keys()
        if new_ids:
            db.query(AllowedEmailDomain).filter(
                AllowedEmailDomain.id.in_(new_ids),
                AllowedEmailDomain.domain.like(f"{TEST_DOMAIN_PREFIX}%"),
            ).delete(synchronize_session=False)

        for row_id, snapshot in before.items():
            db.query(AllowedEmailDomain).filter(
                AllowedEmailDomain.id == row_id,
            ).update(snapshot, synchronize_session=False)

        db.commit()


# ─── Test user factory ────────────────────────────────────────────────────────

def create_test_user(email: str, password: str = "SecurePass42!") -> dict:
    """
    Insert a test user directly into the dev DB via auth storage.
    Use this in tests that need a pre-existing user (login tests, reset tests).
    The user gets the 'student' role; no consent_records are created.
    """
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    return auth_storage.save_user({
        "name":            "Integration Test User",
        "email":           email,
        "hashed_password": pw_hash,
        "role":            "student",
    })


# ─── Multi-role helpers (ADR-018) ─────────────────────────────────────────────

def add_user_role(user_id: int, role_name: str, expires_at=None) -> None:
    """
    Добавляет пользователю активную (или просроченную, если expires_at в прошлом)
    роль напрямую в user_roles. Идемпотентно по (user_id, role_id).
    """
    with SessionLocal() as db:
        role = db.query(Role).filter(Role.name == role_name).first()
        if role is None:
            raise RuntimeError(f"Роль {role_name} не сидирована в тестовой БД")
        existing = (
            db.query(UserRole)
            .filter(UserRole.user_id == user_id, UserRole.role_id == role.id)
            .first()
        )
        if existing is not None:
            existing.expires_at = expires_at
        else:
            db.add(UserRole(
                user_id=user_id, role_id=role.id, expires_at=expires_at,
            ))
        db.commit()


def remove_all_user_roles(user_id: int) -> None:
    """Снимает все роли пользователя (для сценария 'нет активных ролей')."""
    with SessionLocal() as db:
        db.query(UserRole).filter(
            UserRole.user_id == user_id
        ).delete(synchronize_session=False)
        db.commit()


def create_multi_role_user(
    client,
    roles: list[str],
    password: str = "SecurePass42!",
) -> tuple[str, int, str]:
    """
    Создаёт пользователя с несколькими активными ролями и логинит его.

    Возвращает (session_token, user_id, email). Первая роль назначается через
    save_user, остальные добираются прямым insert в user_roles.
    """
    email = f"integ_multirole_{uuid.uuid4().hex[:10]}@example.com"
    primary = roles[0] if roles else "student"
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    user = auth_storage.save_user({
        "name":            f"MultiRole {uuid.uuid4().hex[:6]}",
        "email":           email,
        "hashed_password": pw_hash,
        "role":            primary,
    })
    user_id = int(user["id"])
    for role_name in roles[1:]:
        add_user_role(user_id, role_name)

    r = client.post(
        "/api/auth/login", json={"email": email, "password": password},
    )
    assert r.status_code == 200, r.text
    return r.json()["session_token"], user_id, email
