import { apiFetch } from './client';

// Заметки психолога в карточке клиента (ADR-035, существующий session_notes).
// Тексты заметок не логировать.

export function getClientNotes(studentUuid, { before, size = 20 } = {}) {
  const params = new URLSearchParams({ size });
  if (before) params.set('before', before);
  return apiFetch(`/api/psychologist/clients/${studentUuid}/notes?${params}`);
}

export function createClientNote(studentUuid, { content, noteType, appointmentUuid }) {
  const body = { content, note_type: noteType };
  if (appointmentUuid) body.appointment_uuid = appointmentUuid;
  return apiFetch(`/api/psychologist/clients/${studentUuid}/notes`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

// version — обязательный CAS: 409, если заметку уже изменили.
export function updateClientNote(studentUuid, noteUuid, { content, noteType, version }) {
  return apiFetch(`/api/psychologist/clients/${studentUuid}/notes/${noteUuid}`, {
    method: 'PATCH',
    body: JSON.stringify({ content, note_type: noteType, version }),
  });
}
