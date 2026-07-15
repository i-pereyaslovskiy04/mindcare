import { normalizeRoles, primaryRole, ROLE_PRIORITY } from './roles';

describe('normalizeRoles', () => {
  test('explicit roles[] is source of truth (even empty)', () => {
    expect(normalizeRoles({ roles: [], role: 'psychologist' })).toEqual([]);
    expect(normalizeRoles({ roles: ['admin'], role: 'student' })).toEqual(['admin']);
  });

  test('legacy [role] fallback only when roles field is absent', () => {
    expect(normalizeRoles({ role: 'supervisor' })).toEqual(['supervisor']);
    expect(normalizeRoles({})).toEqual([]);
    expect(normalizeRoles(null)).toEqual([]);
  });

  test('dedupes, drops unknown roles, sorts by priority', () => {
    expect(
      normalizeRoles({ roles: ['psychologist', 'admin', 'psychologist', 'wizard'] }),
    ).toEqual(['admin', 'psychologist']);
    expect(normalizeRoles({ roles: ['student', 'supervisor', 'admin'] }))
      .toEqual(['admin', 'supervisor', 'student']);
  });
});

describe('primaryRole', () => {
  test('highest by priority, null when empty', () => {
    expect(primaryRole(['psychologist', 'supervisor'])).toBe('supervisor');
    expect(primaryRole(['student', 'admin'])).toBe('admin');
    expect(primaryRole([])).toBeNull();
  });

  test('accepts a user-like object', () => {
    expect(primaryRole({ roles: ['psychologist', 'admin'] })).toBe('admin');
  });
});

test('ROLE_PRIORITY order', () => {
  expect(ROLE_PRIORITY).toEqual(['admin', 'supervisor', 'psychologist', 'student']);
});
