"""
Stage 4A — immutable event registry + validate_registry.

REGISTRY владеет destination / actor-role policy / tx_mode / failure_policy / metadata
allowlist для каждого стабильного события. Caller не выбирает таблицу и не
переопределяет транзакционный режим. Регистрируются нормализованные имена текущих
событий (перенос writer'ов — Stage 4B).

validate_registry() принимает произвольный набор specs (для негативных тестов без
изменения production REGISTRY) и вызывается на импорте против REGISTRY (fail-fast).
"""
from __future__ import annotations

import re
from types import MappingProxyType
from typing import Iterable, Mapping

from app.audit.contracts import (
    USER_ROLES, ActorPolicy, AuditError, Destination, DescriptionPolicy, EventSpec,
    FailurePolicy, FieldSpec, Outcome, StringFormat, TargetPolicy, TxMode,
)
from app.audit.validation import is_denylisted_key

_NAME_MAX = {Destination.AUTH_LOG: 150, Destination.AUDIT_LOG: 100}
_FAILURE_CODE_MAX = 100
_STATIC_DESC_MAX = 200
_ATTACHMENT_MAX_BYTES = 104_857_600  # 100 MiB

# Стабильные машинные имена: только lowercase snake_case, начинается с буквы.
_STABLE_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")

_VALID_FIELD_TYPES = frozenset({"str", "int", "bool", "str_list", "int_list"})
_STRING_FIELD_TYPES = frozenset({"str", "str_list"})
_INT_FIELD_TYPES = frozenset({"int", "int_list"})

# ── переиспользуемые FieldSpec ────────────────────────────────────────────────
_ROLE_LIST = FieldSpec(type="str_list", fmt=StringFormat.ENUM, enum=USER_ROLES)
_ROLE_DIFF_META = MappingProxyType({
    "roles_before": _ROLE_LIST, "roles_after": _ROLE_LIST,
    "added": _ROLE_LIST, "removed": _ROLE_LIST,
})
_PROFILE_META = MappingProxyType({
    "fields": FieldSpec(
        type="str_list", fmt=StringFormat.ENUM,
        enum=frozenset({"full_name", "phone"}),
    ),
})
_ATTACH_UPLOAD_META = MappingProxyType({
    "file_size": FieldSpec(type="int", min_value=0, max_value=_ATTACHMENT_MAX_BYTES),
    "mime_type": FieldSpec(type="str", fmt=StringFormat.MIME_TYPE, max_len=100),
})
_EMPTY: Mapping[str, FieldSpec] = MappingProxyType({})

# ── Stage 8: read-only admin viewer журналов ─────────────────────────────────
# Публичные закрытые множества: имя журнала и СТАБИЛЬНЫЕ ИМЕНА применённых
# фильтров. Значения фильтров (даты, UUID, id, email) в metadata не попадают
# никогда — только факт «фильтр такого рода был применён».
AUDIT_JOURNALS: frozenset = frozenset({"audit_log", "auth_log", "data_change_log"})
AUDIT_FILTER_KEYS: frozenset = frozenset({
    "date_range",     # применён всегда: даже умолчание задаёт 7-дневное окно
    "actor",          # actor_uuid
    "actor_kind",
    "actor_role",
    "event",          # event_type (audit) / event (auth)
    "outcome",
    "entity",         # entity_type
    "record",         # entity_id / record_id
    "target",         # target_user_uuid
    "success",
    "table",          # table_name
    "operation",
    "access_events",  # только при include_access_events=true
})
_ACCESS_META = MappingProxyType({
    "journal": FieldSpec(
        type="str", fmt=StringFormat.ENUM, enum=AUDIT_JOURNALS, max_len=32,
    ),
    "filter_keys": FieldSpec(
        type="str_list", fmt=StringFormat.ENUM, enum=AUDIT_FILTER_KEYS, max_len=32,
    ),
})
# Stage 5B-1: linked-event несёт псевдонимный внутренний id субъекта (не ПДн:
# email/UUID/ФИО не пишутся) для самостоятельной прослеживаемости card→user.
_CARD_LINK_META = MappingProxyType({
    "linked_user_id": FieldSpec(type="int", min_value=1),
})


