import { apiFetch } from './client';

// ── Admin ─────────────────────────────────────────────────────────────────────

export function getAdminCategories({ page = 1, size = 50, search, is_active } = {}) {
  const params = new URLSearchParams({ page, size });
  if (search) params.set('search', search);
  if (is_active !== undefined && is_active !== null) {
    params.set('is_active', String(is_active));
  }
  return apiFetch(`/api/admin/categories?${params}`);
}

export function getAdminCategoryItem(id) {
  return apiFetch(`/api/admin/categories/${id}`);
}

export function createCategory(data) {
  return apiFetch('/api/admin/categories', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export function updateCategory(id, data) {
  return apiFetch(`/api/admin/categories/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
}

export function deleteCategory(id) {
  return apiFetch(`/api/admin/categories/${id}`, { method: 'DELETE' });
}
