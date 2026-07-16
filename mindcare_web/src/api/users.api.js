/**
 * Users API (admin) — all /api/admin/users/* calls.
 *
 * All functions go through apiFetch (client.js).
 * Requires admin role — enforced server-side.
 */

import { apiFetch } from './client';

const BASE = '/api/admin/users';

/** GET /api/admin/users — paginated list with optional search/filter. */
export function getUsers({
  page = 1,
  size = 20,
  search = '',
  role = '',
  is_active = '',
  sort = 'created_at',
  order = 'desc',
  include_deleted = false,
} = {}) {
  const params = new URLSearchParams({ page, size, sort, order });
  if (search)           params.set('search', search);
  if (role)             params.set('role', role);
  if (is_active !== '') params.set('is_active', is_active);
  if (include_deleted)  params.set('include_deleted', 'true');
  return apiFetch(`${BASE}/?${params}`);
}

/** GET /api/admin/users/:uuid */
export function getUser(uuid) {
  return apiFetch(`${BASE}/${uuid}`);
}

/** POST /api/admin/users — creates psychologist or admin account. */
export function createUser(data) {
  return apiFetch(`${BASE}/`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

/**
 * PATCH /api/admin/users/:uuid — partial update.
 *
 * Allowlist: defensive filtering — только эти поля уходят на backend,
 * неизвестные поля отбрасываются. Multi-role (ADR-018): `roles` — целевой набор
 * STAFF-ролей (student сохраняется backend'ом). Legacy `role` оставлен для
 * совместимости, но новый UI шлёт `roles`. При добавлении staff-роли backend
 * требует legal_basis_confirmed + basis_type + basis_reference; useUserForm
 * гарантирует их присутствие только когда роль реально добавляется.
 */
const EDITABLE_FIELDS = [
  'full_name', 'phone', 'is_active',
  'role', 'roles',
  'legal_basis_confirmed', 'basis_type', 'basis_reference', 'legal_basis_comment',
];

export function updateUser(uuid, data) {
  const body = {};
  for (const key of EDITABLE_FIELDS) {
    if (data[key] !== undefined) body[key] = data[key];
  }
  return apiFetch(`${BASE}/${uuid}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
}

/** DELETE /api/admin/users/:uuid — soft delete, revokes all sessions. */
export function deleteUser(uuid) {
  return apiFetch(`${BASE}/${uuid}`, { method: 'DELETE' });
}
