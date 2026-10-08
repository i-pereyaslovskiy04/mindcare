import { render, screen, waitFor, act, fireEvent } from '@testing-library/react';
import { AuthProvider, useAuth } from './AuthContext';
import * as authApi from '../../api/auth.api';

jest.mock('../../api/auth.api');
jest.mock('../../api/client', () => ({
  configureClient: jest.fn(),
  apiFetch: jest.fn(),
}));
const mockNavigate = jest.fn();
let mockLocation = { pathname: '/' };
jest.mock('react-router-dom', () => ({
  useNavigate: () => mockNavigate,
  useLocation: () => mockLocation,
}), { virtual: true });

const SESSION_KEY = 'mindcare_session';
const ACTIVE_ROLE_KEY = 'mindcare_active_role';

function Consumer() {
  const { user, activeRole, loading, setActiveRole, refreshUser, logout } = useAuth();
  return (
    <div>
      <div data-testid="loading">{String(loading)}</div>
      <div data-testid="roles">{user ? user.roles.join(',') : 'null'}</div>
      <div data-testid="active">{activeRole ?? 'null'}</div>
      <button onClick={() => setActiveRole('admin')}>set-admin</button>
      <button onClick={() => setActiveRole('supervisor')}>set-supervisor</button>
      <button onClick={() => refreshUser()}>refresh</button>
      <button onClick={() => logout()}>logout</button>
    </div>
  );
}

function renderAuth() {
  return render(<AuthProvider><Consumer /></AuthProvider>);
}

async function waitReady() {
  await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'));
}

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  jest.clearAllMocks();
  mockLocation = { pathname: '/' };
  authApi.logout.mockResolvedValue({});
});

test('legacy role is normalized to roles[]', async () => {
  localStorage.setItem(SESSION_KEY, 'tok');
  authApi.me.mockResolvedValue({ id: '1', email: 'a@b.c', name: 'A', role: 'psychologist' });
  renderAuth();
  await waitReady();
  expect(screen.getByTestId('roles')).toHaveTextContent('psychologist');
});

test('explicit roles:[] is NOT replaced by legacy role', async () => {
  localStorage.setItem(SESSION_KEY, 'tok');
  authApi.me.mockResolvedValue({ id: '1', roles: [], role: 'psychologist' });
  renderAuth();
  await waitReady();
  // user существует, но roles пустой → join('') === '' (НЕ подменяется на [role])
  expect(screen.getByTestId('roles').textContent).toBe('');
});

test('roles are deduped and sorted by priority', async () => {
  localStorage.setItem(SESSION_KEY, 'tok');
  authApi.me.mockResolvedValue({ roles: ['psychologist', 'admin', 'psychologist'] });
  renderAuth();
  await waitReady();
  expect(screen.getByTestId('roles')).toHaveTextContent('admin,psychologist');
});

test('valid stored activeRole is restored', async () => {
  localStorage.setItem(SESSION_KEY, 'tok');
  localStorage.setItem(ACTIVE_ROLE_KEY, 'supervisor');
  authApi.me.mockResolvedValue({ roles: ['psychologist', 'supervisor'] });
  renderAuth();
  await waitReady();
  expect(screen.getByTestId('active')).toHaveTextContent('supervisor');
});

test('invalid stored activeRole is cleared (state + localStorage)', async () => {
  localStorage.setItem(SESSION_KEY, 'tok');
  localStorage.setItem(ACTIVE_ROLE_KEY, 'admin');
  authApi.me.mockResolvedValue({ roles: ['psychologist'] });
  renderAuth();
  await waitReady();
  await waitFor(() => expect(screen.getByTestId('active')).toHaveTextContent('null'));
  expect(localStorage.getItem(ACTIVE_ROLE_KEY)).toBeNull();
});

test('no session on restore clears stored activeRole', async () => {
  localStorage.setItem(ACTIVE_ROLE_KEY, 'admin'); // no SESSION_KEY
  renderAuth();
  await waitReady();
  expect(screen.getByTestId('active')).toHaveTextContent('null');
  expect(localStorage.getItem(ACTIVE_ROLE_KEY)).toBeNull();
});

