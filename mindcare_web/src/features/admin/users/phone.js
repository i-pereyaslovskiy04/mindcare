/**
 * Маска ввода телефона (RU), без сторонних зависимостей.
 *
 * Пользователь вводит только цифры; отображение форматируется как
 * +7 (XXX) XXX-XX-XX. Ведущая 8 или 7 нормализуется к коду страны +7;
 * код города (949 и т.п.) не навязывается. Пустое значение остаётся пустым.
 */
export function formatPhoneInput(value) {
  if (value == null) return '';

  let digits = String(value).replace(/\D/g, '');
  if (digits === '') return '';

  // Нормализация кода страны: ведущие 8 или 7 → +7; иначе считаем,
  // что введён 10-значный национальный номер, и подставляем 7.
  if (digits[0] === '8') digits = `7${digits.slice(1)}`;
  else if (digits[0] !== '7') digits = `7${digits}`;

  // 7 (код страны) + до 10 цифр национального номера.
  digits = digits.slice(0, 11);
  const rest = digits.slice(1);

  let out = '+7';
  if (rest.length > 0) out += ` (${rest.slice(0, 3)}`;
  if (rest.length >= 3) out += ')';
  if (rest.length > 3) out += ` ${rest.slice(3, 6)}`;
  if (rest.length > 6) out += `-${rest.slice(6, 8)}`;
  if (rest.length > 8) out += `-${rest.slice(8, 10)}`;
  return out;
}

export const PHONE_PLACEHOLDER = '+7 (949) 000-00-00';
