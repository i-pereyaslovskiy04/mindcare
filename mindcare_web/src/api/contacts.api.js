import { apiFetch } from './client';

/**
 * Контакты пользователя (ADR-032).
 *
 * Владелец (вне режима «под именем»; в impersonation backend отвечает 403):
 *   GET → { version, updated_at, items, limits, catalog }
 *   PUT { version, items } → то же + changed. У КАЖДОГО item обязателен `id` —
 *   UUID, созданный клиентом один раз (повтор после потерянного ответа — no-op).
 *   409 contacts_version_conflict (err.body.current_version), 422 contacts_invalid
 *   (err.body.errors: [{index, field, code}] — без значений).
 * Сотрудник (психолог с активным сопровождением / супервизор), только чтение:
 *   GET → { primary_phone, items, updated_at, catalog }; 404 — недоступно,
 *   503 — не удалось зафиксировать обращение (данные не отдаются).
 * Значения контактов не логировать.
 */
const OWN = '/api/auth/profile/contacts';

export function getMyContacts() {
  return apiFetch(OWN);
}

export function saveMyContacts({ version, items }) {
  return apiFetch(OWN, {
    method: 'PUT',
    body: JSON.stringify({ version, items }),
  });
}

export function getUserContacts(userUuid) {
  return apiFetch(`/api/staff/users/${encodeURIComponent(userUuid)}/contacts`);
}