test('setActiveRole rejects a role without membership', async () => {
  localStorage.setItem(SESSION_KEY, 'tok');
  authApi.me.mockResolvedValue({ roles: ['psychologist'] });
  renderAuth();
  await waitReady();
  fireEvent.click(screen.getByText('set-admin')); // not a member
  expect(screen.getByTestId('active')).toHaveTextContent('null');
});

test('setActiveRole accepts a member role', async () => {
  localStorage.setItem(SESSION_KEY, 'tok');
  authApi.me.mockResolvedValue({ roles: ['psychologist', 'admin'] });
  renderAuth();
  await waitReady();
  fireEvent.click(screen.getByText('set-admin'));
  expect(screen.getByTestId('active')).toHaveTextContent('admin');
  expect(localStorage.getItem(ACTIVE_ROLE_KEY)).toBe('admin');
});

test('refreshUser clears activeRole if the role is no longer assigned', async () => {
  localStorage.setItem(SESSION_KEY, 'tok');
  localStorage.setItem(ACTIVE_ROLE_KEY, 'supervisor');
  authApi.me.mockResolvedValueOnce({ roles: ['psychologist', 'supervisor'] });
  renderAuth();
  await waitReady();
  expect(screen.getByTestId('active')).toHaveTextContent('supervisor');

  authApi.me.mockResolvedValueOnce({ roles: ['psychologist'] });
  fireEvent.click(screen.getByText('refresh'));
  await waitFor(() => expect(screen.getByTestId('active')).toHaveTextContent('null'));
});

test('logout clears activeRole', async () => {
  localStorage.setItem(SESSION_KEY, 'tok');
  authApi.me.mockResolvedValue({ roles: ['psychologist', 'admin'] });
  renderAuth();
  await waitReady();
  fireEvent.click(screen.getByText('set-admin'));
  expect(screen.getByTestId('active')).toHaveTextContent('admin');

  fireEvent.click(screen.getByText('logout'));
  await waitFor(() => expect(screen.getByTestId('roles')).toHaveTextContent('null'));
  expect(screen.getByTestId('active')).toHaveTextContent('null');
  expect(localStorage.getItem(ACTIVE_ROLE_KEY)).toBeNull();
});

test('auth:session-expired clears activeRole and user', async () => {
  localStorage.setItem(SESSION_KEY, 'tok');
  authApi.me.mockResolvedValue({ roles: ['psychologist', 'admin'] });
  renderAuth();
  await waitReady();
  fireEvent.click(screen.getByText('set-admin'));
  expect(screen.getByTestId('active')).toHaveTextContent('admin');

  await act(async () => {
    window.dispatchEvent(new Event('auth:session-expired'));
  });
  await waitFor(() => expect(screen.getByTestId('roles')).toHaveTextContent('null'));
  expect(screen.getByTestId('active')).toHaveTextContent('null');
  expect(localStorage.getItem(ACTIVE_ROLE_KEY)).toBeNull();
  // Канонический вход: главная + AuthModal «Вход» с сообщением, не /login.
  expect(mockNavigate).toHaveBeenCalledTimes(1);
  expect(mockNavigate).toHaveBeenCalledWith('/', {
    replace: true,
    state: { openAuth: 'login', message: 'Сессия истекла. Войдите снова.' },
  });
  expect(mockNavigate.mock.calls.flat()).not.toContain('/login');
});

test('failed restore clears token and activeRole', async () => {
  localStorage.setItem(SESSION_KEY, 'tok');
  localStorage.setItem(ACTIVE_ROLE_KEY, 'admin');
  authApi.me.mockRejectedValue(new Error('401'));
  renderAuth();
  await waitReady();
  expect(screen.getByTestId('roles')).toHaveTextContent('null');
  expect(screen.getByTestId('active')).toHaveTextContent('null');
  expect(localStorage.getItem(ACTIVE_ROLE_KEY)).toBeNull();
});

// ── Stage Social Auth 3B: вход через провайдера и общий путь сессии ──────────

