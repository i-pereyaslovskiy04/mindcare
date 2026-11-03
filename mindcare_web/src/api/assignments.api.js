import { apiFetch } from './client';

/**
 * Задания психолога клиенту (ADR-033). Все ответы — без кеша; в режиме
 * «под именем» backend отвечает 403.
 *
 * Клиент (membership-роль student):
 *   GET  /api/assignments/my?view=open|history&before&size
 *        → { items, has_more, next_cursor, total } — keyset-пагинация;
 *   GET  /api/assignments/my/summary → { open_count, completed_count, total_count };
 *   POST /api/assignments/my/{uuid}/complete → { uuid, status, …, changed }
 *        409 assignment_engagement_inactive / assignment_finalized, 404, 503.
 * Психолог (строгое активное сопровождение):
 *   GET  /api/psychologist/clients/{studentUuid}/assignments?before&size
 *        (чтение фиксируется в журнале; 503 — не удалось зафиксировать, тексты
 *        не отдаются);
 *   POST /api/psychologist/clients/{studentUuid}/assignments
 *        { text, due_date?, article_uuid? } → 201;
 *   POST /api/psychologist/assignments/{uuid}/cancel.
 * Тексты заданий не логировать.
 */

function query(params) {
  const q = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') q.set(key, String(value));
  });
  const s = q.toString();
  return s ? `?${s}` : '';
}

export function getMyAssignments({ view = 'open', before, size } = {}) {
  return apiFetch(`/api/assignments/my${query({ view, before, size })}`);
}

export function getMyAssignmentsSummary() {
  return apiFetch('/api/assignments/my/summary');
}

export function completeMyAssignment(uuid) {
  return apiFetch(`/api/assignments/my/${encodeURIComponent(uuid)}/complete`, { method: 'POST' });
}

export function getClientAssignments(studentUuid, { before, size } = {}) {
  return apiFetch(
    `/api/psychologist/clients/${encodeURIComponent(studentUuid)}/assignments${query({ before, size })}`,
  );
}

export function createClientAssignment(studentUuid, { text, dueDate, articleUuid }) {
  return apiFetch(`/api/psychologist/clients/${encodeURIComponent(studentUuid)}/assignments`, {
    method: 'POST',
    body: JSON.stringify({
      text,
      due_date: dueDate || null,
      article_uuid: articleUuid || null,
    }),
  });
}

export function cancelAssignment(uuid) {
  return apiFetch(`/api/psychologist/assignments/${encodeURIComponent(uuid)}/cancel`, {
    method: 'POST',
  });
}
