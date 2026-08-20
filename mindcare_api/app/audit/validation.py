"""
Stage 4A — валидация actor/target/outcome/metadata/context + denylist.

Все ошибки — AuditError; тексты НЕ содержат исходных значений (email/ua/ip/metadata/
исключений). Импортирует только contracts + app.core.normalization (без registry/
service — во избежание циклов).
"""
from __future__ import annotations

import ipaddress
import re
from typing import Mapping, Optional

from app.core.normalization import normalize_email

from app.audit.contracts import (
    USER_ROLES, Actor, AuditError, Destination, EventSpec, FieldSpec, Outcome,
    RequestContext, StringFormat, Target, TargetPolicy, ActorPolicy,
)

# ── Denylist (defense-in-depth; НЕ заменяет per-event allowlist) ──────────────
SENSITIVE_TOKENS: frozenset = frozenset({
    "email", "phone", "password", "secret", "token", "ciphertext", "plaintext",
    "checksum", "traceback", "ssn", "dob",
    # Stage 6-0: токены, покрывающие ПДн/терапевтический контент в ИМЕНАХ полей
    # data_change_log. Через registry-инвариант (change_registry) любое поле с
    # таким именем может быть только NAME_ONLY и физически не получит
    # value-политику. Проверено, что ни один существующий metadata-ключ REGISTRY
    # (roles_before/roles_after/added/removed/fields/file_size/mime_type/
    # linked_user_id) этими токенами не задевается.
    "birth", "birthdate", "comment", "concern", "content", "note", "notes",
    "diagnosis", "answer", "mood", "diary",
})
SENSITIVE_KEYS: frozenset = frozenset({
    "password_hash", "session_token", "access_token", "refresh_token",
    "original_filename", "storage_key", "error_message", "full_name",
    "request_body", "response_body", "old_content", "new_content",
})