function LoginConsumer() {
  const {
    user, login, completeOAuthLogin, completeOAuthRegistration, logout, loading,
  } = useAuth();
  return (
    <div>
      <div data-testid="loading">{String(loading)}</div>
      <div data-testid="roles">{user ? user.roles.join(',') : 'null'}</div>
      <button onClick={() => login({ email: 'a@b.c', password: 'pw' })}>pw-login</button>
      <button onClick={() => completeOAuthLogin('tkt_SYNTH').catch(() => {})}>oauth-login</button>
      <button onClick={() => completeOAuthRegistration('tkt_REG', '123456', true).catch(() => {})}>
        oauth-register
      </button>
      <button onClick={() => logout()}>logout</button>
    </div>
  );
}

function renderLogin() {
  return render(<AuthProvider><LoginConsumer /></AuthProvider>);
}

test('вход по паролю: прежний контракт (login → токен → /me → user)', async () => {
  authApi.login.mockResolvedValue({ session_token: 'pw-token', roles: ['student'] });
  authApi.me.mockResolvedValue({ roles: ['student'] });
  renderLogin();
  await waitReady();

  fireEvent.click(screen.getByText('pw-login'));
  await waitFor(() => expect(screen.getByTestId('roles')).toHaveTextContent('student'));
  expect(authApi.login).toHaveBeenCalledWith({ email: 'a@b.c', password: 'pw' });
  expect(localStorage.getItem(SESSION_KEY)).toBe('pw-token');
  expect(authApi.oauthComplete).not.toHaveBeenCalled();
});

test('completeOAuthLogin: ticket → oauthComplete → токен → /me → нормализованный user', async () => {
  authApi.oauthComplete.mockResolvedValue({ session_token: 'social-token', roles: ['student'] });
  authApi.me.mockResolvedValue({ role: 'student' });          // legacy → roles[]
  renderLogin();
  await waitReady();

  fireEvent.click(screen.getByText('oauth-login'));
  await waitFor(() => expect(screen.getByTestId('roles')).toHaveTextContent('student'));
  expect(authApi.oauthComplete).toHaveBeenCalledWith('tkt_SYNTH');
  expect(authApi.oauthComplete).toHaveBeenCalledTimes(1);
  expect(authApi.me).toHaveBeenCalledTimes(1);
  expect(localStorage.getItem(SESSION_KEY)).toBe('social-token');
  expect(authApi.login).not.toHaveBeenCalled();
  // ticket нигде не сохраняется
  expect(JSON.stringify({ ...localStorage })).not.toContain('tkt_SYNTH');
});

test('completeOAuthLogin: ошибка complete — ни токена, ни пользователя', async () => {
  authApi.oauthComplete.mockRejectedValue(Object.assign(new Error('x'), { status: 400 }));
  renderLogin();
  await waitReady();

  fireEvent.click(screen.getByText('oauth-login'));
  await waitFor(() => expect(authApi.oauthComplete).toHaveBeenCalled());
  expect(localStorage.getItem(SESSION_KEY)).toBeNull();
  expect(screen.getByTestId('roles')).toHaveTextContent('null');
  expect(authApi.me).not.toHaveBeenCalled();
});

test('выход из social-сессии — тот же logout', async () => {
  authApi.oauthComplete.mockResolvedValue({ session_token: 'social-token' });
  authApi.me.mockResolvedValue({ roles: ['student'] });
  renderLogin();
  await waitReady();
  fireEvent.click(screen.getByText('oauth-login'));
  await waitFor(() => expect(screen.getByTestId('roles')).toHaveTextContent('student'));

  fireEvent.click(screen.getByText('logout'));
  await waitFor(() => expect(screen.getByTestId('roles')).toHaveTextContent('null'));
  expect(authApi.logout).toHaveBeenCalledTimes(1);
  expect(localStorage.getItem(SESSION_KEY)).toBeNull();
});

// ── Stage Social Auth 4: завершение регистрации через провайдера ─────────────

