import { apiFetch } from './client';

// ── Public ────────────────────────────────────────────────────────────────────

export function getNews({ page = 1, size = 10, search } = {}) {
  const params = new URLSearchParams({ page, size });
  if (search) params.set('search', search);
  return apiFetch(`/api/news?${params}`);
}

export function getNewsById(uuid) {
  return apiFetch(`/api/news/${uuid}`);
}

// ── Admin ─────────────────────────────────────────────────────────────────────

export function getAdminNews({ page = 1, size = 20, search, is_published } = {}) {
  const params = new URLSearchParams({ page, size });
  if (search) params.set('search', search);
  if (is_published !== undefined && is_published !== null) {
    params.set('is_published', String(is_published));
  }
  return apiFetch(`/api/admin/news?${params}`);
}

export function getAdminNewsItem(uuid) {
  return apiFetch(`/api/admin/news/${uuid}`);
}

export function createNews(data) {
  return apiFetch('/api/admin/news', { method: 'POST', body: JSON.stringify(data) });
}

export function updateNews(uuid, data) {
  return apiFetch(`/api/admin/news/${uuid}`, { method: 'PATCH', body: JSON.stringify(data) });
}

export function deleteNews(uuid) {
  return apiFetch(`/api/admin/news/${uuid}`, { method: 'DELETE' });
}
