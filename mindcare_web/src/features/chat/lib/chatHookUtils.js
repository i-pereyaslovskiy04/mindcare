export const POLL_MESSAGES_MS = 8000;
export const POLL_LIST_MS = 30000;
export const LIST_PAGE_SIZE = 100;
export const HISTORY_LIMIT = 100;
export const SNAPSHOT_LIMIT = 50;

export const STATUS_FALLBACK = {
  403: 'Нет доступа к этому чату',
  404: 'Диалог не найден или недоступен',
  409: 'Диалог закрыт',
  429: 'Слишком много сообщений. Попробуйте позже.',
};

export function errText(e, fallback) {
  const m = e?.message;
  if (typeof m === 'string' && m && !m.includes('[object') && !/^HTTP \d+$/.test(m)) {
    return m;
  }
  return STATUS_FALLBACK[e?.status] || fallback;
}
