import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import RegisterForm from './RegisterForm';
import * as AuthContext from '../AuthContext';
import * as authApi from '../../../api/auth.api';
import * as configApi from '../../../api/config.api';
import * as domainsApi from '../../../api/domains.api';

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
// emailDomainNamesOf остаётся настоящим (requireActual): автомок вернул бы undefined.
jest.mock('../../../api/domains.api', () => ({
  ...jest.requireActual('../../../api/domains.api'),
  getPublicEmailDomains: jest.fn(),
}));

const login = jest.fn();
const EMAIL = 'student@a.example';

// Тексты отказа по домену формирует backend (из активного allowlist БД); форма
// выводит их как есть. Домены здесь — синтетические, в коде формы их нет.
const SERVER_MESSAGE =
  'Для регистрации по электронной почте используйте адрес с одним из разрешённых доменов: @b.example.';
const hintText = (...domains) => `Разрешённые домены: ${domains.map((d) => `@${d}`).join(', ')}`;
const rejected = (message, status = 422) => Object.assign(new Error(message), { status });

beforeEach(() => {
  jest.clearAllMocks();
  AuthContext.useAuth.mockReturnValue({ login });
  configApi.getPublicConfig.mockResolvedValue({ social_providers: ['yandex'] });
  domainsApi.getPublicEmailDomains.mockResolvedValue({ domains: ['a.example', 'b.example'] });
  authApi.registerInit.mockResolvedValue({ message: 'ok' });
  authApi.registerConfirm.mockResolvedValue({ message: 'ok' });
});

const emailInput = () => screen.getByLabelText('Email');

function fillAndSubmit(email = EMAIL) {
  fireEvent.change(screen.getByLabelText('Имя'), { target: { value: 'Иван Тестов' } });
  fireEvent.change(emailInput(), { target: { value: email } });
  fireEvent.change(screen.getByLabelText('Пароль'), { target: { value: 'SecurePass42!' } });
  fireEvent.change(screen.getByLabelText('Повторите пароль'), { target: { value: 'SecurePass42!' } });
  fireEvent.click(screen.getByRole('checkbox'));
  fireEvent.click(screen.getByRole('button', { name: 'Продолжить' }));
}

const pasteCode = (code = '123456') => fireEvent.paste(
  screen.getByLabelText('Цифра 1'),
  { clipboardData: { getData: () => code } },
);

// Запрос доменов отправлен и его промис-цепочка отработала (макрозадача).
async function settled() {
  await waitFor(() => expect(domainsApi.getPublicEmailDomains).toHaveBeenCalled());
  await act(async () => { await new Promise((resolve) => { setTimeout(resolve, 0); }); });
}

// ── подсказка: домены только из ответа backend ───────────────────────────────

test('подсказка под полем Email: домены из ответа backend, связана через aria-describedby', async () => {
  render(<RegisterForm onSuccess={jest.fn()} />);

  const hint = await screen.findByText(hintText('a.example', 'b.example'));
  expect(hint).toHaveAttribute('id', 'r-email-domains');
  expect(emailInput()).toHaveAttribute('aria-describedby', 'r-email-domains');
});

test('нейтральный placeholder; ни одного домена в форме, которого не прислал backend', async () => {
  domainsApi.getPublicEmailDomains.mockResolvedValue({ domains: ['zzz.example'] });
  render(<RegisterForm onSuccess={jest.fn()} />);

  await screen.findByText(hintText('zzz.example'));
  expect(emailInput()).toHaveAttribute('placeholder', 'Введите email');
  expect(document.body.textContent).not.toContain('donnu');
  expect(document.body.innerHTML).not.toContain('donnu');
});

test('при невалидном email к описанию добавляется и сообщение об ошибке', async () => {
  render(<RegisterForm onSuccess={jest.fn()} />);
  await screen.findByText(hintText('a.example', 'b.example'));

  fireEvent.change(emailInput(), { target: { value: 'not-an-email' } });
  fireEvent.blur(emailInput());
  expect(emailInput()).toHaveAttribute('aria-describedby', 'r-email-hint r-email-domains');
});

test.each([
  ['список пуст', () => domainsApi.getPublicEmailDomains.mockResolvedValue({ domains: [] })],
  ['запрос упал', () => domainsApi.getPublicEmailDomains.mockRejectedValue(new Error('network'))],
  ['мусор в ответе', () => domainsApi.getPublicEmailDomains.mockResolvedValue({ domains: 'a.example' })],
])('подсказки нет, форма работает как обычно: %s', async (_name, arrange) => {
  arrange();
  render(<RegisterForm onSuccess={jest.fn()} />);
  await settled();

  expect(screen.queryByText(/Разрешённые домены/)).toBeNull();
  expect(emailInput()).not.toHaveAttribute('aria-describedby');

  fillAndSubmit();
  await screen.findByRole('group', { name: 'Код подтверждения' });
  expect(authApi.registerInit).toHaveBeenCalledWith({
    name: 'Иван Тестов', email: EMAIL, password: 'SecurePass42!',
  });
});

