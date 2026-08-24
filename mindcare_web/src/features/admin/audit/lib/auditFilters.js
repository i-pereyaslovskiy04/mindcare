/**
 * Модель состояния фильтров admin audit viewer — чистые функции без React.
 *
 * Ключевое решение: фильтры хранятся ПО ЖУРНАЛАМ, а не одним плоским объектом.
 * Наборы допустимых значений у журналов разные (`actor_kind=system` существует
 * для `audit_log` и не существует для `auth_log`/`data_change_log`; у `auth_log`
 * нет фильтра роли вовсе), поэтому общий объект при переключении вкладки унёс бы
 * чужое значение и получил 422. При раздельных срезах отправить чужой ключ
 * физически невозможно.
 */

import {
  USER_ENTITY_TYPE,
  USER_TABLE_NAME,
  categoryOf,
} from './auditLabels';
import { dateSpanDays, moscowToday, shiftDateOnly } from './auditFormatters';

export const SOURCES = ['audit_log', 'auth_log', 'data_change_log'];

/**
 * Лимиты на случай недоступного `/options`. Совпадают с текущими значениями
 * backend'а, но авторитетом не являются: сервер всё равно проверяет сам.
 */
export const FALLBACK_LIMITS = Object.freeze({
  default_range_days: 7,
  max_range_days: 90,
  default_page_size: 20,
  max_page_size: 100,
  max_result_window: 100000,
  orders: ['asc', 'desc'],
});

// entity_id / record_id — колонки PostgreSQL INTEGER. Это не произвольный
// лимит, а физический диапазон типа: значение вне него backend отвергает 422.
export const MIN_RECORD_REF = 1;
export const MAX_RECORD_REF = 2147483647;

export const ORDER_OPTIONS = [
  { value: 'desc', label: 'Сначала новые' },
  { value: 'asc', label: 'Сначала старые' },
];

/** Общие для всех трёх журналов фильтры. */
export function defaultCommon(rangeDays = FALLBACK_LIMITS.default_range_days) {
  const dateTo = moscowToday();
  return {
    dateFrom: shiftDateOnly(dateTo, -(rangeDays - 1)),
    dateTo,
    order: 'desc',
    actorUuid: '',
  };
}

export const COMMON_KEYS = ['dateFrom', 'dateTo', 'order', 'actorUuid'];

/** Дефолтные срезы фильтров каждого журнала. `category` — frontend-only. */
export const SOURCE_DEFAULTS = Object.freeze({
  audit_log: Object.freeze({
    actorKind: '',
    actorRole: '',
    category: '',
    eventType: '',
    outcome: '',
    entityType: '',
    entityId: '',
    includeAccessEvents: false,
  }),
  auth_log: Object.freeze({
    actorKind: '',
    event: '',
    success: null,
  }),
  data_change_log: Object.freeze({
    actorKind: '',
    actorRole: '',
    tableName: '',
    operation: '',
    recordId: '',
  }),
});

export function defaultBySource() {
  return {
    audit_log: { ...SOURCE_DEFAULTS.audit_log },
    auth_log: { ...SOURCE_DEFAULTS.auth_log },
    data_change_log: { ...SOURCE_DEFAULTS.data_change_log },
  };
}

/**
 * Раскладывает патч `setFilters` на общий срез и срез текущего журнала.
 * Ключ, не принадлежащий ни одному из них, отбрасывается: так чужой фильтр не
 * может просочиться в состояние из-за опечатки в компоненте.
 */
export function routeFilterPatch(patch, source) {
  const common = {};
  const slice = {};
  const ignored = [];
  const sliceDefaults = SOURCE_DEFAULTS[source] ?? {};

  for (const [key, value] of Object.entries(patch ?? {})) {
    if (COMMON_KEYS.includes(key)) {
      common[key] = value;
    } else if (Object.prototype.hasOwnProperty.call(sliceDefaults, key)) {
      slice[key] = value;
    } else {
      ignored.push(key);
    }
  }

  return { common, slice, ignored };
}

/**
 * Смена категории обнуляет выбранное событие, если оно в новую категорию не
 * входит. Иначе Select показывал бы одну категорию, а запрос уходил бы с
 * событием из другой.
 */
export function pruneEventForCategory(eventType, category) {
  if (!eventType) return '';
  if (!category) return eventType;
  return categoryOf(eventType) === category ? eventType : '';
}

