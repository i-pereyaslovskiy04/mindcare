import { isoToDateOnly, dateOnlyToPublishedAtIso, dateOnlyToDisplay } from './dateHelpers';

describe('isoToDateOnly', () => {
  test('ISO datetime → YYYY-MM-DD', () => {
    expect(isoToDateOnly('2026-06-14T12:00:00.000Z')).toBe('2026-06-14');
  });

  test('date-only остаётся как есть', () => {
    expect(isoToDateOnly('2026-06-14')).toBe('2026-06-14');
  });

  test('null / undefined / "" → ""', () => {
    expect(isoToDateOnly(null)).toBe('');
    expect(isoToDateOnly(undefined)).toBe('');
    expect(isoToDateOnly('')).toBe('');
  });

  test('мусор → ""', () => {
    expect(isoToDateOnly('not-a-date')).toBe('');
  });
});

describe('dateOnlyToPublishedAtIso', () => {
  test('YYYY-MM-DD → ISO в полдень UTC', () => {
    expect(dateOnlyToPublishedAtIso('2026-06-14')).toBe('2026-06-14T12:00:00.000Z');
  });

  test('пусто / null → null', () => {
    expect(dateOnlyToPublishedAtIso('')).toBeNull();
    expect(dateOnlyToPublishedAtIso(null)).toBeNull();
  });

  test('round-trip с isoToDateOnly сохраняет дату', () => {
    const iso = dateOnlyToPublishedAtIso('2026-12-31');
    expect(isoToDateOnly(iso)).toBe('2026-12-31');
  });
});

describe('dateOnlyToDisplay', () => {
  test('YYYY-MM-DD → дд.мм.гггг', () => {
    expect(dateOnlyToDisplay('2026-06-14')).toBe('14.06.2026');
  });

  test('пусто → ""', () => {
    expect(dateOnlyToDisplay('')).toBe('');
    expect(dateOnlyToDisplay(null)).toBe('');
  });
});
