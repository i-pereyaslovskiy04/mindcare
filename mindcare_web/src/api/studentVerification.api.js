import { apiFetch } from './client';

/**
 * Подтверждение статуса студента ДонГУ (ADR-029).
 *
 * Self-service (чистый student вне режима «под именем»): собственный статус и
 * подача заявки. Каталог факультетов — любой аутентифицированный; коды и
 * подписи приходят только с backend (на клиенте не зашиты).
 *
 * Supervisor: список (без номера билета), карточка (полный номер — под аудитом
 * на backend), решения. Ошибки несут стабильный err.code.
 * Номер билета и пояснение отказа не логировать.
 */

const BASE = '/api/student-verification';
const SUPERVISOR_BASE = '/api/supervisor/student-verifications';

/** GET → { items: [{ code, label }] } */
export function getFaculties() {
  return apiFetch(`${BASE}/faculties`);
}

/** GET → { status, can_submit, current } */
export function getMyVerification() {
  return apiFetch(`${BASE}/me`);
}

/** POST { faculty_code, ticket_number } → { status, can_submit, current } */
export function submitMyVerification({ faculty_code, ticket_number }) {
  return apiFetch(`${BASE}/me`, {
    method: 'POST',
    body: JSON.stringify({ faculty_code, ticket_number }),
  });
}

/** GET ?status&page&size&search → { items, total, page, size } */
export function getStudentVerifications({ page = 1, size = 20, status = 'pending', search } = {}) {
  const params = new URLSearchParams({ page, size, status });
  if (search) params.set('search', search);
  return apiFetch(`${SUPERVISOR_BASE}?${params}`);
}

/** GET карточки: содержит полный номер билета. */
export function getStudentVerification(uuid) {
  return apiFetch(`${SUPERVISOR_BASE}/${encodeURIComponent(uuid)}`);
}

export function approveStudentVerification(uuid) {
  return apiFetch(`${SUPERVISOR_BASE}/${encodeURIComponent(uuid)}/approve`, {
    method: 'POST',
  });
}

export function rejectStudentVerification(uuid, reason) {
  return apiFetch(`${SUPERVISOR_BASE}/${encodeURIComponent(uuid)}/reject`, {
    method: 'POST',
    body: JSON.stringify({ reason }),
  });
}
