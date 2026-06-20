import { apiFetch } from './client';

// ── Student-facing (Этап B/D) ─────────────────────────────────────────────────

export function getTests({ page = 1, size = 20, search } = {}) {
  const params = new URLSearchParams({ page, size });
  if (search) params.set('search', search);
  return apiFetch(`/api/tests?${params}`);
}

export function getTestForTake(uuid) {
  return apiFetch(`/api/tests/${uuid}`);
}

export function submitTest(uuid, answers) {
  return apiFetch(`/api/tests/${uuid}/submit`, {
    method: 'POST',
    body: JSON.stringify({ answers }),
  });
}

export function getTestConsent() {
  return apiFetch('/api/tests/consent');
}

export function acceptTestConsent() {
  return apiFetch('/api/tests/consent/accept', { method: 'POST' });
}

export function getTestResults({ page = 1, size = 20 } = {}) {
  const params = new URLSearchParams({ page, size });
  return apiFetch(`/api/tests/results?${params}`);
}

export function getTestResult(resultUuid) {
  return apiFetch(`/api/tests/results/${resultUuid}`);
}

// ── Admin / supervisor (Этап A/C) ─────────────────────────────────────────────

export function getAdminTests({ page = 1, size = 20, search, is_active } = {}) {
  const params = new URLSearchParams({ page, size });
  if (search) params.set('search', search);
  if (is_active !== undefined && is_active !== null) {
    params.set('is_active', String(is_active));
  }
  return apiFetch(`/api/admin/tests?${params}`);
}

export function getAdminTest(uuid) {
  return apiFetch(`/api/admin/tests/${uuid}`);
}

export function createTest(data) {
  return apiFetch('/api/admin/tests', { method: 'POST', body: JSON.stringify(data) });
}

export function updateTest(uuid, data) {
  return apiFetch(`/api/admin/tests/${uuid}`, { method: 'PATCH', body: JSON.stringify(data) });
}

export function deleteTest(uuid) {
  return apiFetch(`/api/admin/tests/${uuid}`, { method: 'DELETE' });
}
