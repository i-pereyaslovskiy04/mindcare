/**
 * Admin audit viewer API — все вызовы /api/admin/audit/*.
 *
 * Read-only: у журналов нет ни мутаций, ни detail-эндпоинта, ни экспорта, и
 * добавлять их сюда нельзя. Каждая функция сериализует ТОЛЬКО ключи из своего
 * allowlist'а — произвольный объект параметров не принимается, неизвестные поля
 * молча отбрасываются (тот же приём, что в `users.api.js::updateUser`).
 *
 * Свободного поиска по журналам не существует: участник адресуется точным
 * `actor_uuid`, поэтому ни имя, ни email пользователя в query не попадают.
 *
 * Требуется роль admin — проверяется на сервере.
 */

import { apiFetch } from './client';

const BASE = '/api/admin/audit';

const COMMON_KEYS = ['page', 'size', 'date_from', 'date_to', 'order'];

const AUDIT_KEYS = [
  'actor_uuid',
  'actor_kind',
  'actor_role',
  'event_type',
  'outcome',
  'entity_type',
  'entity_id',
  'include_access_events',
];

const AUTH_KEYS = [
  'actor_uuid',
  'actor_kind',
  'event',
  'success',
];

const DCL_KEYS = [
  'actor_uuid',
  'actor_kind',
  'actor_role',
  'table_name',
  'operation',
  'record_id',
];

/**
 * «Не задано» — это только null / undefined / пустая строка.
 *
 * Истинностная проверка здесь была бы дефектом: `success=false` (просмотр
 * неудачных входов) — валидное применённое значение, и оно обязано уйти на
 * сервер.
 */
function isSet(value) {
  return value !== null && value !== undefined && value !== '';
}

function buildParams(keys, params) {
  const search = new URLSearchParams();
  for (const key of [...COMMON_KEYS, ...keys]) {
    const value = params?.[key];
    if (isSet(value)) search.set(key, String(value));
  }
  return search;
}

/** GET /api/admin/audit/options — безопасные значения фильтров из registry. */
export function getAuditOptions() {
  return apiFetch(`${BASE}/options`);
}

/** GET /api/admin/audit/events — журнал `audit_log`. */
export function getAuditEvents(params) {
  return apiFetch(`${BASE}/events?${buildParams(AUDIT_KEYS, params)}`);
}

/** GET /api/admin/audit/auth-events — журнал `auth_log`. */
export function getAuthEvents(params) {
  return apiFetch(`${BASE}/auth-events?${buildParams(AUTH_KEYS, params)}`);
}

/** GET /api/admin/audit/data-changes — журнал `data_change_log`. */
export function getDataChanges(params) {
  return apiFetch(`${BASE}/data-changes?${buildParams(DCL_KEYS, params)}`);
}

/** Журнал → функция загрузки его страницы. */
export const AUDIT_LOADERS = {
  audit_log: getAuditEvents,
  auth_log: getAuthEvents,
  data_change_log: getDataChanges,
};
