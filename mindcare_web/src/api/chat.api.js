import { apiFetch, apiFetchBlob } from './client';

/**
 * Chat API (student side, Stage 28d).
 *
 * Backend: /api/chat/my-conversation* — single one-to-one conversation
 * со своим психологом (по therapy_engagement). conversation === null,
 * если психолог ещё не назначен.
 */

export const getMyConversation = () =>
  apiFetch('/api/chat/my-conversation');

export const getMyConversationMessages = ({ limit, before, after } = {}) => {
  const params = new URLSearchParams();
  if (limit != null) params.set('limit', limit);
  if (before != null) params.set('before', before);
  if (after != null) params.set('after', after);
  const qs = params.toString();
  return apiFetch(`/api/chat/my-conversation/messages${qs ? `?${qs}` : ''}`);
};

export const sendMyConversationMessage = (content) =>
  apiFetch('/api/chat/my-conversation/messages', {
    method: 'POST',
    body: JSON.stringify({ content }),
  });

export const markMyConversationRead = () =>
  apiFetch('/api/chat/my-conversation/read', { method: 'POST' });

/**
 * Student side list/archive (Stage 31t): беседы студента по engagements
 * (active + non-empty inactive), чтение/отправка/read по conversation uuid.
 * Старые /my-conversation* остаются для legacy/back-compat.
 */

export const getStudentConversations = ({ page, size } = {}) => {
  const params = new URLSearchParams();
  if (page != null) params.set('page', page);
  if (size != null) params.set('size', size);
  const qs = params.toString();
  return apiFetch(`/api/chat/student/conversations${qs ? `?${qs}` : ''}`);
};

export const getStudentConversationMessages = (
  conversationUuid,
  { limit, before, after } = {},
) => {
  const params = new URLSearchParams();
  if (limit != null) params.set('limit', limit);
  if (before != null) params.set('before', before);
  if (after != null) params.set('after', after);
  const qs = params.toString();
  return apiFetch(`/api/chat/student/conversations/${conversationUuid}/messages${qs ? `?${qs}` : ''}`);
};

export const sendStudentConversationMessage = (conversationUuid, content) =>
  apiFetch(`/api/chat/student/conversations/${conversationUuid}/messages`, {
    method: 'POST',
    body: JSON.stringify({ content }),
  });

export const markStudentConversationRead = (conversationUuid) =>
  apiFetch(`/api/chat/student/conversations/${conversationUuid}/read`, { method: 'POST' });

export const editStudentMessage = (conversationUuid, messageUuid, content) =>
  apiFetch(`/api/chat/student/conversations/${conversationUuid}/messages/${messageUuid}`, {
    method: 'PATCH',
    body: JSON.stringify({ content }),
  });

export const deleteStudentMessage = (conversationUuid, messageUuid) =>
  apiFetch(`/api/chat/student/conversations/${conversationUuid}/messages/${messageUuid}`, {
    method: 'DELETE',
  });

/**
 * Psychologist side (Stage 28e): беседы со своими студентами по engagements.
 */

export const getPsychologistConversations = ({ page, size } = {}) => {
  const params = new URLSearchParams();
  if (page != null) params.set('page', page);
  if (size != null) params.set('size', size);
  const qs = params.toString();
  return apiFetch(`/api/chat/conversations${qs ? `?${qs}` : ''}`);
};

export const getPsychologistConversation = (conversationUuid) =>
  apiFetch(`/api/chat/conversations/${conversationUuid}`);

export const getPsychologistConversationMessages = (
  conversationUuid,
  { limit, before, after } = {},
) => {
  const params = new URLSearchParams();
  if (limit != null) params.set('limit', limit);
  if (before != null) params.set('before', before);
  if (after != null) params.set('after', after);
  const qs = params.toString();
  return apiFetch(`/api/chat/conversations/${conversationUuid}/messages${qs ? `?${qs}` : ''}`);
};

export const sendPsychologistConversationMessage = (conversationUuid, content) =>
  apiFetch(`/api/chat/conversations/${conversationUuid}/messages`, {
    method: 'POST',
    body: JSON.stringify({ content }),
  });

export const markPsychologistConversationRead = (conversationUuid) =>
  apiFetch(`/api/chat/conversations/${conversationUuid}/read`, { method: 'POST' });

export const editPsychologistMessage = (conversationUuid, messageUuid, content) =>
  apiFetch(`/api/chat/conversations/${conversationUuid}/messages/${messageUuid}`, {
    method: 'PATCH',
    body: JSON.stringify({ content }),
  });

export const deletePsychologistMessage = (conversationUuid, messageUuid) =>
  apiFetch(`/api/chat/conversations/${conversationUuid}/messages/${messageUuid}`, {
    method: 'DELETE',
  });

/**
 * System conversation (Stage 29b/29c): read-only feed системных уведомлений
 * текущего пользователя. Отправка сообщений не поддерживается (write-эндпоинта нет).
 */

export const getSystemConversation = () =>
  apiFetch('/api/chat/system-conversation');

export const getSystemMessages = ({ limit, before, after } = {}) => {
  const params = new URLSearchParams();
  if (limit != null) params.set('limit', limit);
  if (before != null) params.set('before', before);
  if (after != null) params.set('after', after);
  const qs = params.toString();
  return apiFetch(`/api/chat/system-conversation/messages${qs ? `?${qs}` : ''}`);
};

export const markSystemConversationRead = () =>
  apiFetch('/api/chat/system-conversation/read', { method: 'POST' });

/**
 * Скачивание вложений чата (Stage 32d).
 * Возвращает { blob, filename } — filename из Content-Disposition или null.
 */
export const downloadStudentAttachment = (conversationUuid, attachmentUuid) =>
  apiFetchBlob(
    `/api/chat/student/conversations/${conversationUuid}/attachments/${attachmentUuid}/download`,
  );

export const downloadPsychologistAttachment = (conversationUuid, attachmentUuid) =>
  apiFetchBlob(
    `/api/chat/conversations/${conversationUuid}/attachments/${attachmentUuid}/download`,
  );
