import { render, screen, waitFor, act, fireEvent } from '@testing-library/react';
import { AuthProvider, useAuth } from './AuthContext';
import * as authApi from '../../api/auth.api';

jest.mock('../../api/auth.api');
jest.mock('../../api/client', () => ({
  configureClient: jest.fn(),
  apiFetch: jest.fn(),
}));
jest.mock('react-router-dom', () => ({
  useNavigate: () => jest.fn(),
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
  jest.clearAllMocks();
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
  const { user, login, completeOAuthLogin, logout, loading } = useAuth();
  return (
    <div>
      <div data-testid="loading">{String(loading)}</div>
      <div data-testid="roles">{user ? user.roles.join(',') : 'null'}</div>
      <button onClick={() => login({ email: 'a@b.c', password: 'pw' })}>pw-login</button>
      <button onClick={() => completeOAuthLogin('tkt_SYNTH').catch(() => {})}>oauth-login</button>
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
