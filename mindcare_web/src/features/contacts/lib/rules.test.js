/* eslint-disable no-script-url */
import { DEFAULT_LIMITS } from './draft';
import { errorsFromServer, messageFor, validateRows } from './rules';

const CATALOG = {
  types: [
    { code: 'phone', service_kind: null },
    { code: 'email', service_kind: null },
    { code: 'messenger', service_kind: 'messenger' },
    { code: 'social', service_kind: 'social' },
    { code: 'website', service_kind: null },
    { code: 'other', service_kind: null },
  ],
};

const row = (patch) => ({
  id: 'r1', type: 'phone', service: '', value: '', label: '', ...patch,
});

const codeOf = (patch) => {
  const res = validateRows([row(patch)], CATALOG);
  return res.errors.r1 ? Object.values(res.errors.r1)[0] : null;
};

describe('validateRows', () => {
  it('допустимые значения проходят', () => {
    const rows = [
      row({ id: 'a', type: 'phone', value: '+7 (900) 123-45-67' }),
      row({ id: 'b', type: 'email', value: 'me@example.org' }),
      row({ id: 'c', type: 'messenger', service: 'telegram', value: '@my_name' }),
      row({ id: 'd', type: 'social', service: 'vk', value: 'https://vk.com/id1' }),
      row({ id: 'e', type: 'website', value: 'example.org' }),
      row({ id: 'f', type: 'other', value: 'Лично на кафедре', label: 'Как найти' }),
    ];
    const res = validateRows(rows, CATALOG);
    expect(res.hasErrors).toBe(false);
    expect(res.firstInvalid).toBeNull();
  });

  it('пустое значение — «Заполните поле»', () => {
    expect(codeOf({ type: 'phone', value: '  ' })).toBe(messageFor('required'));
  });

  it.each([
    [{ type: 'phone', value: '12345' }, 'invalid_phone'],
    [{ type: 'phone', value: 'abc' }, 'invalid_phone'],
    [{ type: 'email', value: 'not-an-email' }, 'invalid_email'],
    [{ type: 'website', value: 'javascript:alert(1)' }, 'unsafe_url'],
    [{ type: 'website', value: 'https://u:p@example.org' }, 'unsafe_url'],
    [{ type: 'website', value: 'localhost' }, 'invalid_url'],
    [{ type: 'social', service: 'vk', value: 'a' }, 'invalid_value'],
    [{ type: 'phone', value: '+7900\u0007123' }, 'invalid_characters'],
    [{ type: 'phone', value: '+7900‮123' }, 'invalid_characters'],
  ])('%j → %s', (patch, code) => {
    expect(codeOf(patch)).toBe(messageFor(code));
  });

  it('мессенджер/соцсеть требуют сервис', () => {
    const res = validateRows([row({ type: 'messenger', value: '@name' })], CATALOG);
    expect(res.errors.r1.service).toBe(messageFor('service_required'));
    expect(res.firstInvalid).toEqual({ id: 'r1', field: 'service' });
  });

  it('«другое» и «другой сервис» требуют название', () => {
    expect(validateRows([row({ type: 'other', value: 'x' })], CATALOG).errors.r1.label)
      .toBe(messageFor('label_required'));
    const res = validateRows(
      [row({ type: 'social', service: 'other', value: 'https://a.example', label: '' })],
      CATALOG,
    );
    expect(res.errors.r1.label).toBe(messageFor('label_required'));
  });

  it('длины ограничены лимитами', () => {
    const long = validateRows(
      [row({ type: 'other', value: 'x'.repeat(DEFAULT_LIMITS.value_max + 1), label: 'ok' })],
      CATALOG,
    );
    expect(long.errors.r1.value).toContain(String(DEFAULT_LIMITS.value_max));
    const label = validateRows(
      [row({ type: 'other', value: 'v', label: 'x'.repeat(DEFAULT_LIMITS.label_max + 1) })],
      CATALOG,
    );
    expect(label.errors.r1.label).toContain(String(DEFAULT_LIMITS.label_max));
  });

  it('дубли значений отклоняются, с учётом @ и регистра', () => {
    const rows = [
      row({ id: 'a', type: 'messenger', service: 'telegram', value: '@Name' }),
      row({ id: 'b', type: 'messenger', service: 'telegram', value: 'name' }),
    ];
    const res = validateRows(rows, CATALOG);
    expect(res.errors.b.value).toBe(messageFor('duplicate'));
    expect(res.errors.a).toBeUndefined();
    expect(res.firstInvalid).toEqual({ id: 'b', field: 'value' });
  });

  it('значение не попадает в текст ошибки', () => {
    const secret = 'secret-value@@';
    const res = validateRows([row({ type: 'email', value: secret })], CATALOG);
    expect(JSON.stringify(res.errors)).not.toContain(secret);
  });
});

