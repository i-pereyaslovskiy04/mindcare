import { apiFetch } from './client';

const ADMIN_BASE = '/api/admin/email-domains';

/** GET /api/admin/email-domains — список разрешённых доменов (активные + off). */
export function getEmailDomains() {
  return apiFetch(`${ADMIN_BASE}/`);
}

/** POST /api/admin/email-domains — добавить домен. */
export function createEmailDomain(data) {
  return apiFetch(`${ADMIN_BASE}/`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

/**
 * PATCH /api/admin/email-domains/:id — отключить / включить домен либо изменить
 * комментарий. data: { is_active?, comment? }.
 */
export function updateEmailDomain(id, data) {
  return apiFetch(`${ADMIN_BASE}/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
}
