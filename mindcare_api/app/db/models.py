"""
Compatibility shim — обратная совместимость с импортами вида:
    from app.db.models import User, Role, AuthLog, ...

Все реальные определения теперь в app/db/models/ (пакет).
Этот файл просто реэкспортирует их под теми же именами.

НЕ добавляй сюда новые модели — используй app/db/models/<module>.py.
"""

# Полный реэкспорт из нового пакета
from app.db.models import (  # noqa: F401
    # auth
    Role,
    Permission,
    RolePermission,
    User,
    UserRole,
    UserSession,
    RefreshToken,
    UserMfaMethod,
    # profiles
    StudentProfile,
    PsychologistProfile,
    EmergencyContact,
    # consents
    Consent,
    ConsentRecord,
    # media
    MediaFile,
    MediaVersion,
    # content
    Category,
    Article,
    ArticleCategory,
    News,
    HelpResource,
    QuestionsAnswers,
    # diagnostics
    Test,
    TestCategory,
    Question,
    Option,
    QuestionMedia,
    OptionMedia,
    TestResult,
    TestResultScale,
    StudentAnswer,
    # consultations
    TherapyEngagement,
    ScheduleRule,
    ScheduleException,
    Appointment,
    SessionNote,
    # notifications
    NotificationTemplate,
    Notification,
    # audit
    AuditLog,
    AuthLog,
    DataChangeLog,
    # otp
    OtpVerification,
)
