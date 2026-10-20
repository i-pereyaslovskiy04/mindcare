import { formatPhoneInput } from './phone';

describe('formatPhoneInput', () => {
  test('10-значный национальный номер получает код страны', () => {
    expect(formatPhoneInput('9491234567')).toBe('+7 (949) 123-45-67');
  });

  test('ведущая 7 нормализуется к +7', () => {
    expect(formatPhoneInput('79491234567')).toBe('+7 (949) 123-45-67');
  });

  test('ведущая 8 нормализуется к +7', () => {
    expect(formatPhoneInput('89491234567')).toBe('+7 (949) 123-45-67');
  });

  test('пустое значение остаётся пустым', () => {
    expect(formatPhoneInput('')).toBe('');
    expect(formatPhoneInput(null)).toBe('');
    expect(formatPhoneInput(undefined)).toBe('');
  });

  test('лишние символы игнорируются', () => {
    expect(formatPhoneInput('+7 (949) 123-45-67')).toBe('+7 (949) 123-45-67');
    expect(formatPhoneInput('8 949 abc 123 45 67')).toBe('+7 (949) 123-45-67');
  });

  test('частичный ввод форматируется прогрессивно', () => {
    expect(formatPhoneInput('949')).toBe('+7 (949)');
    expect(formatPhoneInput('94912')).toBe('+7 (949) 12');
  });
});
