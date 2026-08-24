"""
Stage 8 — бизнес-слой read-only admin viewer журналов: валидация запроса,
безопасная проекция строки в DTO и аудит самого просмотра.

Модуль не знает про FastAPI/HTTP: нарушение контракта запроса — это
`AuditQueryError`, которое route превращает в 422. Сбой записи access-события —
`AuditError`/`AuditStorageError` из facade, которое route превращает в 503 и
которое обязано погасить выдачу целиком (fail-closed: не записали факт
просмотра — не отдали журнал).

Три сквозных правила проекции:

  1. Классификация актора берётся из `admin_policy`, то есть из тех же множеств
     `ActorPolicy`, по которым `admin_storage` строит SQL-предикаты. Иначе
     фильтр и отображение разошлись бы.
  2. `validation.validate_metadata()` НЕ является финальной DTO-проекцией. Она
     защищает от мусора в БД, но пропускает всё, что объявил EventSpec, —
     включая `linked_user_id` (внутренний `users.id`). Поверх неё стоит закрытый
     `_METADATA_DTO_POLICY`; неклассифицированный ключ отбрасывается.
  3. Всё, что противоречит собственной спеке строки (роль вне allowlist, чужой
     `entity_type`, незарегистрированный failure code, операция вне
     `allowed_operations`), редактируется, а не показывается «как есть».
"""
from __future__ import annotations

import enum
from datetime import date, datetime, time, timedelta, timezone
from typing import Mapping, Optional
from uuid import UUID

from app.core.normalization import mask_email

from app.audit import admin_policy as pol
from app.audit import admin_storage as storage
from app.audit import validation
from app.audit.admin_schemas import (
    ActorOut, AuditEventOut, AuditEventsPage, AuditLimitsOut, AuditOptionsOut,
    AuthEventOut, AuthEventsPage, DataChangeOut, DataChangesPage, TargetOut,
    TargetUserOut,
)
from app.audit.change_contracts import PG_INT32_MAX
from app.audit.change_registry import CHANGE_REGISTRY
from app.audit.contracts import Actor, AuditError, Outcome, TargetPolicy
from app.audit.registry import AUDIT_FILTER_KEYS, REGISTRY
from app.audit.request_context import build_request_context
from app.audit.service import record_event

# Moscow — UTC+3 без переходов с 2014 года. Константа объявлена локально
# намеренно: импорт из app.appointments.service связал бы audit-слой с
# доменным модулем расписаний. ZoneInfo не используется — на Windows-хостах
# базы tzdata может не быть.
MOSCOW_TZ = timezone(timedelta(hours=3))

DEFAULT_RANGE_DAYS: int = 7
MAX_RANGE_DAYS: int = 90
DEFAULT_PAGE_SIZE: int = 20
MAX_PAGE_SIZE: int = 100
# Верхняя граница глубины выборки: OFFSET по 90-дневному окну на нескольких
# партициях линейно дорожает. Глубокая навигация — задача cursor pagination,
# она вынесена в backlog.
MAX_RESULT_WINDOW: int = 100_000

# Границы точечных фильтров. entity_id/record_id — колонки PostgreSQL INTEGER,
# поэтому это НЕ произвольный лимит, а физический диапазон типа: значение вне
# него не может существовать в журнале и обязано давать 422, а не молчаливую
# пустую страницу и не psycopg2 overflow.
MIN_RECORD_REF: int = 1
MAX_RECORD_REF: int = PG_INT32_MAX

_ORDERS = frozenset(pol.ORDERS)
_OUTCOMES = frozenset(pol.OUTCOMES)


