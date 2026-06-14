/**
 * Date-only helpers for the admin DateInput.
 *
 * Контракт backend для published_at не меняется: это ISO datetime string или null.
 * UI работает только с датой (YYYY-MM-DD); время фиксируется при отправке.
 */

const ISO_DATE_RE = /^(\d{4})-(\d{2})-(\d{2})/;
const DATE_ONLY_RE = /^(\d{4})-(\d{2})-(\d{2})$/;

/**
 * ISO / любая строка / null → 'YYYY-MM-DD' или ''.
 * Берём первые 10 символов даты — без time/timezone, без Date-парсинга,
 * чтобы не было сдвига дня в локальной таймзоне.
 */
export function isoToDateOnly(iso) {
  if (!iso) return '';
  const m = ISO_DATE_RE.exec(String(iso));
  return m ? `${m[1]}-${m[2]}-${m[3]}` : '';
}

/**
 * 'YYYY-MM-DD' → ISO datetime string или null.
 * Время фиксируем на 12:00:00 UTC: при отображении в любой таймзоне
 * (от UTC-11 до UTC+13) календарный день остаётся прежним.
 */
export function dateOnlyToPublishedAtIso(date) {
  if (!date) return null;
  const m = DATE_ONLY_RE.exec(String(date));
  if (!m) return null;
  return `${m[1]}-${m[2]}-${m[3]}T12:00:00.000Z`;
}

/** 'YYYY-MM-DD' → 'дд.мм.гггг' (для отображения в поле). Иначе ''. */
export function dateOnlyToDisplay(date) {
  const m = DATE_ONLY_RE.exec(String(date ?? ''));
  return m ? `${m[3]}.${m[2]}.${m[1]}` : '';
}

const pad = (n) => String(n).padStart(2, '0');

/** (year, month0, day) → 'YYYY-MM-DD'. */
export function partsToDateOnly(year, month0, day) {
  return `${year}-${pad(month0 + 1)}-${pad(day)}`;
}

/** 'YYYY-MM-DD' → { year, month0, day } или null. */
export function dateOnlyToParts(date) {
  const m = DATE_ONLY_RE.exec(String(date ?? ''));
  if (!m) return null;
  return { year: Number(m[1]), month0: Number(m[2]) - 1, day: Number(m[3]) };
}

/** Кол-во дней в месяце (month0 = 0..11). */
export function daysInMonth(year, month0) {
  return new Date(Date.UTC(year, month0 + 1, 0)).getUTCDate();
}

/** Индекс первого дня месяца, неделя с понедельника (0 = Пн .. 6 = Вс). */
export function firstWeekdayMonday(year, month0) {
  const sundayFirst = new Date(Date.UTC(year, month0, 1)).getUTCDay();
  return (sundayFirst + 6) % 7;
}

/** Сегодня как 'YYYY-MM-DD' в локальной дате пользователя. */
export function todayDateOnly() {
  const now = new Date();
  return partsToDateOnly(now.getFullYear(), now.getMonth(), now.getDate());
}
