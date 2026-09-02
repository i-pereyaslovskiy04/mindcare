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

export function submitTest(uuid, answers, timedOut = false) {
  return apiFetch(`/api/tests/${uuid}/submit`, {
    method: 'POST',
    body: JSON.stringify({ answers, timed_out: timedOut }),
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

// ── Staff-доступ к результатам (Этап E, supervisor/psychologist) ──────────────
// activeRole → заголовок X-Active-Role (нужен только multi-role staff; backend
// валидирует по membership). Список — metadata; деталь — под audit.

function _roleHeader(activeRole) {
  return activeRole ? { 'X-Active-Role': activeRole } : {};
}

export function getStudentTestResults(studentUuid, activeRole, { page = 1, size = 20 } = {}) {
  const params = new URLSearchParams({ student_uuid: studentUuid, page, size });
  return apiFetch(`/api/staff/test-results?${params}`, { headers: _roleHeader(activeRole) });
}

export function getStaffTestResult(resultUuid, activeRole) {
  return apiFetch(`/api/staff/test-results/${resultUuid}`, { headers: _roleHeader(activeRole) });
}

// ── Admin / supervisor (Этап A/C) ─────────────────────────────────────────────

export function getAdminTests({ page = 1, size = 20, search, is_active, status } = {}) {
  const params = new URLSearchParams({ page, size });
  if (search) params.set('search', search);
  if (is_active !== undefined && is_active !== null) {
    params.set('is_active', String(is_active));
  }
  // status не передан → бэк отдаёт ВСЕ статусы (см. app/tests/routes_admin.py)
  if (status) params.set('status', status);
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

/**
 * Анализ несохранённого дерева: достижимый диапазон баллов и проблемы порогов
 * (дыры в покрытии, недостижимые пороги, ссылки на несуществующие шкалы).
 * Ничего не сохраняет — подсчёт остаётся единственным, на бэкенде.
 */
export function analyzeTest({ scoring, questions, interpretations }) {
  return apiFetch('/api/admin/tests/analyze', {
    method: 'POST',
    body: JSON.stringify({ scoring, questions, interpretations }),
  });
}

/**
 * Пробный подсчёт несохранённого дерева: тот же scoring, что у студента.
 * Ничего не сохраняет — ни результата, ни ответов.
 */
export function previewScore({ scoring, questions, interpretations, answers }) {
  return apiFetch('/api/admin/tests/preview-score', {
    method: 'POST',
    body: JSON.stringify({ scoring, questions, interpretations, answers }),
  });
}

/** Копия методики (черновик). Штатный путь правки теста, по которому есть результаты. */
export function duplicateTest(uuid) {
  return apiFetch(`/api/admin/tests/${uuid}/duplicate`, { method: 'POST' });
}

export function deleteTest(uuid) {
  return apiFetch(`/api/admin/tests/${uuid}`, { method: 'DELETE' });
}

// ── Moderation workflow (Этап F) ────────────────────────────────────────────

/** admin/supervisor публикуют тест (из draft/in_review/needs_changes). */
export function publishTest(uuid) {
  return apiFetch(`/api/admin/tests/${uuid}/publish`, { method: 'POST' });
}

/** admin/supervisor возвращают тест на доработку (только из in_review). */
export function returnTest(uuid, reason) {
  return apiFetch(`/api/admin/tests/${uuid}/return`, {
    method: 'POST',
    body: JSON.stringify({ reason: reason || null }),
  });
}

// ── Авторство psychologist (Этап F2) ────────────────────────────────────────
// Только свои тесты; создание всегда даёт status=draft (бэк игнорирует
// присланный status); правка/удаление — только пока draft/needs_changes.

export function getMyTests({ page = 1, size = 20, search, status } = {}) {
  const params = new URLSearchParams({ page, size });
  if (search) params.set('search', search);
  if (status) params.set('status', status);
  return apiFetch(`/api/psychologist/tests?${params}`);
}

export function getMyTest(uuid) {
  return apiFetch(`/api/psychologist/tests/${uuid}`);
}

export function createMyTest(data) {
  return apiFetch('/api/psychologist/tests', { method: 'POST', body: JSON.stringify(data) });
}

export function updateMyTest(uuid, data) {
  return apiFetch(`/api/psychologist/tests/${uuid}`, { method: 'PATCH', body: JSON.stringify(data) });
}

export function deleteMyTest(uuid) {
  return apiFetch(`/api/psychologist/tests/${uuid}`, { method: 'DELETE' });
}

/** Автор отправляет свой draft/needs_changes тест на модерацию. */
export function submitTestForReview(uuid) {
  return apiFetch(`/api/psychologist/tests/${uuid}/submit-for-review`, { method: 'POST' });
}

export function analyzeMyTest({ scoring, questions, interpretations }) {
  return apiFetch('/api/psychologist/tests/analyze', {
    method: 'POST',
    body: JSON.stringify({ scoring, questions, interpretations }),
  });
}

export function previewMyScore({ scoring, questions, interpretations, answers }) {
  return apiFetch('/api/psychologist/tests/preview-score', {
    method: 'POST',
    body: JSON.stringify({ scoring, questions, interpretations, answers }),
  });
}