def _spec(
    name, destination, actor_policy, roles, target_policy, entity_type,
    outcomes, failure_codes, metadata, tx_mode, failure_policy,
    user_email_allowed=False,
) -> EventSpec:
    return EventSpec(
        name=name, destination=destination, actor_policy=actor_policy,
        allowed_actor_roles=frozenset(roles),
        target_policy=target_policy, entity_type=entity_type,
        allowed_outcomes=frozenset(outcomes),
        allowed_failure_codes=frozenset(failure_codes),
        metadata_schema=metadata if isinstance(metadata, MappingProxyType)
        else MappingProxyType(dict(metadata)),
        tx_mode=tx_mode, failure_policy=failure_policy,
        user_email_allowed=user_email_allowed,
    )


def _auth(name, actor_policy, roles, outcomes, failure_codes, email=False) -> EventSpec:
    return _spec(
        name, Destination.AUTH_LOG, actor_policy, roles,
        TargetPolicy.FORBIDDEN, None, outcomes, failure_codes, _EMPTY,
        TxMode.INDEPENDENT, FailurePolicy.SOFT, user_email_allowed=email,
    )


def _audit_ok(name, roles, entity_type, metadata=_EMPTY,
              tx_mode=TxMode.ATOMIC, failure_policy=FailurePolicy.RAISE,
              actor_policy=ActorPolicy.USER_REQUIRED) -> EventSpec:
    return _spec(
        name, Destination.AUDIT_LOG, actor_policy, roles,
        TargetPolicy.REQUIRED, entity_type, {Outcome.SUCCESS}, frozenset(),
        metadata, tx_mode, failure_policy,
    )


def _audit_fail(name, roles, failure_codes) -> EventSpec:
    """Stage 5A-2 — durable best-effort failure событие. Фиксированный контракт:
    AUDIT_LOG / USER_REQUIRED / target FORBIDDEN / entity_type=None / outcomes
    {FAILURE} / metadata пусто / INDEPENDENT / SOFT / description NONE."""
    return _spec(
        name, Destination.AUDIT_LOG, ActorPolicy.USER_REQUIRED, roles,
        TargetPolicy.FORBIDDEN, None, {Outcome.FAILURE}, failure_codes,
        _EMPTY, TxMode.INDEPENDENT, FailurePolicy.SOFT,
    )


_STAFF = {"student", "psychologist", "supervisor", "admin"}
_CHAT_PARTIES = {"student", "psychologist"}

_ALL: list[EventSpec] = []

# ── AUTH_LOG ─────────────────────────────────────────────────────────────────
_ALL += [
    _auth("registration_succeeded", ActorPolicy.USER_REQUIRED, {"student"},
          {Outcome.SUCCESS}, frozenset(), email=True),
    _auth("registration_failed", ActorPolicy.ANONYMOUS_ONLY, frozenset(),
          {Outcome.FAILURE},
          {"otp_invalid", "otp_expired", "domain_not_allowed", "internal_error"},
          email=True),
    _auth("login", ActorPolicy.USER_REQUIRED, _STAFF, {Outcome.SUCCESS},
          frozenset(), email=True),
    # no_active_roles (ADR-018) — штатный доменный отказ: credentials верны, но
    # активных ролей нет. Отдельное СОБЫТИЕ не заводится: это исход того же
    # failed_login, поэтому registry count не меняется.
    _auth("failed_login", ActorPolicy.ANONYMOUS_ONLY, frozenset(),
          {Outcome.FAILURE},
          {"invalid_credentials", "no_active_roles", "internal_error"},
          email=True),
    _auth("logout", ActorPolicy.USER_REQUIRED, _STAFF, {Outcome.SUCCESS},
          frozenset()),
    _auth("password_change", ActorPolicy.USER_REQUIRED, _STAFF, {Outcome.SUCCESS},
          frozenset()),
    _auth("password_reset", ActorPolicy.ANONYMOUS_ONLY, frozenset(),
          {Outcome.SUCCESS, Outcome.FAILURE},
          {"otp_invalid", "otp_expired", "user_not_found", "password_policy",
           "internal_error"}, email=True),
]

