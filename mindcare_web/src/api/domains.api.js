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

const PUBLIC_BASE = '/api/public/email-domains';

/**
 * GET /api/public/email-domains → { domains: string[] } — БЕЗ авторизации.
 * Только имена активных доменов, по которым можно создать аккаунт по email
 * (подсказка формы регистрации): id, комментариев и отключённых строк в ответе
 * нет. Это не проверка — допуск решает backend (init — ранняя проверка,
 * confirm — authoritative в транзакции).
 */
export function getPublicEmailDomains() {
  return apiFetch(PUBLIC_BASE);
}

/**
 * Безопасно извлекает имена доменов из ответа публичного endpoint: всё, что не
 * массив непустых строк, — пустой список (подсказка просто не показывается).
 */
export function emailDomainNamesOf(response) {
  const list = response?.domains;
  if (!Array.isArray(list)) return [];
  return list.filter((name) => typeof name === 'string' && name.trim() !== '');
}
