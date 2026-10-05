import { StrictMode } from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import OAuthCallbackPage from './OAuthCallbackPage';
import * as AuthContext from '../AuthContext';
import * as authApi from '../../../api/auth.api';

const mockNavigate = jest.fn();
jest.mock('react-router-dom', () => ({
  useNavigate: () => mockNavigate,
  // state/replace Link'а выводятся в data-атрибуты — так тест видит, куда и с
  // каким router state ведёт ссылка.
  Link: ({ to, state, replace, children, ...rest }) => (
    <a href={to} data-state={JSON.stringify(state ?? null)} data-replace={String(!!replace)} {...rest}>
      {children}
    </a>
  ),
}), { virtual: true });
jest.mock('../AuthContext', () => ({ useAuth: jest.fn() }));
jest.mock('../../../api/auth.api', () => ({ oauthRegistrationInit: jest.fn() }));
// Шпион над НАСТОЯЩИМ общим шагом кода: считает монтирования, рендер не
// подменяется (реализация восстанавливается в beforeEach — CRA resetMocks).
jest.mock('../ui/RegistrationOtpStep', () => {
  const actual = jest.requireActual('../ui/RegistrationOtpStep');
  return { __esModule: true, ...actual, default: jest.fn() };
});
// eslint-disable-next-line import/first
import RegistrationOtpStep from '../ui/RegistrationOtpStep';

const ActualRegistrationOtpStep = jest.requireActual('../ui/RegistrationOtpStep').default;

const TICKET = 'tkt_SYNTHETIC_0123456789abcdefghij';

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
}

/** В router state — только фиксированный текст, без ticket и деталей сервера. */
function expectNoLeakInNavigation(...secrets) {
  const blob = JSON.stringify(mockNavigate.mock.calls);
  for (const secret of [TICKET, ...secrets]) expect(blob).not.toContain(secret);
}
const events = [];
let completeOAuthLogin;
let completeOAuthRegistration;
let replaceSpy;

function setUrl(hash) {
  window.history.replaceState(null, '', `/auth/callback${hash}`);
}

function mockAuth(over = {}) {
  AuthContext.useAuth.mockReturnValue({
    completeOAuthLogin, completeOAuthRegistration, loading: false, ...over,
  });
}

