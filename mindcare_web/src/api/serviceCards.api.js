import { apiFetch } from './client';

// ── Публичный (без auth) ─────────────────────────────────────────────────────

export const getServiceCards = () => apiFetch('/api/service-cards');

// ── Supervisor (admin+supervisor кабинеты) ───────────────────────────────────

export const getSupervisorServiceCards = () =>
  apiFetch('/api/supervisor/service-cards?include_inactive=true');

export const createServiceCard = (data) =>
  apiFetch('/api/supervisor/service-cards', {
    method: 'POST',
    body: JSON.stringify(data),
  });

export const updateServiceCard = (id, data) =>
  apiFetch(`/api/supervisor/service-cards/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });

export const deleteServiceCard = (id) =>
  apiFetch(`/api/supervisor/service-cards/${id}`, {
    method: 'DELETE',
  });
