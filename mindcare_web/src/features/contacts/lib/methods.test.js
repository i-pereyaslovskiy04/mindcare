import {
  EMAIL_NOTE, OFFERED_METHOD_KEYS, buildMethods, formatContactPhone, methodKey, methodOf,
  needsName, offeredMethods, valueSpec,
} from './methods';
import { PHONE_PLACEHOLDER, formatPhoneInput } from '../../admin/users/phone';

// Каталог в форме ответа backend (app/user_contacts/catalog.py::catalog_dto).
const CATALOG = {
  types: [
    { code: 'phone', label: 'Телефон', service_kind: null },
    { code: 'email', label: 'Email', service_kind: null },
    { code: 'messenger', label: 'Мессенджер', service_kind: 'messenger' },
    { code: 'social', label: 'Социальная сеть', service_kind: 'social' },
    { code: 'website', label: 'Сайт', service_kind: null },
    { code: 'other', label: 'Другое', service_kind: null },
  ],
  services: {
    messenger: [
      { code: 'telegram', label: 'Telegram' },
      { code: 'whatsapp', label: 'WhatsApp' },
      { code: 'viber', label: 'Viber' },
      { code: 'max', label: 'MAX' },
      { code: 'signal', label: 'Signal' },
      { code: 'skype', label: 'Skype' },
      { code: 'other', label: 'Другой мессенджер' },
    ],
    social: [
      { code: 'vk', label: 'VK' },
      { code: 'ok', label: 'Одноклассники' },
      { code: 'instagram', label: 'Instagram' },
      { code: 'facebook', label: 'Facebook' },
      { code: 'linkedin', label: 'LinkedIn' },
      { code: 'x', label: 'X (Twitter)' },
      { code: 'youtube', label: 'YouTube' },
      { code: 'rutube', label: 'RUTUBE' },
      { code: 'other', label: 'Другая соцсеть' },
    ],
  },
};

describe('buildMethods', () => {
  const methods = buildMethods(CATALOG);

  it('варианты — из каталога, в его порядке; сервисы развёрнуты в отдельные варианты', () => {
    expect(methods.map((m) => m.label)).toEqual([
      'Телефон', 'Email',
      'Telegram', 'WhatsApp', 'Viber', 'MAX', 'Signal', 'Skype', 'Другой мессенджер',
      'VK', 'Одноклассники', 'Instagram', 'Facebook', 'LinkedIn', 'X (Twitter)', 'YouTube', 'RUTUBE', 'Другая соцсеть',
      'Сайт', 'Другое',
    ]);
  });

  it('число вариантов равно числу типов без сервиса плюс числу сервисов каталога', () => {
    const expected = CATALOG.types.filter((t) => !t.service_kind).length
      + Object.values(CATALOG.services).reduce((sum, list) => sum + list.length, 0);
    expect(methods).toHaveLength(expected);
  });

  it('ключи уникальны, а type/service ↔ ключ — взаимно однозначно', () => {
    const keys = methods.map((m) => m.key);
    expect(new Set(keys).size).toBe(keys.length);
    methods.forEach((m) => {
      expect(m.key).toBe(methodKey(m.type, m.service));
      expect(methodOf(methods, m.type, m.service)).toBe(m);
    });
    // Одноимённые сервисы разных видов не смешиваются.
    expect(methodOf(methods, 'messenger', 'other').label).toBe('Другой мессенджер');
    expect(methodOf(methods, 'social', 'other').label).toBe('Другая соцсеть');
  });

  it('service ровно там, где его требует каталог; у остальных null', () => {
    const allowed = (m) => {
      const kind = CATALOG.types.find((t) => t.code === m.type).service_kind;
      return kind ? CATALOG.services[kind].map((s) => s.code) : [null];
    };
    expect(methods.map((m) => allowed(m).includes(m.service))).toEqual(methods.map(() => true));
  });

  it('«Название» нужно только вариантам «Другой …» и типу other', () => {
    const named = methods.filter((m) => m.requiresName).map((m) => m.label);
    expect(named).toEqual(['Другой мессенджер', 'Другая соцсеть', 'Другое']);
  });

  it('без каталога — пустой список, без исключений', () => {
    expect(buildMethods(null)).toEqual([]);
    expect(buildMethods({})).toEqual([]);
  });

  it('новый сервис каталога появляется без изменения клиента', () => {
    const extended = {
      ...CATALOG,
      services: { ...CATALOG.services, messenger: [{ code: 'zulip', label: 'Zulip' }, ...CATALOG.services.messenger] },
    };
    expect(methodOf(buildMethods(extended), 'messenger', 'zulip').label).toBe('Zulip');
  });
});