test('completeOAuthRegistration: confirm → токен → /me → user, без входа по паролю', async () => {
  authApi.oauthRegistrationConfirm.mockResolvedValue({
    session_token: 'reg-token', roles: ['student'],
  });
  authApi.me.mockResolvedValue({ roles: ['student'], has_password: false });
  renderLogin();
  await waitReady();

  fireEvent.click(screen.getByText('oauth-register'));
  await waitFor(() => expect(screen.getByTestId('roles')).toHaveTextContent('student'));
  expect(authApi.oauthRegistrationConfirm).toHaveBeenCalledTimes(1);
  expect(authApi.oauthRegistrationConfirm).toHaveBeenCalledWith({
    ticket: 'tkt_REG', code: '123456', consentAccepted: true,
  });
  expect(authApi.me).toHaveBeenCalledTimes(1);
  expect(localStorage.getItem(SESSION_KEY)).toBe('reg-token');
  expect(authApi.login).not.toHaveBeenCalled();
  expect(authApi.oauthComplete).not.toHaveBeenCalled();
  expect(JSON.stringify({ ...localStorage })).not.toContain('tkt_REG');
});

test('completeOAuthRegistration: отказ confirm — ни токена, ни пользователя', async () => {
  authApi.oauthRegistrationConfirm.mockRejectedValue(
    Object.assign(new Error('x'), { status: 400, code: 'otp_invalid' }));
  renderLogin();
  await waitReady();

  fireEvent.click(screen.getByText('oauth-register'));
  await waitFor(() => expect(authApi.oauthRegistrationConfirm).toHaveBeenCalled());
  expect(localStorage.getItem(SESSION_KEY)).toBeNull();
  expect(screen.getByTestId('roles')).toHaveTextContent('null');
  expect(authApi.me).not.toHaveBeenCalled();
});

// ── незавершённая регистрация через провайдера: только память приложения ────

const SOCIAL_TICKET = 'tkt_REG_CONTEXT_0123456789abcdefgh';

function SocialConsumer() {
  const {
    user, loading, socialRegistration, beginSocialRegistration, clearSocialRegistration,
    completeOAuthRegistration, logout,
  } = useAuth();
  return (
    <div>
      <div data-testid="loading">{String(loading)}</div>
      <div data-testid="roles">{user ? user.roles.join(',') : 'null'}</div>
      <div data-testid="social">
        {socialRegistration
          ? `${socialRegistration.provider}:${String(socialRegistration.emailStep)}:${
            socialRegistration.ticket === SOCIAL_TICKET ? 'ticket-ok' : 'ticket-other'}`
          : 'none'}
      </div>
      <button
        onClick={() => beginSocialRegistration({
          ticket: SOCIAL_TICKET, provider: 'vk', emailStep: true, email: 'leak@donnu.ru',
        })}
      >
        begin
      </button>
      <button onClick={() => beginSocialRegistration({ ticket: '', provider: 'vk' })}>begin-empty</button>
      <button onClick={() => beginSocialRegistration(null)}>begin-null</button>
      <button onClick={() => clearSocialRegistration()}>clear</button>
      <button onClick={() => completeOAuthRegistration(SOCIAL_TICKET, '123456', true).catch(() => {})}>
        confirm
      </button>
      <button onClick={() => logout()}>logout</button>
    </div>
  );
}

function renderSocial() {
  return render(<AuthProvider><SocialConsumer /></AuthProvider>);
}

const socialState = () => screen.getByTestId('social').textContent;

test('beginSocialRegistration: ticket живёт только в памяти — не в storage, URL и истории', async () => {
  const setItem = jest.spyOn(Storage.prototype, 'setItem');
  renderSocial();
  await waitReady();
  expect(socialState()).toBe('none');

  fireEvent.click(screen.getByText('begin'));
  expect(socialState()).toBe('vk:true:ticket-ok');

  expect(setItem).not.toHaveBeenCalled();
  expect(JSON.stringify({ ...localStorage, ...sessionStorage })).not.toContain(SOCIAL_TICKET);
  expect(window.location.href).not.toContain(SOCIAL_TICKET);
  expect(JSON.stringify(window.history.state ?? null)).not.toContain(SOCIAL_TICKET);
  expect(JSON.stringify(mockNavigate.mock.calls)).not.toContain(SOCIAL_TICKET);
  expect(document.body.innerHTML).not.toContain(SOCIAL_TICKET);
  setItem.mockRestore();
});

