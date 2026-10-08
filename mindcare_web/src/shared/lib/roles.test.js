import {
  normalizeRoles, primaryRole, selectableRoles, roleLabel,
  ROLE_PRIORITY, ROLE_LABELS, ROLE_BADGE_TONES,
} from './roles';

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

describe('selectableRoles', () => {
  test('staff: student скрыт, если есть другие роли', () => {
    expect(selectableRoles({ roles: ['admin', 'student'] })).toEqual(['admin']);
    expect(selectableRoles({ roles: ['student', 'psychologist', 'supervisor'] }))
      .toEqual(['supervisor', 'psychologist']);
  });

  test('чистый студент: student остаётся', () => {
    expect(selectableRoles({ roles: ['student'] })).toEqual(['student']);
    expect(selectableRoles({ role: 'student' })).toEqual(['student']);
  });

  test('пустой набор — пустой список', () => {
    expect(selectableRoles({ roles: [] })).toEqual([]);
    expect(selectableRoles(null)).toEqual([]);
  });
});

test('ROLE_PRIORITY order', () => {
  expect(ROLE_PRIORITY).toEqual(['admin', 'supervisor', 'psychologist', 'student']);
});

describe('подписи ролей (единая карта)', () => {
  test('student подписан «Пользователь», подписи остальных ролей прежние', () => {
    expect(ROLE_LABELS).toEqual({
      student: 'Пользователь',
      psychologist: 'Психолог',
      supervisor: 'Супервизор',
      admin: 'Администратор',
    });
  });

  test('код роли, приоритет и тон badge не зависят от подписи', () => {
    ROLE_PRIORITY.forEach((r) => {
      expect(typeof ROLE_LABELS[r]).toBe('string');
      expect(ROLE_BADGE_TONES[r]).toBe(`role-${r}`);
    });
    expect(normalizeRoles({ roles: ['student'] })).toEqual(['student']);
    expect(primaryRole(['student'])).toBe('student');
  });

  test('roleLabel: известная роль → подпись, неизвестная → как есть, пусто → пустая строка', () => {
    expect(roleLabel('student')).toBe('Пользователь');
    expect(roleLabel('admin')).toBe('Администратор');
    expect(roleLabel('wizard')).toBe('wizard');
    expect(roleLabel(undefined)).toBe('');
    expect(roleLabel(null)).toBe('');
  });
});
