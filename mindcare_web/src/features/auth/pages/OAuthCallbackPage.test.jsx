/**
 * /auth/callback — технический маршрут: вход известной identity завершается
 * здесь же (→ /dashboard), ticket регистрации передаётся в память приложения
 * (AuthContext) и страница уходит на главную, терминальные ошибки уходят на
 * главную с сообщением. Экранов регистрации (шаг email, шаг кода) и своей
 * карточки у маршрута нет — они в AuthModal
 * (см. ui/SocialRegistrationFlow.test.jsx и socialRegistration.integration.test.jsx).
 */
import fs from 'fs';
import path from 'path';
import { StrictMode } from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import OAuthCallbackPage, { PHASE } from './OAuthCallbackPage';
import * as AuthContext from '../AuthContext';
import * as authApi from '../../../api/auth.api';

const mockNavigate = jest.fn();
jest.mock('react-router-dom', () => ({
  useNavigate: () => mockNavigate,
  Link: ({ to, children, ...rest }) => <a href={to} {...rest}>{children}</a>,
}), { virtual: true });
jest.mock('../AuthContext', () => ({ useAuth: jest.fn() }));
// Маршрут сам в сеть не ходит: любые вызовы регистрации здесь — ошибка.
jest.mock('../../../api/auth.api', () => ({
  oauthRegistrationInit: jest.fn(),
  oauthRegistrationPreview: jest.fn(),
  oauthRegistrationConfirm: jest.fn(),
}));

const TICKET = 'tkt_SYNTHETIC_0123456789abcdefghij';
const REG_TICKET = 'tkt_REG_SYNTHETIC_zyxwvutsrqponmlk';

const MSG = Object.freeze({
  disabled: 'Доступ к аккаунту сейчас недоступен. Обратитесь к администратору.',
  notAllowed: 'Вход через Яндекс для этой учётной записи недоступен.',
  ticketGone: 'Ссылка для входа устарела или уже использована. Начните вход заново.',
  tooMany: 'Слишком много попыток. Попробуйте немного позже.',
  loginFailed: 'Не удалось выполнить вход. Попробуйте ещё раз.',
  cancelled: 'Вход через Яндекс отменён.',
  providerFailed: 'Не удалось выполнить вход через Яндекс. Попробуйте ещё раз.',
  invalidLink: 'Ссылка для входа недействительна. Начните вход заново.',
});

/**
 * Терминальная ошибка callback: ровно один replace-переход на главную, где
 * AuthModal открывается на «Входе» с этим сообщением и тоном. Своей карточки
 * ошибки у callback нет: ни alert, ни ссылки «Вернуться ко входу».
 */
function expectCanonicalModalError(message, messageTone) {
  expect(mockNavigate).toHaveBeenCalledTimes(1);
  expect(mockNavigate).toHaveBeenCalledWith('/', {
    replace: true,
    state: { openAuth: 'login', message, messageTone },
  });
  expect(screen.queryByRole('alert')).toBeNull();
  expect(screen.queryByRole('link', { name: 'Вернуться ко входу' })).toBeNull();
  expect(screen.queryByText(message)).toBeNull();
  expect(beginSocialRegistration).not.toHaveBeenCalled();
}

/** В router state — только фиксированный текст, без ticket и деталей сервера. */
function expectNoLeakInNavigation(...secrets) {
  const blob = JSON.stringify(mockNavigate.mock.calls);
  for (const secret of [TICKET, REG_TICKET, ...secrets]) expect(blob).not.toContain(secret);
}

/** Ни шага email, ни шага кода, ни сетевых вызовов регистрации. */
function expectNoRegistrationUi() {
  expect(screen.queryByRole('heading')).toBeNull();
  expect(screen.queryByRole('group', { name: 'Код подтверждения' })).toBeNull();
  expect(screen.queryByRole('textbox')).toBeNull();
  expect(screen.queryByRole('button')).toBeNull();
  expect(screen.queryByRole('checkbox')).toBeNull();
  expect(authApi.oauthRegistrationInit).not.toHaveBeenCalled();
  expect(authApi.oauthRegistrationPreview).not.toHaveBeenCalled();
  expect(authApi.oauthRegistrationConfirm).not.toHaveBeenCalled();
}