# ── AUDIT_LOG: роли, пользователи, supervisor, домены ────────────────────────
_ALL += [
    _audit_ok("admin_role_add", {"admin"}, "user", _ROLE_DIFF_META),
    _audit_ok("admin_role_remove", {"admin"}, "user", _ROLE_DIFF_META),
    _audit_ok("admin_role_update", {"admin"}, "user", _ROLE_DIFF_META),
    _audit_ok("admin_user_created", {"admin"}, "user"),
    _audit_ok("admin_user_updated", {"admin"}, "user"),
    _audit_ok("admin_user_deleted", {"admin"}, "user"),
    # Stage 5A-1: lifecycle success events. is_active-переход НЕ дублируется в
    # admin_user_updated (тот — только full_name/phone). ATOMIC/RAISE, metadata пуст.
    _audit_ok("admin_user_activated", {"admin"}, "user"),
    _audit_ok("admin_user_deactivated", {"admin"}, "user"),
    # Восстановление soft-deleted аккаунта при self-registration (actor = сам
    # восстановленный student). Пишется только в reactivation-ветке.
    _audit_ok("user_reactivated", {"student"}, "user"),
    _audit_ok("profile_updated", _STAFF, "user", _PROFILE_META),
    # supervisor-операции доступны и supervisor, и admin (routes:
    # resolve_role_or_403(allowed={"admin","supervisor"})) — actor_role может быть
    # "admin", поэтому оба разрешены (иначе admin-инициированная операция → 500).
    _audit_ok("supervisor_create_student", {"supervisor", "admin"}, "user"),
    _audit_ok("supervisor_assign_psychologist", {"supervisor", "admin"},
              "therapy_engagement"),
    _audit_ok("supervisor_reactivate_psychologist", {"supervisor", "admin"},
              "therapy_engagement"),
    _audit_ok("supervisor_transfer_psychologist", {"supervisor", "admin"},
              "therapy_engagement"),
    _audit_ok("supervisor_close_engagement", {"supervisor", "admin"},
              "therapy_engagement"),
    _audit_ok("email_domain_add", {"admin"}, "allowed_email_domain"),
    _audit_ok("email_domain_disable", {"admin"}, "allowed_email_domain"),
    _audit_ok("email_domain_reactivate", {"admin"}, "allowed_email_domain"),
    _audit_ok("email_domain_update", {"admin"}, "allowed_email_domain"),
]

# ── AUDIT_LOG: session_notes ─────────────────────────────────────────────────
_ALL += [
    _audit_ok("session_note_created", {"psychologist"}, "session_note"),
    _audit_ok("session_note_updated", {"psychologist"}, "session_note"),
    # privileged content read — INDEPENDENT/SOFT (fail-open PROVISIONAL, §12)
    _audit_ok("session_note_content_read", {"supervisor"}, "session_note",
              tx_mode=TxMode.INDEPENDENT, failure_policy=FailurePolicy.SOFT),
]

# ── AUDIT_LOG: chat (INDEPENDENT/SOFT) ───────────────────────────────────────
_ALL += [
    # chat_conversation_created создаётся и lazy-путём student (_CHAT_PARTIES), и
    # supervisor/admin через assign/transfer (Stage 4B-3) — actor может быть любой
    # из всех 4 ролей; остальные chat-события actor'а не расширяют.
    _audit_ok("chat_conversation_created", _STAFF, "chat_conversation",
              tx_mode=TxMode.INDEPENDENT, failure_policy=FailurePolicy.SOFT),
    _audit_ok("chat_message_edited", _CHAT_PARTIES, "chat_message",
              tx_mode=TxMode.INDEPENDENT, failure_policy=FailurePolicy.SOFT),
    _audit_ok("chat_message_deleted", _CHAT_PARTIES, "chat_message",
              tx_mode=TxMode.INDEPENDENT, failure_policy=FailurePolicy.SOFT),
    _audit_ok("chat_attachment_uploaded", _CHAT_PARTIES, "chat_attachment",
              _ATTACH_UPLOAD_META,
              tx_mode=TxMode.INDEPENDENT, failure_policy=FailurePolicy.SOFT),
    _audit_ok("chat_attachment_downloaded", _CHAT_PARTIES, "chat_attachment",
              tx_mode=TxMode.INDEPENDENT, failure_policy=FailurePolicy.SOFT),
    # system-беседа — SYSTEM actor, INDEPENDENT/SOFT
    _audit_ok("system_conversation_created", frozenset(), "chat_conversation",
              tx_mode=TxMode.INDEPENDENT, failure_policy=FailurePolicy.SOFT,
              actor_policy=ActorPolicy.SYSTEM),
]

# ── AUDIT_LOG: контент CRUD (ATOMIC/RAISE) ───────────────────────────────────
for _base in ("article", "news", "tag", "category"):
    for _op in ("created", "updated", "deleted"):
        _ALL.append(_audit_ok(f"{_base}_{_op}", {"admin"}, _base))
