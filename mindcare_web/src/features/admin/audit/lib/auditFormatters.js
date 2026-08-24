/**
 * Чистое форматирование значений admin audit viewer.
 *
 * Все временные метки журналов показываются в Europe/Moscow независимо от
 * часового пояса браузера: журнал — единый организационный документ, и запись
 * не должна выглядеть по-разному у администраторов в разных TZ. Смещение
 * никогда не считается вручную (+3h) — только через Intl с timeZone.
 */

const MOSCOW_TZ = 'Europe/Moscow';

const DATE_TIME_FMT = new Intl.DateTimeFormat('ru-RU', {
  timeZone: MOSCOW_TZ,
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
});

const DATE_ONLY_FMT = new Intl.DateTimeFormat('ru-RU', {
  timeZone: MOSCOW_TZ,
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
});

const DATE_ONLY_PARTS_FMT = new Intl.DateTimeFormat('ru-RU', {
  timeZone: MOSCOW_TZ,
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
});

export const EMPTY_VALUE = '—';

function toDate(value) {
  if (value == null || value === '') return null;
  const date = value instanceof Date ? value : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

/** Дата и время события по МСК. Невалидное значение → «—», без исключения. */
export function formatMoscowDateTime(value) {
  const date = toDate(value);
  return date ? DATE_TIME_FMT.format(date) : EMPTY_VALUE;
}

/** То же, но с явной подписью пояса — для details, где важна однозначность. */
export function formatMoscowDateTimeLong(value) {
  const date = toDate(value);
  return date ? `${DATE_TIME_FMT.format(date)} МСК` : EMPTY_VALUE;
}

/** Дата без времени (например, границы выбранного периода). */
export function formatMoscowDate(value) {
  const date = toDate(value);
  return date ? DATE_ONLY_FMT.format(date) : EMPTY_VALUE;
}

/** `YYYY-MM-DD` из строки `YYYY-MM-DD` в человекочитаемый вид. */
export function formatDateOnly(dateOnly) {
  if (typeof dateOnly !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(dateOnly)) {
    return EMPTY_VALUE;
  }
  const [year, month, day] = dateOnly.split('-');
  return `${day}.${month}.${year}`;
}

/**
 * Сегодняшняя дата по Москве в формате `YYYY-MM-DD`.
 *
 * Собирается из formatToParts, а не из локали с «удобным» форматом: набор
 * локалей у движка не гарантирован, а порядок частей — гарантирован.
 */
export function moscowToday() {
  const parts = DATE_ONLY_PARTS_FMT.formatToParts(new Date());
  const get = (type) => parts.find((p) => p.type === type)?.value ?? '';
  return `${get('year')}-${get('month')}-${get('day')}`;
}

/** Сдвиг календарной даты `YYYY-MM-DD` на целое число дней (UTC-арифметика). */
export function shiftDateOnly(dateOnly, days) {
  if (typeof dateOnly !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(dateOnly)) {
    return dateOnly;
  }
  const [year, month, day] = dateOnly.split('-').map(Number);
  const ms = Date.UTC(year, month - 1, day) + days * 86400000;
  const shifted = new Date(ms);
  const pad = (n) => String(n).padStart(2, '0');
  return `${shifted.getUTCFullYear()}-${pad(shifted.getUTCMonth() + 1)}-${pad(shifted.getUTCDate())}`;
}

/** Число календарных дней в закрытом интервале [from, to]. */
export function dateSpanDays(from, to) {
  const parse = (value) => {
    if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
    const [y, m, d] = value.split('-').map(Number);
    return Date.UTC(y, m - 1, d);
  };
  const a = parse(from);
  const b = parse(to);
  if (a === null || b === null) return null;
  return Math.round((b - a) / 86400000) + 1;
}

/**
 * Маскирование email по правилу backend `app.core.normalization.mask_email`:
 * первый символ локальной части + домен. Невалидное значение → «***».
 *
 * Нужно на клиенте потому, что admin users API (источник данных для выбора
 * участника) отдаёт полный адрес, а страница журнала не показывает полных
 * адресов нигде.
 */
export function maskEmail(email) {
  if (typeof email !== 'string' || !email.includes('@')) return '***';
  const at = email.indexOf('@');
  const local = email.slice(0, at);
  const domain = email.slice(at + 1);
  if (!local || !domain) return '***';
  return `${local[0]}***@${domain}`;
}

const SIZE_UNITS = ['Б', 'КБ', 'МБ', 'ГБ'];

/** Размер файла из details вложения чата. */
export function formatFileSize(bytes) {
  if (typeof bytes !== 'number' || !Number.isFinite(bytes) || bytes < 0) {
    return EMPTY_VALUE;
  }
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < SIZE_UNITS.length - 1) {
    value /= 1024;
    unit += 1;
  }
  const rounded = unit === 0 ? value : Math.round(value * 10) / 10;
  return `${String(rounded).replace('.', ',')} ${SIZE_UNITS[unit]}`;
}
