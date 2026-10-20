import {
  applyMethod, emptyRow, isDirty, itemsForCompare, newContactId, rowsFromItems, serviceKindOf, toPayloadItems,
} from './draft';

const CATALOG = {
  types: [
    { code: 'phone', label: 'Телефон', service_kind: null },
    { code: 'email', label: 'Email', service_kind: null },
    { code: 'messenger', label: 'Мессенджер', service_kind: 'messenger' },
    { code: 'social', label: 'Социальная сеть', service_kind: 'social' },
    { code: 'website', label: 'Сайт', service_kind: null },
    { code: 'other', label: 'Другое', service_kind: null },
  ],
};

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

describe('newContactId', () => {
  it('возвращает UUIDv4 и разные значения', () => {
    const a = newContactId();
    const b = newContactId();
    expect(a).toMatch(UUID_RE);
    expect(a).not.toBe(b);
  });

  it('работает без crypto.randomUUID', () => {
    const original = window.crypto;
    Object.defineProperty(window, 'crypto', { value: undefined, configurable: true });
    try {
      expect(newContactId()).toMatch(UUID_RE);
    } finally {
      Object.defineProperty(window, 'crypto', { value: original, configurable: true });
    }
  });
});

describe('draft', () => {
  it('emptyRow создаёт строку со своим id', () => {
    const row = emptyRow('email');
    expect(row).toMatchObject({ type: 'email', service: '', value: '', label: '' });
    expect(row.id).toMatch(UUID_RE);
  });

  it('serviceKindOf берёт вид сервиса из каталога', () => {
    expect(serviceKindOf(CATALOG, 'messenger')).toBe('messenger');
    expect(serviceKindOf(CATALOG, 'phone')).toBeNull();
    expect(serviceKindOf(null, 'phone')).toBeNull();
  });

  it('toPayloadItems: trim, пустая подпись → null, сервис только где нужен', () => {
    const rows = [
      { id: 'a', type: 'phone', service: 'x', value: ' +7900 ', label: '  ' },
      { id: 'b', type: 'messenger', service: 'telegram', value: '@n', label: ' рабочий ' },
    ];
    expect(toPayloadItems(rows, CATALOG)).toEqual([
      { id: 'a', type: 'phone', service: null, value: '+7900', label: null },
      { id: 'b', type: 'messenger', service: 'telegram', value: '@n', label: 'рабочий' },
    ]);
  });

  it('id строки сохраняется при повторной сборке payload (повтор отправки)', () => {
    const rows = [emptyRow('phone')];
    rows[0].value = '+79001234567';
    const first = toPayloadItems(rows, CATALOG);
    const second = toPayloadItems(rows, CATALOG);
    expect(second).toEqual(first);
  });

  it('rowsFromItems/itemsForCompare нормализуют пустые поля', () => {
    const items = [{ id: 'a', type: 'phone', service: null, value: '+7', label: null }];
    expect(rowsFromItems(items)).toEqual([
      { id: 'a', type: 'phone', service: '', value: '+7', label: '' },
    ]);
    expect(itemsForCompare(items)).toEqual(items);
    expect(rowsFromItems(null)).toEqual([]);
  });

  it('isDirty сравнивает черновик с сохранённым', () => {
    const server = [{ id: 'a', type: 'phone', service: null, value: '+7900', label: null }];
    const rows = rowsFromItems(server);
    expect(isDirty(rows, server, CATALOG)).toBe(false);
    expect(isDirty([{ ...rows[0], value: ' +7900 ' }], server, CATALOG)).toBe(false);
    expect(isDirty([{ ...rows[0], value: '+7901' }], server, CATALOG)).toBe(true);
    expect(isDirty([], server, CATALOG)).toBe(true);
  });
});

describe('applyMethod', () => {
  const TG = { type: 'messenger', service: 'telegram' };
  const OTHER_MESSENGER = { type: 'messenger', service: 'other' };
  const PHONE = { type: 'phone', service: null };
  const OTHER = { type: 'other', service: null };

  it('type и service меняются вместе: прежний service не остаётся у несовместимого типа', () => {
    const row = { id: 'a', type: 'messenger', service: 'telegram', value: '@a', label: '' };
    const next = applyMethod(row, PHONE, null);
    expect(next).toMatchObject({ type: 'phone', service: '', value: '@a' });
    expect(toPayloadItems([next], CATALOG)[0]).toMatchObject({ type: 'phone', service: null });
  });

  it('тот же способ — та же строка (без лишних обновлений)', () => {
    const row = { id: 'a', type: 'messenger', service: 'telegram', value: '', label: '' };
    expect(applyMethod(row, TG, null)).toBe(row);
  });

  it('значение и id при смене способа сохраняются', () => {
    const row = { id: 'a', type: 'phone', service: '', value: '+7900', label: '' };
    expect(applyMethod(row, TG, null)).toMatchObject({ id: 'a', value: '+7900', service: 'telegram' });
  });

  it('название, введённое в этой сессии, на обычный способ не переносится', () => {
    const row = { id: 'a', type: 'messenger', service: 'other', value: 'x', label: 'Мой сервис' };
    expect(applyMethod(row, TG, null).label).toBe('');
  });

  it('сохранённая подпись не стирается: при уходе с «Другого» возвращается именно она', () => {
    const saved = { id: 'a', type: 'messenger', service: 'other', value: 'x', label: 'Сохранённое' };
    const edited = { id: 'a', type: 'messenger', service: 'other', value: 'x', label: 'Правка в сессии' };
    expect(applyMethod(edited, TG, saved).label).toBe('Сохранённое');
    // правки названия не было — подпись остаётся как есть
    const untouched = { ...edited, label: 'Сохранённое' };
    expect(applyMethod(untouched, TG, saved).label).toBe('Сохранённое');
  });

  it('прежняя подпись обычного контакта переживает смену способа', () => {
    const saved = { id: 'a', type: 'phone', service: null, value: '+7900', label: 'рабочий' };
    const row = { id: 'a', type: 'phone', service: '', value: '+7900', label: 'рабочий' };
    expect(applyMethod(row, TG, saved).label).toBe('рабочий');
    expect(applyMethod(row, OTHER, saved).label).toBe('рабочий');
    expect(applyMethod(row, OTHER_MESSENGER, saved).label).toBe('рабочий');
  });
});

describe('payload по способам связи', () => {
  const rows = (type, service, value, label = '') => [{ id: 'a', type, service, value, label }];

  it.each([
    ['phone', '', '+79001234567', { type: 'phone', service: null }],
    ['email', '', 'me@example.org', { type: 'email', service: null }],
    ['website', '', 'example.org', { type: 'website', service: null }],
    ['messenger', 'telegram', '@name', { type: 'messenger', service: 'telegram' }],
    ['social', 'vk', 'https://vk.com/id1', { type: 'social', service: 'vk' }],
  ])('%s/%s → type/service и label:null для нового контакта', (type, service, value, expected) => {
    expect(toPayloadItems(rows(type, service, value), CATALOG)[0]).toEqual({
      id: 'a', value, label: null, ...expected,
    });
  });

  it('«Другой …» несёт название в label', () => {
    expect(toPayloadItems(rows('messenger', 'other', 'id1', '  Мой сервис '), CATALOG)[0])
      .toMatchObject({ type: 'messenger', service: 'other', label: 'Мой сервис' });
  });

  it('прежняя подпись обычного контакта сохраняется в payload', () => {
    expect(toPayloadItems(rows('phone', '', '+79001234567', 'рабочий'), CATALOG)[0].label).toBe('рабочий');
  });
});
