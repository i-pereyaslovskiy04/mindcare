import { apiFetch } from './client';

// ── Public ────────────────────────────────────────────────────────────────────

export function getArticles({ page = 1, size = 10, search, category_id, tag_uuid } = {}) {
  const params = new URLSearchParams({ page, size });
  if (search)      params.set('search', search);
  if (category_id) params.set('category_id', category_id);
  if (tag_uuid)    params.set('tag_uuid', tag_uuid);
  return apiFetch(`/api/articles?${params}`);
}

/** Темы опубликованных статей — варианты фильтра «Тема» библиотеки. */
export function getArticleTags() {
  return apiFetch('/api/articles/tags');
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

// ── ADR-034: свои статьи автора ──────────────────────────────────────────────
// role: 'psychologist' (по умолчанию) — публикует проверяющий после submit;
// 'supervisor' (Дополнение 2026-10-28) — публикует сам (publishMyArticle).
// Создание — черновик; правка опубликованной снимает её с публикации;
// 409 article_state_conflict (err.body.current_status) — недопустимый статус.

const AUTHOR_BASES = {
  psychologist: '/api/psychologist/articles',
  supervisor: '/api/supervisor/articles',
};

function authorBase(role) {
  return AUTHOR_BASES[role] || AUTHOR_BASES.psychologist;
}

export function getMyArticles({ page = 1, size = 20, search, status } = {}, role) {
  const q = new URLSearchParams({ page, size });
  if (search) q.set('search', search);
  if (status) q.set('status', status);
  return apiFetch(`${authorBase(role)}?${q}`);
}

export function getMyArticle(uuid, role) {
  return apiFetch(`${authorBase(role)}/${encodeURIComponent(uuid)}`);
}

export function createMyArticle(data, role) {
  return apiFetch(authorBase(role), { method: 'POST', body: JSON.stringify(data) });
}

export function updateMyArticle(uuid, data, role) {
  return apiFetch(`${authorBase(role)}/${encodeURIComponent(uuid)}`, {
    method: 'PATCH', body: JSON.stringify(data),
  });
}

export function deleteMyArticle(uuid, role) {
  return apiFetch(`${authorBase(role)}/${encodeURIComponent(uuid)}`, { method: 'DELETE' });
}

/** Психолог: на проверку (draft / needs_changes → in_review). */
export function submitMyArticle(uuid) {
  return apiFetch(`${AUTHOR_BASES.psychologist}/${encodeURIComponent(uuid)}/submit`, { method: 'POST' });
}

/** Супервизор: опубликовать свою статью сам (draft / needs_changes → published). */
export function publishMyArticle(uuid) {
  return apiFetch(`${AUTHOR_BASES.supervisor}/${encodeURIComponent(uuid)}/publish`, { method: 'POST' });
}

// ── ADR-034: модерация (supervisor / admin) ──────────────────────────────────

export function getReviewArticles({ page = 1, size = 20 } = {}) {
  return apiFetch(`/api/review/articles?${new URLSearchParams({ page, size })}`);
}

/** Только число статей на проверке — бейдж меню проверяющего. */
export function getReviewArticlesPendingCount() {
  return apiFetch('/api/review/articles/pending-count');
}

export function getReviewArticle(uuid) {
  return apiFetch(`/api/review/articles/${encodeURIComponent(uuid)}`);
}

export function publishReviewArticle(uuid) {
  return apiFetch(`/api/review/articles/${encodeURIComponent(uuid)}/publish`, { method: 'POST' });
}

export function returnReviewArticle(uuid, comment) {
  return apiFetch(`/api/review/articles/${encodeURIComponent(uuid)}/return`, {
    method: 'POST', body: JSON.stringify({ comment: comment || null }),
  });
}
