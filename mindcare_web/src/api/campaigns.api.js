import { apiFetch, apiFetchBlob } from './client';

/**
 * Тестовые кампании по публичной ссылке (ADR-036).
 *
 * Публично (без входа): анкета по токену ссылки и отправка ответов.
 * Супервизор: кампании, ссылки, участники (ФИО — под аудитом на backend),
 * выгрузка xlsx, удаление. ФИО, ответы и токены не логировать.
 */

const PUBLIC_BASE = '/api/public/campaigns';
const SUPERVISOR_BASE = '/api/supervisor/campaigns';

const enc = encodeURIComponent;

// ── публично ─────────────────────────────────────────────────────────────────

/** GET → { title, test_title, instruction, consent, faculties, questions } */
export function getPublicCampaign(token) {
  return apiFetch(`${PUBLIC_BASE}/${enc(token)}`);
}

/** POST → { status: 'accepted' } (201 — принято, 200 — повтор того же ключа) */
export function submitPublicCampaign(token, body) {
  return apiFetch(`${PUBLIC_BASE}/${enc(token)}/submit`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

// ── супервизор ───────────────────────────────────────────────────────────────

/** GET → [{ uuid, title }] — тесты, доступные для кампаний. */
export function getCampaignTests() {
  return apiFetch(`${SUPERVISOR_BASE}/tests`);
}

/** GET ?size&before → { items, has_more } (новые сверху) */
export function getCampaigns({ size = 20, before } = {}) {
  const params = new URLSearchParams({ size });
  if (before) params.set('before', before);
  return apiFetch(`${SUPERVISOR_BASE}?${params}`);
}

/** POST { title, test_uuid } → карточка со ссылкой */
export function createCampaign({ title, test_uuid }) {
  return apiFetch(SUPERVISOR_BASE, {
    method: 'POST',
    body: JSON.stringify({ title, test_uuid }),
  });
}

export function getCampaign(uuid) {
  return apiFetch(`${SUPERVISOR_BASE}/${enc(uuid)}`);
}

/** PATCH { status: 'open'|'closed' } → карточка */
export function setCampaignStatus(uuid, status) {
  return apiFetch(`${SUPERVISOR_BASE}/${enc(uuid)}/status`, {
    method: 'PATCH',
    body: JSON.stringify({ status }),
  });
}

export function rotateCampaignLink(uuid) {
  return apiFetch(`${SUPERVISOR_BASE}/${enc(uuid)}/rotate-link`, { method: 'POST' });
}

export function deleteCampaign(uuid) {
  return apiFetch(`${SUPERVISOR_BASE}/${enc(uuid)}`, { method: 'DELETE' });
}

/** GET ?size&after → { items, has_more } (по времени прохождения) */
export function getCampaignResponses(uuid, { size = 50, after } = {}) {
  const params = new URLSearchParams({ size });
  if (after) params.set('after', after);
  return apiFetch(`${SUPERVISOR_BASE}/${enc(uuid)}/responses?${params}`);
}

export function deleteCampaignResponse(uuid, responseUuid) {
  return apiFetch(
    `${SUPERVISOR_BASE}/${enc(uuid)}/responses/${enc(responseUuid)}`,
    { method: 'DELETE' },
  );
}

/**
 * GET первичной обработки: баллы, уровни, достоверность и типы участников
 * + сводка по отфильтрованному набору. Фильтры — на сервере:
 * { faculty_code, gender, validity: 'valid'|'invalid', type: имя | '__none__' }.
 */
export function getCampaignResults(uuid, filters = {}) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value) params.set(key, value);
  });
  const query = params.toString();
  return apiFetch(`${SUPERVISOR_BASE}/${enc(uuid)}/results${query ? `?${query}` : ''}`);
}

/** GET xlsx → { blob, filename } */
export function downloadCampaignResults(uuid) {
  return apiFetchBlob(`${SUPERVISOR_BASE}/${enc(uuid)}/export.xlsx`);
}
