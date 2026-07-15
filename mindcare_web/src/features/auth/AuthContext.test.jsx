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
