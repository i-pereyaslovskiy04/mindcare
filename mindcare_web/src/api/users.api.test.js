import { updateUser } from './users.api';
import { apiFetch } from './client';

jest.mock('./client');

beforeEach(() => {
  apiFetch.mockResolvedValue({});
});

describe('updateUser — PATCH allowlist', () => {
  test('omits role and unknown fields from PATCH body', () => {
    updateUser('u1', {
      full_name: 'A',
      phone: 'p',
      is_active: true,
      role: 'admin',          // не должно уходить на backend
      junk: 1,                // случайное поле — отбрасывается
    });
    expect(apiFetch).toHaveBeenCalledTimes(1);
    const [url, opts] = apiFetch.mock.calls[0];
    expect(url).toBe('/api/admin/users/u1');
    expect(opts.method).toBe('PATCH');
    expect(JSON.parse(opts.body)).toEqual({
      full_name: 'A',
      phone: 'p',
      is_active: true,
    });
  });

  test('sends only provided editable fields', () => {
    updateUser('u2', { full_name: 'B' });
    const [, opts] = apiFetch.mock.calls[0];
    expect(JSON.parse(opts.body)).toEqual({ full_name: 'B' });
  });
});
