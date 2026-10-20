/**
 * Клиентская проверка контактов — зеркало серверных правил (ADR-032). Сервер
 * авторитетен: эта проверка лишь не отправляет заведомо неверное и подсвечивает
 * поле. Значения в сообщения не подставляются.
 */
import { DEFAULT_LIMITS, serviceKindOf } from './draft';
import { needsName } from './methods';

export const ERROR_MESSAGES = {
  required: 'Заполните поле',
  too_long: 'Слишком длинное значение',
  too_many: 'Достигнут предел числа контактов',
  invalid_id: 'Внутренняя ошибка контакта. Удалите строку и добавьте её заново',
  duplicate_id: 'Внутренняя ошибка контакта. Удалите строку и добавьте её заново',
  invalid_type: 'Выберите способ связи',
  invalid_service: 'Выберите способ связи',
  service_required: 'Выберите способ связи',
  service_not_allowed: 'Выберите способ связи',
  label_required: 'Укажите название способа связи',
  invalid_phone: 'Введите корректный номер: с кодом страны или 10 цифр',
  invalid_email: 'Введите корректный email',
  invalid_url: 'Введите корректную ссылку (http:// или https://)',
  unsafe_url: 'Допустимы только ссылки http:// и https:// без логина и пароля',
  invalid_value: 'Укажите имя пользователя (например, @name), номер телефона или ссылку',
  invalid_characters: 'Уберите недопустимые символы',
  duplicate: 'Такой контакт уже добавлен',
  unknown_field: 'Запрос не принят. Обновите страницу и повторите',
  invalid_json: 'Запрос не принят. Обновите страницу и повторите',
  invalid_uuid: 'Запрос не принят. Обновите страницу и повторите',
  out_of_range: 'Запрос не принят. Обновите страницу и повторите',
};

export function messageFor(code, limits = DEFAULT_LIMITS, field) {
  if (code === 'too_long') {
    const max = field === 'label' ? limits.label_max : limits.value_max;
    return `Слишком длинное значение (максимум ${max} символов)`;
  }
  return ERROR_MESSAGES[code] ?? 'Проверьте значение';
}

const PHONE_CHARS = /^\+?[\d\s().-]+$/;
const HANDLE = /^@?[\p{L}\p{N}_.-]{2,100}$/u;
const SCHEME = /^([a-zA-Z][a-zA-Z0-9+.-]*):\/\//;
const DANGEROUS = /^(javascript|data|vbscript|file|mailto|tel|sms|blob|about|ftp|ws|wss)\s*:/i;
const ANY_SCHEME = /^[a-zA-Z][a-zA-Z0-9+.-]*:(?!\d+(\/|$))/;
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
// eslint-disable-next-line no-control-regex
const CONTROL = /[\u0000-\u001f\u007f\u2028\u2029\u202a-\u202e\u2066-\u2069\u200e\u200f\u061c]/;

function phoneOk(text) {
  if (!PHONE_CHARS.test(text)) return false;
  const digits = text.replace(/\D/g, '');
  if (text.startsWith('+')) return digits.length >= 7 && digits.length <= 15;
  return digits.length >= 10 && digits.length <= 15;
}

function urlCode(text) {
  if (/\s/.test(text)) return 'invalid_url';
  const scheme = SCHEME.exec(text);
  let candidate;
  if (scheme) {
    if (!['http', 'https'].includes(scheme[1].toLowerCase())) return 'unsafe_url';
    candidate = text;
  } else if (DANGEROUS.test(text) || ANY_SCHEME.test(text)) {
    return 'unsafe_url';
  } else if (text.startsWith('//')) {
    return 'invalid_url';
  } else {
    candidate = `https://${text}`;
  }
  let url;
  try {
    url = new URL(candidate);
  } catch {
    return 'invalid_url';
  }
  if (url.username || url.password) return 'unsafe_url';
  const host = url.hostname;
  if (!host || !host.includes('.') || /^\d+$/.test(host.split('.').pop())) return 'invalid_url';
  return null;
}

