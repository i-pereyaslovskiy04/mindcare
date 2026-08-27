import { apiFetch } from './client';

// ── Публичный (без auth) ─────────────────────────────────────────────────────

export const getBannerSlides = (placement = 'home') =>
  apiFetch(`/api/banner-slides?placement=${encodeURIComponent(placement)}`);

// ── Supervisor (admin+supervisor кабинеты) ───────────────────────────────────

export const getSupervisorBannerSlides = (placement) => {
  const params = new URLSearchParams({ include_inactive: 'true' });
  if (placement) params.set('placement', placement);
  return apiFetch(`/api/supervisor/banner-slides?${params}`);
};

export const createBannerSlide = (data) =>
  apiFetch('/api/supervisor/banner-slides', {
    method: 'POST',
    body: JSON.stringify(data),
  });

export const updateBannerSlide = (id, data) =>
  apiFetch(`/api/supervisor/banner-slides/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });

export const deleteBannerSlide = (id) =>
  apiFetch(`/api/supervisor/banner-slides/${id}`, {
    method: 'DELETE',
  });
