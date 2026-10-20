import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import LoginForm from './LoginForm';
import RegisterForm from './RegisterForm';
import * as AuthContext from '../AuthContext';
import * as authApi from '../../../api/auth.api';
import * as configApi from '../../../api/config.api';
import * as oauthLib from '../lib/oauthCallback';

const mockNavigate = jest.fn();
jest.mock('react-router-dom', () => ({
  useNavigate: () => mockNavigate,
}), { virtual: true });
jest.mock('../AuthContext', () => ({ useAuth: jest.fn() }));
jest.mock('../../../api/auth.api', () => ({
  oauthStart: jest.fn(),
  registerInit: jest.fn(),
  registerConfirm: jest.fn(),
}));
jest.mock('../../../api/config.api', () => ({
  ...jest.requireActual('../../../api/config.api'),
  getPublicConfig: jest.fn(),
}));
// RegisterForm читает публичный список доменов; здесь он не важен — пустой.
// Обычная функция, а не jest.fn(): resetMocks (CRA) обнулил бы её реализацию.
jest.mock('../../../api/domains.api', () => ({
  ...jest.requireActual('../../../api/domains.api'),
  getPublicEmailDomains: () => Promise.resolve({ domains: [] }),
}));
jest.mock('../lib/oauthCallback', () => ({
  ...jest.requireActual('../lib/oauthCallback'),
  navigateToProvider: jest.fn(),
}));

const login = jest.fn();
const AUTHORIZE_URL = 'https://oauth.yandex.ru/authorize?state=SYNTHETIC';

const yandexButton = () => screen.getByRole('button', { name: 'Войти через Яндекс' });
const vkButton = () => screen.getByRole('button', { name: /ВКонтакте/ });

beforeEach(() => {
  jest.clearAllMocks();
  login.mockResolvedValue({ roles: ['psychologist', 'supervisor'] });
  AuthContext.useAuth.mockReturnValue({ login });
  configApi.getPublicConfig.mockResolvedValue({ social_providers: ['yandex'] });
  authApi.oauthStart.mockResolvedValue({ authorize_url: AUTHORIZE_URL });
});

function renderLogin() {
  return render(<LoginForm onSuccess={jest.fn()} onForgotPassword={jest.fn()} />);
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
  renderLogin();
  await submitPassword();
  expect(mockNavigate).toHaveBeenCalledWith('/dashboard');
});

// ── соцкнопки: одинаково на обеих вкладках (Stage Social Auth 4) ─────────────

const FORMS = [
  ['LoginForm', () => renderLogin()],
  ['RegisterForm', () => render(<RegisterForm onSuccess={jest.fn()} />)],
];

describe.each(FORMS)('%s — быстрая авторизация', (_name, renderForm) => {
  test('есть VK (disabled) и Яндекс, Telegram нет', async () => {
    renderForm();
    await waitFor(() => expect(yandexButton()).toBeEnabled());
    expect(vkButton()).toBeDisabled();
    expect(screen.queryByText(/Telegram/i)).toBeNull();
    expect(screen.queryByRole('button', { name: /Telegram/i })).toBeNull();
  });

  test('Яндекс запускает один и тот же oauthStart("yandex")', async () => {
    renderForm();
    await waitFor(() => expect(yandexButton()).toBeEnabled());
    fireEvent.click(yandexButton());
    await waitFor(() => expect(oauthLib.navigateToProvider).toHaveBeenCalledWith(AUTHORIZE_URL));
    expect(authApi.oauthStart).toHaveBeenCalledTimes(1);
    expect(authApi.oauthStart).toHaveBeenCalledWith('yandex');
    expect(login).not.toHaveBeenCalled();
    expect(authApi.registerInit).not.toHaveBeenCalled();
  });

  test('клик по VK ничего не отправляет', async () => {
    renderForm();
    await waitFor(() => expect(yandexButton()).toBeEnabled());
    fireEvent.click(vkButton());
    expect(authApi.oauthStart).not.toHaveBeenCalled();
  });

  test('Яндекс недоступен на backend → кнопка видна, но disabled', async () => {
    configApi.getPublicConfig.mockResolvedValue({ social_providers: [] });
    renderForm();
    await waitFor(() => expect(configApi.getPublicConfig).toHaveBeenCalled());
    expect(yandexButton()).toBeDisabled();
  });
});

test('конфиг недоступен → вход по паролю работает как обычно', async () => {
  configApi.getPublicConfig.mockRejectedValue(new Error('network'));
  renderLogin();
  await waitFor(() => expect(configApi.getPublicConfig).toHaveBeenCalled());
  await submitPassword();
  expect(mockNavigate).toHaveBeenCalledWith('/dashboard');
});

test('после ошибки старта Яндекса вход по паролю доступен', async () => {
  authApi.oauthStart.mockRejectedValue(Object.assign(new Error('x'), { status: 500 }));
  renderLogin();
  await waitFor(() => expect(yandexButton()).toBeEnabled());
  fireEvent.click(yandexButton());
  await screen.findByText('Не удалось начать вход через Яндекс. Попробуйте ещё раз.');
  await submitPassword();
  expect(mockNavigate).toHaveBeenCalledWith('/dashboard');
});

test('обычная форма регистрации по email не изменилась: есть поля пароля', async () => {
  render(<RegisterForm onSuccess={jest.fn()} />);
  await waitFor(() => expect(yandexButton()).toBeEnabled());
  expect(screen.getByLabelText('Пароль')).toBeInTheDocument();
  expect(screen.getByLabelText('Повторите пароль')).toBeInTheDocument();
});
