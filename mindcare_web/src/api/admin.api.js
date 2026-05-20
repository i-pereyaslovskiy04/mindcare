import { apiFetch } from './client';

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
  if (search) params.set('search', search);
  if (role) params.set('role', role);
  if (is_active !== '') params.set('is_active', is_active);
  return apiFetch(`/api/admin/users/?${params}`);
}