const events = [];
let completeOAuthLogin;
let beginSocialRegistration;
let replaceSpy;

function setUrl(hash) {
  window.history.replaceState(null, '', `/auth/callback${hash}`);
}

function mockAuth(over = {}) {
  AuthContext.useAuth.mockReturnValue({
    completeOAuthLogin, beginSocialRegistration, loading: false, ...over,
  });
}

beforeEach(() => {
  jest.clearAllMocks();
  sessionStorage.clear();
  localStorage.clear();
  events.length = 0;
  completeOAuthLogin = jest.fn(() => {
    events.push(`complete:${window.location.hash === '' ? 'scrubbed' : 'dirty'}`);
    return Promise.resolve({ roles: ['student'] });
  });
  beginSocialRegistration = jest.fn(() => {
    events.push(`handoff:${window.location.hash === '' ? 'scrubbed' : 'dirty'}`);
  });
  mockNavigate.mockImplementation((to) => { events.push(`navigate:${to}`); });
  mockAuth();
});

afterEach(() => {
  replaceSpy?.mockRestore();
  replaceSpy = undefined;
  window.history.replaceState(null, '', '/');
});

function spyReplace() {
  const original = window.history.replaceState.bind(window.history);
  replaceSpy = jest.spyOn(window.history, 'replaceState').mockImplementation((...args) => {
    events.push('scrub');
    return original(...args);
  });
}

/**
 * Пишет КАЖДОЕ состояние DOM с момента первого коммита: появлялись ли шаг
 * кода, шаг email и какой статус был виден. MutationObserver ловит даже
 * кратковременную вставку узлов («вспышку»).
 */
function recordDom() {
  const seen = [];
  const snapshot = () => {
    seen.push({
      otp: screen.queryByLabelText('Цифра 1') !== null
        || screen.queryByText('Подтверждение регистрации') !== null,
      email: screen.queryByText('Почта для регистрации') !== null
        || screen.queryByRole('textbox') !== null,
      status: screen.queryByRole('status')?.textContent ?? '',
    });
  };
  const observer = new MutationObserver(snapshot);
  observer.observe(document.body, { subtree: true, childList: true, characterData: true });
  return { seen, snapshot, stop: () => observer.disconnect() };
}

// ── вход известной identity ──────────────────────────────────────────────────

test('fragment вычищается ДО обмена ticket, complete ровно один', async () => {
  setUrl(`#result=login&ticket=${TICKET}`);
  spyReplace();
  render(<OAuthCallbackPage />);

  await waitFor(() => expect(completeOAuthLogin).toHaveBeenCalledTimes(1));
  expect(completeOAuthLogin).toHaveBeenCalledWith(TICKET);
  expect(events.slice(0, 2)).toEqual(['scrub', 'complete:scrubbed']);
  expect(window.location.hash).toBe('');
  expect(window.location.pathname).toBe('/auth/callback');
});

test('успех → replace-переход на /dashboard (не на кабинет напрямую)', async () => {
  setUrl(`#result=login&ticket=${TICKET}`);
  render(<OAuthCallbackPage />);
  await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/dashboard', { replace: true }));
  expect(mockNavigate).toHaveBeenCalledTimes(1);
  expect(beginSocialRegistration).not.toHaveBeenCalled();
});

test('пока идёт обмен — статус «Выполняем вход через Яндекс…», ticket не в DOM', async () => {
  setUrl(`#result=login&ticket=${TICKET}`);
  completeOAuthLogin.mockReturnValue(new Promise(() => {}));
  const { container } = render(<OAuthCallbackPage />);
  expect(screen.getByRole('status')).toHaveTextContent('Выполняем вход через Яндекс…');
  await waitFor(() => expect(completeOAuthLogin).toHaveBeenCalled());
  expect(container.innerHTML).not.toContain(TICKET);
  expect(window.location.href).not.toContain(TICKET);
});

test('React StrictMode: один ticket → ровно ОДИН complete', async () => {
  setUrl(`#result=login&ticket=${TICKET}`);
  render(<StrictMode><OAuthCallbackPage /></StrictMode>);
  await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/dashboard', { replace: true }));
  expect(completeOAuthLogin).toHaveBeenCalledTimes(1);
  expect(mockNavigate).toHaveBeenCalledTimes(1);
  expect(screen.queryByRole('alert')).toBeNull();
});

