// Подписи и форматирование заданий (ADR-033). Время — по Москве (Intl,
// timeZone 'Europe/Moscow'); срок — календарная дата без времени.

export const STATUS_LABELS = {
  active:    'В работе',
  completed: 'Выполнено',
  cancelled: 'Отменено',
};

// Badge tone для shared Badge.
export const STATUS_TONES = {
  active:    'neutral',
  completed: 'success',
  cancelled: 'warning',
};

const DUE_FORMAT = new Intl.DateTimeFormat('ru-RU', {
  day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC',
});

const MOMENT_FORMAT = new Intl.DateTimeFormat('ru-RU', {
  day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit',
  timeZone: 'Europe/Moscow',
});

/** 'YYYY-MM-DD' → «26 октября 2026 г.» (дата без сдвига часового пояса). */
export function formatDueDate(value) {
  if (!value || typeof value !== 'string') return '';
  const [y, m, d] = value.split('-').map(Number);
  if (!y || !m || !d) return '';
  return DUE_FORMAT.format(new Date(Date.UTC(y, m - 1, d)));
}

/** ISO-момент → «26 октября, 14:05» по Москве. */
export function formatMoment(iso) {
  if (!iso) return '';
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? '' : MOMENT_FORMAT.format(date);
}
