import { emailDomainNamesOf, getEmailDomains, getPublicEmailDomains } from './domains.api';
import { apiFetch } from './client';

jest.mock('./client');

test('getPublicEmailDomains — публичный GET /api/public/email-domains через apiFetch', () => {
  apiFetch.mockResolvedValue({ domains: ['a.example'] });
  getPublicEmailDomains();
  expect(apiFetch).toHaveBeenCalledTimes(1);
  // без метода, тела и заголовков — обычный GET без параметров
  expect(apiFetch).toHaveBeenCalledWith('/api/public/email-domains');
});

test('админский список остаётся на admin-пути: публичный endpoint его не подменяет', () => {
  apiFetch.mockResolvedValue([]);
  getEmailDomains();
  expect(apiFetch).toHaveBeenCalledWith('/api/admin/email-domains/');
});

test.each([
  [{ domains: ['a.example', 'b.example'] }, ['a.example', 'b.example']],
  [{ domains: [] }, []],
  [{ domains: ['a.example', 42, null, '', '   ', {}] }, ['a.example']],
  [{ domains: 'a.example' }, []],
  [{ domains: null }, []],
  [{}, []],
  [null, []],
  [undefined, []],
  [['a.example'], []],
])('emailDomainNamesOf(%j) → %j', (response, expected) => {
  expect(emailDomainNamesOf(response)).toEqual(expected);
});

test('emailDomainNamesOf берёт только поле domains: служебные поля игнорируются', () => {
  const response = { domains: ['a.example'], id: 7, comment: 'внутренний', items: ['x.example'] };
  expect(emailDomainNamesOf(response)).toEqual(['a.example']);
});