test('обмен ждёт восстановления сессии AuthContext, но fragment вычищен сразу', async () => {
  setUrl(`#result=login&ticket=${TICKET}`);
  mockAuth({ loading: true });
  const { rerender } = render(<OAuthCallbackPage />);
  expect(window.location.hash).toBe('');
  expect(completeOAuthLogin).not.toHaveBeenCalled();

  mockAuth({ loading: false });
  rerender(<OAuthCallbackPage />);
  await waitFor(() => expect(completeOAuthLogin).toHaveBeenCalledTimes(1));
  expect(completeOAuthLogin).toHaveBeenCalledWith(TICKET);

  rerender(<OAuthCallbackPage />);
  expect(completeOAuthLogin).toHaveBeenCalledTimes(1);
});

test('адрес перехода из fragment игнорируется', async () => {
  setUrl(`#result=login&ticket=${TICKET}&next=https://evil.example/&redirect=/admin`);
  render(<OAuthCallbackPage />);
  await waitFor(() => expect(mockNavigate).toHaveBeenCalled());
  expect(mockNavigate).toHaveBeenCalledWith('/dashboard', { replace: true });
  expect(window.location.hash).toBe('');
});

test.each([
  ['обычный режим', (ui) => ui],
  ['StrictMode', (ui) => <StrictMode>{ui}</StrictMode>],
])('result=login (%s): ни шаг кода, ни шаг email не появляются ни на один кадр', async (_, wrap) => {
  setUrl(`#result=login&ticket=${TICKET}`);
  let resolveLogin;
  completeOAuthLogin.mockReturnValue(new Promise((r) => { resolveLogin = r; }));
  const dom = recordDom();

  render(wrap(<OAuthCallbackPage />));
  dom.snapshot();
  expect(screen.getByRole('status')).toHaveTextContent('Выполняем вход через Яндекс…');
  await waitFor(() => expect(completeOAuthLogin).toHaveBeenCalledTimes(1));
  await act(async () => { resolveLogin({ roles: ['student'] }); });
  await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/dashboard', { replace: true }));
  dom.snapshot();
  dom.stop();

  expect(dom.seen.length).toBeGreaterThan(1);
  expect(dom.seen.some((s) => s.otp || s.email)).toBe(false);
  expect(dom.seen.some((s) => /Отправляем код|Готовим регистрацию/.test(s.status))).toBe(false);
  expectNoRegistrationUi();
  expect(beginSocialRegistration).not.toHaveBeenCalled();   // продолжения в модалке не будет
  expect(completeOAuthLogin).toHaveBeenCalledTimes(1);
  expect(completeOAuthLogin).toHaveBeenCalledWith(TICKET);
  expect(mockNavigate).toHaveBeenCalledTimes(1);
});

// ── терминальные ошибки → главная + AuthModal (не карточка callback) ─────────

test.each([
  ['аккаунт отключён', { status: 403, code: 'account_unavailable' }, MSG.disabled],
  ['не чистый студент', { status: 403, code: 'social_login_not_allowed' }, MSG.notAllowed],
  ['ticket истёк/использован', { status: 400, code: 'oauth_ticket_invalid' }, MSG.ticketGone],
  ['лимит', { status: 429 }, MSG.tooMany],
  ['сбой сервера', { status: 500 }, MSG.loginFailed],
])('ошибка complete (%s) → AuthModal «Вход», тон error', async (_, errProps, message) => {
  setUrl(`#result=login&ticket=${TICKET}`);
  completeOAuthLogin.mockRejectedValue(
    Object.assign(new Error('RAW server detail SECRET'), errProps),
  );
  render(<OAuthCallbackPage />);

  await waitFor(() => expect(mockNavigate).toHaveBeenCalled());
  expectCanonicalModalError(message, 'error');
  expectNoLeakInNavigation('RAW server detail', 'SECRET');
  expectNoRegistrationUi();
});

