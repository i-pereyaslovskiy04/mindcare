import {
  AUTH_TABS, authEntryState, authRequestFrom, DEFAULT_MESSAGE_TONE, registrationReferenceFrom,
  safeMessageTone,
} from './authEntry';
import { fragmentTone } from './oauthCallback';

test('тон — только info | error, иное → info', () => {
  expect(safeMessageTone('info')).toBe('info');
  expect(safeMessageTone('error')).toBe('error');
  for (const bad of ['warning', 'errorMessage', '', null, undefined, 42, {}]) {
    expect(safeMessageTone(bad)).toBe(DEFAULT_MESSAGE_TONE);
  }
});

test('authRequestFrom: вкладка, строковое сообщение, тон', () => {
  expect(authRequestFrom(null)).toBeNull();
  expect(authRequestFrom({ openAuth: 'admin', message: 'x' })).toBeNull();
  expect(authRequestFrom({ openAuth: 'register' }))
    .toEqual({ tab: 'register', message: '', messageTone: 'info' });
  expect(authRequestFrom({ openAuth: 'login', message: 'Текст', messageTone: 'error' }))
    .toEqual({ tab: 'login', message: 'Текст', messageTone: 'error' });
  expect(authRequestFrom({ openAuth: 'login', message: { html: '<b>' }, messageTone: 'error' }))
    .toEqual({ tab: 'login', message: '', messageTone: 'info' });
  expect(authRequestFrom({ openAuth: 'login', message: 'Текст', messageTone: 'x' }))
    .toEqual({ tab: 'login', message: 'Текст', messageTone: 'info' });
});

test('authEntryState: без сообщения — только openAuth; тон нормализуется', () => {
  expect(authEntryState('register')).toEqual({ openAuth: 'register' });
  expect(authEntryState('weird', 'Текст', 'error'))
    .toEqual({ openAuth: 'login', message: 'Текст', messageTone: 'error' });
  expect(authEntryState('login', 'Текст', 'bad'))
    .toEqual({ openAuth: 'login', message: 'Текст', messageTone: 'info' });
  expect(authEntryState('login', '', 'error')).toEqual({ openAuth: 'login' });
});

test('fragmentTone: отмена — info, остальное — error', () => {
  expect(fragmentTone({ kind: 'error', code: 'oauth_cancelled' })).toBe('info');
  expect(fragmentTone({ kind: 'error', code: 'account_unavailable' })).toBe('error');
  expect(fragmentTone({ kind: 'error', code: null })).toBe('error');
  expect(fragmentTone({ kind: 'invalid' })).toBe('error');
});

describe('шаг подтверждения регистрации (confirm)', () => {
  it('router state openAuth=confirm открывает шаг подтверждения', () => {
    expect(authRequestFrom({ openAuth: 'confirm' })).toEqual({
      tab: 'confirm', message: '', messageTone: 'info',
    });
  });

  it('authEntryState допускает confirm и по-прежнему отбрасывает неизвестное', () => {
    expect(authEntryState('confirm')).toEqual({ openAuth: 'confirm' });
    expect(authEntryState('admin')).toEqual({ openAuth: 'login' });
    expect(AUTH_TABS).toEqual(['login', 'register']);
  });
});

// ── reference продолжения регистрации из fragment ссылки ────────────────────

const REF = '8a62d590-71a1-4b17-90f7-4a5ff0c9d782';

test('registrationReferenceFrom: #r=<UUIDv4> → reference в нижнем регистре', () => {
  expect(registrationReferenceFrom(`#r=${REF}`)).toBe(REF);
  expect(registrationReferenceFrom(`r=${REF}`)).toBe(REF);
  expect(registrationReferenceFrom(`#r=${REF.toUpperCase()}`)).toBe(REF);
  expect(registrationReferenceFrom(`#x=1&r=${REF}`)).toBe(REF);
});

test('registrationReferenceFrom: иное → null', () => {
  for (const bad of [
    '', '#', '#r=', '#r=not-a-uuid', `#ref=${REF}`, `#r=${REF}x`,
    '#r=8a62d590-71a1-1b17-90f7-4a5ff0c9d782',          // не v4
    '#r=00000000-0000-0000-0000-000000000000',
    null, undefined, 42, {},
  ]) {
    expect(registrationReferenceFrom(bad)).toBeNull();
  }
});
