"""
Центральный реэкспорт всех ORM-моделей.

ПОРЯДОК ИМПОРТА ВАЖЕН (FK-зависимости):
  auth        — Role, Permission, User (базовые сущности, на которые FK у всех остальных)
  profiles    — StudentProfile, PsychologistProfile (FK → users)
  consents    — Consent, ConsentRecord (FK → users)
  media       — MediaFile, MediaVersion (FK → users)
  content     — Category, Article, News, ... (FK → users, media)
  diagnostics — Test, Question, Option, TestResult, ... (FK → users, categories, media)
  consultations — TherapyEngagement, Appointment, SessionNote, ... (FK → users)
  notifications — NotificationTemplate, Notification (FK → users)
  audit       — AuditLog, AuthLog, DataChangeLog (FK → users)
  otp         — OtpVerification (standalone)

Все модули импортируются здесь, чтобы Base.metadata содержал все 41 таблицу
до вызова Alembic autogenerate или любого кода, читающего metadata.tables.

Схема БД управляется через Alembic (mindcare_api/alembic/).
"""

# ── auth ──────────────────────────────────────────────────────────────────────
from app.db.models.auth import (  # noqa: F401
    Role,
    Permission,
    RolePermission,
    User,
    UserRole,
    UserSession,
    RefreshToken,
    UserMfaMethod,
)

# ── profiles ──────────────────────────────────────────────────────────────────
from app.db.models.profiles import (  # noqa: F401
    StudentProfile,
    PsychologistProfile,
    EmergencyContact,
)

# ── consents ──────────────────────────────────────────────────────────────────
from app.db.models.consents import (  # noqa: F401
    Consent,
    ConsentRecord,
)

# ── legal basis ───────────────────────────────────────────────────────────────
from app.db.models.legal_basis import UserLegalBasisRecord  # noqa: F401

# ── media ─────────────────────────────────────────────────────────────────────
from app.db.models.media import (  # noqa: F401
    MediaFile,
    MediaVersion,
)

# ── content ───────────────────────────────────────────────────────────────────
from app.db.models.content import (  # noqa: F401
    Category,
    Article,
    ArticleCategory,
    News,
    HelpResource,
    QuestionsAnswers,
    Tag,
    ArticleTag,
    NewsTag,
    TestTag,
)

# ── diagnostics ───────────────────────────────────────────────────────────────
from app.db.models.diagnostics import (  # noqa: F401
    Test,
    TestCategory,
    Question,
    Option,
    QuestionMedia,
    OptionMedia,
    TestResult,
    TestResultScale,
    StudentAnswer,
)

# ── consultations ─────────────────────────────────────────────────────────────
from app.db.models.consultations import (  # noqa: F401
    TherapyEngagement,
    ScheduleRule,
    ScheduleException,
    Appointment,
    SessionNote,
)

# ── chat (FK → therapy_engagements, users) ───────────────────────────────────
from app.db.models.chat import (  # noqa: F401
    ChatConversation,
    ChatMessage,
    ChatAttachment,
)

# ── notifications ─────────────────────────────────────────────────────────────
from app.db.models.notifications import (  # noqa: F401
    NotificationTemplate,
    Notification,
)

# ── audit ─────────────────────────────────────────────────────────────────────
from app.db.models.audit import (  # noqa: F401
    AuditLog,
    AuthLog,
    DataChangeLog,
)

# ── otp ───────────────────────────────────────────────────────────────────────
from app.db.models.otp import OtpVerification  # noqa: F401

__all__ = [
    # auth
    "Role", "Permission", "RolePermission",
    "User", "UserRole", "UserSession", "RefreshToken", "UserMfaMethod",
    # profiles
    "StudentProfile", "PsychologistProfile", "EmergencyContact",
    # consents
    "Consent", "ConsentRecord",
    # legal basis
    "UserLegalBasisRecord",
    # media
    "MediaFile", "MediaVersion",
    # content
    "Category", "Article", "ArticleCategory", "News", "HelpResource", "QuestionsAnswers",
    "Tag", "ArticleTag", "NewsTag", "TestTag",
    # diagnostics
    "Test", "TestCategory", "Question", "Option", "QuestionMedia", "OptionMedia",
    "TestResult", "TestResultScale", "StudentAnswer",
    # consultations
    "TherapyEngagement", "ScheduleRule", "ScheduleException", "Appointment", "SessionNote",
    # chat
    "ChatConversation", "ChatMessage", "ChatAttachment",
    # notifications
    "NotificationTemplate", "Notification",
    # audit
    "AuditLog", "AuthLog", "DataChangeLog",
    # otp
    "OtpVerification",
]