test.each([
  ['account_unavailable', MSG.disabled, 'error'],
  ['social_login_not_allowed', MSG.notAllowed, 'error'],
  ['oauth_failed', MSG.providerFailed, 'error'],
  ['oauth_email_required',
    'Яндекс ID не передал адрес электронной почты, поэтому зарегистрироваться '
    + 'через Яндекс не получится. Зарегистрируйтесь по email и паролю.', 'error'],
  ['social_registration_not_available',
    'Аккаунт Яндекс пока не привязан к MindCare. '
    + 'Вход через Яндекс доступен только для уже связанных аккаунтов.', 'error'],
  ['oauth_cancelled', MSG.cancelled, 'info'],
])('#error=%s → AuthModal «Вход» (тон %s), fragment вычищен', (code, message, tone) => {
  setUrl(`#error=${code}`);
  spyReplace();
  render(<OAuthCallbackPage />);

  expect(events[0]).toBe('scrub');
  expect(window.location.hash).toBe('');
  expectCanonicalModalError(message, tone);
  expect(completeOAuthLogin).not.toHaveBeenCalled();
  expectNoRegistrationUi();
});

test('ошибка провайдера: текст провайдера во fragment не попадает в сообщение', () => {
  setUrl('#error=oauth_failed&error_description=RAW%20provider%20detail');
  render(<OAuthCallbackPage />);
  expectCanonicalModalError(MSG.providerFailed, 'error');
  expectNoLeakInNavigation('RAW provider detail', 'error_description');
});

test('неизвестный код ошибки не показывается — общее сообщение', () => {
  setUrl('#error=evil_<b>code</b>');
  render(<OAuthCallbackPage />);
  expectCanonicalModalError(MSG.loginFailed, 'error');
  expectNoLeakInNavigation('evil');
});

test.each([
  ['без fragment', ''],
  ['мусорный fragment', '#result=login&ticket=bad ticket!'],
  ['неизвестный шаг регистрации', `#result=registration&ticket=${REG_TICKET}&step=password`],
  ['шаг у входа', `#result=login&ticket=${TICKET}&step=email`],
])('недействительная ссылка (%s) → AuthModal «Вход», ничего не вызывается', (_, hash) => {
  setUrl(hash);
  render(<OAuthCallbackPage />);
  expectCanonicalModalError(MSG.invalidLink, 'error');
  expectNoLeakInNavigation();
  expect(completeOAuthLogin).not.toHaveBeenCalled();
  expectNoRegistrationUi();
});

test('StrictMode: терминальная ошибка — ровно один переход на главную', () => {
  setUrl('#error=account_unavailable');
  render(<StrictMode><OAuthCallbackPage /></StrictMode>);
  expectCanonicalModalError(MSG.disabled, 'error');
});

// ── регистрация: техническая передача на главную (AuthModal) ────────────────

/**
 * Ровно одна передача ticket в память приложения и ровно один replace на `/`
 * БЕЗ router state. Больше ничего маршрут не делает.
 */
function expectHandoff(continuation) {
  expect(beginSocialRegistration).toHaveBeenCalledTimes(1);
  expect(beginSocialRegistration).toHaveBeenCalledWith(continuation);
  expect(mockNavigate).toHaveBeenCalledTimes(1);
  expect(mockNavigate).toHaveBeenCalledWith('/', { replace: true });
  expect(completeOAuthLogin).not.toHaveBeenCalled();
  expectNoRegistrationUi();
}