test('список не блокирует форму: решение о домене принимает backend', async () => {
  render(<RegisterForm onSuccess={jest.fn()} />);
  await screen.findByText(hintText('a.example', 'b.example'));

  fillAndSubmit('someone@not-in-list.example');
  await screen.findByRole('group', { name: 'Код подтверждения' });
  expect(authApi.registerInit).toHaveBeenCalledWith(
    expect.objectContaining({ email: 'someone@not-in-list.example' }),
  );
});

// ── отказ по домену на init ──────────────────────────────────────────────────

test('init: текст отказа выводится как пришёл с backend, подсказка перечитывается', async () => {
  domainsApi.getPublicEmailDomains
    .mockResolvedValueOnce({ domains: ['a.example', 'b.example'] })
    .mockResolvedValueOnce({ domains: ['b.example'] });
  authApi.registerInit.mockRejectedValue(rejected(SERVER_MESSAGE));
  render(<RegisterForm onSuccess={jest.fn()} />);
  await screen.findByText(hintText('a.example', 'b.example'));

  fillAndSubmit();

  expect(await screen.findByText(SERVER_MESSAGE)).toHaveAttribute('role', 'alert');
  // подсказка не спорит со свежим текстом ошибки: список перечитан
  expect(await screen.findByText(hintText('b.example'))).toBeInTheDocument();
  expect(screen.queryByText(hintText('a.example', 'b.example'))).toBeNull();
  expect(domainsApi.getPublicEmailDomains).toHaveBeenCalledTimes(2);
  // остались на шаге формы, код не запрашивался
  expect(screen.queryByRole('group', { name: 'Код подтверждения' })).toBeNull();
  expect(authApi.registerConfirm).not.toHaveBeenCalled();
});

test('init: ошибка не 422 (например, сбой письма) подсказку не перечитывает', async () => {
  authApi.registerInit.mockRejectedValue(rejected('Не удалось отправить письмо. Попробуйте позже.', 500));
  render(<RegisterForm onSuccess={jest.fn()} />);
  await screen.findByText(hintText('a.example', 'b.example'));

  fillAndSubmit();

  expect(await screen.findByText('Не удалось отправить письмо. Попробуйте позже.')).toBeInTheDocument();
  expect(domainsApi.getPublicEmailDomains).toHaveBeenCalledTimes(1);
});

// ── отказ по домену на confirm (домен отключили между шагами) ────────────────

test('confirm: тот же текст отказа, вход не выполняется, после «Изменить данные» подсказка свежая', async () => {
  domainsApi.getPublicEmailDomains
    .mockResolvedValueOnce({ domains: ['a.example', 'b.example'] })
    .mockResolvedValueOnce({ domains: ['b.example'] });
  authApi.registerConfirm.mockRejectedValue(rejected(SERVER_MESSAGE));
  render(<RegisterForm onSuccess={jest.fn()} />);
  await screen.findByText(hintText('a.example', 'b.example'));

  fillAndSubmit();
  await screen.findByRole('group', { name: 'Код подтверждения' });
  pasteCode();

  await waitFor(() => expect(authApi.registerConfirm).toHaveBeenCalledWith({
    email: EMAIL, code: '123456',
  }));
  expect(await screen.findByText(SERVER_MESSAGE)).toHaveAttribute('role', 'alert');
  expect(login).not.toHaveBeenCalled();
  expect(mockNavigate).not.toHaveBeenCalled();
  await waitFor(() => expect(domainsApi.getPublicEmailDomains).toHaveBeenCalledTimes(2));

  fireEvent.click(screen.getByRole('button', { name: '← Изменить данные' }));
  expect(await screen.findByText(hintText('b.example'))).toBeInTheDocument();
  expect(emailInput()).toHaveValue(EMAIL);            // введённые данные сохранены
});

test('confirm: ошибка неверного кода (400) подсказку не перечитывает', async () => {
  authApi.registerConfirm.mockRejectedValue(rejected('Неверный код. Осталось попыток: 4', 400));
  render(<RegisterForm onSuccess={jest.fn()} />);
  await screen.findByText(hintText('a.example', 'b.example'));

  fillAndSubmit();
  await screen.findByRole('group', { name: 'Код подтверждения' });
  pasteCode();

  expect(await screen.findByText('Неверный код. Осталось попыток: 4')).toBeInTheDocument();
  expect(domainsApi.getPublicEmailDomains).toHaveBeenCalledTimes(1);
});