# test CRUD доступен admin И supervisor на HTTP-уровне
# (app/tests/routes_admin.py: require_role("admin","supervisor")) — роли widened
# до {admin, supervisor}, чтобы supervisor-инициированная операция не падала в
# validate_actor (Stage 4B-5B). Count не меняется — правка role-set.
for _op in ("created", "updated", "duplicated", "deleted"):
    _ALL.append(_audit_ok(f"test_{_op}", {"admin", "supervisor"}, "test"))

# ── AUDIT_LOG: психодиагностика (student) ────────────────────────────────────
_ALL += [
    _audit_ok("test_consent_accepted", {"student"}, "consent_record"),
    _audit_ok("test_submitted", {"student"}, "test_result"),
]

# ── AUDIT_LOG: Stage 5A-2 durable failure события (INDEPENDENT/SOFT) ──────────
_ALL += [
    _audit_fail("admin_user_create_failed", {"admin"},
                {"email_already_exists", "domain_not_allowed", "internal_error"}),
    _audit_fail("admin_user_update_failed", {"admin"},
                {"user_not_found", "invalid_request", "role_policy_violation",
                 "self_admin_protected", "legal_basis_required", "internal_error"}),
    _audit_fail("admin_user_delete_failed", {"admin"},
                {"user_not_found", "internal_error"}),
    _audit_fail("profile_update_failed", _STAFF,
                {"user_not_found", "invalid_request", "internal_error"}),
]

# ── AUDIT_LOG: Stage 5B-1 appointments + walk-in cards (success lifecycle) ────
_ALL += [
    # Один appointment_created для student self-book и supervisor/admin manual
    # booking — actor.role различает self vs staff. metadata={}.
    _audit_ok("appointment_created",
              {"student", "supervisor", "admin"}, "appointment"),
    _audit_ok("appointment_confirmed", {"psychologist"}, "appointment"),
    _audit_ok("appointment_declined", {"psychologist"}, "appointment"),
    _audit_ok("appointment_cancelled", {"student"}, "appointment"),
    _audit_ok("unregistered_student_card_created",
              {"supervisor", "admin"}, "unregistered_student_card"),
    _audit_ok("unregistered_student_card_updated",
              {"supervisor", "admin"}, "unregistered_student_card"),
    _audit_ok("unregistered_student_card_archived",
              {"supervisor", "admin"}, "unregistered_student_card"),
    # Авто-привязка карточки к аккаунту: actor = student (self-reg) ЛИБО
    # supervisor/admin (staff-created). metadata несёт псевдонимный subject id.
    _audit_ok("unregistered_student_card_linked",
              {"student", "supervisor", "admin"},
              "unregistered_student_card", _CARD_LINK_META),
]

# ── AUDIT_LOG: Stage 5B-2 appointments/cards durable failure (INDEPENDENT/SOFT) ─
# Только доказанные precommit typed business-отказы с security/compliance-ценностью:
# access-control denial + consent-gate. Обычная input/UX-валидация НЕ логируется
# (audit-worthiness review, Stage 5B-2 §3). internal_error намеренно отсутствует —
# типизированного internal precommit AppointmentError в домене нет. Карточка
# update/archive не имеют auditable-пути → событий нет.
_ALL += [
    _audit_fail("appointment_create_failed",
                {"student", "supervisor", "admin"},
                {"account_inactive", "engagement_required"}),
    _audit_fail("appointment_cancel_failed", {"student"}, {"access_denied"}),
    _audit_fail("appointment_confirm_failed", {"psychologist"},
                {"access_denied"}),
    _audit_fail("appointment_decline_failed", {"psychologist"},
                {"access_denied"}),
    _audit_fail("unregistered_student_card_create_failed",
                {"supervisor", "admin"}, {"consent_required"}),
]

