import { apiFetch } from './client';

export const getDiaryEmotions = () =>
  apiFetch('/api/diary/emotions');

export const getTodayDiaryEntry = () =>
  apiFetch('/api/diary/today');

export const saveTodayDiaryEntry = ({ mood_score, entry_text, emotions }) =>
  apiFetch('/api/diary/today', {
    method: 'PUT',
    body: JSON.stringify({ mood_score, entry_text, emotions }),
  });

export const getDiaryEntries = ({ limit = 10, offset = 0 } = {}) => {
  const params = new URLSearchParams({ limit, offset });
  return apiFetch(`/api/diary/entries?${params}`);
};

export const getDiarySummary = (period) =>
  apiFetch(`/api/diary/summary?period=${encodeURIComponent(period)}`);
