import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
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
const SHORT_HINT = 'Используйте почту разрешённого домена';
const INFO = 'Показать разрешённые домены';
const DOMAIN_ERROR = 'Этот домен не поддерживается.';
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
const infoButton = () => screen.getByRole('button', { name: INFO });
const domainsPanel = () => screen.queryByRole('group', { name: 'Разрешённые домены' });

/** Открывает список кнопкой-info и возвращает домены, как их видит пользователь. */
async function listedDomains() {
  await screen.findByText(SHORT_HINT);
  if (!domainsPanel()) fireEvent.click(infoButton());
  return within(domainsPanel()).getAllByRole('listitem').map((li) => li.textContent);
}

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

test('под полем Email — короткая подсказка; полного списка постоянно нет', async () => {
  render(<RegisterForm onSuccess={jest.fn()} />);

  const hint = await screen.findByText(SHORT_HINT);
  expect(hint).toHaveAttribute('id', 'r-email-domains');
  expect(emailInput()).toHaveAttribute('aria-describedby', 'r-email-domains');
  expect(domainsPanel()).toBeNull();
  expect(screen.queryByText('@a.example')).not.toBeVisible();
  expect(screen.queryByText(/Разрешённые домены:/)).toBeNull();
});

test('info-кнопка: доступное имя, aria-expanded/aria-controls; клик открывает список из ответа backend', async () => {
  render(<RegisterForm onSuccess={jest.fn()} />);
  await screen.findByText(SHORT_HINT);

  const info = infoButton();
  expect(info).toHaveAttribute('type', 'button');
  expect(info).toHaveAttribute('aria-expanded', 'false');
  const panelId = info.getAttribute('aria-controls');
  expect(panelId).toBeTruthy();

  fireEvent.click(info);
  expect(info).toHaveAttribute('aria-expanded', 'true');
  const panel = domainsPanel();
  expect(panel).toHaveAttribute('id', panelId);
  expect(panel).toBeVisible();
  expect(within(panel).getByText('Разрешённые домены')).toBeInTheDocument();
  expect(within(panel).getAllByRole('listitem').map((li) => li.textContent))
    .toEqual(['@a.example', '@b.example']);

  // Повторный клик закрывает.
  fireEvent.click(info);
  expect(info).toHaveAttribute('aria-expanded', 'false');
  expect(domainsPanel()).toBeNull();
});

test('Escape закрывает список, не доходит до обработчика модалки и возвращает фокус на кнопку', async () => {
  const modalEscape = jest.fn();
  document.addEventListener('keydown', modalEscape);
  try {
    render(<RegisterForm onSuccess={jest.fn()} />);
    await screen.findByText(SHORT_HINT);
    const info = infoButton();
    info.focus();
    fireEvent.click(info);
    expect(domainsPanel()).not.toBeNull();

    fireEvent.keyDown(info, { key: 'Escape' });
    expect(domainsPanel()).toBeNull();
    expect(info).toHaveAttribute('aria-expanded', 'false');
    expect(info).toHaveFocus();
    expect(modalEscape).not.toHaveBeenCalled();

    // Закрытый список Escape не перехватывает — его получает модалка.
    fireEvent.keyDown(info, { key: 'Escape' });
    expect(modalEscape).toHaveBeenCalledTimes(1);
  } finally {
    document.removeEventListener('keydown', modalEscape);
  }
});

test('клик снаружи закрывает список, клик внутри — нет', async () => {
  render(<RegisterForm onSuccess={jest.fn()} />);
  await screen.findByText(SHORT_HINT);
  fireEvent.click(infoButton());

  fireEvent.mouseDown(within(domainsPanel()).getByText('@a.example'));
  expect(domainsPanel()).not.toBeNull();

  fireEvent.mouseDown(screen.getByLabelText('Пароль'));
  expect(domainsPanel()).toBeNull();
  expect(infoButton()).toHaveAttribute('aria-expanded', 'false');
});