# ── AUDIT_LOG: Stage 5C-1 meeting types + schedules (success lifecycle) ───────
# Только supervisor/admin (routes: require_role("admin","supervisor"),
# _sup_role). metadata={} для всех — masштаб физической перезаписи серии не
# нужен для семантической идентификации действия (deactivate/restore) и не
# добавляется. target для расписания-серии — schedule_series (integer identity,
# Stage 5C-0), НЕ series_id (UUID) и НЕ психолог.
_ALL += [
    _audit_ok("meeting_type_created", {"supervisor", "admin"}, "meeting_type"),
    _audit_ok("meeting_type_updated", {"supervisor", "admin"}, "meeting_type"),
    _audit_ok("meeting_type_activated", {"supervisor", "admin"}, "meeting_type"),
    _audit_ok("meeting_type_deactivated",
              {"supervisor", "admin"}, "meeting_type"),
    # Слайды баннера главной страницы — та же admin+supervisor форма, что и
    # meeting_types: is_active выделен в отдельные activated/deactivated,
    # а не смешан с generic updated.
    _audit_ok("banner_slide_created", {"supervisor", "admin"}, "banner_slide"),
    _audit_ok("banner_slide_updated", {"supervisor", "admin"}, "banner_slide"),
    _audit_ok("banner_slide_activated", {"supervisor", "admin"}, "banner_slide"),
    _audit_ok("banner_slide_deactivated",
              {"supervisor", "admin"}, "banner_slide"),
    # Физическое удаление (не soft) — у banner_slide нет входящих FK.
    _audit_ok("banner_slide_deleted", {"supervisor", "admin"}, "banner_slide"),
    # Карточки услуг страницы /services — та же admin+supervisor форма, что и
    # banner_slide: is_active выделен в отдельные activated/deactivated,
    # физическое удаление (не soft) — нет входящих FK.
    _audit_ok("service_card_created", {"supervisor", "admin"}, "service_card"),
    _audit_ok("service_card_updated", {"supervisor", "admin"}, "service_card"),
    _audit_ok("service_card_activated", {"supervisor", "admin"}, "service_card"),
    _audit_ok("service_card_deactivated",
              {"supervisor", "admin"}, "service_card"),
    _audit_ok("service_card_deleted", {"supervisor", "admin"}, "service_card"),
    _audit_ok("schedule_created", {"supervisor", "admin"}, "schedule_series"),
    _audit_ok("schedule_updated", {"supervisor", "admin"}, "schedule_series"),
    _audit_ok("schedule_deactivated",
              {"supervisor", "admin"}, "schedule_series"),
    _audit_ok("schedule_restored", {"supervisor", "admin"}, "schedule_series"),
    _audit_ok("schedule_extended", {"supervisor", "admin"}, "schedule_series"),
    _audit_ok("schedule_rule_created",
              {"supervisor", "admin"}, "schedule_rule"),
    _audit_ok("schedule_rule_deactivated",
              {"supervisor", "admin"}, "schedule_rule"),
    _audit_ok("schedule_break_created",
              {"supervisor", "admin"}, "schedule_break"),
    _audit_ok("schedule_break_deactivated",
              {"supervisor", "admin"}, "schedule_break"),
    _audit_ok("schedule_exception_created",
              {"supervisor", "admin"}, "schedule_exception"),
]

# ── AUDIT_LOG: Stage 5C-2 group sessions + student registrations ──────────────
# booking_enabled и status — семантически значимые переходы, поэтому вынесены в
# отдельные события и НЕ входят в generic group_session_updated. `completed`
# принадлежит system maintenance (5C-3) и через generic PATCH запрещён, поэтому
# ручного события завершения здесь нет. Регистрации: actor — сам student,
# target — внутренний integer GroupSessionRegistration.id (не UUID).
_ALL += [
    _audit_ok("group_session_created",
              {"supervisor", "admin"}, "group_session"),
    _audit_ok("group_session_updated",
              {"supervisor", "admin"}, "group_session"),
    _audit_ok("group_session_booking_opened",
              {"supervisor", "admin"}, "group_session"),
    _audit_ok("group_session_booking_closed",
              {"supervisor", "admin"}, "group_session"),
    _audit_ok("group_session_cancelled",
              {"supervisor", "admin"}, "group_session"),
    _audit_ok("group_session_registered",
              {"student"}, "group_session_registration"),
    _audit_ok("group_session_registration_cancelled",
              {"student"}, "group_session_registration"),
]

# ── AUDIT_LOG: Stage 5C-3 system maintenance (SYSTEM actor, ATOMIC/RAISE) ─────
# Выполняются явными CLI-job'ами вне HTTP: actor — Actor.system() (user_id=NULL,
# user_role='system'), request-контекста нет (context=None). ATOMIC/RAISE: audit
# стейджится в той же транзакции, что и мутация, поэтому сбой аудита откатывает
# сам переход и job завершается ненулевым кодом. Ролей нет — SYSTEM actor_policy.
_ALL += [
    _audit_ok("group_session_completed", frozenset(), "group_session",
              actor_policy=ActorPolicy.SYSTEM),
    _audit_ok("schedule_auto_extended", frozenset(), "schedule_series",
              actor_policy=ActorPolicy.SYSTEM),
]

