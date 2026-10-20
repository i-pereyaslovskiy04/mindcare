import { deactivateUser, restoreUser, updateUser } from './users.api';
import { apiFetch } from './client';

jest.mock('./client');

beforeEach(() => {
  apiFetch.mockResolvedValue({});
});

describe('updateUser — PATCH allowlist', () => {
  test('passes role and legal basis fields, drops unknown fields (Stage 31n)', () => {
    updateUser('u1', {
      full_name: 'A',
      phone: 'p',
      is_active: true,
      role: 'psychologist',
      legal_basis_confirmed: true,
      basis_type: 'employment',
      basis_reference: 'приказ №5',
      legal_basis_comment: 'комментарий',
      junk: 1,                // случайное поле — отбрасывается
    });
    expect(apiFetch).toHaveBeenCalledTimes(1);
    const [url, opts] = apiFetch.mock.calls[0];
    expect(url).toBe('/api/admin/users/u1');
    expect(opts.method).toBe('PATCH');
    expect(JSON.parse(opts.body)).toEqual({
      full_name: 'A',
      phone: 'p',
      role: 'psychologist',
      legal_basis_confirmed: true,
      basis_type: 'employment',
      basis_reference: 'приказ №5',
      legal_basis_comment: 'комментарий',
    });
    expect(JSON.parse(opts.body)).not.toHaveProperty('junk');
  });

  test('sends only provided editable fields (no role when omitted)', () => {
    updateUser('u2', { full_name: 'B' });
    const [, opts] = apiFetch.mock.calls[0];
    expect(JSON.parse(opts.body)).toEqual({ full_name: 'B' });
  });

  test('still filters unknown fields when no role/legal basis given', () => {
    updateUser('u3', { full_name: 'C', phone: 'x', is_active: false, junk: 2 });
    const [, opts] = apiFetch.mock.calls[0];
    expect(JSON.parse(opts.body)).toEqual({
      full_name: 'C',
      phone: 'x',
    });
  });

  test('ADR-028: is_active is never sent through PATCH', () => {
    updateUser('u4', { full_name: 'D', is_active: false });
    const [, opts] = apiFetch.mock.calls[0];
    expect(JSON.parse(opts.body)).not.toHaveProperty('is_active');
  });
});

describe('lifecycle (ADR-028)', () => {
  test('deactivateUser posts the reason to /deactivate', () => {
    deactivateUser('u5', 'Причина');
    const [url, opts] = apiFetch.mock.calls[0];
    expect(url).toBe('/api/admin/users/u5/deactivate');
    expect(opts.method).toBe('POST');
    expect(JSON.parse(opts.body)).toEqual({ reason: 'Причина' });
  });

  test('restoreUser posts to /restore without a body', () => {
    restoreUser('u6');
    const [url, opts] = apiFetch.mock.calls[0];
    expect(url).toBe('/api/admin/users/u6/restore');
    expect(opts).toEqual({ method: 'POST' });
  });
});
