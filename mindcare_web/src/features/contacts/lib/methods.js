/**
 * «Способ связи» — единый выбор вместо пары «тип + сервис» (ADR-032).
 *
 * Варианты строятся ТОЛЬКО из backend-каталога (`catalog.types`/`catalog.services`):
 * копии списка сервисов на клиенте нет. Новому контакту редактор предлагает
 * подмножество каталога (OFFERED_METHOD_KEYS — фильтр по ключам, не копия).
 * Внутри по-прежнему используются `type` и `service`, формат API не меняется.
 * Ключ варианта однозначен: `type` для типов без
 * сервиса (`phone`) и `type:service` для остальных (`messenger:other` ≠ `social:other`).
 */
import { PHONE_PLACEHOLDER, formatPhoneInput } from '../../admin/users/phone';

export const OTHER_SERVICE = 'other';

// Номер другой страны — до 15 цифр (E.164), как принимает normalize_phone на сервере.
const MAX_PHONE_DIGITS = 15;

/**
 * Ввод значения способа «Телефон» (и при наборе, и при вставке). В поле остаются
 * только цифры номера: буквы и прочие символы удаляются всегда.
 * - Российский номер — та же маска, что у основного телефона (formatPhoneInput:
 *   +7 (XXX) XXX-XX-XX, не больше 11 цифр).
 * - Номер другой страны (начат с «+» и кода не 7) — контракт контактов (ADR-032)
 *   его принимает: остаются «+» и цифры, не больше 15; в +7 не переписывается.
 * Значение прежнего способа связи сюда не попадает: смена способа его очищает.
 */
export function formatContactPhone(value) {
  const text = value == null ? '' : String(value).trimStart();
  const digits = text.replace(/\D/g, '');
  if (text.startsWith('+')) {
    // Одиночный «+» — начало номера другой страны, его не стираем.
    if (digits === '') return '+';
    if (digits[0] !== '7') return `+${digits.slice(0, MAX_PHONE_DIGITS)}`;
  }
  return formatPhoneInput(text);
}

export const methodKey = (type, service) => (service ? `${type}:${service}` : type);

/** Нужно ли обязательное «Название» (неизвестный сервису способ связи). */
export function needsName(item) {
  return item?.type === 'other' || item?.service === OTHER_SERVICE;
}

function makeMethod(type, service, label) {
  return {
    key: methodKey(type, service),
    type,
    service: service || null,
    label,
    requiresName: needsName({ type, service }),
  };
}

/** Упорядоченный список вариантов в порядке каталога. */
export function buildMethods(catalog) {
  const methods = [];
  (catalog?.types ?? []).forEach((type) => {
    if (!type.service_kind) {
      methods.push(makeMethod(type.code, null, type.label));
      return;
    }
    (catalog?.services?.[type.service_kind] ?? []).forEach((service) => {
      methods.push(makeMethod(type.code, service.code, service.label));
    });
  });
  return methods;
}

/**
 * Способы связи, которые редактор предлагает для НОВОГО контакта, — продуктово
 * ограниченное подмножество каталога (ADR-032, дополнение 2026-10-20), в этом
 * порядке. Это фильтр по ключам, а не копия каталога: подписи и наличие варианта
 * по-прежнему берутся из backend; полный каталог сохраняется для совместимости.
 */
export const OFFERED_METHOD_KEYS = Object.freeze([
  'phone',
  'messenger:telegram',
  'messenger:max',
  'social:vk',
  'email',
  'messenger:whatsapp',
  'other',
]);

/**
 * Варианты селектора одной строки: короткий список + способы из `keepKeys`
 * (текущий и сохранённый способ строки), даже если их нет в коротком списке, —
 * ранее сохранённый Instagram, сайт и т. п. отображаются, остаются выбираемыми
 * в своей строке и сохраняются без потери данных. Дополнительные — после
 * короткого списка, в порядке каталога. Если каталог не содержит ни одного
 * варианта короткого списка, предлагается весь каталог.
 */
export function offeredMethods(methods, keepKeys = []) {
  const byKey = new Map(methods.map((method) => [method.key, method]));
  const offered = OFFERED_METHOD_KEYS.map((key) => byKey.get(key)).filter(Boolean);
  if (offered.length === 0) return methods;
  const extra = methods.filter(
    (method) => !OFFERED_METHOD_KEYS.includes(method.key) && keepKeys.includes(method.key),
  );
  return [...offered, ...extra];
}

/** Вариант для сохранённого type/service; null, если его нет в каталоге. */
export function methodOf(methods, type, service) {
  const key = methodKey(type, service || null);
  return methods.find((method) => method.key === key) ?? null;
}

// Подсказка внутри строки — короткая, в одну строку: длинные пояснения
// ломают компактную строку контакта.
export const EMAIL_NOTE = 'Только для связи, не используется для входа.';

/**
 * Подпись, подсказка, placeholder и режим ввода поля значения. Тексты описывают
 * то, что сервер действительно принимает; ограничений отдельных сервисов,
 * которых нет в контракте, не вводится. Пример значения — в placeholder;
 * подсказка остаётся только там, где есть правило формата (телефон, ссылки
 * «Другой …») или важное пояснение (email — не адрес аккаунта).
 */
export function valueSpec(method) {
  // format — преобразование ввода (маска) или undefined: значение как введено.
  const base = {
    inputType: 'text', inputMode: undefined, placeholder: undefined, format: undefined,
  };
  if (!method) return { ...base, label: 'Контакт', hint: undefined };
  if (method.type === 'phone') {
    return {
      ...base,
      label: 'Номер телефона',
      inputType: 'tel',
      inputMode: 'tel',
      placeholder: PHONE_PLACEHOLDER,
      hint: undefined,
      format: formatContactPhone,
    };
  }
  if (method.type === 'email') {
    return {
      ...base,
      label: 'Email',
      inputType: 'email',
      inputMode: 'email',
      placeholder: 'name@example.ru',
      hint: EMAIL_NOTE,
    };
  }
  if (method.type === 'website') {
    return {
      ...base,
      label: 'Адрес сайта',
      inputMode: 'url',
      placeholder: 'example.org или https://example.org',
      hint: undefined,
    };
  }
  if (method.type === 'other') {
    return { ...base, label: 'Контакт', hint: undefined };
  }
  if (method.service === OTHER_SERVICE) {
    return {
      ...base,
      label: 'Контакт или ссылка',
      hint: 'Ссылка — только http:// или https://',
    };
  }
  // WhatsApp: сервер принимает номер (нормализуется как телефон), ссылку или
  // имя — как у любого мессенджера; маски нет, подсказан самый частый вариант.
  if (method.type === 'messenger' && method.service === 'whatsapp') {
    return {
      ...base,
      label: 'Номер телефона или ссылка',
      placeholder: PHONE_PLACEHOLDER,
      hint: undefined,
    };
  }
  if (method.type === 'messenger') {
    return {
      ...base,
      label: 'Имя пользователя, номер или ссылка',
      placeholder: '@username',
      hint: undefined,
    };
  }
  return {
    ...base,
    label: 'Имя пользователя или ссылка',
    placeholder: '@username',
    hint: undefined,
  };
}
