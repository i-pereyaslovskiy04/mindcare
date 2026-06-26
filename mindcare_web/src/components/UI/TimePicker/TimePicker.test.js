import { parseTime } from './TimePicker';

describe('parseTime', () => {
  test('HH:MM stays as-is', () => {
    expect(parseTime('09:00')).toBe('09:00');
    expect(parseTime('23:59')).toBe('23:59');
    expect(parseTime('00:00')).toBe('00:00');
  });

  test('single-digit shorthand normalised', () => {
    expect(parseTime('9:5')).toBe('09:05');
    expect(parseTime('0:0')).toBe('00:00');
  });

  test('arbitrary valid minutes accepted (step=1 support)', () => {
    expect(parseTime('10:01')).toBe('10:01');
    expect(parseTime('10:07')).toBe('10:07');
    expect(parseTime('10:59')).toBe('10:59');
  });

  test('out-of-range → null', () => {
    expect(parseTime('24:00')).toBeNull();
    expect(parseTime('12:60')).toBeNull();
    expect(parseTime('-1:00')).toBeNull();
  });

  test('non-string / empty → null', () => {
    expect(parseTime(null)).toBeNull();
    expect(parseTime(undefined)).toBeNull();
    expect(parseTime(900)).toBeNull();
    expect(parseTime('')).toBeNull();
    expect(parseTime('abc')).toBeNull();
    expect(parseTime('12')).toBeNull();
    expect(parseTime('12:00:00')).toBeNull();
  });
});
