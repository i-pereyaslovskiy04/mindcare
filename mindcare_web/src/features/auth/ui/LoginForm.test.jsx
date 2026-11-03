import {
  act, createEvent, render, screen, fireEvent, waitFor,
} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
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

// ── «Забыли пароль?»: blur-проверка поля не отменяет клик ───────────────────
//
// Регрессия: фокус в пустом Email → нажатие на ссылку → blur вставлял ошибку
// выше ссылки, ссылка сдвигалась между mousedown и mouseup, и клик терялся.
// В jsdom нет раскладки, поэтому проверяется механизм: mousedown по ссылке не
// уводит фокус из поля, blur и ошибка не появляются до активации.

function renderLoginWithForgot() {
  const onForgotPassword = jest.fn();
  render(<LoginForm onSuccess={jest.fn()} onForgotPassword={onForgotPassword} />);
  return { onForgotPassword, forgot: screen.getByRole('button', { name: 'Забыли пароль?' }) };
}

describe('«Забыли пароль?»', () => {
  test('нажатие мыши не уводит фокус из пустого Email: одна активация, без ошибки', () => {
    const { onForgotPassword, forgot } = renderLoginWithForgot();
    const email = screen.getByLabelText('Email');
    email.focus();

    const mouseDown = createEvent.mouseDown(forgot);
    fireEvent(forgot, mouseDown);
    expect(mouseDown.defaultPrevented).toBe(true);
    expect(email).toHaveFocus();

    userEvent.click(forgot);                         // mousedown → mouseup → click
    expect(onForgotPassword).toHaveBeenCalledTimes(1);
    expect(email).toHaveFocus();                     // blur не было
    expect(email).not.toHaveAttribute('aria-invalid');
  });

  test('невалидный Email и уже показанная ошибка — ссылка срабатывает с первого клика', () => {
    const { onForgotPassword, forgot } = renderLoginWithForgot();
    const email = screen.getByLabelText('Email');
    userEvent.type(email, 'abc');
    userEvent.click(forgot);
    expect(onForgotPassword).toHaveBeenCalledTimes(1);

    fireEvent.blur(email);                           // ошибка уже видна
    expect(email).toHaveAttribute('aria-invalid', 'true');
    act(() => { screen.getByLabelText('Пароль').focus(); });   // blur Email — внутри act
    userEvent.click(forgot);
    expect(onForgotPassword).toHaveBeenCalledTimes(2);
  });

  test('клавиатура: Enter и Space на кнопке открывают восстановление', () => {
    const { onForgotPassword, forgot } = renderLoginWithForgot();
    expect(forgot).toHaveAttribute('type', 'button');
    forgot.focus();
    userEvent.type(forgot, '{enter}', { skipClick: true });
    expect(onForgotPassword).toHaveBeenCalledTimes(1);
    userEvent.type(forgot, '{space}', { skipClick: true });
    expect(onForgotPassword).toHaveBeenCalledTimes(2);
  });

  test('blur-проверка Email осталась: уход из пустого поля показывает ошибку', () => {
    renderLoginWithForgot();
    const email = screen.getByLabelText('Email');
    email.focus();
    userEvent.tab();
    expect(email).toHaveAttribute('aria-invalid', 'true');
    expect(email).toHaveAccessibleDescription('Введите корректный email');
  });

  test('ссылка не отправляет форму входа', () => {
    const { forgot } = renderLoginWithForgot();
    userEvent.click(forgot);
    expect(login).not.toHaveBeenCalled();
    expect(mockNavigate).not.toHaveBeenCalled();
  });
});
