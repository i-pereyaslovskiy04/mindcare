/**
 * Утилиты времени для записи/расписания. Москва — UTC+3 (без DST с 2014).
 *
 * Контракт: формы хранят локальное «настенное» московское время как строку
 * 'YYYY-MM-DDTHH:MM'. Перед отправкой в API оно конвертируется в tz-aware ISO
 * (UTC) через localToMskIso — «голое» локальное время в API уходить не должно.
 */

const pad = (n) => String(n).padStart(2, '0');

/** 'YYYY-MM-DDTHH:MM' (московское настенное время) → ISO UTC string, либо null. */
export function localToMskIso(local) {
  if (!local) return null;
  // Гарантируем секунды для корректного парсинга Date.
  const withSeconds = local.length === 16 ? `${local}:00` : local;
  return new Date(`${withSeconds}+03:00`).toISOString();
}

/** ISO datetime → 'YYYY-MM-DDTHH:MM' в Москве (для заполнения формы), либо ''. */
export function mskIsoToLocal(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  const msk = new Date(d.getTime() + 3 * 60 * 60 * 1000);
  return msk.toISOString().slice(0, 16);
}

/**
 * Опции времени [{ value, label }] вида 'HH:MM' от 00:00 с шагом stepMinutes.
 * Используется deprecated TimeSelect (новые формы — shared TimePicker).
 */
export function buildTimeOptions(stepMinutes = 15) {
  const out = [];
  for (let m = 0; m < 24 * 60; m += stepMinutes) {
    const v = `${pad(Math.floor(m / 60))}:${pad(m % 60)}`;
    out.push({ value: v, label: v });
  }
  return out;
}
