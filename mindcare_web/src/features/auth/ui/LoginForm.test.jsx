import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import LoginForm from './LoginForm';
import RegisterForm from './RegisterForm';
import * as AuthContext from '../AuthContext';
import * as authApi from '../../../api/auth.api';
import * as configApi from '../../../api/config.api';

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

const login = jest.fn();
const AUTHORIZE_URL = 'https://oauth.yandex.ru/authorize?state=SYNTHETIC';


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

// ── social-блок — в AuthModal, не в формах (один на обе вкладки) ────────────

const FORMS = [
  ['LoginForm', () => renderLogin()],
  ['RegisterForm', () => render(<RegisterForm onSuccess={jest.fn()} />)],
];

test.each(FORMS)('%s не рендерит VK/Яндекс и не запрашивает конфиг провайдеров', async (_name, renderForm) => {
  renderForm();
  expect(screen.queryByRole('button', { name: /Продолжить через/ })).toBeNull();
  expect(screen.queryByText('Продолжить через')).toBeNull();
  expect(screen.queryByText('или по email')).toBeNull();
  expect(configApi.getPublicConfig).not.toHaveBeenCalled();
  // Отложенные обновления формы (список доменов) — внутри act.
  expect(await screen.findByLabelText('Пароль')).toBeInTheDocument();
});

test('вход по паролю не зависит от провайдеров: oauthStart не вызывается', async () => {
  renderLogin();
  await submitPassword();
  expect(mockNavigate).toHaveBeenCalledWith('/dashboard');
  expect(authApi.oauthStart).not.toHaveBeenCalled();
});

test('обычная форма регистрации по email не изменилась: есть поля пароля', async () => {
  render(<RegisterForm onSuccess={jest.fn()} />);
  expect(await screen.findByLabelText('Пароль')).toBeInTheDocument();
  expect(screen.getByLabelText('Повторите пароль')).toBeInTheDocument();
});
