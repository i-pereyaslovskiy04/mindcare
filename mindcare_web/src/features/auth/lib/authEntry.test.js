import {
  authEntryState, authRequestFrom, DEFAULT_MESSAGE_TONE, safeMessageTone,
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