/** Код ошибки значения для строки или null. */
function valueCode(type, service, raw) {
  const text = (raw || '').trim();
  if (!text) return 'required';
  if (CONTROL.test(text)) return 'invalid_characters';
  if (type === 'phone') return phoneOk(text) ? null : 'invalid_phone';
  if (type === 'email') return text.length <= 254 && EMAIL.test(text) ? null : 'invalid_email';
  if (type === 'website') return urlCode(text);
  if (type === 'messenger' || type === 'social') {
    if (service === 'other') return SCHEME.test(text) ? urlCode(text) : null;
    if (type === 'messenger' && PHONE_CHARS.test(text)) return phoneOk(text) ? null : 'invalid_phone';
    if (text.includes('/') || text.toLowerCase().startsWith('www.') || SCHEME.test(text)) {
      return urlCode(text);
    }
    return HANDLE.test(text) ? null : 'invalid_value';
  }
  return null;
}

// Канон телефона — как normalize_phone на сервере: «+цифры», 8/7/10-значные RU-номера → +7….
function canonPhone(text) {
  const digits = text.replace(/\D/g, '');
  if (text.startsWith('+')) return `+${digits}`;
  if (digits.length === 11 && (digits[0] === '7' || digits[0] === '8')) return `+7${digits.slice(1)}`;
  if (digits.length === 10) return `+7${digits}`;
  return `+${digits}`;
}

function dupKey(row) {
  const text = (row.value || '').trim();
  let value = text.toLowerCase();
  const phoneLike = row.type === 'phone'
    || (row.type === 'messenger' && row.service !== 'other');
  if (phoneLike && PHONE_CHARS.test(text)) value = canonPhone(text);
  else if (row.type === 'messenger' || row.type === 'social') value = value.replace(/^@+/, '');
  return `${row.type}|${row.service || ''}|${value}`;
}

/**
 * rows: строки черновика; catalog/limits — из ответа backend.
 * Возвращает { errors: { [rowId]: { field: message } }, hasErrors, firstInvalid }.
 * firstInvalid — { id, field } первой ошибочной строки (для фокуса).
 */
export function validateRows(rows, catalog, limits = DEFAULT_LIMITS) {
  const errors = {};
  let firstInvalid = null;
  const seen = new Set();

  const add = (row, field, code) => {
    errors[row.id] = { ...(errors[row.id] || {}), [field]: messageFor(code, limits, field) };
    if (!firstInvalid) firstInvalid = { id: row.id, field };
  };

  rows.forEach((row) => {
    const kind = serviceKindOf(catalog, row.type);
    if (kind && !row.service) add(row, 'service', 'service_required');

    // Поле «Название» видно (и проверяется) только у вариантов «Другой …». Прежняя
    // подпись обычного контакта скрыта: её не стираем и на клиенте не проверяем —
    // сервер авторитетен, а его ошибка по ней исправима (см. errorsFromServer).
    if (needsName(row)) {
      const label = (row.label || '').trim();
      if (label.length > limits.label_max) add(row, 'label', 'too_long');
      else if (CONTROL.test(label)) add(row, 'label', 'invalid_characters');
      else if (!label) add(row, 'label', 'label_required');
    }

    const value = (row.value || '').trim();
    if (value.length > limits.value_max) add(row, 'value', 'too_long');
    else {
      const code = valueCode(row.type, row.service, row.value);
      if (code) add(row, 'value', code);
    }

    if (!errors[row.id]) {
      const key = dupKey(row);
      if (seen.has(key)) add(row, 'value', 'duplicate');
      seen.add(key);
    }
  });

  return { errors, hasErrors: Object.keys(errors).length > 0, firstInvalid };
}

/** Серверные errors[] (index/field/code) → { errors по id строки, firstInvalid }. */
export function errorsFromServer(serverErrors, rows, limits = DEFAULT_LIMITS) {
  const errors = {};
  let firstInvalid = null;
  let general = null;
  (serverErrors || []).forEach(({ index, field, code }) => {
    const row = Number.isInteger(index) ? rows[index] : null;
    if (!row) {
      general = messageFor(code, limits, field);
      return;
    }
    const name = field || 'value';
    // Ошибка скрытой подписи: поля на экране нет, поэтому она выводится на уровне
    // контакта с явным действием «Удалить прежнюю подпись» (данные сами не стираются).
    const key = name === 'label' && !needsName(row) ? 'hiddenLabel' : name;
    errors[row.id] = { ...(errors[row.id] || {}), [key]: messageFor(code, limits, name) };
    if (!firstInvalid) firstInvalid = { id: row.id, field: name };
  });
  return { errors, firstInvalid, general };
}
