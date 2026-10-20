"""
Единственная карта message_code → текст system-сообщения (ADR-029).

В outbox (system_message_intents) хранится только код: текста там нет, поэтому
намерения не содержат ни plaintext, ни ПДн. Тексты фиксированные, plain text
без HTML; номер студенческого билета и свободное пояснение отказа в них не
попадают никогда — пояснение пользователь видит только в настройках.

Внутренняя ссылка — обычная строка пути. Кликабельной её делает frontend
(LinkifiedText, точный allowlist, только для system-сообщений).
"""
from types import MappingProxyType

STUDENT_VERIFICATION_SETTINGS_PATH = "/student/settings#student-verification"

STUDENT_VERIFICATION_INVITE = "student_verification_invite"
STUDENT_VERIFICATION_APPROVED = "student_verification_approved"
STUDENT_VERIFICATION_REJECTED = "student_verification_rejected"

MESSAGE_TEMPLATES = MappingProxyType({
    STUDENT_VERIFICATION_INVITE: (
        "Вы можете подтвердить, что являетесь студентом Донецкого "
        "государственного университета. Выберите факультет и укажите номер "
        "студенческого билета в настройках аккаунта.\n\n"
        f"Открыть раздел: {STUDENT_VERIFICATION_SETTINGS_PATH}"
    ),
    STUDENT_VERIFICATION_APPROVED: "Ваш статус студента ДонГУ подтверждён.",
    STUDENT_VERIFICATION_REJECTED: (
        "Подтверждение статуса студента ДонГУ отклонено. Посмотрите пояснение "
        "и исправьте данные в настройках.\n\n"
        f"Открыть раздел: {STUDENT_VERIFICATION_SETTINGS_PATH}"
    ),
})


def invite_event_key(user_id: int) -> str:
    """Ключ приглашения — стабилен для пользователя (одно приглашение)."""
    return f"student_verification_invite:user:{int(user_id)}"


def result_event_key(request_uuid) -> str:
    """Ключ результата — свой для каждой заявки (повторная — свой ключ)."""
    return f"student_verification_result:{request_uuid}"