beforeEach(() => {
  jest.clearAllMocks();
  RegistrationOtpStep.mockImplementation(ActualRegistrationOtpStep);
  events.length = 0;
  completeOAuthLogin = jest.fn((ticket) => {
    events.push(`complete:${window.location.hash === '' ? 'scrubbed' : 'dirty'}`);
    return Promise.resolve({ roles: ['student'] });
  });
  completeOAuthRegistration = jest.fn().mockResolvedValue({ roles: ['student'] });
  authApi.oauthRegistrationInit.mockResolvedValue({ message: 'ok', email_masked: 'i***@yandex.ru' });
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

// ── успех ────────────────────────────────────────────────────────────────────

test('fragment вычищается ДО обмена ticket, complete ровно один', async () => {
  setUrl(`#result=login&ticket=${TICKET}`);
  spyReplace();
  render(<OAuthCallbackPage />);

  await waitFor(() => expect(completeOAuthLogin).toHaveBeenCalledTimes(1));
  expect(completeOAuthLogin).toHaveBeenCalledWith(TICKET);
  expect(events).toEqual(['scrub', 'complete:scrubbed']);
  expect(window.location.hash).toBe('');
  expect(window.location.pathname).toBe('/auth/callback');
});

test('успех → replace-переход на /dashboard (не на кабинет напрямую)', async () => {
  setUrl(`#result=login&ticket=${TICKET}`);
  render(<OAuthCallbackPage />);
  await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/dashboard', { replace: true }));
  expect(mockNavigate).toHaveBeenCalledTimes(1);
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
  expect(RegistrationOtpStep).not.toHaveBeenCalled();
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
  expect(authApi.oauthRegistrationInit).not.toHaveBeenCalled();
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
])('недействительная ссылка (%s) → AuthModal «Вход», ничего не вызывается', (_, hash) => {
  setUrl(hash);
  render(<OAuthCallbackPage />);
  expectCanonicalModalError(MSG.invalidLink, 'error');
  expect(completeOAuthLogin).not.toHaveBeenCalled();
  expect(authApi.oauthRegistrationInit).not.toHaveBeenCalled();
});

test('StrictMode: терминальная ошибка — ровно один переход на главную', () => {
  setUrl('#error=account_unavailable');
  render(<StrictMode><OAuthCallbackPage /></StrictMode>);
  expectCanonicalModalError(MSG.disabled, 'error');
});

// ── регистрация через Яндекс (Stage Social Auth 4, UX hotfix) ────────────────

const REG_TICKET = 'tkt_REG_SYNTHETIC_zyxwvutsrqponmlk';
const MASKED = 'i***@yandex.ru';

async function codeStep() {
  return screen.findByRole('group', { name: 'Код подтверждения' });
}

function typeCode(value = '123456') {
  fireEvent.paste(screen.getByLabelText('Цифра 1'), {
    clipboardData: { getData: () => value },
  });
}

test('#result=registration → код отправляется автоматически, fragment вычищен сразу', async () => {
  setUrl(`#result=registration&ticket=${REG_TICKET}`);
  spyReplace();
  let resolveInit;
  authApi.oauthRegistrationInit.mockReturnValue(new Promise((r) => { resolveInit = r; }));
  const { container } = render(<OAuthCallbackPage />);

  expect(events).toEqual(['scrub']);
  expect(window.location.hash).toBe('');
  expect(screen.getByRole('status')).toHaveTextContent('Отправляем код подтверждения…');
  expect(authApi.oauthRegistrationInit).toHaveBeenCalledTimes(1);
  expect(authApi.oauthRegistrationInit).toHaveBeenCalledWith({ ticket: REG_TICKET });

  resolveInit({ message: 'ok', email_masked: MASKED });
  await codeStep();
  expect(screen.getByText('Подтверждение регистрации')).toBeInTheDocument();
  expect(screen.getByText(MASKED)).toBeInTheDocument();
  expect(container.innerHTML).not.toContain(REG_TICKET);
  expect(window.location.href).not.toContain(REG_TICKET);
  // Это не вход: обмен ticket на сессию не запускается.
  expect(completeOAuthLogin).not.toHaveBeenCalled();
});

test('registration: нет полей имени, email, пароля и вкладок — только код и согласие', async () => {
  setUrl(`#result=registration&ticket=${REG_TICKET}`);
  render(<OAuthCallbackPage />);
  await codeStep();

  expect(screen.queryByLabelText('Имя')).toBeNull();
  expect(screen.queryByLabelText('Email')).toBeNull();
  expect(screen.queryByLabelText(/Пароль/)).toBeNull();
  expect(screen.queryAllByRole('textbox').filter((el) => !/Цифра/.test(el.getAttribute('aria-label') || ''))).toEqual([]);
  expect(screen.queryByRole('tablist')).toBeNull();
  expect(screen.queryByRole('tab')).toBeNull();
  expect(screen.getByRole('checkbox')).not.toBeChecked();
  expect(screen.getByText(/Отправить повторно через/)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Подтвердить' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '← Начать заново' })).toBeInTheDocument();
});

test('registration в StrictMode: init уходит ровно один раз', async () => {
  setUrl(`#result=registration&ticket=${REG_TICKET}`);
  render(<StrictMode><OAuthCallbackPage /></StrictMode>);
  await codeStep();
  expect(authApi.oauthRegistrationInit).toHaveBeenCalledTimes(1);
  expect(authApi.oauthRegistrationInit).toHaveBeenCalledWith({ ticket: REG_TICKET });
});

test('registration: ticket не пишется в storage и navigation state', async () => {
  const setItem = jest.spyOn(Storage.prototype, 'setItem');
  setUrl(`#result=registration&ticket=${REG_TICKET}`);
  render(<OAuthCallbackPage />);
  await codeStep();

  expect(setItem).not.toHaveBeenCalled();
  expect(JSON.stringify(window.history.state ?? null)).not.toContain(REG_TICKET);
  expect(mockNavigate).not.toHaveBeenCalled();
  setItem.mockRestore();
});

test('registration: без согласия код не подтверждается', async () => {
  setUrl(`#result=registration&ticket=${REG_TICKET}`);
  render(<OAuthCallbackPage />);
  await codeStep();
  typeCode();
  fireEvent.click(screen.getByRole('button', { name: 'Подтвердить' }));

  expect(await screen.findByText('Необходимо принять политику персональных данных'))
    .toBeInTheDocument();
  await new Promise((r) => setTimeout(r, 200));
  expect(completeOAuthRegistration).not.toHaveBeenCalled();
});

test('registration: код + согласие → сессия через AuthContext → /dashboard (replace)', async () => {
  setUrl(`#result=registration&ticket=${REG_TICKET}`);
  render(<OAuthCallbackPage />);
  await codeStep();
  fireEvent.click(screen.getByRole('checkbox'));
  typeCode();

  await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/dashboard', { replace: true }));
  expect(completeOAuthRegistration).toHaveBeenCalledTimes(1);
  expect(completeOAuthRegistration).toHaveBeenCalledWith(REG_TICKET, '123456', true);
  expect(completeOAuthLogin).not.toHaveBeenCalled();
});

test('registration: повторная отправка — тот же ticket, таймер заново', async () => {
  jest.useFakeTimers();
  try {
    setUrl(`#result=registration&ticket=${REG_TICKET}`);
    render(<OAuthCallbackPage />);
    await act(async () => { await Promise.resolve(); });
    for (let i = 0; i < 61; i += 1) {
      // eslint-disable-next-line no-await-in-loop
      await act(async () => { jest.advanceTimersByTime(1000); });
    }
    const resend = screen.getByRole('button', { name: 'Отправить повторно' });
    fireEvent.click(resend);
    await waitFor(() => expect(authApi.oauthRegistrationInit).toHaveBeenCalledTimes(2));

    expect(authApi.oauthRegistrationInit).toHaveBeenCalledTimes(2);
    expect(authApi.oauthRegistrationInit.mock.calls[1][0]).toEqual({ ticket: REG_TICKET });
    expect(await screen.findByText(/Отправить повторно через/)).toBeInTheDocument();
  } finally {
    jest.useRealTimers();
  }
});

test.each([
  [{ status: 409, code: 'email_already_exists' },
    'Аккаунт с таким email уже существует. Войдите по email и паролю.'],
  [{ status: 400, code: 'oauth_ticket_invalid' },
    'Время на завершение регистрации истекло. Начните заново через Яндекс.'],
  [{ status: 500, code: 'email_delivery_failed' }, 'Не удалось отправить письмо. Попробуйте позже.'],
  [{ status: 500 }, 'Не удалось завершить регистрацию. Попробуйте ещё раз.'],
])('registration: ошибка init %j → AuthModal «Вход» с текстом, тон error', async (props, text) => {
  authApi.oauthRegistrationInit.mockRejectedValue(
    Object.assign(new Error('RAW server SECRET'), props),
  );
  setUrl(`#result=registration&ticket=${REG_TICKET}`);
  render(<OAuthCallbackPage />);

  await waitFor(() => expect(mockNavigate).toHaveBeenCalled());
  expect(mockNavigate).toHaveBeenCalledTimes(1);
  expect(mockNavigate).toHaveBeenCalledWith('/', {
    replace: true, state: { openAuth: 'login', message: text, messageTone: 'error' },
  });
  expect(JSON.stringify(mockNavigate.mock.calls)).not.toMatch(/RAW server|SECRET|tkt_REG/);
  expect(screen.queryByRole('alert')).toBeNull();
  expect(screen.queryByRole('group', { name: 'Код подтверждения' })).toBeNull();
  expect(RegistrationOtpStep).not.toHaveBeenCalled();
  expect(authApi.oauthRegistrationInit).toHaveBeenCalledTimes(1);
});

test('registration: email занят на confirm → отказ, подтверждение и повтор заблокированы', async () => {
  completeOAuthRegistration.mockRejectedValue(Object.assign(new Error('x'), {
    status: 409, code: 'email_already_exists',
  }));
  setUrl(`#result=registration&ticket=${REG_TICKET}`);
  render(<OAuthCallbackPage />);
  await codeStep();
  fireEvent.click(screen.getByRole('checkbox'));
  typeCode();

  expect(await screen.findByText(
    'Аккаунт с таким email уже существует. Войдите по email и паролю.',
  )).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Подтвердить' })).toBeDisabled();
  expect(screen.queryByText(/Отправить повторно/)).toBeNull();
  expect(mockNavigate).not.toHaveBeenCalled();
});

test('«← Начать заново» → главная + AuthModal «Регистрация», backend не вызывается', async () => {
  setUrl(`#result=registration&ticket=${REG_TICKET}`);
  render(<OAuthCallbackPage />);
  await codeStep();
  authApi.oauthRegistrationInit.mockClear();

  fireEvent.click(screen.getByRole('button', { name: '← Начать заново' }));

  expect(mockNavigate).toHaveBeenCalledWith('/', { replace: true, state: { openAuth: 'register' } });
  expect(authApi.oauthRegistrationInit).not.toHaveBeenCalled();
  expect(completeOAuthRegistration).not.toHaveBeenCalled();
});


// ── регрессия: вспышка шага кода при входе известной identity ───────────────

/**
 * Пишет КАЖДОЕ состояние DOM с момента первого коммита: появлялись ли поле
 * кода, заголовок шага кода и какой статус был виден. MutationObserver ловит
 * даже кратковременную вставку узлов (то, что пользователь видит «вспышкой»).
 */
function recordDom() {
  const seen = [];
  const snapshot = () => {
    seen.push({
      otpField: screen.queryByLabelText('Цифра 1') !== null,
      otpGroup: screen.queryByRole('group', { name: 'Код подтверждения' }) !== null,
      otpTitle: screen.queryByText('Подтверждение регистрации') !== null,
      status: screen.queryByRole('status')?.textContent ?? '',
    });
  };
  const observer = new MutationObserver(snapshot);
  observer.observe(document.body, { subtree: true, childList: true, characterData: true });
  return { seen, snapshot, stop: () => observer.disconnect() };
}

test.each([
  ['обычный режим', (ui) => ui],
  ['StrictMode', (ui) => <StrictMode>{ui}</StrictMode>],
])('result=login (%s): шаг кода не монтируется ни на один кадр', async (_, wrap) => {
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

  expect(RegistrationOtpStep).not.toHaveBeenCalled();          // ни одного монтирования
  expect(dom.seen.length).toBeGreaterThan(1);
  expect(dom.seen.some((s) => s.otpField || s.otpGroup || s.otpTitle)).toBe(false);
  expect(dom.seen.some((s) => /Отправляем код/.test(s.status))).toBe(false);
  expect(authApi.oauthRegistrationInit).not.toHaveBeenCalled();
  expect(completeOAuthLogin).toHaveBeenCalledTimes(1);
  expect(completeOAuthLogin).toHaveBeenCalledWith(TICKET);
  expect(mockNavigate).toHaveBeenCalledTimes(1);
});

test('result=login + ошибка complete: шаг кода тоже не появляется', async () => {
  setUrl(`#result=login&ticket=${TICKET}`);
  completeOAuthLogin.mockRejectedValue(Object.assign(new Error('x'), { status: 400, code: 'oauth_ticket_invalid' }));
  const dom = recordDom();
  render(<OAuthCallbackPage />);
  await waitFor(() => expect(mockNavigate).toHaveBeenCalled());
  dom.stop();
  expect(RegistrationOtpStep).not.toHaveBeenCalled();
  expect(dom.seen.some((s) => s.otpField || s.otpTitle)).toBe(false);
  expect(authApi.oauthRegistrationInit).not.toHaveBeenCalled();
});

test('result=registration: пока init не завершён, шага кода нет; после успеха — есть', async () => {
  setUrl(`#result=registration&ticket=${REG_TICKET}`);
  let resolveInit;
  authApi.oauthRegistrationInit.mockReturnValue(new Promise((r) => { resolveInit = r; }));
  const dom = recordDom();

  render(<OAuthCallbackPage />);
  dom.snapshot();
  expect(screen.getByRole('status')).toHaveTextContent('Отправляем код подтверждения…');
  expect(RegistrationOtpStep).not.toHaveBeenCalled();
  expect(screen.queryByRole('group', { name: 'Код подтверждения' })).toBeNull();
  // Статус входа для регистрации не показывается вовсе.
  expect(dom.seen.some((s) => /Выполняем вход/.test(s.status))).toBe(false);
  expect(dom.seen.some((s) => s.otpField || s.otpTitle)).toBe(false);

  await act(async () => { resolveInit({ message: 'ok', email_masked: MASKED }); });
  dom.stop();

  expect(await codeStep()).toBeInTheDocument();
  expect(RegistrationOtpStep).toHaveBeenCalled();
  expect(screen.queryByRole('status')).toBeNull();
  expect(authApi.oauthRegistrationInit).toHaveBeenCalledTimes(1);
  expect(completeOAuthLogin).not.toHaveBeenCalled();
});

test('result=registration в StrictMode: init один, complete входа не вызывается', async () => {
  setUrl(`#result=registration&ticket=${REG_TICKET}`);
  render(<StrictMode><OAuthCallbackPage /></StrictMode>);
  await codeStep();
  expect(authApi.oauthRegistrationInit).toHaveBeenCalledTimes(1);
  expect(completeOAuthLogin).not.toHaveBeenCalled();
});

test('после успешной регистрации шаг кода не возвращается и статус регистрации не мелькает', async () => {
  setUrl(`#result=registration&ticket=${REG_TICKET}`);
  render(<OAuthCallbackPage />);
  await codeStep();
  fireEvent.click(screen.getByRole('checkbox'));
  typeCode();
  await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/dashboard', { replace: true }));
  expect(screen.queryByRole('group', { name: 'Код подтверждения' })).toBeNull();
  expect(screen.queryByText('Отправляем код подтверждения…')).toBeNull();
  expect(authApi.oauthRegistrationInit).toHaveBeenCalledTimes(1);
});

// ── регистрация остаётся на callback, вход — /dashboard ─────────────────────

test('регистрация: шаг кода остаётся на /auth/callback, перехода на главную нет', async () => {
  setUrl(`#result=registration&ticket=${REG_TICKET}`);
  render(<OAuthCallbackPage />);
  await codeStep();
  expect(RegistrationOtpStep).toHaveBeenCalled();
  expect(window.location.pathname).toBe('/auth/callback');
  expect(mockNavigate).not.toHaveBeenCalled();
});
