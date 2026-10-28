import { apiFetch } from './client';

/**
 * Избранные материалы пользователя (ADR-034). Только для себя; в режиме
 * «под именем» backend отвечает 403.
 *   GET    /api/materials/favorites/ids → { uuids, count }
 *   GET    /api/materials/favorites?page&size&search&category_id
 *          → { items, total, page, size } (только опубликованные)
 *   PUT    /api/materials/favorites/{uuid} → 204 (повтор — no-op);
 *          404 material_not_available, 409 favorites_limit
 *   DELETE /api/materials/favorites/{uuid} → 204 (повтор — no-op)
 */
const BASE = '/api/materials/favorites';

export function getFavoriteIds() {
  return apiFetch(`${BASE}/ids`);
}

export function getFavoriteMaterials({ page = 1, size = 10, search, category_id, tag_uuid } = {}) {
  const q = new URLSearchParams({ page, size });
  if (search) q.set('search', search);
  if (category_id != null) q.set('category_id', category_id);
  if (tag_uuid) q.set('tag_uuid', tag_uuid);
  return apiFetch(`${BASE}?${q}`);
}

export function addFavorite(uuid) {
  return apiFetch(`${BASE}/${encodeURIComponent(uuid)}`, { method: 'PUT' });
}

export function removeFavorite(uuid) {
  return apiFetch(`${BASE}/${encodeURIComponent(uuid)}`, { method: 'DELETE' });
}