describe('регистрация: передача ticket главной', () => {
  test('новая VK identity (#result=registration&step=email) → память приложения → replace на `/`', () => {
    sessionStorage.setItem('mindcare_oauth_provider', 'vk');
    setUrl(`#result=registration&ticket=${REG_TICKET}&step=email`);
    spyReplace();
    const dom = recordDom();
    const { container } = render(<OAuthCallbackPage />);
    dom.snapshot();
    dom.stop();

    expectHandoff({ ticket: REG_TICKET, provider: 'vk', emailStep: true });
    // Сначала вычищен fragment, потом передача, потом переход.
    expect(events).toEqual(['scrub', 'handoff:scrubbed', 'navigate:/']);
    expect(window.location.hash).toBe('');
    // Самого шага email на /auth/callback нет ни на один кадр.
    expect(dom.seen.some((s) => s.email || s.otp)).toBe(false);
    expect(dom.seen.some((s) => s.status !== '')).toBe(false);
    expect(container.innerHTML).not.toContain(REG_TICKET);
  });

  test('Яндекс (#result=registration без step) → та же передача, emailStep=false', () => {
    setUrl(`#result=registration&ticket=${REG_TICKET}`);
    spyReplace();
    const dom = recordDom();
    render(<OAuthCallbackPage />);
    dom.snapshot();
    dom.stop();

    expectHandoff({ ticket: REG_TICKET, provider: 'yandex', emailStep: false });
    expect(events).toEqual(['scrub', 'handoff:scrubbed', 'navigate:/']);
    // Код здесь не отправляется и шаг кода не рисуется — это делает AuthModal.
    expect(dom.seen.some((s) => s.email || s.otp)).toBe(false);
  });

  test.each([
    ['VK', '&step=email', { emailStep: true }],
    ['Яндекс', '', { emailStep: false }],
  ])('StrictMode (%s): одна передача и один переход', (_, step, expected) => {
    setUrl(`#result=registration&ticket=${REG_TICKET}${step}`);
    render(<StrictMode><OAuthCallbackPage /></StrictMode>);
    expectHandoff({ ticket: REG_TICKET, provider: 'yandex', ...expected });
  });

  test('ticket не попадает в URL, router state, storage и DOM', () => {
    const setItem = jest.spyOn(Storage.prototype, 'setItem');
    setUrl(`#result=registration&ticket=${REG_TICKET}&step=email`);
    const { container } = render(<OAuthCallbackPage />);

    expect(beginSocialRegistration).toHaveBeenCalledTimes(1);
    expect(mockNavigate).toHaveBeenCalledWith('/', { replace: true });   // без state
    expectNoLeakInNavigation();
    expect(window.location.href).not.toContain(REG_TICKET);
    expect(JSON.stringify(window.history.state ?? null)).not.toContain(REG_TICKET);
    expect(setItem).not.toHaveBeenCalled();
    expect(JSON.stringify({ ...localStorage, ...sessionStorage })).not.toContain(REG_TICKET);
    expect(container.innerHTML).not.toContain(REG_TICKET);
    setItem.mockRestore();
  });

  test('передача не ждёт восстановления сессии и не повторяется при перерисовке', () => {
    setUrl(`#result=registration&ticket=${REG_TICKET}&step=email`);
    mockAuth({ loading: true });
    const { rerender } = render(<OAuthCallbackPage />);
    expect(beginSocialRegistration).toHaveBeenCalledTimes(1);

    mockAuth({ loading: false });
    rerender(<OAuthCallbackPage />);
    rerender(<OAuthCallbackPage />);
    expect(beginSocialRegistration).toHaveBeenCalledTimes(1);
    expect(mockNavigate).toHaveBeenCalledTimes(1);
  });

  test('адрес перехода из fragment игнорируется — только `/`', () => {
    setUrl(`#result=registration&ticket=${REG_TICKET}&step=email&next=https://evil.example/`);
    render(<OAuthCallbackPage />);
    expect(mockNavigate).toHaveBeenCalledTimes(1);
    expect(mockNavigate).toHaveBeenCalledWith('/', { replace: true });
  });
});

// ── VK ID: тексты входа и ошибок ─────────────────────────────────────────────

