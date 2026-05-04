import { apiFetch } from './client';

export const getPsychologists = () =>
  apiFetch('/api/psychologists');

export const getAvailableSlots = (psychologistId, date) =>
  apiFetch(`/api/psychologists/${psychologistId}/available-slots?date=${date}`);

export const bookAppointment = (data) =>
  apiFetch('/api/appointments', {
    method: 'POST',
    body: JSON.stringify(data),
  });
