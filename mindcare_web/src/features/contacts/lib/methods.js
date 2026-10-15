/**
 * «Способ связи» — единый выбор вместо пары «тип + сервис» (ADR-031).
 *
 * Варианты строятся ТОЛЬКО из backend-каталога (`catalog.types`/`catalog.services`):
 * копии списка сервисов на клиенте нет. Внутри по-прежнему используются `type` и
 * `service`, формат API не меняется. Ключ варианта однозначен: `type` для типов без
 * сервиса (`phone`) и `type:service` для остальных (`messenger:other` ≠ `social:other`).
 */
import { PHONE_PLACEHOLDER } from '../../admin/users/phone';

export const OTHER_SERVICE = 'other';

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

/** Вариант для сохранённого type/service; null, если его нет в каталоге. */
export function methodOf(methods, type, service) {
  const key = methodKey(type, service || null);
  return methods.find((method) => method.key === key) ?? null;
}

/**
 * Подпись, подсказка, placeholder и режим ввода поля значения. Тексты описывают
 * то, что сервер действительно принимает; ограничений отдельных сервисов,
 * которых нет в контракте, не вводится.
 */
export function valueSpec(method) {
  const base = { inputType: 'text', inputMode: undefined, placeholder: undefined };
  if (!method) return { ...base, label: 'Контакт', hint: undefined };
  if (method.type === 'phone') {
    return {
      ...base,
      label: 'Номер телефона',
      inputType: 'tel',
      inputMode: 'tel',
      placeholder: PHONE_PLACEHOLDER,
      hint: 'С кодом страны или 10 цифр',
    };
  }
  if (method.type === 'email') {
    return {
      ...base,
      label: 'Email',
      inputMode: 'email',
      placeholder: 'name@example.org',
      hint: undefined,
    };
  }
  if (method.type === 'website') {
    return {
      ...base,
      label: 'Адрес сайта',
      inputMode: 'url',
      placeholder: 'example.org',
      hint: 'Ссылка вида example.org или https://example.org',
    };
  }
  if (method.type === 'other') {
    return { ...base, label: 'Контакт', hint: 'Любой текст' };
  }
  if (method.service === OTHER_SERVICE) {
    return {
      ...base,
      label: 'Контакт или ссылка',
      hint: 'Любой текст; ссылка — только http:// или https://',
    };
  }
  if (method.type === 'messenger') {
    return {
      ...base,
      label: 'Имя пользователя, номер или ссылка',
      placeholder: '@username',
      hint: 'Например: @name, номер телефона или ссылка',
    };
  }
  return {
    ...base,
    label: 'Имя пользователя или ссылка',
    placeholder: '@username',
    hint: 'Например: @name или ссылка на профиль',
  };
}