describe('methodOf / needsName', () => {
  const methods = buildMethods(CATALOG);

  it('сохранённый контакт отображается своим вариантом; пустой сервис = null', () => {
    expect(methodOf(methods, 'phone', null).label).toBe('Телефон');
    expect(methodOf(methods, 'phone', '').label).toBe('Телефон');
    expect(methodOf(methods, 'messenger', 'telegram').label).toBe('Telegram');
  });

  it('контакт вне каталога → null', () => {
    expect(methodOf(methods, 'messenger', 'icq')).toBeNull();
    expect(methodOf(methods, 'fax', null)).toBeNull();
  });

  it('needsName', () => {
    expect(needsName({ type: 'other', service: '' })).toBe(true);
    expect(needsName({ type: 'social', service: 'other' })).toBe(true);
    expect(needsName({ type: 'messenger', service: 'telegram' })).toBe(false);
    expect(needsName(null)).toBe(false);
  });
});

describe('valueSpec', () => {
  const methods = buildMethods(CATALOG);
  const spec = (type, service = null) => valueSpec(methodOf(methods, type, service));

  it('телефон: tel, маска основного телефона, тот же placeholder', () => {
    expect(spec('phone')).toMatchObject({
      label: 'Номер телефона', inputType: 'tel', inputMode: 'tel',
      placeholder: PHONE_PLACEHOLDER, format: formatContactPhone, hint: undefined,
    });
  });

  it('маска есть только у «Телефона»', () => {
    methods.filter((m) => m.type !== 'phone').forEach((m) => {
      expect(valueSpec(m).format).toBeUndefined();
      expect(valueSpec(m).inputType).not.toBe('tel');
    });
  });

  it('WhatsApp: номер или ссылка, без маски; MAX и Telegram — правила мессенджера', () => {
    expect(spec('messenger', 'whatsapp')).toMatchObject({
      label: 'Номер телефона или ссылка', placeholder: PHONE_PLACEHOLDER, format: undefined,
    });
    expect(spec('messenger', 'max')).toMatchObject({
      label: 'Имя пользователя, номер или ссылка', placeholder: '@username', format: undefined,
    });
    expect(spec('messenger', 'telegram').label).toBe('Имя пользователя, номер или ссылка');
  });

  it('подсказки внутри строки — короткие, без абзацев', () => {
    const hints = methods.map((m) => valueSpec(m).hint).filter((hint) => hint !== undefined);
    expect(hints.length).toBeGreaterThan(0);
    hints.forEach((hint) => expect(hint.length).toBeLessThanOrEqual(50));
  });

  it('email и сайт: свой режим ввода; у email — пояснение, что это не адрес аккаунта', () => {
    expect(spec('email')).toMatchObject({
      label: 'Email', inputType: 'email', inputMode: 'email', placeholder: 'name@example.ru', hint: EMAIL_NOTE,
    });
    expect(EMAIL_NOTE).toBe('Только для связи, не используется для входа.');
    expect(spec('website')).toMatchObject({ label: 'Адрес сайта', inputMode: 'url', hint: undefined });
    expect(spec('website').placeholder).toMatch(/example\.org/);
  });

  it('очевидные подсказки убраны: пример — в placeholder', () => {
    expect(spec('messenger', 'telegram')).toMatchObject({ placeholder: '@username', hint: undefined });
    expect(spec('social', 'vk')).toMatchObject({ placeholder: '@username', hint: undefined });
    expect(spec('other').hint).toBeUndefined();
  });

  it('мессенджер: имя, номер или ссылка; соцсеть: имя или ссылка', () => {
    expect(spec('messenger', 'telegram').label).toBe('Имя пользователя, номер или ссылка');
    expect(spec('social', 'vk').label).toBe('Имя пользователя или ссылка');
  });

  it('«Другой …» и тип other: произвольный текст, ссылка — только http(s)', () => {
    expect(spec('messenger', 'other').label).toBe('Контакт или ссылка');
    expect(spec('messenger', 'other').hint).toMatch(/http/);
    expect(spec('other').label).toBe('Контакт');
  });

  it('неизвестный вариант не ломает форму', () => {
    expect(valueSpec(null).label).toBe('Контакт');
  });
});

