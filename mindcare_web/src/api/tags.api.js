import { apiFetch } from './client';

const ADMIN_BASE  = '/api/admin/tags';
const PUBLIC_BASE = '/api/tags';

/** GET /api/admin/tags — список тегов с поиском и пагинацией. */
export function getTags({ page = 1, size = 50, search = '' } = {}) {
  const params = new URLSearchParams({ page, size });
  if (search) params.set('search', search);
  return apiFetch(`${ADMIN_BASE}/?${params}`);
}

/** POST /api/admin/tags — создать тег. */
export function createTag(data) {
  return apiFetch(`${ADMIN_BASE}/`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

/** PATCH /api/admin/tags/:uuid — переименовать тег. */
export function updateTag(uuid, data) {
  return apiFetch(`${ADMIN_BASE}/${uuid}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
}

/** DELETE /api/admin/tags/:uuid — удалить тег (каскадно удаляет все связи). */
export function deleteTag(uuid) {
  return apiFetch(`${ADMIN_BASE}/${uuid}`, { method: 'DELETE' });
}

/** GET /api/tags — публичный список для autocomplete в редакторе контента. */
export function getTagsPublic({ search = '', limit = 20 } = {}) {
  const params = new URLSearchParams({ limit });
  if (search) params.set('search', search);
  return apiFetch(`${PUBLIC_BASE}/?${params}`);
}
