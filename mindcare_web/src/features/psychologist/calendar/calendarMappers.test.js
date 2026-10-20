import {
  mskDateKey,
  subjectLabel,
  appointmentToEvent,
  groupSessionToEvent,
  groupEventsByDay,
  isHomeUpcomingEvent,
  buildMonthGrid,
  monthBounds,
  addDaysToKey,
} from './calendarMappers';

describe('mskDateKey (Europe/Moscow)', () => {
  test('UTC late evening maps to next Moscow day', () => {
    // 2026-06-23T22:30:00Z → Moscow 01:30 of 2026-06-24
    expect(mskDateKey('2026-06-23T22:30:00Z')).toBe('2026-06-24');
  });

  test('UTC midday stays same Moscow day', () => {
    expect(mskDateKey('2026-06-24T09:00:00Z')).toBe('2026-06-24');
  });

  test('empty input → empty string', () => {
    expect(mskDateKey('')).toBe('');
  });
});

describe('subjectLabel', () => {
  test('registered student', () => {
    const appt = { student: { full_name: 'Иванов Иван' } };
    expect(subjectLabel(appt)).toEqual({ name: 'Иванов Иван', isCard: false });
  });

  test('unregistered card', () => {
    const appt = { unregistered_student_card: { full_name: 'Петров Пётр' } };
    expect(subjectLabel(appt)).toEqual({ name: 'Петров Пётр', isCard: true });
  });

  test('no subject', () => {
    expect(subjectLabel({})).toEqual({ name: 'Клиент не указан', isCard: false });
  });
});

describe('groupEventsByDay', () => {
  test('counts per day and sorts within day by start ASC', () => {
    const a1 = appointmentToEvent({
      uuid: 'a1', starts_at: '2026-06-24T12:00:00Z', status: 'confirmed',
      meeting_type_name: 'Консультация', modality: 'online',
      student: { full_name: 'A' },
    });
    const a2 = appointmentToEvent({
      uuid: 'a2', starts_at: '2026-06-24T08:00:00Z', status: 'pending_confirmation',
      meeting_type_name: 'Консультация', modality: 'online',
      student: { full_name: 'B' },
    });
    const a3 = appointmentToEvent({
      uuid: 'a3', starts_at: '2026-06-25T09:00:00Z', status: 'confirmed',
      meeting_type_name: 'Консультация', modality: 'in_person',
      student: { full_name: 'C' },
    });
    const byDay = groupEventsByDay([a1, a2, a3]);
    expect(Object.keys(byDay).sort()).toEqual(['2026-06-24', '2026-06-25']);
    expect(byDay['2026-06-24']).toHaveLength(2);
    // a2 (08:00) earlier than a1 (12:00)
    expect(byDay['2026-06-24'].map(e => e.id)).toEqual(['a2', 'a1']);
    expect(byDay['2026-06-25']).toHaveLength(1);
  });
});

describe('isHomeUpcomingEvent', () => {
  const apptEv = (status) => appointmentToEvent({
    uuid: 'x', starts_at: '2026-06-24T09:00:00Z', status,
    meeting_type_name: 'Консультация', modality: 'online',
    student: { full_name: 'A' },
  });
  const groupEv = (status) => groupSessionToEvent({
    uuid: 'g', starts_at: '2026-06-24T09:00:00Z', status,
    title: 'Группа', format: 'in_person', capacity: 5, registered_count: 1,
  });

  test('keeps pending/confirmed appointments', () => {
    expect(isHomeUpcomingEvent(apptEv('pending_confirmation'))).toBe(true);
    expect(isHomeUpcomingEvent(apptEv('confirmed'))).toBe(true);
  });

  test('drops cancelled/declined/completed/no_show appointments', () => {
    expect(isHomeUpcomingEvent(apptEv('cancelled'))).toBe(false);
    expect(isHomeUpcomingEvent(apptEv('declined'))).toBe(false);
    expect(isHomeUpcomingEvent(apptEv('completed'))).toBe(false);
    expect(isHomeUpcomingEvent(apptEv('no_show'))).toBe(false);
  });

  test('keeps scheduled group events only', () => {
    expect(isHomeUpcomingEvent(groupEv('scheduled'))).toBe(true);
    expect(isHomeUpcomingEvent(groupEv('cancelled'))).toBe(false);
  });
});

describe('buildMonthGrid', () => {
  test('returns 35 or 42 cells, Monday-first, marks current month', () => {
    const cells = buildMonthGrid(2026, 5); // June 2026
    expect(cells.length === 35 || cells.length === 42).toBe(true);
    const current = cells.filter(c => c.current);
    expect(current.length).toBe(30); // June has 30 days
    expect(current[0].day).toBe(1);
    expect(current[current.length - 1].day).toBe(30);
  });
});

describe('monthBounds', () => {
  test('first and last day of month', () => {
    expect(monthBounds(2026, 1)).toEqual({
      dateFrom: '2026-02-01', dateTo: '2026-02-28',
    });
    expect(monthBounds(2026, 5)).toEqual({
      dateFrom: '2026-06-01', dateTo: '2026-06-30',
    });
  });
});

describe('addDaysToKey', () => {
  test('adds days across month boundary', () => {
    expect(addDaysToKey('2026-06-28', 7)).toBe('2026-07-05');
  });
  test('adds within month', () => {
    expect(addDaysToKey('2026-06-01', 7)).toBe('2026-06-08');
  });
});