test('неподдерживаемый домен: ошибка у поля и действие, открывающее тот же список', async () => {
  render(<RegisterForm onSuccess={jest.fn()} />);
  await screen.findByText(SHORT_HINT);

  fireEvent.change(emailInput(), { target: { value: 'someone@gmail.example' } });
  expect(screen.queryByText(DOMAIN_ERROR)).toBeNull();      // не во время ввода
  fireEvent.blur(emailInput());

  const error = screen.getByText(DOMAIN_ERROR);
  expect(error).toHaveAttribute('role', 'alert');
  expect(error).toHaveAttribute('id', 'r-email-domain-error');
  expect(emailInput()).toHaveAttribute('aria-invalid', 'true');
  // Формат корректен: описание — ошибка домена и подсказка, без r-email-hint.
  expect(emailInput()).toHaveAttribute('aria-describedby', 'r-email-domain-error r-email-domains');

  const action = screen.getByRole('button', { name: 'Посмотреть разрешённые домены' });
  expect(action).toHaveAttribute('aria-expanded', 'false');
  expect(action.getAttribute('aria-controls')).toBe(infoButton().getAttribute('aria-controls'));
  fireEvent.click(action);
  expect(action).toHaveAttribute('aria-expanded', 'true');
  expect(infoButton()).toHaveAttribute('aria-expanded', 'true');
  expect(within(domainsPanel()).getAllByRole('listitem').map((li) => li.textContent))
    .toEqual(['@a.example', '@b.example']);

  // Правка адреса снимает ошибку до следующей проверки.
  fireEvent.change(emailInput(), { target: { value: 'someone@a.example' } });
  expect(screen.queryByText(DOMAIN_ERROR)).toBeNull();
  expect(emailInput()).not.toHaveAttribute('aria-invalid');
});

test('разрешённый домен (без учёта регистра и пробелов) ошибку не показывает', async () => {
  render(<RegisterForm onSuccess={jest.fn()} />);
  await screen.findByText(SHORT_HINT);
  fireEvent.change(emailInput(), { target: { value: '  Student@A.Example ' } });
  fireEvent.blur(emailInput());
  expect(screen.queryByText(DOMAIN_ERROR)).toBeNull();
  expect(screen.queryByRole('button', { name: 'Посмотреть разрешённые домены' })).toBeNull();
});

test('нейтральный placeholder; ни одного домена в форме, которого не прислал backend', async () => {
  domainsApi.getPublicEmailDomains.mockResolvedValue({ domains: ['zzz.example'] });
  render(<RegisterForm onSuccess={jest.fn()} />);

  expect(await listedDomains()).toEqual(['@zzz.example']);
  expect(emailInput()).toHaveAttribute('placeholder', 'Введите email');
  expect(document.body.textContent).not.toContain('donnu');
  expect(document.body.innerHTML).not.toContain('donnu');
});

test('при невалидном email к описанию добавляется и сообщение об ошибке', async () => {
  render(<RegisterForm onSuccess={jest.fn()} />);
  await screen.findByText(SHORT_HINT);

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

  expect(screen.queryByText(SHORT_HINT)).toBeNull();
  expect(screen.queryByRole('button', { name: INFO })).toBeNull();
  expect(emailInput()).not.toHaveAttribute('aria-describedby');

  fillAndSubmit();
  await screen.findByRole('group', { name: 'Код подтверждения' });
  expect(authApi.registerInit).toHaveBeenCalledWith({
    name: 'Иван Тестов', email: EMAIL, password: 'SecurePass42!',
  });
});

test('список не блокирует форму: решение о домене принимает backend', async () => {
  render(<RegisterForm onSuccess={jest.fn()} />);
  await screen.findByText(SHORT_HINT);

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
  await screen.findByText(SHORT_HINT);

  fillAndSubmit();

  expect(await screen.findByText(SERVER_MESSAGE)).toHaveAttribute('role', 'alert');
  // список не спорит со свежим текстом ошибки: перечитан
  await waitFor(() => expect(domainsApi.getPublicEmailDomains).toHaveBeenCalledTimes(2));
  await waitFor(async () => expect(await listedDomains()).toEqual(['@b.example']));
  // адрес проверен при отправке: по свежему списку его домен не поддерживается
  expect(screen.getByText(DOMAIN_ERROR)).toBeInTheDocument();
  // остались на шаге формы, код не запрашивался
  expect(screen.queryByRole('group', { name: 'Код подтверждения' })).toBeNull();
  expect(authApi.registerConfirm).not.toHaveBeenCalled();
});

test('init: ошибка не 422 (например, сбой письма) подсказку не перечитывает', async () => {
  authApi.registerInit.mockRejectedValue(rejected('Не удалось отправить письмо. Попробуйте позже.', 500));
  render(<RegisterForm onSuccess={jest.fn()} />);
  await screen.findByText(SHORT_HINT);

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
  await screen.findByText(SHORT_HINT);

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
  expect(await listedDomains()).toEqual(['@b.example']);
  expect(emailInput()).toHaveValue(EMAIL);            // введённые данные сохранены
});