class AuditQueryError(Exception):
    """Нарушение контракта запроса. Route отдаёт 422 с этим сообщением."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


# ── DTO-политика metadata (вторая ступень после validate_metadata) ────────────

class MetaPolicy(enum.Enum):
    PASS = "pass"                        # ключ отдаётся как есть
    USER_ID_TO_UUID = "user_id_to_uuid"  # внутренний users.id → <name>_uuid


_METADATA_DTO_POLICY: Mapping[str, MetaPolicy] = {
    # role diff — только имена ролей
    "roles_before": MetaPolicy.PASS,
    "roles_after": MetaPolicy.PASS,
    "added": MetaPolicy.PASS,
    "removed": MetaPolicy.PASS,
    # self-profile — только имена изменённых полей
    "fields": MetaPolicy.PASS,
    # вложение чата — размер и MIME, без имени файла и checksum
    "file_size": MetaPolicy.PASS,
    "mime_type": MetaPolicy.PASS,
    # само событие просмотра журналов
    "journal": MetaPolicy.PASS,
    "filter_keys": MetaPolicy.PASS,
    # псевдонимный внутренний id субъекта: наружу только как UUID
    "linked_user_id": MetaPolicy.USER_ID_TO_UUID,
}

_ID_SUFFIX = "_id"
_UUID_SUFFIX = "_uuid"


def _uuid_key(key: str) -> str:
    return key[: -len(_ID_SUFFIX)] + _UUID_SUFFIX


def validate_metadata_dto_policy(
    *,
    registry: Mapping = REGISTRY,
    policy: Mapping[str, MetaPolicy] = _METADATA_DTO_POLICY,
) -> None:
    """Каждый metadata-ключ каждого EventSpec обязан быть классифицирован.

    Проверяется на импорте (как `build_registry` / `build_change_registry`):
    новый ключ в registry без явного решения «отдавать / преобразовать» роняет
    старт приложения, а не утекает молча в ответ API.
    """
    for spec in registry.values():
        for key in spec.metadata_schema:
            meta_policy = policy.get(key)
            if meta_policy is None:
                raise AuditError(f"metadata key {key!r} has no DTO policy")
            if meta_policy is MetaPolicy.USER_ID_TO_UUID and not key.endswith(_ID_SUFFIX):
                raise AuditError(f"metadata key {key!r} cannot be mapped to a uuid")


validate_metadata_dto_policy()


# ── Валидация запроса ─────────────────────────────────────────────────────────

def resolve_window(
    date_from: Optional[date], date_to: Optional[date],
) -> tuple[datetime, datetime]:
    """Даты (Europe/Moscow) → timezone-aware полуинтервал [start, end).

    Обе даты опущены — последние 7 календарных дней включая сегодня. Ровно одна
    дата — ошибка: молчаливое достраивание второй границы дало бы разный объём
    выборки при внешне одинаковом запросе.
    """
    if (date_from is None) != (date_to is None):
        raise AuditQueryError(
            "Укажите обе границы периода date_from и date_to либо ни одной"
        )

    if date_from is None:
        date_to = datetime.now(MOSCOW_TZ).date()
        date_from = date_to - timedelta(days=DEFAULT_RANGE_DAYS - 1)

    if date_from > date_to:
        raise AuditQueryError("date_from не может быть позже date_to")

    span_days = (date_to - date_from).days + 1
    if span_days > MAX_RANGE_DAYS:
        raise AuditQueryError(
            f"Период не может превышать {MAX_RANGE_DAYS} дней (запрошено {span_days})"
        )

    start = datetime.combine(date_from, time.min, tzinfo=MOSCOW_TZ)
    end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=MOSCOW_TZ)
    return start, end


def validate_paging(page: int, size: int) -> None:
    if page < 1:
        raise AuditQueryError("page должен быть не меньше 1")
    if not (1 <= size <= MAX_PAGE_SIZE):
        raise AuditQueryError(f"size должен быть в диапазоне 1..{MAX_PAGE_SIZE}")
    if (page - 1) * size + size > MAX_RESULT_WINDOW:
        raise AuditQueryError(
            f"Слишком глубокая страница: смещение не может превышать "
            f"{MAX_RESULT_WINDOW}. Сузьте период или фильтры"
        )


def _validate_choice(value: Optional[str], allowed, field: str) -> Optional[str]:
    if value is None:
        return None
    if value not in allowed:
        raise AuditQueryError(f"Недопустимое значение {field}")
    return value


def _validate_record_ref(value: Optional[int], field: str) -> Optional[int]:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise AuditQueryError(f"{field} должен быть целым числом")
    if not (MIN_RECORD_REF <= value <= MAX_RECORD_REF):
        raise AuditQueryError(
            f"{field} должен быть в диапазоне {MIN_RECORD_REF}..{MAX_RECORD_REF}"
        )
    return value


def _validate_order(order: str) -> str:
    if order not in _ORDERS:
        raise AuditQueryError("Недопустимое значение order")
    return order


def _validate_kind(journal: str, actor_kind: Optional[str]) -> Optional[str]:
    """Класс актора проверяется по РЕАЛЬНО достижимому набору своего журнала.

    Например `system` недостижим для `data_change_log`, пока все TableSpec
    объявлены USER_REQUIRED, — принимать такое значение значило бы обещать
    заведомо пустую выборку.
    """
    if actor_kind is None:
        return None
    if actor_kind not in pol.POLICY_BY_JOURNAL[journal].kinds:
        raise AuditQueryError("Недопустимое значение actor_kind для этого журнала")
    return actor_kind


def _reject_internal_id_for_user_target(
    *, entity_key: Optional[str], user_key_value: str,
    record_ref: Optional[int], target_user_uuid: Optional[UUID],
    ref_field: str, entity_field: str,
) -> None:
    """Внутренний `users.id` не является публичным идентификатором.

    «Цель — человек» адресуется ТОЛЬКО через `target_user_uuid`. Одного запрета
    пары `<entity_field>=<user_key_value>` + `<ref_field>` для этого мало:
    целочисленный идентификатор без явно указанного типа цели неоднозначен и
    сопоставляется в том числе с пользовательскими строками, а значит
    превращает `users.id` в рабочий ключ поиска — по нему можно перебором
    получить UUID и текущее ФИО из безопасной сводки цели.

    Поэтому целочисленный идентификатор допускается только вместе с явным
    НЕ-пользовательским типом цели: тогда он однозначно относится к
    `meeting_types`, `appointments` и т. п. и человека не идентифицирует.
    """
    if target_user_uuid is not None:
        if record_ref is not None:
            raise AuditQueryError(
                f"target_user_uuid нельзя сочетать с {ref_field}"
            )
        if entity_key is not None and entity_key != user_key_value:
            raise AuditQueryError(
                f"target_user_uuid применим только при {entity_field}={user_key_value}"
            )

    if record_ref is not None:
        if entity_key is None:
            raise AuditQueryError(
                f"{ref_field} требует явного {entity_field}: целочисленный "
                f"идентификатор без типа цели неоднозначен"
            )
        if entity_key == user_key_value:
            raise AuditQueryError(
                f"Для пользовательской цели используйте target_user_uuid вместо {ref_field}"
            )


def _filter_keys(pairs: Mapping[str, bool]) -> list:
    """Стабильные ИМЕНА применённых фильтров. Значений здесь нет и быть не может.

    `date_range` присутствует всегда: окно применяется даже когда обе даты
    опущены. Признак применённости всегда вычисляется вызывающим через
    `is not None`, а не через истинность значения, иначе `success=false`
    (просмотр неудачных входов) не попал бы в журнал.
    """
    keys = {"date_range"} | {name for name, applied in pairs.items() if applied}
    unknown = keys - AUDIT_FILTER_KEYS
    if unknown:
        raise AuditError("unregistered audit filter key")
    return sorted(keys)


# ── Проекция ──────────────────────────────────────────────────────────────────

def _project_actor(policy, *, key, actor_id, role, row) -> tuple[ActorOut, bool]:
    """Actor DTO + признак того, что часть строки пришлось скрыть.

    `unavailable` ВСЕГДА помечается как отредактированный. Это класс «актора
    установить не удалось», и он возникает только при аномалии: обнулённый
    FK-ссылкой `actor_id` (`ON DELETE SET NULL` после физического удаления
    аккаунта), отсутствующая строка `users`, роль вне `allowed_actor_roles`
    своей спеки либо неизвестное имя события. Администратор должен видеть, что
    здесь потеряны сведения, а не считать, что действие совершил «никто».

    `anonymous` и `system` — штатные, полностью определённые классы актора и
    признака редактирования НЕ получают.
    """
    user_found = row.actor_row_id is not None
    kind = pol.classify_actor(
        policy, key=key, actor_id=actor_id, role=role, user_found=user_found,
    )
    redacted = kind == pol.KIND_UNAVAILABLE

    if kind != pol.KIND_USER:
        return ActorOut(kind=kind), redacted

    return ActorOut(
        kind=kind,
        user_uuid=row.actor_user_uuid,
        display_name_current=row.actor_full_name,
        email_masked=mask_email(row.actor_email or ""),
        role_at_event=pol.role_at_event(policy, kind, role),
        is_deleted_current=row.actor_deleted_at is not None,
    ), redacted


def _target_user(row) -> Optional[TargetUserOut]:
    if row.target_user_uuid is None:
        return None
    return TargetUserOut(
        user_uuid=row.target_user_uuid,
        display_name_current=row.target_full_name,
        email_masked=mask_email(row.target_email or ""),
        is_deleted_current=row.target_deleted_at is not None,
    )


def _project_target(spec, row) -> tuple[Optional[TargetOut], bool]:
    """Target проверяется против КОНКРЕТНОГО EventSpec, а не «известен вообще».

    Несогласованная legacy-строка (цель у события, которое цели не имеет; чужой
    entity_type; неположительный id) редактируется целиком.
    """
    has_target = row.entity_type is not None or row.entity_id is not None

    if spec is None:
        return None, has_target

    if spec.target_policy is TargetPolicy.FORBIDDEN:
        return None, has_target

    if row.entity_type != spec.entity_type:
        return None, True
    if not isinstance(row.entity_id, int) or row.entity_id <= 0:
        return None, True

    if spec.entity_type == pol.USER_ENTITY_TYPE:
        # entity_ref намеренно не заполняется: это users.id.
        target_user = _target_user(row)
        return (
            TargetOut(entity_type=spec.entity_type, entity_ref=None, user=target_user),
            target_user is None,
        )

    return TargetOut(entity_type=spec.entity_type, entity_ref=row.entity_id), False


def _project_outcome(spec, raw_outcome, raw_code) -> tuple[Optional[str], Optional[str], bool]:
    """Исход и код отказа — только в рамках контракта конкретного события."""
    if spec is None:
        # Спеки нет: сверять не с чем, поэтому не показываем ничего.
        return None, None, True

    if raw_outcome not in _OUTCOMES:
        return None, None, True
    if Outcome(raw_outcome) not in spec.allowed_outcomes:
        return None, None, True

    if raw_outcome == Outcome.FAILURE.value:
        if raw_code and raw_code in spec.allowed_failure_codes:
            return raw_outcome, raw_code, False
        return raw_outcome, None, True

    # success не может нести код отказа — если несёт, это противоречие.
    return raw_outcome, None, raw_code is not None


def _project_metadata(spec, raw) -> tuple[dict, bool, dict]:
    """Вторая ступень: закрытый DTO-allowlist поверх validate_metadata.

    Возвращает `(details, redacted, pending)`, где `pending` — ключи, значение
    которых ещё предстоит заменить внутренним id на UUID батчем по всей
    странице (иначе получился бы N+1 запрос на строку).
    """
    if spec is None:
        return {}, True, {}

    try:
        safe = validation.validate_metadata(spec, raw)
    except AuditError:
        # Мусор в колонке не должен ронять всю страницу и не должен частично
        # просачиваться наружу.
        return {}, True, {}

    details: dict = {}
    pending: dict = {}
    redacted = False

    for key, value in safe.items():
        meta_policy = _METADATA_DTO_POLICY.get(key)
        if meta_policy is None:
            redacted = True                     # fail-closed для новых ключей
            continue
        if meta_policy is MetaPolicy.PASS:
            details[key] = value
            continue
        # USER_ID_TO_UUID
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            redacted = True
            continue
        pending[_uuid_key(key)] = value

    return details, redacted, pending


def _apply_pending_uuids(details: dict, pending: dict, uuid_by_id: Mapping) -> bool:
    """Подставляет разрешённые UUID; неразрешённый id ключа не даёт."""
    redacted = False
    for dto_key, user_id in pending.items():
        user_uuid = uuid_by_id.get(user_id)
        if user_uuid is None:
            redacted = True
            continue
        details[dto_key] = str(user_uuid)
    return redacted


# ── Access-event ──────────────────────────────────────────────────────────────

def _record_access(
    *, journal: str, filter_keys: list, actor_id: int, actor_role: str,
    ip: Optional[str], user_agent: Optional[str], session_id_hash: Optional[str],
) -> None:
    """Фиксирует факт привилегированного массового чтения журналов.

    Вызывается ПОСЛЕ успешной выборки и проекции, но ДО отдачи ответа: событие
    не попадает в собственный результат, а его сбой (INDEPENDENT + RAISE)
    пробрасывается наружу и гасит выдачу целиком.
    """
    record_event(
        event=pol.ACCESS_EVENT,
        actor=Actor.user(actor_id, actor_role),
        outcome=Outcome.SUCCESS,
        metadata={"journal": journal, "filter_keys": filter_keys},
        context=build_request_context(
            ip=ip, user_agent=user_agent, session_id_hash=session_id_hash,
        ),
    )


# ── /events ───────────────────────────────────────────────────────────────────

def list_audit_events(
    *,
    actor_id: int,
    actor_role: str,
    ip: Optional[str],
    user_agent: Optional[str],
    session_id_hash: Optional[str],
    page: int = 1,
    size: int = DEFAULT_PAGE_SIZE,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    order: str = "desc",
    actor_uuid: Optional[UUID] = None,
    actor_kind: Optional[str] = None,
    filter_actor_role: Optional[str] = None,
    event_type: Optional[str] = None,
    outcome: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    target_user_uuid: Optional[UUID] = None,
    include_access_events: bool = False,
) -> AuditEventsPage:
    validate_paging(page, size)
    order = _validate_order(order)
    start, end = resolve_window(date_from, date_to)

    actor_kind = _validate_kind(pol.JOURNAL_AUDIT, actor_kind)
    filter_actor_role = _validate_choice(filter_actor_role, pol.ACTOR_ROLES, "actor_role")
    event_type = _validate_choice(event_type, pol.AUDIT_EVENT_NAMES, "event_type")
    outcome = _validate_choice(outcome, _OUTCOMES, "outcome")
    entity_type = _validate_choice(entity_type, pol.ENTITY_TYPES, "entity_type")
    entity_id = _validate_record_ref(entity_id, "entity_id")
    _reject_internal_id_for_user_target(
        entity_key=entity_type, user_key_value=pol.USER_ENTITY_TYPE,
        record_ref=entity_id, target_user_uuid=target_user_uuid,
        ref_field="entity_id", entity_field="entity_type",
    )

    # Событие просмотра исключается по умолчанию, чтобы штатная лента не
    # заполнялась собственным следом. Явный интерес к нему — либо точечный
    # фильтр, либо include_access_events.
    exclude_access = not (
        include_access_events or event_type == pol.ACCESS_EVENT
    )

    rows, total = storage.list_audit_events(
        start=start, end=end, order=order, page=page, size=size,
        actor_uuid=actor_uuid, actor_kind=actor_kind, actor_role=filter_actor_role,
        event_type=event_type, outcome=outcome, entity_type=entity_type,
        entity_id=entity_id, target_user_uuid=target_user_uuid,
        exclude_access_events=exclude_access,
    )

    items = _project_audit_rows(rows)

    _record_access(
        journal=pol.JOURNAL_AUDIT,
        filter_keys=_filter_keys({
            "actor": actor_uuid is not None,
            "actor_kind": actor_kind is not None,
            "actor_role": filter_actor_role is not None,
            "event": event_type is not None,
            "outcome": outcome is not None,
            "entity": entity_type is not None,
            "record": entity_id is not None,
            "target": target_user_uuid is not None,
            "access_events": include_access_events,
        }),
        actor_id=actor_id, actor_role=actor_role,
        ip=ip, user_agent=user_agent, session_id_hash=session_id_hash,
    )

    return AuditEventsPage(items=items, total=total, page=page, size=size)


def _project_audit_rows(rows) -> list:
    """Двухпроходная проекция: сначала собираем внутренние id из metadata,
    затем одним запросом меняем их на UUID."""
    staged = []
    pending_ids: set = set()

    for row in rows:
        spec = pol.audit_spec(row.event_type)
        actor, actor_redacted = _project_actor(
            pol.AUDIT_POLICY, key=row.event_type, actor_id=row.actor_id,
            role=row.actor_role, row=row,
        )
        target, target_redacted = _project_target(spec, row)
        outcome, failure_code, outcome_redacted = _project_outcome(
            spec, row.outcome, row.failure_code,
        )
        details, meta_redacted, pending = _project_metadata(spec, row.raw_metadata)
        pending_ids.update(pending.values())

        staged.append((
            row, spec, actor, target, outcome, failure_code, details, pending,
            actor_redacted or target_redacted or outcome_redacted or meta_redacted,
        ))

    uuid_by_id = storage.resolve_user_uuids(pending_ids) if pending_ids else {}

    items = []
    for (row, spec, actor, target, outcome, failure_code, details, pending,
         redacted) in staged:
        redacted = _apply_pending_uuids(details, pending, uuid_by_id) or redacted
        items.append(AuditEventOut(
            entry_id=str(row.entry_id),
            occurred_at=row.occurred_at,
            event_code=row.event_type if spec is not None else pol.LEGACY_EVENT_CODE,
            known_event=spec is not None,
            actor=actor,
            target=target,
            outcome=outcome,
            failure_code=failure_code,
            details=details,
            details_redacted=redacted,
        ))
    return items


# ── /auth-events ──────────────────────────────────────────────────────────────

def list_auth_events(
    *,
    actor_id: int,
    actor_role: str,
    ip: Optional[str],
    user_agent: Optional[str],
    session_id_hash: Optional[str],
    page: int = 1,
    size: int = DEFAULT_PAGE_SIZE,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    order: str = "desc",
    actor_uuid: Optional[UUID] = None,
    actor_kind: Optional[str] = None,
    event: Optional[str] = None,
    success: Optional[bool] = None,
) -> AuthEventsPage:
    validate_paging(page, size)
    order = _validate_order(order)
    start, end = resolve_window(date_from, date_to)

    actor_kind = _validate_kind(pol.JOURNAL_AUTH, actor_kind)
    event = _validate_choice(event, pol.AUTH_EVENT_NAMES, "event")

    rows, total = storage.list_auth_events(
        start=start, end=end, order=order, page=page, size=size,
        actor_uuid=actor_uuid, actor_kind=actor_kind, event=event, success=success,
    )

    items = []
    for row in rows:
        spec = pol.auth_spec(row.event)
        actor, actor_redacted = _project_actor(
            pol.AUTH_POLICY, key=row.event, actor_id=row.actor_id,
            role=None, row=row,
        )
        failure_code, failure_redacted = _project_auth_failure(
            spec, bool(row.success), row.failure_reason,
        )
        items.append(AuthEventOut(
            entry_id=str(row.entry_id),
            occurred_at=row.occurred_at,
            event_code=row.event if spec is not None else pol.LEGACY_EVENT_CODE,
            known_event=spec is not None,
            actor=actor,
            success=bool(row.success),
            failure_code=failure_code,
            email_masked=mask_email(row.event_email or ""),
            details_redacted=actor_redacted or failure_redacted,
        ))

    _record_access(
        journal=pol.JOURNAL_AUTH,
        filter_keys=_filter_keys({
            "actor": actor_uuid is not None,
            "actor_kind": actor_kind is not None,
            "event": event is not None,
            "success": success is not None,
        }),
        actor_id=actor_id, actor_role=actor_role,
        ip=ip, user_agent=user_agent, session_id_hash=session_id_hash,
    )

    return AuthEventsPage(items=items, total=total, page=page, size=size)


def _project_auth_failure(spec, success: bool, raw_reason) -> tuple[Optional[str], bool]:
    """`auth_log.failure_reason` — VARCHAR(255), в legacy-строках там мог быть
    свободный текст. Наружу идёт только код, зарегистрированный этим событием."""
    if spec is None:
        return None, True
    if success:
        return None, raw_reason is not None
    if raw_reason and raw_reason in spec.allowed_failure_codes:
        return raw_reason, False
    return None, True


# ── /data-changes ─────────────────────────────────────────────────────────────

def list_data_changes(
    *,
    actor_id: int,
    actor_role: str,
    ip: Optional[str],
    user_agent: Optional[str],
    session_id_hash: Optional[str],
    page: int = 1,
    size: int = DEFAULT_PAGE_SIZE,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    order: str = "desc",
    actor_uuid: Optional[UUID] = None,
    actor_kind: Optional[str] = None,
    filter_actor_role: Optional[str] = None,
    table_name: Optional[str] = None,
    operation: Optional[str] = None,
    record_id: Optional[int] = None,
    target_user_uuid: Optional[UUID] = None,
) -> DataChangesPage:
    validate_paging(page, size)
    order = _validate_order(order)
    start, end = resolve_window(date_from, date_to)

    actor_kind = _validate_kind(pol.JOURNAL_DCL, actor_kind)
    filter_actor_role = _validate_choice(filter_actor_role, pol.ACTOR_ROLES, "actor_role")
    table_name = _validate_choice(table_name, pol.CHANGE_TABLE_NAMES, "table_name")
    # Операции берутся из union реальных allowed_operations, а не из всех трёх
    # литералов: сегодня ни один TableSpec не допускает INSERT/DELETE.
    operation = _validate_choice(operation, pol.CHANGE_OPERATIONS, "operation")
    record_id = _validate_record_ref(record_id, "record_id")
    _reject_internal_id_for_user_target(
        entity_key=table_name, user_key_value=pol.USERS_TABLE,
        record_ref=record_id, target_user_uuid=target_user_uuid,
        ref_field="record_id", entity_field="table_name",
    )

    rows, total = storage.list_data_changes(
        start=start, end=end, order=order, page=page, size=size,
        actor_uuid=actor_uuid, actor_kind=actor_kind, actor_role=filter_actor_role,
        table_name=table_name, operation=operation, record_id=record_id,
        target_user_uuid=target_user_uuid,
    )

    items = [_project_data_change_row(row) for row in rows]

    _record_access(
        journal=pol.JOURNAL_DCL,
        filter_keys=_filter_keys({
            "actor": actor_uuid is not None,
            "actor_kind": actor_kind is not None,
            "actor_role": filter_actor_role is not None,
            "table": table_name is not None,
            "operation": operation is not None,
            "record": record_id is not None,
            "target": target_user_uuid is not None,
        }),
        actor_id=actor_id, actor_role=actor_role,
        ip=ip, user_agent=user_agent, session_id_hash=session_id_hash,
    )

    return DataChangesPage(items=items, total=total, page=page, size=size)


def _project_data_change_row(row) -> DataChangeOut:
    spec = CHANGE_REGISTRY.get(row.table_name)
    actor, actor_redacted = _project_actor(
        pol.DCL_POLICY, key=row.table_name, actor_id=row.actor_id,
        role=row.actor_role, row=row,
    )

    if spec is None:
        # Неизвестная таблица: аллоулиста полей нет, значит нельзя показать ни
        # состав изменений, ни операцию, ни идентификатор строки.
        return DataChangeOut(
            entry_id=str(row.entry_id),
            occurred_at=row.occurred_at,
            known_change=False,
            actor=actor,
            table_name=None,
            record_id=None,
            operation=None,
            changed_fields=[],
            target_user=None,
            details_redacted=True,
        )

    raw_fields = row.changed_fields or []
    kept = sorted({f for f in raw_fields if isinstance(f, str) and f in spec.fields})
    dropped = len(kept) != len(raw_fields)

    allowed_ops = {op.value for op in spec.allowed_operations}
    operation = row.operation if row.operation in allowed_ops else None

    is_users = row.table_name == pol.USERS_TABLE
    target_user = _target_user(row) if is_users else None

    return DataChangeOut(
        entry_id=str(row.entry_id),
        occurred_at=row.occurred_at,
        known_change=True,
        actor=actor,
        table_name=row.table_name,
        # users.id наружу не отдаётся — идентичность только через target_user.
        record_id=None if is_users else row.record_id,
        operation=operation,
        changed_fields=kept,
        target_user=target_user,
        details_redacted=(
            actor_redacted or dropped or operation is None
            or (is_users and target_user is None)
        ),
    )


# ── /options ──────────────────────────────────────────────────────────────────

def build_options() -> AuditOptionsOut:
    """Значения фильтров, вычисленные из живых REGISTRY / CHANGE_REGISTRY.

    Никаких EventSpec internals, metadata schemas, строк журналов и
    пользовательских данных: только стабильные машинные имена и лимиты.
    """
    return AuditOptionsOut(
        audit_events=sorted(pol.AUDIT_EVENT_NAMES),
        auth_events=sorted(pol.AUTH_EVENT_NAMES),
        actor_roles=sorted(pol.ACTOR_ROLES),
        outcomes=list(pol.OUTCOMES),
        entity_types=sorted(pol.ENTITY_TYPES),
        tables=sorted(pol.CHANGE_TABLE_NAMES),
        operations=sorted(pol.CHANGE_OPERATIONS),
        actor_kinds={
            journal: list(policy.kinds)
            for journal, policy in pol.POLICY_BY_JOURNAL.items()
        },
        limits=AuditLimitsOut(
            default_range_days=DEFAULT_RANGE_DAYS,
            max_range_days=MAX_RANGE_DAYS,
            default_page_size=DEFAULT_PAGE_SIZE,
            max_page_size=MAX_PAGE_SIZE,
            max_result_window=MAX_RESULT_WINDOW,
            orders=list(pol.ORDERS),
        ),
    )
