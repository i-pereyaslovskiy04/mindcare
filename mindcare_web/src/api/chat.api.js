import { apiFetch } from './client';

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
