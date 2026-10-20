import { buildGrid, dateKey, dayLabel } from './calendarUtils';

const keys = (cells) => cells.map((c) => dateKey(c.year, c.month, c.day));

describe('buildGrid', () => {
  test('октябрь 2026 (начинается в четверг) — 35 ячеек, неделя с понедельника', () => {
    const cells = buildGrid(2026, 9);
    expect(cells).toHaveLength(35);
    // Пн 28 сен … Ср 30 сен — хвост сентября, затем 1 октября (чт).
    expect(keys(cells).slice(0, 4)).toEqual([
      '2026-09-28', '2026-09-29', '2026-09-30', '2026-10-01',
    ]);
    expect(cells.slice(0, 3).every((c) => !c.current)).toBe(true);
    expect(cells.filter((c) => c.current)).toHaveLength(31);
    // Первая ячейка каждой строки — понедельник.
    for (let row = 0; row < 5; row += 1) {
      const c = cells[row * 7];
      expect(new Date(c.year, c.month, c.day).getDay()).toBe(1);
    }
  });

  test('март 2026 (начинается в воскресенье) — 42 ячейки', () => {
    const cells = buildGrid(2026, 2);
    expect(cells).toHaveLength(42);
    expect(keys(cells)[6]).toBe('2026-03-01');
    expect(cells[6].current).toBe(true);
  });

  test('февраль 2027 (с понедельника, 28 дней) — 35 ячеек, без хвоста января', () => {
    const cells = buildGrid(2027, 1);
    expect(cells).toHaveLength(35);
    expect(keys(cells)[0]).toBe('2027-02-01');
    expect(keys(cells).slice(28)).toEqual([
      '2027-03-01', '2027-03-02', '2027-03-03', '2027-03-04',
      '2027-03-05', '2027-03-06', '2027-03-07',
    ]);
  });

  test('переход через год: декабрь → январь и январь ← декабрь', () => {
    const dec = keys(buildGrid(2026, 11));
    expect(dec[0]).toBe('2026-11-30');
    expect(dec.slice(-3)).toEqual(['2027-01-01', '2027-01-02', '2027-01-03']);

    const jan = keys(buildGrid(2027, 0));
    expect(jan.slice(0, 5)).toEqual([
      '2026-12-28', '2026-12-29', '2026-12-30', '2026-12-31', '2027-01-01',
    ]);
  });
});

test('dayLabel: число, месяц в родительном падеже, день недели, состояние', () => {
  expect(dayLabel(2026, 9, 16)).toBe('16 октября, пятница');
  expect(dayLabel(2026, 9, 14, { hasEvents: true })).toBe('14 октября, среда, есть события');
  expect(dayLabel(2027, 0, 1, { hasEvents: true, selected: true }))
    .toBe('1 января, пятница, есть события, выбрано');
  expect(dayLabel(2026, 9, 20, { selected: true })).toBe('20 октября, вторник, выбрано');
});