test('в памяти остаются только ticket, provider и emailStep — посторонние поля отброшены', async () => {
  let captured;
  function Probe() {
    captured = useAuth().socialRegistration;
    return null;
  }
  render(<AuthProvider><SocialConsumer /><Probe /></AuthProvider>);
  await waitReady();
  fireEvent.click(screen.getByText('begin'));

  expect(captured).toEqual({ ticket: SOCIAL_TICKET, provider: 'vk', emailStep: true });
  expect(Object.isFrozen(captured)).toBe(true);
});

test.each(['begin-empty', 'begin-null'])('%s: без ticket продолжение не создаётся', async (button) => {
  renderSocial();
  await waitReady();
  fireEvent.click(screen.getByText(button));
  expect(socialState()).toBe('none');
});

test('clearSocialRegistration забывает ticket («Начать заново», закрытие модалки)', async () => {
  renderSocial();
  await waitReady();
  fireEvent.click(screen.getByText('begin'));
  expect(socialState()).toBe('vk:true:ticket-ok');

  fireEvent.click(screen.getByText('clear'));
  expect(socialState()).toBe('none');
});

test('после «обновления страницы» (новый AuthProvider) продолжение не восстанавливается', async () => {
  const view = renderSocial();
  await waitReady();
  fireEvent.click(screen.getByText('begin'));
  expect(socialState()).toBe('vk:true:ticket-ok');
  view.unmount();

  renderSocial();                                   // память приложения начинается с нуля
  await waitReady();
  expect(socialState()).toBe('none');
});

test('успешная регистрация устанавливает сессию и забывает ticket', async () => {
  authApi.oauthRegistrationConfirm.mockResolvedValue({ session_token: 'reg-token' });
  authApi.me.mockResolvedValue({ roles: ['student'] });
  renderSocial();
  await waitReady();
  fireEvent.click(screen.getByText('begin'));

  fireEvent.click(screen.getByText('confirm'));
  await waitFor(() => expect(screen.getByTestId('roles')).toHaveTextContent('student'));
  await waitFor(() => expect(socialState()).toBe('none'));
  expect(JSON.stringify({ ...localStorage })).not.toContain(SOCIAL_TICKET);
});

test('отказ confirm ticket не забывает — пользователь может исправить код', async () => {
  authApi.oauthRegistrationConfirm.mockRejectedValue(
    Object.assign(new Error('x'), { status: 400, code: 'otp_invalid' }));
  renderSocial();
  await waitReady();
  fireEvent.click(screen.getByText('begin'));

  fireEvent.click(screen.getByText('confirm'));
  await waitFor(() => expect(authApi.oauthRegistrationConfirm).toHaveBeenCalled());
  expect(socialState()).toBe('vk:true:ticket-ok');
});

test('уже вошедшему пользователю продолжение регистрации не сохраняется', async () => {
  localStorage.setItem(SESSION_KEY, 'tok');
  authApi.me.mockResolvedValue({ roles: ['student'] });
  renderSocial();
  await waitReady();

  fireEvent.click(screen.getByText('begin'));
  await waitFor(() => expect(socialState()).toBe('none'));
});

test.each(['/auth/callback', '/'])('на %s продолжение сохраняется', async (pathname) => {
  mockLocation = { pathname };
  renderSocial();
  await waitReady();
  fireEvent.click(screen.getByText('begin'));
  expect(socialState()).toBe('vk:true:ticket-ok');
});

test('уход с главной забывает ticket', async () => {
  const view = renderSocial();
  await waitReady();
  fireEvent.click(screen.getByText('begin'));
  expect(socialState()).toBe('vk:true:ticket-ok');

  mockLocation = { pathname: '/news' };
  view.rerender(<AuthProvider><SocialConsumer /></AuthProvider>);
  await waitFor(() => expect(socialState()).toBe('none'));

  mockLocation = { pathname: '/' };                 // возврат на главную его не возвращает
  view.rerender(<AuthProvider><SocialConsumer /></AuthProvider>);
  expect(socialState()).toBe('none');
});

test('logout забывает незавершённую регистрацию', async () => {
  renderSocial();
  await waitReady();
  fireEvent.click(screen.getByText('begin'));
  fireEvent.click(screen.getByText('logout'));
  await waitFor(() => expect(socialState()).toBe('none'));
});
