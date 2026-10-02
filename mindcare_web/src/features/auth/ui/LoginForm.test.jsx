import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import LoginForm from './LoginForm';
import * as AuthContext from '../AuthContext';
import * as authApi from '../../../api/auth.api';
import * as configApi from '../../../api/config.api';
import * as oauthLib from '../lib/oauthCallback';

const mockNavigate = jest.fn();
jest.mock('react-router-dom', () => ({
  useNavigate: () => mockNavigate,
}), { virtual: true });
jest.mock('../AuthContext', () => ({ useAuth: jest.fn() }));
jest.mock('../../../api/auth.api', () => ({ oauthStart: jest.fn() }));
jest.mock('../../../api/config.api', () => ({
  ...jest.requireActual('../../../api/config.api'),
  getPublicConfig: jest.fn(),
}));
jest.mock('../lib/oauthCallback', () => ({
  ...jest.requireActual('../lib/oauthCallback'),
  navigateToProvider: jest.fn(),
}));

const login = jest.fn();
const AUTHORIZE_URL = 'https://oauth.yandex.ru/authorize?state=SYNTHETIC';
// Собирается из частей: литерал script-URL в исходнике запрещён линтером.
const SCRIPT_URL = ['javascript', 'alert(1)'].join(':');

beforeEach(() => {
  jest.clearAllMocks();
  login.mockResolvedValue({ roles: ['psychologist', 'supervisor'] });
  AuthContext.useAuth.mockReturnValue({ login });
  configApi.getPublicConfig.mockResolvedValue({ social_providers: [] });
});

function renderForm() {
  return render(<LoginForm onSuccess={jest.fn()} onForgotPassword={jest.fn()} />);
}

async function openWithYandex() {
  configApi.getPublicConfig.mockResolvedValue({ social_providers: ['yandex'] });
  renderForm();
  return screen.findByRole('button', { name: 'Войти через Яндекс' });
}

async function submitPassword() {
  fireEvent.change(screen.getByLabelText('Email'), {
    target: { value: 'user@donnu.ru' },
  });
  fireEvent.change(screen.getByLabelText('Пароль'), {
    target: { value: 'secret123' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Войти' }));
  await waitFor(() => expect(login).toHaveBeenCalled());
}

test('successful login navigates to /dashboard (not a role-specific home)', async () => {
  renderForm();
  await submitPassword();
  expect(mockNavigate).toHaveBeenCalledWith('/dashboard');
});

// ── видимость провайдеров ────────────────────────────────────────────────────

test('Яндекс включён на backend → кнопка видна вместе с разделителем', async () => {
  const button = await openWithYandex();
  expect(button).toBeEnabled();
  expect(screen.getByText('или продолжить с email')).toBeInTheDocument();
});

test('провайдеров нет → блока быстрой авторизации нет', async () => {
  renderForm();
  await waitFor(() => expect(configApi.getPublicConfig).toHaveBeenCalled());
  expect(screen.queryByRole('button', { name: 'Войти через Яндекс' })).toBeNull();
  expect(screen.queryByText('Быстрая авторизация')).toBeNull();
  expect(screen.queryByText('или продолжить с email')).toBeNull();
});

test('конфиг недоступен → без кнопки, вход по паролю работает', async () => {
  configApi.getPublicConfig.mockRejectedValue(new Error('network'));
  renderForm();
  await waitFor(() => expect(configApi.getPublicConfig).toHaveBeenCalled());
  expect(screen.queryByRole('button', { name: 'Войти через Яндекс' })).toBeNull();
  await submitPassword();
  expect(mockNavigate).toHaveBeenCalledWith('/dashboard');
});

test('Telegram и VK не показываются как рабочие провайдеры', async () => {
  configApi.getPublicConfig.mockResolvedValue({ social_providers: ['yandex', 'vk', 'telegram'] });
  renderForm();
  await screen.findByRole('button', { name: 'Войти через Яндекс' });
  expect(screen.queryByRole('button', { name: /Telegram/ })).toBeNull();
  expect(screen.queryByRole('button', { name: /ВКонтакте|VK/ })).toBeNull();
});

// ── клик по Яндексу ──────────────────────────────────────────────────────────

test('клик → один oauthStart и top-level переход на authorize_url', async () => {
  authApi.oauthStart.mockResolvedValue({ authorize_url: AUTHORIZE_URL });
  const button = await openWithYandex();
  fireEvent.click(button);

  await waitFor(() => expect(oauthLib.navigateToProvider).toHaveBeenCalledWith(AUTHORIZE_URL));
  expect(authApi.oauthStart).toHaveBeenCalledTimes(1);
  expect(authApi.oauthStart).toHaveBeenCalledWith('yandex');
  expect(login).not.toHaveBeenCalled();
});

test('во время старта кнопка заблокирована — повторный клик не шлёт второй start', async () => {
  authApi.oauthStart.mockReturnValue(new Promise(() => {}));
  const button = await openWithYandex();
  fireEvent.click(button);
  fireEvent.click(button);
  fireEvent.click(button);

  await waitFor(() => expect(button).toBeDisabled());
  expect(authApi.oauthStart).toHaveBeenCalledTimes(1);
  expect(button).toHaveAttribute('aria-busy', 'true');
});

test('authorize_url не сохраняется в storage', async () => {
  const setItem = jest.spyOn(Storage.prototype, 'setItem');
  authApi.oauthStart.mockResolvedValue({ authorize_url: AUTHORIZE_URL });
  fireEvent.click(await openWithYandex());
  await waitFor(() => expect(oauthLib.navigateToProvider).toHaveBeenCalled());
  expect(setItem).not.toHaveBeenCalled();
  setItem.mockRestore();
});

test.each([
  [{ status: 429 }, 'Слишком много попыток. Попробуйте немного позже.'],
  [{ status: 404, code: 'oauth_provider_unavailable' },
    'Вход через Яндекс сейчас недоступен. Войдите по email и паролю.'],
  [{ status: 500 }, 'Не удалось начать вход через Яндекс. Попробуйте ещё раз.'],
])('ошибка start %j → безопасное сообщение, кнопка снова доступна', async (props, message) => {
  authApi.oauthStart.mockRejectedValue(Object.assign(new Error('RAW internal detail'), props));
  const button = await openWithYandex();
  fireEvent.click(button);

  expect(await screen.findByText(message)).toBeInTheDocument();
  expect(screen.queryByText(/RAW internal/)).toBeNull();
  expect(oauthLib.navigateToProvider).not.toHaveBeenCalled();
  expect(button).toBeEnabled();
});

test.each([
  [{}], [{ authorize_url: '' }], [{ authorize_url: SCRIPT_URL }],
  [{ authorize_url: 'http://oauth.yandex.ru/authorize' }],
])('некорректный authorize_url (%j) → без перехода', async (payload) => {
  authApi.oauthStart.mockResolvedValue(payload);
  fireEvent.click(await openWithYandex());
  expect(await screen.findByText('Не удалось начать вход через Яндекс. Попробуйте ещё раз.'))
    .toBeInTheDocument();
  expect(oauthLib.navigateToProvider).not.toHaveBeenCalled();
});

test('после ошибки старта вход по паролю доступен', async () => {
  authApi.oauthStart.mockRejectedValue(Object.assign(new Error('x'), { status: 500 }));
  fireEvent.click(await openWithYandex());
  await screen.findByText('Не удалось начать вход через Яндекс. Попробуйте ещё раз.');
  await submitPassword();
  expect(mockNavigate).toHaveBeenCalledWith('/dashboard');
});
