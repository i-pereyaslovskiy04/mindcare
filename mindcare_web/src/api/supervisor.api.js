import { apiFetch } from './client';

// ── Students ──────────────────────────────────────────────────────────────────

export function getSupervisorStudents({ page = 1, size = 20, search } = {}) {
  const params = new URLSearchParams({ page, size });
  if (search) params.set('search', search);
  return apiFetch(`/api/supervisor/students?${params}`);
}

// ── Psychologists ─────────────────────────────────────────────────────────────

export function getSupervisorPsychologists({ page = 1, size = 100, search } = {}) {
  const params = new URLSearchParams({ page, size });
  if (search) params.set('search', search);
  return apiFetch(`/api/supervisor/psychologists?${params}`);
}

// ── Engagements ───────────────────────────────────────────────────────────────

export function getSupervisorEngagements({
  page = 1,
  size = 20,
  status,
  student_search,
  psychologist_search,
} = {}) {
  const params = new URLSearchParams({ page, size });
  if (status)             params.set('status', status);
  if (student_search)     params.set('student_search', student_search);
  if (psychologist_search) params.set('psychologist_search', psychologist_search);
  return apiFetch(`/api/supervisor/engagements?${params}`);
}

export function createEngagement({ client_id, psychologist_id, primary_concern }) {
  return apiFetch('/api/supervisor/engagements', {
    method: 'POST',
    body: JSON.stringify({ client_id, psychologist_id, primary_concern }),
  });
}

export function transferEngagement(engagementId, { new_psychologist_id, transfer_reason }) {
  return apiFetch(`/api/supervisor/engagements/${engagementId}/transfer`, {
    method: 'PATCH',
    body: JSON.stringify({ new_psychologist_id, transfer_reason }),
  });
}

export function closeEngagement(engagementId, { reason } = {}) {
  return apiFetch(`/api/supervisor/engagements/${engagementId}/close`, {
    method: 'PATCH',
    body: JSON.stringify({ reason: reason || null }),
  });
}

// ── Unregistered student cards ────────────────────────────────────────────────
// Карточки незарегистрированных (пришедших лично) студентов. Используются как
// субъект ручной записи супервизором без active engagement.

export function getUnregisteredStudentCards({
  q,
  include_archived = false,
  page = 1,
  size = 20,
} = {}) {
  const params = new URLSearchParams({ page, size });
  if (q) params.set('q', q);
  if (include_archived) params.set('include_archived', 'true');
  return apiFetch(`/api/supervisor/unregistered-student-cards?${params}`);
}

export function createUnregisteredStudentCard(payload) {
  return apiFetch('/api/supervisor/unregistered-student-cards', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateUnregisteredStudentCard(cardId, payload) {
  return apiFetch(`/api/supervisor/unregistered-student-cards/${cardId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function archiveUnregisteredStudentCard(cardId) {
  return apiFetch(
    `/api/supervisor/unregistered-student-cards/${cardId}/archive`,
    { method: 'POST' },
  );
}
