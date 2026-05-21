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
} = {}) {
  const params = new URLSearchParams({ page, size, sort, order });
  if (search)    params.set('search', search);
  if (role)      params.set('role', role);
  if (is_active !== '') params.set('is_active', is_active);
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

/** PATCH /api/admin/users/:uuid — partial update. */
export function updateUser(uuid, data) {
  return apiFetch(`${BASE}/${uuid}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
}

/** DELETE /api/admin/users/:uuid — soft delete, revokes all sessions. */
export function deleteUser(uuid) {
  return apiFetch(`${BASE}/${uuid}`, { method: 'DELETE' });
}
