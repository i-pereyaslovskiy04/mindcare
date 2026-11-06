import { apiFetch, apiFetchBlob } from './client';

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

// Ответы прохождения — только психологу клиента (под тем же audit content-read).
export function getStaffTestResultAnswers(resultUuid, activeRole) {
  return apiFetch(`/api/staff/test-results/${resultUuid}/answers`, {
    headers: _roleHeader(activeRole),
  });
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
export function analyzeTest({
  scoring, questions, interpretations, scoring_rules: scoringRules = null,
}) {
  return apiFetch('/api/admin/tests/analyze', {
    method: 'POST',
    // ADR-037: правила обработки — сверка с вопросами (rule_issues).
    body: JSON.stringify({ scoring, questions, interpretations, scoring_rules: scoringRules }),
  });
}

/**
 * Пробный подсчёт несохранённого дерева: тот же scoring, что у студента.
 * Ничего не сохраняет — ни результата, ни ответов.
 */
export function previewScore({
  scoring, questions, interpretations, answers, scoring_rules: scoringRules = null,
}) {
  return apiFetch('/api/admin/tests/preview-score', {
    method: 'POST',
    body: JSON.stringify({
      scoring, questions, interpretations, answers, scoring_rules: scoringRules,
    }),
  });
}

/** Копия методики (черновик). Штатный путь правки теста, по которому есть результаты. */
export function duplicateTest(uuid) {
  return apiFetch(`/api/admin/tests/${uuid}/duplicate`, { method: 'POST' });
}

/** ADR-037: новая версия методики — черновик с тем же lineage. */
export function createNewVersion(uuid) {
  return apiFetch(`/api/admin/tests/${uuid}/new-version`, { method: 'POST' });
}

/** ADR-037: исправление текстов без смены структуры (и при наличии результатов). */
export function correctTexts(uuid, body) {
  return apiFetch(`/api/admin/tests/${uuid}/texts`, { method: 'PATCH', body: JSON.stringify(body) });
}

export function deleteTest(uuid) {
  return apiFetch(`/api/admin/tests/${uuid}`, { method: 'DELETE' });
}

// ── Moderation workflow (Этап F) ────────────────────────────────────────────

/** Только число тестов на модерации — бейдж меню проверяющего. */
export function getTestsPendingCount() {
  return apiFetch('/api/admin/tests/pending-count');
}

// Решение модерации — по конкретному состоянию теста, которое видел проверяющий
// (статус + updated_at строки списка). Если под блокировкой состояние иное —
// 409 { code: 'test_state_changed', current_status } без изменений.
function decisionBody(item) {
  return { expected_status: item.status, expected_updated_at: item.updated_at };
}

/** admin/supervisor публикуют тест (из draft/in_review/needs_changes). */
export function publishTest(item) {
  return apiFetch(`/api/admin/tests/${item.uuid}/publish`, {
    method: 'POST',
    body: JSON.stringify(decisionBody(item)),
  });
}

/** admin/supervisor возвращают тест на доработку (только из in_review). */
export function returnTest(item, reason) {
  return apiFetch(`/api/admin/tests/${item.uuid}/return`, {
    method: 'POST',
    body: JSON.stringify({ ...decisionBody(item), reason: reason || null }),
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

/**
 * Копия своего теста (черновик) — Этап F2.2. Работает для любого статуса
 * источника (включая published/in_review): не мутирует оригинал, в отличие от
 * updateMyTest на published (та снимает исходный тест с публикации).
 */
export function duplicateMyTest(uuid) {
  return apiFetch(`/api/psychologist/tests/${uuid}/duplicate`, { method: 'POST' });
}

export function createMyNewVersion(uuid) {
  return apiFetch(`/api/psychologist/tests/${uuid}/new-version`, { method: 'POST' });
}

export function correctMyTexts(uuid, body) {
  return apiFetch(`/api/psychologist/tests/${uuid}/texts`, { method: 'PATCH', body: JSON.stringify(body) });
}

/** Автор отправляет свой draft/needs_changes тест на модерацию. */
export function submitTestForReview(uuid) {
  return apiFetch(`/api/psychologist/tests/${uuid}/submit-for-review`, { method: 'POST' });
}

export function analyzeMyTest({
  scoring, questions, interpretations, scoring_rules: scoringRules = null,
}) {
  return apiFetch('/api/psychologist/tests/analyze', {
    method: 'POST',
    // ADR-037: правила обработки — сверка с вопросами (rule_issues).
    body: JSON.stringify({ scoring, questions, interpretations, scoring_rules: scoringRules }),
  });
}

export function previewMyScore({
  scoring, questions, interpretations, answers, scoring_rules: scoringRules = null,
}) {
  return apiFetch('/api/psychologist/tests/preview-score', {
    method: 'POST',
    body: JSON.stringify({
      scoring, questions, interpretations, answers, scoring_rules: scoringRules,
    }),
  });
}

// ── ADR-037: шаблон xlsx, импорт и выгрузка методики ────────────────────────
// base — '/api/admin/tests' (admin/supervisor) или '/api/psychologist/tests'.

export const ADMIN_TESTS_BASE = '/api/admin/tests';
export const MY_TESTS_BASE = '/api/psychologist/tests';

/** → { blob, filename } */
export function downloadMethodologyTemplate(base = ADMIN_TESTS_BASE) {
  return apiFetchBlob(`${base}/methodology-template.xlsx`);
}

/** → { blob, filename } */
export function exportMethodology(uuid, base = ADMIN_TESTS_BASE) {
  return apiFetchBlob(`${base}/${uuid}/methodology.xlsx`);
}

/**
 * dryRun=true → { ok, errors[{sheet,row,column,message}], warnings, summary };
 * иначе → { ..., test_uuid } (черновик). 422 с отчётом — в err.body.
 */
export function importMethodology(file, { dryRun = false, base = ADMIN_TESTS_BASE } = {}) {
  const form = new FormData();
  form.append('file', file);
  return apiFetch(`${base}/import?dry_run=${dryRun ? 'true' : 'false'}`, {
    method: 'POST',
    body: form,
  });
}