/**
 * Разбор точного идентификатора цели. Пустая строка — «не задано» (не ошибка).
 * Возвращает `{ value, error }`; `value` уходит в запрос только когда `error`
 * пуст.
 */
export function parseRecordRef(raw) {
  if (raw === '' || raw === null || raw === undefined) {
    return { value: null, error: null };
  }
  const text = String(raw).trim();
  if (!/^\d+$/.test(text)) {
    return { value: null, error: 'Идентификатор — целое число' };
  }
  const value = Number(text);
  if (value < MIN_RECORD_REF || value > MAX_RECORD_REF) {
    return {
      value: null,
      error: `Допустимый диапазон ${MIN_RECORD_REF}…${MAX_RECORD_REF}`,
    };
  }
  return { value, error: null };
}

/**
 * Точный идентификатор доступен только вместе с явным НЕ-пользовательским типом
 * цели: backend отвергает и «id без типа», и пару «пользователь + id» (по
 * целому числу перебором восстанавливался бы users.id → UUID).
 */
export function isEntityRefAllowed(entityType) {
  return Boolean(entityType) && entityType !== USER_ENTITY_TYPE;
}

export function isRecordRefAllowed(tableName) {
  return Boolean(tableName) && tableName !== USER_TABLE_NAME;
}

/** Клиентская проверка окна. Backend остаётся авторитетным. */
export function validateWindow(dateFrom, dateTo, maxRangeDays) {
  if (!dateFrom || !dateTo) {
    return 'Укажите обе границы периода';
  }
  const span = dateSpanDays(dateFrom, dateTo);
  if (span === null) {
    return 'Некорректная дата';
  }
  if (span < 1) {
    return 'Дата «с» не может быть позже даты «по»';
  }
  if (span > maxRangeDays) {
    return `Период не может превышать ${maxRangeDays} дней (выбрано ${span})`;
  }
  return null;
}

/**
 * Глубина выборки ограничена окном `max_result_window`: при size=20 backend
 * принимает максимум страницу 5000. Без этой поправки обычный
 * `ceil(total / size)` предложил бы страницу 5001 и получил 422.
 */
export function computePagination(total, size, maxResultWindow) {
  const safeSize = size > 0 ? size : FALLBACK_LIMITS.default_page_size;
  const backendPages = Math.ceil((total ?? 0) / safeSize);
  const windowPages = Math.floor(
    (maxResultWindow ?? FALLBACK_LIMITS.max_result_window) / safeSize,
  );
  const totalPages = Math.max(1, Math.min(backendPages, windowPages));
  return { totalPages, windowLimited: backendPages > windowPages };
}

/** Класс актора отправляется только если он достижим для этого журнала. */
function safeActorKind(actorKind, source, options) {
  if (!actorKind) return '';
  const allowed = options?.actor_kinds?.[source];
  if (!Array.isArray(allowed)) return '';
  return allowed.includes(actorKind) ? actorKind : '';
}

/**
 * Состояние → параметры запроса конкретного журнала. Ключи, которых у журнала
 * нет, здесь просто не появляются; `category` не появляется никогда — это
 * группировка опций, а не фильтр API.
 */
export function buildQuery({ source, common, slice, page, size, options }) {
  const base = {
    page,
    size,
    date_from: common.dateFrom,
    date_to: common.dateTo,
    order: common.order,
    actor_uuid: common.actorUuid,
    actor_kind: safeActorKind(slice.actorKind, source, options),
  };

  if (source === 'audit_log') {
    const ref = isEntityRefAllowed(slice.entityType)
      ? parseRecordRef(slice.entityId)
      : { value: null, error: null };
    return {
      ...base,
      actor_role: slice.actorRole,
      event_type: slice.eventType,
      outcome: slice.outcome,
      entity_type: slice.entityType,
      entity_id: ref.error ? null : ref.value,
      include_access_events: slice.includeAccessEvents,
    };
  }

  if (source === 'auth_log') {
    return {
      ...base,
      event: slice.event,
      success: slice.success,
    };
  }

  const ref = isRecordRefAllowed(slice.tableName)
    ? parseRecordRef(slice.recordId)
    : { value: null, error: null };
  return {
    ...base,
    actor_role: slice.actorRole,
    table_name: slice.tableName,
    operation: slice.operation,
    record_id: ref.error ? null : ref.value,
  };
}
