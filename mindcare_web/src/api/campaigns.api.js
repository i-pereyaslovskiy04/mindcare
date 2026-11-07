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

/**
 * GET → { title, test_title, access_code_required, closes_at, instruction,
 * consent, faculties, questions }. При кодовом слове — только «замок»
 * (consent null, вопросов нет). До начала срока — 409 campaign_not_started
 * (err.body.opens_at).
 */
export function getPublicCampaign(token) {
  return apiFetch(`${PUBLIC_BASE}/${enc(token)}`);
}

/** POST { access_code } → та же анкета; неверное слово — 403 access_code_invalid. */
export function unlockPublicCampaign(token, accessCode) {
  return apiFetch(`${PUBLIC_BASE}/${enc(token)}/unlock`, {
    method: 'POST',
    body: JSON.stringify({ access_code: accessCode }),
  });
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

/** PATCH { title } → карточка. Адрес ссылки при переименовании не меняется. */
export function renameCampaign(uuid, title) {
  return apiFetch(`${SUPERVISOR_BASE}/${enc(uuid)}`, {
    method: 'PATCH',
    body: JSON.stringify({ title }),
  });
}

/** PATCH { opens_at, closes_at } (ISO с часовым поясом или null) → карточка */
export function setCampaignSchedule(uuid, { opens_at, closes_at }) {
  return apiFetch(`${SUPERVISOR_BASE}/${enc(uuid)}/schedule`, {
    method: 'PATCH',
    body: JSON.stringify({ opens_at, closes_at }),
  });
}

/** PUT { access_code } → карточка (слово больше не показывается). */
export function setCampaignAccessCode(uuid, accessCode) {
  return apiFetch(`${SUPERVISOR_BASE}/${enc(uuid)}/access-code`, {
    method: 'PUT',
    body: JSON.stringify({ access_code: accessCode }),
  });
}

export function clearCampaignAccessCode(uuid) {
  return apiFetch(`${SUPERVISOR_BASE}/${enc(uuid)}/access-code`, { method: 'DELETE' });
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