# ── AUDIT_LOG: Stage 8 — привилегированное чтение журналов ────────────────────
# Просмотр журналов админом — массовое чтение чувствительной service-use
# metadata, поэтому фиксируется отдельным событием. Контракт отличается от
# _audit_ok/_audit_fail и задаётся напрямую:
#   target FORBIDDEN — читается ВЫБОРКА, а не конкретная сущность;
#   success-only     — 401/403/422 происходят ДО чтения и события не создают,
#                      а сбой БД не должен порождать ложный исход;
#   INDEPENDENT+RAISE — своя транзакция (read-путь бизнес-транзакции не имеет),
#                      но fail-closed: не записали событие → не отдали данные.
_ALL += [
    _spec("audit_logs_viewed", Destination.AUDIT_LOG, ActorPolicy.USER_REQUIRED,
          {"admin"}, TargetPolicy.FORBIDDEN, None,
          {Outcome.SUCCESS}, frozenset(), _ACCESS_META,
          TxMode.INDEPENDENT, FailurePolicy.RAISE),
]


# ── Валидация ────────────────────────────────────────────────────────────────

def _validate_fieldspec(mkey: str, fs: FieldSpec) -> None:
    if fs.type not in _VALID_FIELD_TYPES:
        raise AuditError(f"metadata field {mkey}: invalid type {fs.type!r}")

    if fs.type in _STRING_FIELD_TYPES:
        if fs.fmt is None or not isinstance(fs.fmt, StringFormat):
            raise AuditError(
                f"metadata field {mkey}: string requires an explicit StringFormat"
            )
        if fs.fmt is StringFormat.ENUM:
            if not isinstance(fs.enum, frozenset) or not fs.enum:
                raise AuditError(
                    f"metadata field {mkey}: ENUM requires a non-empty frozenset"
                )
            if not all(isinstance(v, str) for v in fs.enum):
                raise AuditError(f"metadata field {mkey}: ENUM values must be str")
        elif fs.fmt is StringFormat.MIME_TYPE:
            if fs.enum is not None:
                raise AuditError(f"metadata field {mkey}: MIME_TYPE must not have enum")
        if fs.min_value is not None or fs.max_value is not None:
            raise AuditError(
                f"metadata field {mkey}: min/max not applicable to string type"
            )
        if fs.max_len is not None and fs.max_len <= 0:
            raise AuditError(f"metadata field {mkey}: max_len must be positive")
    elif fs.type in _INT_FIELD_TYPES:
        if fs.fmt is not None:
            raise AuditError(f"metadata field {mkey}: int type must not have fmt")
        if fs.enum is not None:
            raise AuditError(f"metadata field {mkey}: int type must not have enum")
        if fs.max_len is not None:
            raise AuditError(
                f"metadata field {mkey}: max_len not applicable to int type"
            )
        if fs.min_value is not None and fs.max_value is not None:
            if fs.min_value > fs.max_value:
                raise AuditError(f"metadata field {mkey}: min_value > max_value")
    elif fs.type == "bool":
        if (fs.fmt is not None or fs.enum is not None or fs.max_len is not None
                or fs.min_value is not None or fs.max_value is not None):
            raise AuditError(
                f"metadata field {mkey}: bool type must not set string/int constraints"
            )