describe('errorsFromServer', () => {
  const rows = [row({ id: 'a', type: 'other', label: 'Название' }), row({ id: 'b' })];

  it('сопоставляет index → id строки и берёт первую для фокуса', () => {
    const res = errorsFromServer(
      [{ index: 1, field: 'value', code: 'invalid_phone' }, { index: 0, field: 'label', code: 'too_long' }],
      rows,
    );
    expect(res.errors.b.value).toBe(messageFor('invalid_phone'));
    expect(res.errors.a.label).toContain(String(DEFAULT_LIMITS.label_max));
    expect(res.firstInvalid).toEqual({ id: 'b', field: 'value' });
    expect(res.general).toBeNull();
  });

  it('ошибка без строки → общее сообщение', () => {
    const res = errorsFromServer([{ index: null, field: 'items', code: 'too_many' }], rows);
    expect(res.general).toBe(messageFor('too_many'));
    expect(res.firstInvalid).toBeNull();
  });

  it('неизвестный код → нейтральное сообщение', () => {
    expect(messageFor('что-то-новое')).toBe('Проверьте значение');
  });
});

describe('прежняя (скрытая) подпись обычного контакта', () => {
  it('клиент её не проверяет и не требует: длинная/необязательная подпись не блокирует отправку', () => {
    const long = 'x'.repeat(DEFAULT_LIMITS.label_max + 50);
    const res = validateRows([row({ value: '+79001234567', label: long })], CATALOG);
    expect(res.hasErrors).toBe(false);
  });

  it('ошибка сервера по скрытой подписи — на уровне контакта (hiddenLabel), поля «label» нет', () => {
    const rows = [row({ id: 'a', value: '+79001234567', label: 'старая' })];
    const res = errorsFromServer([{ index: 0, field: 'label', code: 'too_long' }], rows);
    expect(res.errors.a.hiddenLabel).toContain(String(DEFAULT_LIMITS.label_max));
    expect(res.errors.a.label).toBeUndefined();
    expect(res.firstInvalid).toEqual({ id: 'a', field: 'label' });
  });

  it('ошибка сервера по видимому «Названию» остаётся ошибкой поля', () => {
    const rows = [row({ id: 'a', type: 'social', service: 'other', label: 'x' })];
    const res = errorsFromServer([{ index: 0, field: 'label', code: 'label_required' }], rows);
    expect(res.errors.a.label).toBe(messageFor('label_required'));
    expect(res.errors.a.hiddenLabel).toBeUndefined();
  });
});

describe('согласование с сервером', () => {
  it('«Название» обязательно только у «Другой …» (сервер: label_required)', () => {
    const other = [
      row({ id: 'a', type: 'other', value: 'x' }),
      row({ id: 'b', type: 'messenger', service: 'other', value: 'x' }),
      row({ id: 'c', type: 'social', service: 'other', value: 'x' }),
    ];
    const res = validateRows(other, CATALOG);
    ['a', 'b', 'c'].forEach((id) => {
      expect(res.errors[id].label).toBe(messageFor('label_required'));
    });
    const regular = [
      row({ id: 'd', type: 'phone', value: '+79001234567' }),
      row({ id: 'e', type: 'messenger', service: 'telegram', value: '@name' }),
      row({ id: 'f', type: 'website', value: 'example.org' }),
    ];
    expect(validateRows(regular, CATALOG).hasErrors).toBe(false);
  });

  it('один и тот же телефон в разной записи — дубль (как normalize_phone на сервере)', () => {
    const res = validateRows([
      row({ id: 'a', value: '+7 (949) 123-45-67' }),
      row({ id: 'b', value: '89491234567' }),
    ], CATALOG);
    expect(res.errors.b.value).toBe(messageFor('duplicate'));
    expect(res.errors.a).toBeUndefined();
    const ten = validateRows([
      row({ id: 'a', value: '9491234567' }),
      row({ id: 'b', value: '+79491234567' }),
    ], CATALOG);
    expect(ten.errors.b.value).toBe(messageFor('duplicate'));
  });

  it('телефон в мессенджере сводится к тому же ключу, у «Другого мессенджера» — нет', () => {
    const res = validateRows([
      row({ id: 'a', type: 'messenger', service: 'whatsapp', value: '+7 949 123 45 67' }),
      row({ id: 'b', type: 'messenger', service: 'whatsapp', value: '89491234567' }),
    ], CATALOG);
    expect(res.errors.b.value).toBe(messageFor('duplicate'));
    const other = validateRows([
      row({ id: 'a', type: 'messenger', service: 'other', value: '123456789012', label: 'A' }),
      row({ id: 'b', type: 'messenger', service: 'other', value: '+123456789012', label: 'B' }),
    ], CATALOG);
    expect(other.errors.b).toBeUndefined();
  });

  it('все ошибки способа связи говорят одно и то же — «Выберите способ связи»', () => {
    ['invalid_type', 'invalid_service', 'service_required', 'service_not_allowed'].forEach((code) => {
      expect(messageFor(code)).toBe('Выберите способ связи');
    });
    const res = validateRows([row({ type: 'messenger', service: '', value: '@name' })], CATALOG);
    expect(res.errors.r1.service).toBe('Выберите способ связи');
  });
});