test('confirm: ошибка неверного кода (400) подсказку не перечитывает', async () => {
  authApi.registerConfirm.mockRejectedValue(rejected('Неверный код. Осталось попыток: 4', 400));
  render(<RegisterForm onSuccess={jest.fn()} />);
  await screen.findByText(SHORT_HINT);

  fillAndSubmit();
  await screen.findByRole('group', { name: 'Код подтверждения' });
  pasteCode();

  expect(await screen.findByText('Неверный код. Осталось попыток: 4')).toBeInTheDocument();
  expect(domainsApi.getPublicEmailDomains).toHaveBeenCalledTimes(1);
});

// ── шаг кода: автовход, его сбой, повторная отправка, двойное подтверждение ──

test('успешный confirm → автоматический вход и кабинет', async () => {
  login.mockResolvedValue({});
  const onSuccess = jest.fn();
  render(<RegisterForm onSuccess={onSuccess} />);
  await settled();
  fillAndSubmit();
  await screen.findByRole('group', { name: 'Код подтверждения' });
  pasteCode('012345');
  await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/dashboard'));
  expect(authApi.registerConfirm).toHaveBeenCalledWith({ email: EMAIL, code: '012345' });
  expect(login).toHaveBeenCalledWith({ email: EMAIL, password: 'SecurePass42!' });
  expect(onSuccess).toHaveBeenCalled();
});

test('сбой автовхода после успешного confirm → onRegisteredWithoutLogin(email), не шаг кода', async () => {
  login.mockRejectedValue(new Error('Сеть недоступна'));
  const onRegisteredWithoutLogin = jest.fn();
  const onSuccess = jest.fn();
  render(<RegisterForm onSuccess={onSuccess} onRegisteredWithoutLogin={onRegisteredWithoutLogin} />);
  await settled();
  fillAndSubmit();
  await screen.findByRole('group', { name: 'Код подтверждения' });
  pasteCode();
  await waitFor(() => expect(onRegisteredWithoutLogin).toHaveBeenCalledWith(EMAIL));
  expect(onSuccess).not.toHaveBeenCalled();
  expect(mockNavigate).not.toHaveBeenCalled();
  // К использованному коду не вернуться: форма на первом шаге, пароли стёрты.
  expect(screen.queryByRole('group', { name: 'Код подтверждения' })).toBeNull();
  expect(screen.getByLabelText('Пароль')).toHaveValue('');
  expect(screen.getByLabelText('Повторите пароль')).toHaveValue('');
  expect(screen.queryByText('Сеть недоступна')).toBeNull();
});

test('один код — один confirm: вставка, кнопка и Enter до ответа не дублируют запрос', async () => {
  let resolve;
  authApi.registerConfirm.mockReturnValue(new Promise((r) => { resolve = r; }));
  login.mockResolvedValue({});
  render(<RegisterForm onSuccess={jest.fn()} />);
  await settled();
  fillAndSubmit();
  await screen.findByRole('group', { name: 'Код подтверждения' });
  pasteCode();
  const button = screen.getByRole('button', { name: 'Подтвердить' });
  fireEvent.click(button);
  fireEvent.submit(screen.getByRole('form', { name: 'Подтверждение регистрации' }));
  await waitFor(() => expect(authApi.registerConfirm).toHaveBeenCalledTimes(1));
  fireEvent.click(screen.getByRole('button', { name: 'Проверяем…' }));
  resolve({ message: 'ok' });
  await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/dashboard'));
  expect(authApi.registerConfirm).toHaveBeenCalledTimes(1);
});

test('повторная отправка кода после таймера — тот же init', async () => {
  jest.useFakeTimers();
  try {
    render(<RegisterForm onSuccess={jest.fn()} />);
    await act(async () => { await Promise.resolve(); });
    fillAndSubmit();
    await act(async () => { await Promise.resolve(); });
    await screen.findByRole('group', { name: 'Код подтверждения' });
    expect(screen.getByText(/Отправить повторно через/)).toBeInTheDocument();
    // Отсчёт — цепочка секундных таймеров: каждый следующий ставится после рендера.
    for (let i = 0; i < 61; i += 1) {
      act(() => { jest.advanceTimersByTime(1000); });
    }
    fireEvent.click(screen.getByRole('button', { name: 'Отправить повторно' }));
    await act(async () => { await Promise.resolve(); });
    expect(authApi.registerInit).toHaveBeenCalledTimes(2);
    expect(authApi.registerInit).toHaveBeenLastCalledWith({
      name: 'Иван Тестов', email: EMAIL, password: 'SecurePass42!',
    });
  } finally {
    jest.useRealTimers();
  }
});
