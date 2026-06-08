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
