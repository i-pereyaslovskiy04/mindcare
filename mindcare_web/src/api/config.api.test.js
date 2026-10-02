import { getPublicConfig, socialProvidersOf } from './config.api';
import { apiFetch } from './client';

jest.mock('./client');

test('getPublicConfig — GET /api/public/config через apiFetch', () => {
  apiFetch.mockResolvedValue({ social_providers: ['yandex'] });
  getPublicConfig();
  expect(apiFetch).toHaveBeenCalledWith('/api/public/config');
});

test.each([
  [{ social_providers: ['yandex'] }, ['yandex']],
  [{ social_providers: [] }, []],
  [{ social_providers: ['yandex', 42, null] }, ['yandex']],
  [{ social_providers: 'yandex' }, []],
  [{}, []],
  [null, []],
  [undefined, []],
])('socialProvidersOf(%j) → %j', (config, expected) => {
  expect(socialProvidersOf(config)).toEqual(expected);
});