describe('VK ID', () => {
  beforeEach(() => { sessionStorage.setItem('mindcare_oauth_provider', 'vk'); });

  test('известная VK identity: статус про VK → /dashboard, без email и кода', async () => {
    setUrl(`#result=login&ticket=${TICKET}`);
    let resolveLogin;
    completeOAuthLogin.mockReturnValue(new Promise((r) => { resolveLogin = r; }));
    const dom = recordDom();
    render(<OAuthCallbackPage />);
    dom.snapshot();

    expect(screen.getByRole('status')).toHaveTextContent('Выполняем вход через VK…');
    await waitFor(() => expect(completeOAuthLogin).toHaveBeenCalledTimes(1));
    await act(async () => { resolveLogin({ roles: ['student'] }); });
    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/dashboard', { replace: true }));
    dom.stop();

    expect(mockNavigate).toHaveBeenCalledTimes(1);
    expect(beginSocialRegistration).not.toHaveBeenCalled();
    expect(dom.seen.some((s) => s.email || s.otp)).toBe(false);
    expectNoRegistrationUi();
  });

  test('fallback: код «регистрации нет» по-прежнему даёт AuthModal «Вход» с текстом про VK', () => {
    setUrl('#error=social_registration_not_available');
    render(<OAuthCallbackPage />);
    expectCanonicalModalError(
      'Аккаунт VK пока не привязан к MindCare. '
      + 'Вход через VK доступен только для уже связанных аккаунтов.',
      'error',
    );
    expect(completeOAuthLogin).not.toHaveBeenCalled();
  });

  test('отмена на странице VK → текст про VK, тон info', () => {
    setUrl('#error=oauth_cancelled');
    render(<OAuthCallbackPage />);
    expectCanonicalModalError('Вход через VK отменён.', 'info');
  });

  test('страница callback ничего не пишет в storage', async () => {
    const setItem = jest.spyOn(Storage.prototype, 'setItem');
    setUrl(`#result=login&ticket=${TICKET}`);
    render(<OAuthCallbackPage />);
    await waitFor(() => expect(mockNavigate).toHaveBeenCalled());
    expect(setItem).not.toHaveBeenCalled();
    setItem.mockRestore();
  });
});

test('без запомненного провайдера тексты остаются про Яндекс', () => {
  sessionStorage.clear();
  setUrl('#error=oauth_cancelled');
  render(<OAuthCallbackPage />);
  expectCanonicalModalError('Вход через Яндекс отменён.', 'info');
});

// ── технический маршрут: ни карточки, ни форм, ни своих шагов ───────────────

describe('у /auth/callback нет своей карточки и экранов регистрации', () => {
  const read = (file) => fs.readFileSync(path.join(__dirname, file), 'utf8');

  test.each([
    ['вход', `#result=login&ticket=${TICKET}`],
    ['регистрация VK', `#result=registration&ticket=${REG_TICKET}&step=email`],
    ['регистрация Яндекс', `#result=registration&ticket=${REG_TICKET}`],
    ['ошибка', '#error=oauth_failed'],
  ])('%s: в DOM только нейтральная страница (и статус входа)', (_, hash) => {
    completeOAuthLogin.mockReturnValue(new Promise(() => {}));
    setUrl(hash);
    const { container } = render(<OAuthCallbackPage />);

    // eslint-disable-next-line testing-library/no-container, testing-library/no-node-access
    const classes = [...container.querySelectorAll('[class]')].flatMap((el) => [...el.classList]);
    expect(new Set(classes)).toEqual(new Set(
      hash.includes('result=login') ? ['page', 'status'] : ['page'],
    ));
    expect(screen.queryByText('MindCare')).toBeNull();                 // шапки карточки нет
    expect(screen.queryByText('Психологическая служба ДонГУ')).toBeNull();
    expect(screen.queryByRole('dialog')).toBeNull();                   // и своей модалки тоже
    expect(screen.queryByRole('heading')).toBeNull();
    expect(screen.queryByRole('textbox')).toBeNull();
    expect(screen.queryByRole('button')).toBeNull();
  });

  test('стили маршрута: только страница и статус — классов карточки нет', () => {
    const css = read('OAuthCallbackPage.module.css');
    const selectors = [...css.matchAll(/^\s*\.([A-Za-z][\w-]*)/gm)].map((m) => m[1]);
    expect(new Set(selectors)).toEqual(new Set(['page', 'status']));
    expect(css).not.toMatch(/font-family/);
  });

  test('маршрут не подключает шаги регистрации, стили модалки и API регистрации', () => {
    const source = read('OAuthCallbackPage.jsx');
    const imports = source.match(/^import [\s\S]*?;$/gm).join('\n');
    expect(imports).not.toMatch(/SocialEmailStep|RegistrationOtpStep|SocialRegistrationFlow/);
    expect(imports).not.toMatch(/AuthModal/);
    expect(imports).not.toMatch(/auth\.api/);
  });

  test('фазы маршрута: шагов регистрации среди них нет', () => {
    expect(Object.values(PHASE).sort()).toEqual([
      'completed', 'error', 'loginCompleting', 'registrationHandoff', 'resolving',
    ]);
  });
});
