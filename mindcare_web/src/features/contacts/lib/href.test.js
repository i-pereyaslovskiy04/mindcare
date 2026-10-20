/* eslint-disable no-script-url */
import { contactHref, isSafeHttpUrl, telDigits } from './href';
import { formatPhoneInput } from '../../admin/users/phone';

describe('isSafeHttpUrl', () => {
  it.each([
    ['https://vk.com/id1', true],
    ['http://example.org/a?b=1', true],
    ['javascript:alert(1)', false],
    ['data:text/html,<b>x</b>', false],
    ['ftp://example.org', false],
    ['https://user:pw@example.org', false],
    ['https://exa mple.org', false],
    ['//example.org', false],
    ['example.org', false],
    ['', false],
    [null, false],
    [42, false],
  ])('%s → %s', (value, expected) => {
    expect(isSafeHttpUrl(value)).toBe(expected);
  });
});

describe('contactHref', () => {
  it('URL-типы получают только проверенный http(s)', () => {
    expect(contactHref({ type: 'website', value: 'https://example.org' })).toBe('https://example.org');
    expect(contactHref({ type: 'social', value: 'https://vk.com/a' })).toBe('https://vk.com/a');
    expect(contactHref({ type: 'messenger', value: 'https://t.me/a' })).toBe('https://t.me/a');
  });

  it('javascript:/data: никогда не становятся ссылкой', () => {
    expect(contactHref({ type: 'website', value: 'javascript:alert(1)' })).toBeNull();
    expect(contactHref({ type: 'social', value: 'data:text/html,x' })).toBeNull();
  });

  it('хэндлы и «другое» — без ссылки', () => {
    expect(contactHref({ type: 'messenger', value: '@name' })).toBeNull();
    expect(contactHref({ type: 'other', value: 'https://example.org' })).toBeNull();
  });

  it('email → mailto, телефон → tel только в каноническом виде', () => {
    expect(contactHref({ type: 'email', value: 'a@b.ru' })).toBe('mailto:a@b.ru');
    expect(contactHref({ type: 'email', value: 'a b@c.ru' })).toBeNull();
    expect(contactHref({ type: 'phone', value: '+79001234567' })).toBe('tel:+79001234567');
    expect(contactHref({ type: 'phone', value: '12 34' })).toBeNull();
  });

  it('форматированный телефон нормализуется до +цифры, текст не меняется', () => {
    const item = { type: 'phone', value: '+7 (949) 123-45-67' };
    expect(contactHref(item)).toBe('tel:+79491234567');
    expect(item.value).toBe('+7 (949) 123-45-67');
    expect(contactHref({ type: 'phone', value: '8 (949) 123-45-67' })).toBe('tel:89491234567');
    expect(contactHref({ type: 'phone', value: '+7.949.123.45.67' })).toBe('tel:+79491234567');
  });

  it.each([
    'позвоните +7 949 123-45-67',
    '+7 (949) 123-45-67; rm',
    '+7949123abc67',
    'javascript:alert(1)',
    'tel:+79491234567',
    '+7 (949) 123-45-67 доб. 12',
    '123456',
    '1234567890123456',
    '',
    '   ',
  ])('произвольная строка %j ссылкой не становится', (value) => {
    expect(contactHref({ type: 'phone', value })).toBeNull();
  });

  it('цепочка formatPhoneInput → contactHref даёт корректный tel:', () => {
    const stored = formatPhoneInput('9491234567');
    expect(stored).toBe('+7 (949) 123-45-67');
    expect(contactHref({ type: 'phone', value: stored })).toBe('tel:+79491234567');
    expect(telDigits(formatPhoneInput('89491234567'))).toBe('+79491234567');
  });

  it('пустой элемент не падает', () => {
    expect(contactHref(null)).toBeNull();
    expect(contactHref({})).toBeNull();
  });
});
