import { StrictMode } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import OAuthCallbackPage from './OAuthCallbackPage';
import * as AuthContext from '../AuthContext';

const mockNavigate = jest.fn();
jest.mock('react-router-dom', () => ({
  useNavigate: () => mockNavigate,
  Link: ({ to, children, ...rest }) => <a href={to} {...rest}>{children}</a>,
}), { virtual: true });
jest.mock('../AuthContext', () => ({ useAuth: jest.fn() }));

const TICKET = 'tkt_SYNTHETIC_0123456789abcdefghij';
const events = [];
let completeOAuthLogin;
let replaceSpy;

function setUrl(hash) {
  window.history.replaceState(null, '', `/auth/callback${hash}`);
}

function mockAuth(over = {}) {
  AuthContext.useAuth.mockReturnValue({ completeOAuthLogin, loading: false, ...over });
}

beforeEach(() => {
  jest.clearAllMocks();
  events.length = 0;
  completeOAuthLogin = jest.fn((ticket) => {
    events.push(`complete:${window.location.hash === '' ? 'scrubbed' : 'dirty'}`);
    return Promise.resolve({ roles: ['student'] });
  });
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

test('пока идёт обмен — статус «Выполняется вход…», ticket не в DOM', async () => {
  setUrl(`#result=login&ticket=${TICKET}`);
  completeOAuthLogin.mockReturnValue(new Promise(() => {}));
  const { container } = render(<OAuthCallbackPage />);
  expect(screen.getByRole('status')).toHaveTextContent('Выполняется вход…');
  await waitFor(() => expect(completeOAuthLogin).toHaveBeenCalled());
  expect(container.innerHTML).not.toContain(TICKET);
  expect(window.location.href).not.toContain(TICKET);
});

test('React StrictMode: один ticket → ровно ОДИН complete', async () => {
  setUrl(`#result=login&ticket=${TICKET}`);
  render(<StrictMode><OAuthCallbackPage /></StrictMode>);
  await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/dashboard', { replace: true }));
  expect(completeOAuthLogin).toHaveBeenCalledTimes(1);
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

// ── ошибки complete ──────────────────────────────────────────────────────────

test.each([
  [{ status: 400, code: 'oauth_ticket_invalid' },
    'Ссылка для входа устарела или уже использована. Начните вход заново.'],
  [{ status: 403, code: 'account_unavailable' },
    'Доступ к аккаунту сейчас недоступен. Обратитесь к администратору.'],
  [{ status: 403, code: 'social_login_not_allowed' },
    'Вход через Яндекс для этой учётной записи недоступен.'],
  [{ status: 429 }, 'Слишком много попыток. Попробуйте немного позже.'],
  [{ status: 500 }, 'Не удалось выполнить вход. Попробуйте ещё раз.'],
])('ошибка complete %j → фиксированное сообщение, без перехода', async (errProps, message) => {
  setUrl(`#result=login&ticket=${TICKET}`);
  const err = Object.assign(new Error('RAW server detail SECRET'), errProps);
  completeOAuthLogin.mockRejectedValue(err);
  render(<OAuthCallbackPage />);

  expect(await screen.findByRole('alert')).toHaveTextContent(message);
  expect(screen.queryByText(/RAW server detail/)).toBeNull();
  expect(mockNavigate).not.toHaveBeenCalled();
  expect(screen.getByRole('link', { name: 'Вернуться ко входу' })).toHaveAttribute('href', '/login');
});

// ── ошибки во fragment ───────────────────────────────────────────────────────

test.each([
  ['oauth_cancelled', 'Вход через Яндекс отменён.'],
  ['oauth_failed', 'Не удалось выполнить вход через Яндекс. Попробуйте ещё раз.'],
  ['social_registration_not_available', 'Аккаунт Яндекс пока не привязан к MindCare.'],
  ['account_unavailable', 'Доступ к аккаунту сейчас недоступен. Обратитесь к администратору.'],
  ['social_login_not_allowed', 'Вход через Яндекс для этой учётной записи недоступен.'],
])('#error=%s → сообщение, без complete и без авто-перехода', (code, message) => {
  setUrl(`#error=${code}`);
  spyReplace();
  render(<OAuthCallbackPage />);

  expect(screen.getByRole('alert')).toHaveTextContent(message);
  expect(events).toEqual(['scrub']);
  expect(window.location.hash).toBe('');
  expect(completeOAuthLogin).not.toHaveBeenCalled();
  expect(mockNavigate).not.toHaveBeenCalled();
});

test('регистрация недоступна — объяснение про привязку, без упрёка пользователю', () => {
  setUrl('#error=social_registration_not_available');
  render(<OAuthCallbackPage />);
  expect(screen.getByRole('alert')).toHaveTextContent(
    'Вход через Яндекс доступен только для уже связанных аккаунтов.',
  );
});

test('неизвестный код ошибки не показывается — общее сообщение', () => {
  setUrl('#error=evil_<b>code</b>');
  render(<OAuthCallbackPage />);
  expect(screen.getByRole('alert')).toHaveTextContent('Не удалось выполнить вход. Попробуйте ещё раз.');
  expect(screen.queryByText(/evil/)).toBeNull();
});

test('без fragment — «ссылка недействительна», ничего не вызывается', () => {
  setUrl('');
  render(<OAuthCallbackPage />);
  expect(screen.getByRole('alert')).toHaveTextContent('Ссылка для входа недействительна.');
  expect(completeOAuthLogin).not.toHaveBeenCalled();
});

test('адрес перехода из fragment игнорируется', async () => {
  setUrl(`#result=login&ticket=${TICKET}&next=https://evil.example/&redirect=/admin`);
  render(<OAuthCallbackPage />);
  await waitFor(() => expect(mockNavigate).toHaveBeenCalled());
  expect(mockNavigate).toHaveBeenCalledWith('/dashboard', { replace: true });
  expect(window.location.hash).toBe('');
});

test('кнопка возврата доступна с клавиатуры (ссылка)', () => {
  setUrl('#error=oauth_failed');
  render(<OAuthCallbackPage />);
  const link = screen.getByRole('link', { name: 'Вернуться ко входу' });
  link.focus();
  expect(link).toHaveFocus();
});
