/**
 * Чистые хелперы для календарного обзора психолога (feature-слой).
 *
 * Даты/время — через Intl с timeZone 'Europe/Moscow' (без ручного +3).
 * ПДн (ФИО) только для отображения; здесь ничего не логируется.
 */

export const MONTH_NAMES = [
  'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
  'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь',
];

export const DOW = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];

const _dayKeyFmt = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Europe/Moscow', year: 'numeric', month: '2-digit', day: '2-digit',
});
const _timeFmt = new Intl.DateTimeFormat('ru-RU', {
  timeZone: 'Europe/Moscow', hour: '2-digit', minute: '2-digit',
});

/** ISO → 'YYYY-MM-DD' в московской зоне. */
export function mskDateKey(iso) {
  if (!iso) return '';
  return _dayKeyFmt.format(new Date(iso));
}

/** ISO → 'HH:MM' в московской зоне. */
export function mskTime(iso) {
  if (!iso) return '';
  return _timeFmt.format(new Date(iso));
}

/** 'HH:MM' или 'HH:MM–HH:MM' (если есть ends). */
export function mskTimeRange(starts, ends) {
  const s = mskTime(starts);
  if (!ends) return s;
  return `${s}–${mskTime(ends)}`;
}

/** Субъект записи: registered student / unregistered card. ПДн не логируем. */
export function subjectLabel(appt) {
  if (appt.student) {
    return { name: appt.student.full_name || '—', isCard: false };
  }
  if (appt.unregistered_student_card) {
    return {
      name: appt.unregistered_student_card.full_name || '—',
      isCard: true,
    };
  }
  return { name: 'Клиент не указан', isCard: false };
}

/** Индивидуальная запись → унифицированное событие календаря. */
export function appointmentToEvent(appt) {
  return {
    id: appt.uuid,
    kind: 'appointment',
    dateKey: mskDateKey(appt.starts_at),
    startsAtIso: appt.starts_at,
    time: mskTimeRange(appt.starts_at, appt.ends_at),
    title: appt.meeting_type_name || 'Индивидуальная встреча',
    status: appt.status,
    modality: appt.modality,
    subject: subjectLabel(appt),
  };
}

/** Групповое занятие → унифицированное событие календаря. */
export function groupSessionToEvent(gs) {
  return {
    id: gs.uuid,
    kind: 'group',
    dateKey: mskDateKey(gs.starts_at),
    startsAtIso: gs.starts_at,
    time: mskTimeRange(gs.starts_at, gs.ends_at),
    title: gs.title || gs.meeting_type_name || 'Групповое занятие',
    status: gs.status,
    modality: gs.format,
    registered: gs.registered_count ?? 0,
    capacity: gs.capacity ?? 0,
  };
}

/** Список событий → { [dateKey]: Event[] }, внутри дня сортировка по началу ASC. */
export function groupEventsByDay(events) {
  const map = {};
  for (const ev of events) {
    if (!ev.dateKey) continue;
    (map[ev.dateKey] ||= []).push(ev);
  }
  for (const key of Object.keys(map)) {
    map[key].sort((a, b) => {
      const ta = new Date(a.startsAtIso).getTime();
      const tb = new Date(b.startsAtIso).getTime();
      return ta - tb;
    });
  }
  return map;
}

/**
 * Реальная ближайшая встреча для блока на главной: индивидуальные записи только
 * в статусах pending_confirmation/confirmed; групповые — только scheduled.
 * Отменённые/отклонённые/завершённые не считаются «ближайшими».
 */
export function isHomeUpcomingEvent(ev) {
  if (ev.kind === 'group') return ev.status === 'scheduled';
  return ev.status === 'pending_confirmation' || ev.status === 'confirmed';
}

function _pad(n) {
  return String(n).padStart(2, '0');
}

/** 'YYYY-MM-DD' из числовых year, month(0-11), day. */
export function dateKeyFromParts(year, month, day) {
  return `${year}-${_pad(month + 1)}-${_pad(day)}`;
}

/**
 * Сетка месяца (Monday-first), 35 или 42 ячейки.
 * month — 0-indexed. Каждая ячейка: { day, month, year, current }.
 */
export function buildMonthGrid(year, month) {
  const firstDow = new Date(year, month, 1).getDay();   // 0=Sun
  const startOffset = (firstDow + 6) % 7;                // Mon-first
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const daysInPrev = new Date(year, month, 0).getDate();

  const prevYear = month === 0 ? year - 1 : year;
  const prevMonth = month === 0 ? 11 : month - 1;
  const nextYear = month === 11 ? year + 1 : year;
  const nextMonth = month === 11 ? 0 : month + 1;

  const cells = [];
  for (let i = startOffset - 1; i >= 0; i--) {
    cells.push({ day: daysInPrev - i, month: prevMonth, year: prevYear, current: false });
  }
  for (let d = 1; d <= daysInMonth; d++) {
    cells.push({ day: d, month, year, current: true });
  }
  const total = cells.length <= 35 ? 35 : 42;
  let trailing = 1;
  while (cells.length < total) {
    cells.push({ day: trailing++, month: nextMonth, year: nextYear, current: false });
  }
  return cells;
}

/** Границы месяца для запроса: { dateFrom:'YYYY-MM-01', dateTo:'YYYY-MM-<last>' }. */
export function monthBounds(year, month) {
  const last = new Date(year, month + 1, 0).getDate();
  return {
    dateFrom: dateKeyFromParts(year, month, 1),
    dateTo: dateKeyFromParts(year, month, last),
  };
}

/** Сегодняшний 'YYYY-MM-DD' по Europe/Moscow. */
export function mskTodayKey() {
  return mskDateKey(new Date());
}

/** Прибавить n дней к ключу 'YYYY-MM-DD' через UTC (без локального/DST сдвига). */
export function addDaysToKey(key, n) {
  const [y, m, d] = key.split('-').map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d));
  dt.setUTCDate(dt.getUTCDate() + n);
  return `${dt.getUTCFullYear()}-${_pad(dt.getUTCMonth() + 1)}-${_pad(dt.getUTCDate())}`;
}
