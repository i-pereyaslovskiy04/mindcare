import {
  buildMethods, methodKey, methodOf, needsName, valueSpec,
} from './methods';

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

  it('телефон: tel, inputMode tel, подсказка о формате', () => {
    expect(spec('phone')).toMatchObject({
      label: 'Номер телефона', inputType: 'tel', inputMode: 'tel',
    });
    expect(spec('phone').hint).toMatch(/10 цифр/);
  });

  it('email и сайт: свой режим ввода', () => {
    expect(spec('email')).toMatchObject({ label: 'Email', inputMode: 'email' });
    expect(spec('website')).toMatchObject({ label: 'Адрес сайта', inputMode: 'url' });
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
