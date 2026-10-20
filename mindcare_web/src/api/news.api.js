import { apiFetch } from './client';

// ── Нормализация ──────────────────────────────────────────────────────────────
// Приводит объект из API к формату который ожидают публичные компоненты
// (FeaturedNews, NewsCardSmall, NewsListItem, NewsItemPage).
// Используется и в useNews.js и в NewsSection.jsx — единый источник правды.

function formatDate(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleDateString('ru-RU', {
    day: 'numeric', month: 'long', year: 'numeric',
  });
}

export function normalizeNewsItem(item) {
  return {
    id:          item.uuid,         // для ссылок /news/:id
    uuid:        item.uuid,
    tag:         item.tags?.[0]?.name || '',
    title:       item.title,
    description: '',
    date:        formatDate(item.published_at || item.created_at),
    image:       item.cover_image_url || null,
    content:     item.content,
    tags:        item.tags,
  };
}

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
