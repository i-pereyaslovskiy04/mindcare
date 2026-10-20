/**
 * Безопасная ссылка для контакта. Произвольный текст в href не превращается:
 * ссылка строится только из проверенных значений и только с протоколами
 * https/http (URL), mailto (email) и tel (телефон; форматированный номер
 * нормализуется до «+цифры»). Хэндлы, «другое» и всё
 * прочее ссылкой не становятся; javascript:/data: и т.п. не пройдут никогда.
 */
export function isSafeHttpUrl(value) {
  if (typeof value !== 'string' || /\s/.test(value)) return false;
  try {
    const url = new URL(value);
    return (
      (url.protocol === 'https:' || url.protocol === 'http:')
      && !url.username
      && !url.password
      && Boolean(url.hostname)
    );
  } catch {
    return false;
  }
}

const EMAIL_RE = /^[^\s@<>"']+@[^\s@<>"']+\.[^\s@<>"']+$/;
// Допустимый телефон: необязательный «+», цифры и обычные разделители (пробел,
// скобки, дефис, точка), всего 7–15 цифр. Любые другие символы — не телефон.
const PHONE_DISPLAY_RE = /^\+?[\d\s().-]+$/;

/**
 * Телефон для `tel:` — «+цифры» (или «цифры», если «+» не было). Отображаемое
 * значение (например, «+7 (949) 123-45-67») не меняется; null, если строка не
 * похожа на телефон.
 */
export function telDigits(value) {
  if (typeof value !== 'string') return null;
  const text = value.trim();
  if (!PHONE_DISPLAY_RE.test(text)) return null;
  const digits = text.replace(/\D/g, '');
  if (digits.length < 7 || digits.length > 15) return null;
  return `${text.startsWith('+') ? '+' : ''}${digits}`;
}

export function contactHref(item) {
  const value = item?.value;
  switch (item?.type) {
    case 'website':
    case 'messenger':
    case 'social':
      return isSafeHttpUrl(value) ? value : null;
    case 'email':
      return typeof value === 'string' && EMAIL_RE.test(value) ? `mailto:${value}` : null;
    case 'phone':
      return telDigits(value) ? `tel:${telDigits(value)}` : null;
    default:
      return null;
  }
}
