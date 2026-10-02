import {
  FRAGMENT_ERROR_MESSAGES,
  GENERIC_ERROR_MESSAGE,
  INVALID_LINK_MESSAGE,
  completeErrorMessage,
  fragmentMessage,
  isSafeAuthorizeUrl,
  parseCallbackFragment,
  scrubCallbackFragment,
  startErrorMessage,
} from './oauthCallback';

describe('parseCallbackFragment', () => {
  test('успех: result=login + валидный ticket', () => {
    expect(parseCallbackFragment('#result=login&ticket=abc_DEF-123'))
      .toEqual({ kind: 'login', ticket: 'abc_DEF-123' });
  });

  test.each(Object.keys(FRAGMENT_ERROR_MESSAGES))('известная ошибка %s', (code) => {
    expect(parseCallbackFragment(`#error=${code}`)).toEqual({ kind: 'error', code });
  });

  test('неизвестная ошибка → code=null (сырой код не сохраняется)', () => {
    expect(parseCallbackFragment('#error=toString')).toEqual({ kind: 'error', code: null });
    expect(parseCallbackFragment('#error=x<script>')).toEqual({ kind: 'error', code: null });
  });

  test('ошибка важнее ticket', () => {
    expect(parseCallbackFragment('#error=oauth_failed&result=login&ticket=abc'))
      .toEqual({ kind: 'error', code: 'oauth_failed' });
  });

  test.each([
    '', '#', '#result=login', '#ticket=abc', '#result=other&ticket=abc',
    '#result=login&ticket=', '#result=login&ticket=has space',
    '#result=login&ticket=a%2Fb', `#result=login&ticket=${'x'.repeat(129)}`,
    null, undefined, 42,
  ])('не по контракту → invalid (%p)', (hash) => {
    expect(parseCallbackFragment(hash)).toEqual({ kind: 'invalid' });
  });

  test('лишние поля (next/redirect) не читаются', () => {
    const parsed = parseCallbackFragment('#result=login&ticket=abc&next=https://evil.example');
    expect(parsed).toEqual({ kind: 'login', ticket: 'abc' });
  });
});

describe('scrubCallbackFragment', () => {
  test('убирает fragment, сохраняет путь, query и state истории', () => {
    const state = { key: 'k1' };
    const win = {
      location: { pathname: '/auth/callback', search: '?a=1' },
      history: { state, replaceState: jest.fn() },
    };
    scrubCallbackFragment(win);
    expect(win.history.replaceState).toHaveBeenCalledWith(state, '', '/auth/callback?a=1');
  });
});

describe('сообщения', () => {
  test('fragmentMessage', () => {
    expect(fragmentMessage({ kind: 'error', code: 'oauth_cancelled' }))
      .toBe('Вход через Яндекс отменён.');
    expect(fragmentMessage({ kind: 'error', code: null })).toBe(GENERIC_ERROR_MESSAGE);
    expect(fragmentMessage({ kind: 'invalid' })).toBe(INVALID_LINK_MESSAGE);
  });

  test('completeErrorMessage не пропускает текст сервера', () => {
    expect(completeErrorMessage({ status: 400, code: 'oauth_ticket_invalid', message: 'RAW' }))
      .toBe('Ссылка для входа устарела или уже использована. Начните вход заново.');
    expect(completeErrorMessage({ status: 400, code: 'hasOwnProperty' })).toBe(GENERIC_ERROR_MESSAGE);
    expect(completeErrorMessage(new Error('RAW'))).toBe(GENERIC_ERROR_MESSAGE);
    expect(completeErrorMessage(undefined)).toBe(GENERIC_ERROR_MESSAGE);
  });

  test('startErrorMessage', () => {
    expect(startErrorMessage({ status: 429 })).toBe('Слишком много попыток. Попробуйте немного позже.');
    expect(startErrorMessage({ status: 404, code: 'oauth_provider_unavailable' }))
      .toBe('Вход через Яндекс сейчас недоступен. Войдите по email и паролю.');
    expect(startErrorMessage(new Error('RAW internal')))
      .toBe('Не удалось начать вход через Яндекс. Попробуйте ещё раз.');
  });
});

// Собирается из частей: литерал script-URL в исходнике запрещён линтером.
const SCRIPT_URL = ['javascript', 'alert(1)'].join(':');

describe('isSafeAuthorizeUrl', () => {
  test.each([
    ['https://oauth.yandex.ru/authorize?x=1', true],
    ['http://oauth.yandex.ru/authorize', false],
    [SCRIPT_URL, false],
    ['//evil.example/x', false],
    ['/relative', false],
    ['', false],
    [null, false],
  ])('%p → %p', (url, expected) => {
    expect(isSafeAuthorizeUrl(url)).toBe(expected);
  });
});