def validate_registry(specs: Mapping[str, EventSpec]) -> None:
    """Валидирует произвольный набор specs. Бросает AuditError на первом нарушении."""
    seen: set = set()
    for key, spec in specs.items():
        if key != spec.name:
            raise AuditError(f"registry key {key!r} != spec.name {spec.name!r}")
        if spec.name in seen:
            raise AuditError(f"duplicate event name {spec.name!r}")
        seen.add(spec.name)

        if spec.destination not in (Destination.AUTH_LOG, Destination.AUDIT_LOG):
            raise AuditError(f"{spec.name}: unsupported destination")
        if not spec.name or len(spec.name) > _NAME_MAX[spec.destination]:
            raise AuditError(f"{spec.name}: event name length out of bounds")
        if not _STABLE_NAME_RE.fullmatch(spec.name):
            raise AuditError(f"{spec.name}: event name must be stable snake_case")

        if spec.actor_policy in (ActorPolicy.SYSTEM, ActorPolicy.ANONYMOUS_ONLY):
            if spec.allowed_actor_roles:
                raise AuditError(f"{spec.name}: {spec.actor_policy} must have no roles")
        else:  # USER_REQUIRED / USER_OR_ANONYMOUS
            if not spec.allowed_actor_roles:
                raise AuditError(f"{spec.name}: user policy requires allowed roles")
            if not spec.allowed_actor_roles <= USER_ROLES:
                raise AuditError(f"{spec.name}: roles must be within USER_ROLES")

        if spec.target_policy is TargetPolicy.REQUIRED and not spec.entity_type:
            raise AuditError(f"{spec.name}: target REQUIRED needs entity_type")
        if spec.target_policy is TargetPolicy.FORBIDDEN and spec.entity_type is not None:
            raise AuditError(f"{spec.name}: target FORBIDDEN forbids entity_type")

        if not spec.allowed_outcomes:
            raise AuditError(f"{spec.name}: allowed_outcomes empty")
        for outcome in spec.allowed_outcomes:
            if not isinstance(outcome, Outcome):
                raise AuditError(f"{spec.name}: allowed_outcomes must contain Outcome")
        has_failure = Outcome.FAILURE in spec.allowed_outcomes
        if has_failure and not spec.allowed_failure_codes:
            raise AuditError(f"{spec.name}: FAILURE requires failure codes")
        if not has_failure and spec.allowed_failure_codes:
            raise AuditError(f"{spec.name}: success-only must have no failure codes")
        for code in spec.allowed_failure_codes:
            if not isinstance(code, str) or not code:
                raise AuditError(f"{spec.name}: failure code must be a non-empty str")
            if len(code) > _FAILURE_CODE_MAX:
                raise AuditError(f"{spec.name}: failure code length out of bounds")
            if not _STABLE_NAME_RE.fullmatch(code):
                raise AuditError(f"{spec.name}: failure code must be stable snake_case")

        if spec.tx_mode is TxMode.ATOMIC and spec.failure_policy is not FailurePolicy.RAISE:
            raise AuditError(f"{spec.name}: ATOMIC+SOFT forbidden")

        if spec.user_email_allowed and spec.destination is not Destination.AUTH_LOG:
            raise AuditError(f"{spec.name}: user_email only for AUTH_LOG")
        if spec.destination is Destination.AUTH_LOG and spec.metadata_schema:
            raise AuditError(f"{spec.name}: AUTH_LOG has no metadata column")

        for mkey, fs in spec.metadata_schema.items():
            if is_denylisted_key(mkey):
                raise AuditError(f"{spec.name}: metadata key {mkey!r} is denylisted")
            _validate_fieldspec(mkey, fs)

        if spec.description_policy is DescriptionPolicy.NONE:
            if spec.static_description is not None:
                raise AuditError(
                    f"{spec.name}: NONE description must not set static_description"
                )
        elif spec.description_policy is DescriptionPolicy.STATIC:
            if not spec.static_description:
                raise AuditError(f"{spec.name}: STATIC description requires text")
            if len(spec.static_description) > _STATIC_DESC_MAX:
                raise AuditError(f"{spec.name}: static_description too long")


def build_registry(specs: Iterable[EventSpec]) -> Mapping[str, EventSpec]:
    """Строит immutable registry, обнаруживая дубликаты ДО создания dict.

    Затем валидирует полученный mapping через validate_registry() (fail-fast).
    Используется и production REGISTRY, и негативными тестами (без изменения
    production REGISTRY — им передаётся отдельный список specs).
    """
    seen: set = set()
    mapping: dict = {}
    for spec in specs:
        if spec.name in seen:
            raise AuditError(f"duplicate event name in registry build: {spec.name!r}")
        seen.add(spec.name)
        mapping[spec.name] = spec
    frozen: Mapping[str, EventSpec] = MappingProxyType(mapping)
    validate_registry(frozen)
    return frozen


def get_spec(event: str) -> EventSpec:
    spec = REGISTRY.get(event)
    if spec is None:
        raise AuditError(f"unknown audit event: {event!r}")
    return spec


# Production registry: дубликаты обнаруживаются в build_registry ДО создания dict;
# validate_registry() вызывается изнутри build_registry — fail-fast при импорте.
REGISTRY: Mapping[str, EventSpec] = build_registry(_ALL)
