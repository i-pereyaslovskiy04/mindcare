import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import AuthModal from './AuthModal';
import * as AuthContext from '../AuthContext';
import * as authApi from '../../../api/auth.api';
import * as configApi from '../../../api/config.api';

jest.mock('react-router-dom', () => ({
  useNavigate: () => jest.fn(),
  Link: ({ to, children, ...rest }) => <a href={to} {...rest}>{children}</a>,
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
jest.mock('../forgot-password/ForgotPasswordModal', () => () => null);

beforeEach(() => {
  jest.clearAllMocks();
  AuthContext.useAuth.mockReturnValue({ login: jest.fn() });
  configApi.getPublicConfig.mockResolvedValue({ social_providers: ['yandex'] });
  authApi.registerInit.mockResolvedValue({ message: 'ok' });
});

async function openRegisterTab() {
  render(<AuthModal isOpen onClose={jest.fn()} />);
  // Дождаться списка провайдеров (SocialButtons) до действий пользователя.
  await waitFor(() => expect(screen.getByRole('button', { name: 'Войти через Яндекс' })).toBeEnabled());
  fireEvent.click(screen.getByRole('tab', { name: 'Регистрация' }));
}

// Скрытая вкладка «Вход» остаётся в DOM — запросы только внутри видимой панели.
const registerPanel = () => screen.getByRole('tabpanel', { name: 'Регистрация' });

function fillAndSubmit() {
  const value = (text) => ({ target: { value: text } });
  fireEvent.change(within(registerPanel()).getByLabelText('Имя'), value('Иван Студентов'));
  fireEvent.change(within(registerPanel()).getByLabelText('Email'), value('student@donnu.ru'));
  fireEvent.change(within(registerPanel()).getByLabelText('Пароль'), value('SecurePass42!'));
  fireEvent.change(within(registerPanel()).getByLabelText('Повторите пароль'), value('SecurePass42!'));
  fireEvent.click(within(registerPanel()).getByRole('checkbox'));
  fireEvent.click(within(registerPanel()).getByRole('button', { name: 'Продолжить' }));
}

test('основная форма: вкладки «Вход | Регистрация» есть', async () => {
  await openRegisterTab();
  expect(screen.getByRole('tablist')).toBeInTheDocument();
  expect(screen.getByRole('tab', { name: 'Вход' })).toBeInTheDocument();
  expect(within(registerPanel()).getByLabelText('Имя')).toBeInTheDocument();
});

test('шаг кода обычной регистрации: общий шаг без вкладок, «Изменить данные» возвращает их', async () => {
  await openRegisterTab();
  fillAndSubmit();

  await screen.findByRole('group', { name: 'Код подтверждения' });
  expect(screen.getByRole('heading', { name: 'Подтверждение регистрации' })).toBeInTheDocument();
  expect(screen.getByText('student@donnu.ru')).toBeInTheDocument();
  expect(screen.queryByRole('tablist')).toBeNull();
  expect(screen.queryByRole('tab')).toBeNull();
  expect(screen.queryByRole('checkbox')).toBeNull();   // согласие уже принято на шаге 1

  fireEvent.click(screen.getByRole('button', { name: '← Изменить данные' }));
  expect(screen.getByRole('tablist')).toBeInTheDocument();
  expect(within(registerPanel()).getByLabelText('Имя')).toHaveValue('Иван Студентов');
});