describe('offeredMethods', () => {
  const methods = buildMethods(CATALOG);
  const labels = (list) => list.map((m) => m.label);

  it('новому контакту — короткий список в продуктовом порядке', () => {
    expect(labels(offeredMethods(methods))).toEqual([
      'Телефон', 'Telegram', 'MAX', 'VK', 'Email', 'WhatsApp', 'Другое',
    ]);
    expect(OFFERED_METHOD_KEYS).toHaveLength(7);
    // Все ключи короткого списка есть в полном каталоге backend.
    OFFERED_METHOD_KEYS.forEach((key) => expect(methods.some((m) => m.key === key)).toBe(true));
  });

  it('скрытые способы строки добавляются в конец, в порядке каталога, без дублей', () => {
    expect(labels(offeredMethods(methods, ['website', 'social:instagram', 'messenger:telegram']))).toEqual([
      'Телефон', 'Telegram', 'MAX', 'VK', 'Email', 'WhatsApp', 'Другое', 'Instagram', 'Сайт',
    ]);
  });

  it('ключ вне каталога не добавляет вариант', () => {
    expect(labels(offeredMethods(methods, ['messenger:icq']))).toHaveLength(7);
  });

  it('каталог без вариантов короткого списка — предлагается весь каталог', () => {
    const custom = buildMethods({
      types: [{ code: 'fax', label: 'Факс', service_kind: null }], services: {},
    });
    expect(labels(offeredMethods(custom))).toEqual(['Факс']);
  });

  it('без каталога — пусто', () => {
    expect(offeredMethods([])).toEqual([]);
  });
});

describe('formatContactPhone', () => {
  it.each([
    '9001234567', '89001234567', '79001234567', '+79001234567', '+7 (900) 123-45-67', '8 900 123 45 67', '',
  ])('российский номер %p — ровно как маска основного телефона', (input) => {
    expect(formatContactPhone(input)).toBe(formatPhoneInput(input));
  });

  it('десятки цифр обрезаются до 11 (+7 и 10 цифр номера)', () => {
    expect(formatContactPhone('8445454545454121218448544812345678')).toBe('+7 (445) 454-54-54');
  });

  it('вставка «+7 (234) 234-2выа34234234234234» — без букв, маска +7, 11 цифр', () => {
    const out = formatContactPhone('+7 (234) 234-2выа34234234234234');
    expect(out).toBe('+7 (234) 234-23-42');
    expect(out).not.toMatch(/\p{L}/u);
    expect(out.replace(/\D/g, '')).toHaveLength(11);
  });

  it('буквы в пустое поле не вводятся', () => {
    expect(formatContactPhone('a')).toBe('');
    expect(formatContactPhone('абв')).toBe('');
    expect(formatContactPhone('@ivan')).toBe('');
    expect(formatContactPhone(null)).toBe('');
  });

  it('буквы среди цифр удаляются', () => {
    expect(formatContactPhone('8900abc1234567')).toBe('+7 (900) 123-45-67');
    expect(formatContactPhone('@ivan9')).toBe('+7 (9');
  });

  it('номер другой страны: «+» и цифры, не больше 15, в +7 не переписывается', () => {
    expect(formatContactPhone('+380711234567')).toBe('+380711234567');
    expect(formatContactPhone('+44 20 7946 0958')).toBe('+442079460958');
    expect(formatContactPhone('+380 71 абв 123-45-67')).toBe('+380711234567');
    expect(formatContactPhone('+3807112345678901234')).toBe('+380711234567890');
    expect(formatContactPhone('+')).toBe('+');
    expect(formatContactPhone('+abc')).toBe('+');
  });
});
