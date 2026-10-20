import {
  FRAGMENT_ERROR_MESSAGES,
  GENERIC_ERROR_MESSAGE,
  INVALID_LINK_MESSAGE,
  completeErrorMessage,
  fragmentMessage,
  isRegistrationTerminal,
  isSafeAuthorizeUrl,
  parseCallbackFragment,
  registrationErrorMessage,
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

describe('регистрация (Stage Social Auth 4)', () => {
  test('result=registration разбирается отдельно от login', () => {
    expect(parseCallbackFragment('#result=registration&ticket=abc_DEF-123'))
      .toEqual({ kind: 'registration', ticket: 'abc_DEF-123', emailStep: false });
    expect(parseCallbackFragment('#result=login&ticket=abc'))
      .toEqual({ kind: 'login', ticket: 'abc' });
  });

  test.each([
    '#result=registration', '#result=registration&ticket=', '#result=link&ticket=abc',
    '#result=REGISTRATION&ticket=abc', `#result=registration&ticket=${'x'.repeat(129)}`,
  ])('не по контракту → invalid (%p)', (hash) => {
    expect(parseCallbackFragment(hash)).toEqual({ kind: 'invalid' });
  });

  test('код oauth_email_required и legacy-код ошибки известны', () => {
    expect(parseCallbackFragment('#error=oauth_email_required'))
      .toEqual({ kind: 'error', code: 'oauth_email_required' });
    expect(parseCallbackFragment('#error=social_registration_not_available'))
      .toEqual({ kind: 'error', code: 'social_registration_not_available' });
  });

  test.each([
    [{ status: 409, code: 'email_already_exists', message: 'RAW' },
      'Аккаунт с таким email уже существует. Войдите по email и паролю.'],
    [{ status: 422, code: 'consent_required', message: 'RAW' },
      'Необходимо принять политику персональных данных.'],
    // Снятые в UX hotfix коды больше не имеют своего текста — общее сообщение.
    [{ status: 409, code: 'oauth_registration_data_mismatch', message: 'RAW' },
      'Не удалось завершить регистрацию. Попробуйте ещё раз.'],
    // VK-1B: отказ по домену — фиксированный текст backend (как у обычной регистрации).
    [{ status: 422, code: 'domain_not_allowed', message: 'Домен почты не разрешён.' },
      'Домен почты не разрешён.'],
    [{ status: 422, code: 'domain_not_allowed' },
      'Не удалось завершить регистрацию. Попробуйте ещё раз.'],
    [{ status: 422, code: 'email_required', message: 'RAW' }, 'Укажите адрес электронной почты.'],
    [{ status: 422, code: 'email_invalid', message: 'RAW' },
      'Введите корректный адрес электронной почты.'],
    [{ status: 400, code: 'otp_invalid', message: 'Неверный код. Осталось попыток: 2' },
      'Неверный код. Осталось попыток: 2'],
    [{ status: 429, code: 'otp_cooldown', message: 'Повторная отправка доступна через 30 с' },
      'Повторная отправка доступна через 30 с'],
    [{ status: 429 }, 'Слишком много попыток. Попробуйте немного позже.'],
    [{ status: 422, message: 'email: value is not a valid email address' },
      'Не удалось завершить регистрацию. Попробуйте ещё раз.'],
    [{ status: 500, code: 'unknown_future_code', message: 'RAW internal' },
      'Не удалось завершить регистрацию. Попробуйте ещё раз.'],
    [{ status: 400, code: 'otp_invalid' }, 'Не удалось завершить регистрацию. Попробуйте ещё раз.'],
  ])('registrationErrorMessage(%j)', (err, expected) => {
    expect(registrationErrorMessage(err)).toBe(expected);
  });

  test('isRegistrationTerminal', () => {
    expect(isRegistrationTerminal({ code: 'oauth_ticket_invalid' })).toBe(true);
    expect(isRegistrationTerminal({ code: 'oauth_identity_already_linked' })).toBe(true);
    expect(isRegistrationTerminal({ code: 'otp_invalid' })).toBe(false);
    // email ticket неизменен (он из профиля Яндекса) — этот ticket уже не завершится.
    expect(isRegistrationTerminal({ code: 'email_already_exists' })).toBe(true);
    expect(isRegistrationTerminal({ code: 'consent_required' })).toBe(false);
    expect(isRegistrationTerminal(undefined)).toBe(false);
  });
});

describe('провайдер (Stage Social Auth VK-1A)', () => {
  const {
    DEFAULT_PROVIDER, PROVIDER_LABELS, completeErrorMessage: completeMsg,
    fragmentMessage: fragmentMsg, loginStatusMessage, providerLabel,
    recallOAuthProvider, rememberOAuthProvider, safeProvider, startErrorMessage: startMsg,
  } = jest.requireActual('./oauthCallback');

  const memoryStorage = () => {
    const data = new Map();
    return {
      setItem: (k, v) => data.set(k, String(v)),
      getItem: (k) => (data.has(k) ? data.get(k) : null),
      data,
    };
  };

  test('закрытый список провайдеров, иное → по умолчанию', () => {
    expect(PROVIDER_LABELS).toEqual({ yandex: 'Яндекс', vk: 'VK' });
    expect(DEFAULT_PROVIDER).toBe('yandex');
    expect(safeProvider('vk')).toBe('vk');
    for (const bad of ['telegram', '', null, undefined, 42, {}, '__proto__', 'constructor']) {
      expect(safeProvider(bad)).toBe('yandex');
    }
    expect(providerLabel('vk')).toBe('VK');
    expect(providerLabel('nope')).toBe('Яндекс');
  });

  test('remember/recall хранит только допустимое имя провайдера', () => {
    const storage = memoryStorage();
    expect(recallOAuthProvider(storage)).toBe('yandex');
    rememberOAuthProvider('vk', storage);
    expect([...storage.data.entries()]).toEqual([['mindcare_oauth_provider', 'vk']]);
    expect(recallOAuthProvider(storage)).toBe('vk');
    rememberOAuthProvider('https://evil.example/?ticket=1', storage);
    expect(recallOAuthProvider(storage)).toBe('yandex');
  });

  test('недоступный storage не ломает ни запись, ни чтение', () => {
    const broken = {
      setItem: () => { throw new Error('denied'); },
      getItem: () => { throw new Error('denied'); },
    };
    expect(() => rememberOAuthProvider('vk', broken)).not.toThrow();
    expect(recallOAuthProvider(broken)).toBe('yandex');
    expect(() => rememberOAuthProvider('vk', null)).not.toThrow();
    expect(recallOAuthProvider(null)).toBe('yandex');
  });

  test('тексты называют провайдера, через которого начат вход', () => {
    const cancelled = { kind: 'error', code: 'oauth_cancelled' };
    expect(fragmentMsg(cancelled, 'vk')).toBe('Вход через VK отменён.');
    expect(fragmentMsg(cancelled, 'yandex')).toBe('Вход через Яндекс отменён.');
    expect(fragmentMsg(cancelled)).toBe('Вход через Яндекс отменён.');   // по умолчанию
    expect(fragmentMsg({ kind: 'error', code: 'social_registration_not_available' }, 'vk')).toBe(
      'Аккаунт VK пока не привязан к MindCare. '
      + 'Вход через VK доступен только для уже связанных аккаунтов.',
    );
    expect(fragmentMsg({ kind: 'error', code: 'oauth_failed' }, 'vk'))
      .toBe('Не удалось выполнить вход через VK. Попробуйте ещё раз.');
    expect(completeMsg({ status: 403, code: 'social_login_not_allowed' }, 'vk'))
      .toBe('Вход через VK для этой учётной записи недоступен.');
    expect(completeMsg({ status: 403, code: 'account_unavailable' }, 'vk'))
      .toBe('Доступ к аккаунту сейчас недоступен. Обратитесь к администратору.');
    expect(startMsg({ status: 500 }, 'vk'))
      .toBe('Не удалось начать вход через VK. Попробуйте ещё раз.');
    expect(loginStatusMessage('vk')).toBe('Выполняем вход через VK…');
    expect(loginStatusMessage()).toBe('Выполняем вход через Яндекс…');
  });

  test('набор кодов fragment одинаков для всех провайдеров', () => {
    const codes = Object.keys(jest.requireActual('./oauthCallback').FRAGMENT_ERROR_MESSAGES);
    for (const code of codes) {
      expect(typeof fragmentMsg({ kind: 'error', code }, 'vk')).toBe('string');
    }
  });
});

describe('шаг email и исправимые ошибки (Stage Social Auth VK-1B)', () => {
  const lib = jest.requireActual('./oauthCallback');

  test('step=email помечает регистрацию с выбором адреса', () => {
    expect(lib.parseCallbackFragment('#result=registration&ticket=abc&step=email'))
      .toEqual({ kind: 'registration', ticket: 'abc', emailStep: true });
    expect(lib.parseCallbackFragment('#result=registration&ticket=abc'))
      .toEqual({ kind: 'registration', ticket: 'abc', emailStep: false });
  });

  test.each([
    '#result=registration&ticket=abc&step=otp',
    '#result=registration&ticket=abc&step=',
    '#result=registration&ticket=abc&step=EMAIL',
    '#result=login&ticket=abc&step=email',            // у входа шагов нет
  ])('неизвестный или неуместный step → invalid (%p)', (hash) => {
    expect(lib.parseCallbackFragment(hash)).toEqual({ kind: 'invalid' });
  });

  test('email провайдера из fragment не читается', () => {
    const parsed = lib.parseCallbackFragment(
      '#result=registration&ticket=abc&step=email&email=user%40vk.ru&name=Ivan',
    );
    expect(parsed).toEqual({ kind: 'registration', ticket: 'abc', emailStep: true });
    expect(JSON.stringify(parsed)).not.toContain('vk.ru');
  });

  test('занятый email: терминален при фиксированном адресе, исправим при выборе', () => {
    const taken = { code: 'email_already_exists' };
    expect(lib.isRegistrationTerminal(taken)).toBe(true);                       // Яндекс
    expect(lib.isRegistrationTerminal(taken, { emailEditable: false })).toBe(true);
    expect(lib.isRegistrationTerminal(taken, { emailEditable: true })).toBe(false);   // VK
    for (const code of ['oauth_ticket_invalid', 'oauth_identity_already_linked']) {
      expect(lib.isRegistrationTerminal({ code }, { emailEditable: true })).toBe(true);
    }
    for (const code of ['domain_not_allowed', 'email_required', 'email_invalid',
      'otp_invalid', 'otp_cooldown', 'rate_limited']) {
      expect(lib.isRegistrationTerminal({ code }, { emailEditable: true })).toBe(false);
    }
  });

  test('тексты регистрации называют провайдера', () => {
    expect(lib.registrationErrorMessage({ code: 'oauth_ticket_invalid' }, 'vk'))
      .toBe('Время на завершение регистрации истекло. Начните заново через VK.');
    expect(lib.registrationErrorMessage({ code: 'oauth_identity_already_linked' }, 'vk'))
      .toBe('Этот аккаунт VK уже привязан к MindCare. Нажмите «VK» ещё раз, чтобы войти.');
    expect(lib.registrationErrorMessage({ code: 'oauth_ticket_invalid' }))
      .toBe('Время на завершение регистрации истекло. Начните заново через Яндекс.');
    expect(lib.registrationErrorMessage({ code: 'email_already_exists' }, 'vk'))
      .toBe('Аккаунт с таким email уже существует. Войдите по email и паролю.');
  });
});
