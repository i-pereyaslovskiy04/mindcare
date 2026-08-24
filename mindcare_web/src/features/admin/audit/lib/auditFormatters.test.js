import {
  EMPTY_VALUE,
  dateSpanDays,
  formatDateOnly,
  formatFileSize,
  formatMoscowDate,
  formatMoscowDateTime,
  formatMoscowDateTimeLong,
  maskEmail,
  moscowToday,
  shiftDateOnly,
} from './auditFormatters';

describe('время журналов — всегда Europe/Moscow', () => {
  test('UTC-метка переводится в московское время, а не в TZ процесса', () => {
    // 2026-08-22T11:03:07Z = 14:03:07 МСК (UTC+3, без переходов)
    expect(formatMoscowDateTime('2026-08-22T11:03:07Z')).toBe('22.08.2026, 14:03:07');
  });

  test('секунды показываются', () => {
    expect(formatMoscowDateTime('2026-01-05T20:59:09Z')).toMatch(/23:59:09$/);
  });

  test('переход через полночь по Москве меняет дату', () => {
    // 22:30 UTC = 01:30 следующего дня по Москве
    expect(formatMoscowDateTime('2026-08-22T22:30:00Z')).toBe('23.08.2026, 01:30:00');
  });

  test('зимняя дата тоже UTC+3 — перехода на летнее время в РФ нет', () => {
    expect(formatMoscowDateTime('2026-01-15T09:00:00Z')).toBe('15.01.2026, 12:00:00');
  });

  test('подробный формат добавляет явную подпись пояса', () => {
    expect(formatMoscowDateTimeLong('2026-08-22T11:03:07Z'))
      .toBe('22.08.2026, 14:03:07 МСК');
  });

  test('только дата', () => {
    expect(formatMoscowDate('2026-08-22T11:03:07Z')).toBe('22.08.2026');
  });
});

describe('невалидные метки времени безопасны', () => {
  test.each([null, undefined, '', 'не дата', 'NaN', {}])('%p → «—»', (value) => {
    expect(formatMoscowDateTime(value)).toBe(EMPTY_VALUE);
    expect(formatMoscowDateTimeLong(value)).toBe(EMPTY_VALUE);
    expect(formatMoscowDate(value)).toBe(EMPTY_VALUE);
  });

  test('форматирование не бросает исключение', () => {
    expect(() => formatMoscowDateTime('2026-13-45T99:99:99Z')).not.toThrow();
    expect(formatMoscowDateTime('2026-13-45T99:99:99Z')).toBe(EMPTY_VALUE);
  });
});

describe('календарные даты YYYY-MM-DD', () => {
  test('человекочитаемый вид', () => {
    expect(formatDateOnly('2026-08-22')).toBe('22.08.2026');
  });

  test('мусор → «—»', () => {
    expect(formatDateOnly('22.08.2026')).toBe(EMPTY_VALUE);
    expect(formatDateOnly('')).toBe(EMPTY_VALUE);
    expect(formatDateOnly(null)).toBe(EMPTY_VALUE);
  });

  test('сдвиг на дни переживает границу месяца и года', () => {
    expect(shiftDateOnly('2026-08-22', -6)).toBe('2026-08-16');
    expect(shiftDateOnly('2026-03-01', -1)).toBe('2026-02-28');
    expect(shiftDateOnly('2026-01-01', -1)).toBe('2025-12-31');
    expect(shiftDateOnly('2024-03-01', -1)).toBe('2024-02-29'); // високосный
  });

  test('сегодня по Москве — строка YYYY-MM-DD', () => {
    expect(moscowToday()).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  test('длина закрытого интервала считается включительно', () => {
    expect(dateSpanDays('2026-08-16', '2026-08-22')).toBe(7);
    expect(dateSpanDays('2026-08-22', '2026-08-22')).toBe(1);
    expect(dateSpanDays('2026-08-23', '2026-08-22')).toBe(0);
    expect(dateSpanDays('2026-05-25', '2026-08-22')).toBe(90);
    expect(dateSpanDays('плохо', '2026-08-22')).toBeNull();
  });
});

describe('маскирование email по правилу backend', () => {
  test('первый символ локальной части и полный домен', () => {
    expect(maskEmail('ivan@example.test')).toBe('i***@example.test');
  });

  test('невалидное значение → ***', () => {
    expect(maskEmail('')).toBe('***');
    expect(maskEmail('без-собаки')).toBe('***');
    expect(maskEmail('@example.test')).toBe('***');
    expect(maskEmail('ivan@')).toBe('***');
    expect(maskEmail(null)).toBe('***');
    expect(maskEmail(undefined)).toBe('***');
  });

  test('полный адрес никогда не возвращается целиком', () => {
    const email = 'confidential.person@donnu.ru';
    expect(maskEmail(email)).not.toBe(email);
    expect(maskEmail(email)).not.toContain('confidential');
  });
});

describe('размер файла', () => {
  test('байты, килобайты, мегабайты', () => {
    expect(formatFileSize(512)).toBe('512 Б');
    expect(formatFileSize(2048)).toBe('2 КБ');
    expect(formatFileSize(1536)).toBe('1,5 КБ');
    expect(formatFileSize(5 * 1024 * 1024)).toBe('5 МБ');
  });

  test('мусор → «—»', () => {
    expect(formatFileSize(null)).toBe(EMPTY_VALUE);
    expect(formatFileSize(-1)).toBe(EMPTY_VALUE);
    expect(formatFileSize('много')).toBe(EMPTY_VALUE);
    expect(formatFileSize(NaN)).toBe(EMPTY_VALUE);
  });
});
