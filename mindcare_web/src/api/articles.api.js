import { apiFetch } from './client';

// ── Public ────────────────────────────────────────────────────────────────────

export function getArticles({ page = 1, size = 10, search, category_id } = {}) {
  const params = new URLSearchParams({ page, size });
  if (search)      params.set('search', search);
  if (category_id) params.set('category_id', category_id);
  return apiFetch(`/api/articles?${params}`);
}

export function getArticleById(uuid) {
  return apiFetch(`/api/articles/${uuid}`);
}

export function getPublicCategories() {
  return apiFetch('/api/articles/categories');
}

// ── Admin ─────────────────────────────────────────────────────────────────────

export function getAdminArticles({ page = 1, size = 20, search, is_published, category_id } = {}) {
  const params = new URLSearchParams({ page, size });
  if (search)      params.set('search', search);
  if (category_id) params.set('category_id', category_id);
  if (is_published !== undefined && is_published !== null) {
    params.set('is_published', String(is_published));
  }
  return apiFetch(`/api/admin/articles?${params}`);
}

export function getAdminArticleItem(uuid) {
  return apiFetch(`/api/admin/articles/${uuid}`);
}

export function getAdminCategories() {
  return apiFetch('/api/admin/articles/categories');
}

export function createArticle(data) {
  return apiFetch('/api/admin/articles', { method: 'POST', body: JSON.stringify(data) });
}

export function updateArticle(uuid, data) {
  return apiFetch(`/api/admin/articles/${uuid}`, { method: 'PATCH', body: JSON.stringify(data) });
}

export function deleteArticle(uuid) {
  return apiFetch(`/api/admin/articles/${uuid}`, { method: 'DELETE' });
}