_ALLOWED_METHODS: frozenset = frozenset({
    "GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS",
})
_SESSION_HASH_RE = re.compile(r"[0-9a-fA-F]{64}")
_MIME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*/[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*")
_STR_MAX_DEFAULT = 256
_LIST_MAX = 64
_UA_MAX = 512
_PATH_MAX = 500
_EMAIL_MAX = 255


def _tokens(key: str) -> list:
    # camelCase → snake, затем split по не-alnum, lowercase
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", key)
    return [t for t in re.split(r"[^A-Za-z0-9]+", spaced.lower()) if t]


def is_denylisted_key(key: str) -> bool:
    low = key.lower()
    if low in SENSITIVE_KEYS:
        return True
    return any(tok in SENSITIVE_TOKENS for tok in _tokens(key))


def scan_denylist(obj) -> None:
    """Рекурсивно проверяет ключи вложенных dict/list (defense-in-depth)."""
    if isinstance(obj, Mapping):
        for k, v in obj.items():
            if isinstance(k, str) and is_denylisted_key(k):
                raise AuditError("metadata contains a denylisted key")
            scan_denylist(v)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            scan_denylist(item)


def _is_int(v) -> bool:
    return type(v) is int  # bool исключён (type(True) is bool)


# ── Actor ─────────────────────────────────────────────────────────────────────

def _validate_user_actor(spec: EventSpec, actor: Actor) -> None:
    if not _is_int(actor.user_id) or actor.user_id <= 0:
        raise AuditError("actor user_id must be a positive integer")
    role = actor.role
    if role is None and spec.destination is Destination.AUTH_LOG:
        # ADR-018: аккаунт может не иметь НИ ОДНОЙ активной роли (например
        # единственная роль истекла). Такой пользователь по-прежнему проходит
        # аутентификацию — `role=null`, доступ отклоняется уже на эндпоинтах.
        # auth_log роль актора не хранит вообще (см. service._build_row), поэтому
        # требование роли здесь ничего не защищало, но превращало корректный
        # login/logout в 500. Для AUDIT_LOG роль по-прежнему обязательна: там она
        # реально записывается в user_role.
        return
    if not role or role not in USER_ROLES:
        raise AuditError("actor role is not a valid user role")
    if role not in spec.allowed_actor_roles:
        raise AuditError("actor role is not permitted for this event")


def _validate_anonymous_actor(actor: Actor) -> None:
    if actor.user_id is not None or actor.role is not None:
        raise AuditError("anonymous actor must not carry user_id or role")


def _validate_system_actor(actor: Actor) -> None:
    if actor.user_id is not None or actor.role is not None:
        raise AuditError("system actor must not carry user_id or role")


def validate_actor(spec: EventSpec, actor: Actor) -> None:
    pol = spec.actor_policy
    if pol is ActorPolicy.USER_REQUIRED:
        if actor.kind != "user":
            raise AuditError("event requires an authenticated user actor")
        _validate_user_actor(spec, actor)
    elif pol is ActorPolicy.USER_OR_ANONYMOUS:
        if actor.kind == "user":
            _validate_user_actor(spec, actor)
        elif actor.kind == "anonymous":
            _validate_anonymous_actor(actor)
        else:
            raise AuditError("event requires user or anonymous actor")
    elif pol is ActorPolicy.ANONYMOUS_ONLY:
        if actor.kind != "anonymous":
            raise AuditError("event requires an anonymous actor")
        _validate_anonymous_actor(actor)
    elif pol is ActorPolicy.SYSTEM:
        if actor.kind != "system":
            raise AuditError("event requires the system actor")
        _validate_system_actor(actor)


# ── Target ──────────────────────────────────────────────────────────────────

def validate_target(spec: EventSpec, target: Optional[Target]) -> None:
    if spec.target_policy is TargetPolicy.FORBIDDEN:
        if target is not None:
            raise AuditError("event does not accept a target")
        return
    if target is None:
        raise AuditError("event requires a target")
    if target.entity_type != spec.entity_type:
        raise AuditError("target entity_type does not match event")
    if not _is_int(target.entity_id) or target.entity_id <= 0:
        raise AuditError("target entity_id must be a positive integer")


# ── Outcome / failure code ────────────────────────────────────────────────────

def validate_outcome(spec: EventSpec, outcome: Outcome, code: Optional[str]) -> None:
    if outcome not in spec.allowed_outcomes:
        raise AuditError("outcome not allowed for this event")
    if outcome is Outcome.SUCCESS:
        if code is not None:
            raise AuditError("success must not carry a failure_reason_code")
    else:
        if code is None:
            raise AuditError("failure requires a failure_reason_code")
        if code not in spec.allowed_failure_codes:
            raise AuditError("failure_reason_code is not registered for this event")


# ── Metadata ──────────────────────────────────────────────────────────────────

def _validate_str(mkey: str, fs: FieldSpec, v) -> str:
    if not isinstance(v, str):
        raise AuditError(f"metadata {mkey}: expected string")
    max_len = fs.max_len or _STR_MAX_DEFAULT
    if len(v) > max_len:
        raise AuditError(f"metadata {mkey}: string too long")
    if fs.fmt is StringFormat.ENUM:
        if fs.enum is None or v not in fs.enum:
            raise AuditError(f"metadata {mkey}: value not in allowed enum")
    elif fs.fmt is StringFormat.MIME_TYPE:
        if not _MIME_RE.fullmatch(v):
            raise AuditError(f"metadata {mkey}: invalid MIME type")
    else:
        raise AuditError(f"metadata {mkey}: string field requires a format")
    return v


def _validate_int(mkey: str, fs: FieldSpec, v) -> int:
    if not _is_int(v):
        raise AuditError(f"metadata {mkey}: expected integer (bool rejected)")
    if fs.min_value is not None and v < fs.min_value:
        raise AuditError(f"metadata {mkey}: below min_value")
    if fs.max_value is not None and v > fs.max_value:
        raise AuditError(f"metadata {mkey}: above max_value")
    return v


def _validate_value(mkey: str, fs: FieldSpec, v):
    if v is None:
        if fs.nullable:
            return None
        raise AuditError(f"metadata {mkey}: null not allowed")
    if fs.type == "int":
        return _validate_int(mkey, fs, v)
    if fs.type == "bool":
        if type(v) is not bool:
            raise AuditError(f"metadata {mkey}: expected bool")
        return v
    if fs.type == "str":
        return _validate_str(mkey, fs, v)
    if fs.type == "str_list":
        if not isinstance(v, list):
            raise AuditError(f"metadata {mkey}: expected list")
        if len(v) > _LIST_MAX:
            raise AuditError(f"metadata {mkey}: list too long")
        return [_validate_str(mkey, fs, item) for item in v]
    if fs.type == "int_list":
        if not isinstance(v, list):
            raise AuditError(f"metadata {mkey}: expected list")
        if len(v) > _LIST_MAX:
            raise AuditError(f"metadata {mkey}: list too long")
        return [_validate_int(mkey, fs, item) for item in v]
    raise AuditError(f"metadata {mkey}: unsupported field type")


def validate_metadata(spec: EventSpec, metadata: Optional[Mapping]) -> dict:
    """Возвращает НОВУЮ JSON-safe структуру (без ссылок на caller-объекты)."""
    if metadata is None:
        return {}
    if not isinstance(metadata, Mapping):
        raise AuditError("metadata must be a mapping")
    scan_denylist(metadata)  # defense-in-depth (ключи любого уровня)
    out: dict = {}
    for key, value in metadata.items():
        if not isinstance(key, str):
            raise AuditError("metadata keys must be strings")
        fs = spec.metadata_schema.get(key)
        if fs is None:
            raise AuditError("unknown metadata key for this event")
        out[key] = _validate_value(key, fs, value)  # lists → новые списки
    return out


# ── RequestContext ────────────────────────────────────────────────────────────

def _has_control_chars(s: str) -> bool:
    return any(ord(c) < 32 or ord(c) == 127 for c in s)


def _require_str(value, field_name: str) -> None:
    # Тип проверяется ДО любых len()/regex — иначе неверный тип дал бы TypeError,
    # а не AuditError. Сообщение не содержит самого значения.
    if value is not None and not isinstance(value, str):
        raise AuditError(f"{field_name} must be a string")


def validate_context(ctx: Optional[RequestContext]) -> None:
    if ctx is None:
        return

    _require_str(ctx.ip_address, "ip_address")
    _require_str(ctx.user_agent, "user_agent")
    _require_str(ctx.session_id_hash, "session_id_hash")
    _require_str(ctx.request_path, "request_path")
    _require_str(ctx.request_method, "request_method")

    if ctx.ip_address is not None:
        try:
            ipaddress.ip_address(ctx.ip_address)
        except ValueError:
            raise AuditError("invalid ip_address") from None
    if ctx.user_agent is not None:
        if len(ctx.user_agent) > _UA_MAX or _has_control_chars(ctx.user_agent):
            raise AuditError("invalid user_agent")
    if ctx.session_id_hash is not None:
        if not _SESSION_HASH_RE.fullmatch(ctx.session_id_hash):
            raise AuditError("invalid session_id_hash (expected sha256 hex)")
    if ctx.request_path is not None:
        p = ctx.request_path
        if (len(p) > _PATH_MAX or not p.startswith("/")
                or "?" in p or "#" in p or _has_control_chars(p)):
            raise AuditError("invalid request_path")
    if ctx.request_method is not None:
        if ctx.request_method not in _ALLOWED_METHODS:
            raise AuditError("invalid request_method")


# ── user_email (auth-only) ────────────────────────────────────────────────────

def validate_email(spec: EventSpec, user_email: Optional[str]) -> Optional[str]:
    if user_email is None:
        return None
    if not spec.user_email_allowed:
        raise AuditError("user_email not allowed for this event")
    if not isinstance(user_email, str):
        raise AuditError("user_email must be a string")
    normalized = normalize_email(user_email)   # новая строка, caller не мутируется
    if not normalized:
        raise AuditError("user_email must not be empty")
    if _has_control_chars(normalized):
        raise AuditError("user_email contains control characters")
    if len(normalized) > _EMAIL_MAX:
        raise AuditError("user_email too long")
    return normalized
