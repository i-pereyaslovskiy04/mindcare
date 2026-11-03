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
const SHORT_HINT = 'Почта должна быть на разрешённом домене';
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
const tooltip = () => screen.queryByRole('tooltip');
// Домены в tooltip — текстом через «·» (без отдельных плашек).
const domainsOf = (tip) => tip.textContent.replace('Разрешённые домены', '')
  .split('·').map((part) => part.replace(/\s+/g, ' ').trim()).filter(Boolean);

/** Открывает tooltip кнопкой-info (click/tap) и возвращает домены, как их видит пользователь. */
async function listedDomains() {
  const info = await screen.findByRole('button', { name: INFO });
  if (!tooltip()) fireEvent.click(info);
  return domainsOf(tooltip());
}

function fillAndSubmit(email = EMAIL) {
  fireEvent.change(screen.getByLabelText('ФИО'), { target: { value: 'Иван Тестов' } });
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
  expect(tooltip()).toBeNull();
  expect(screen.getByText(/@a\.example/)).not.toBeVisible();
  expect(screen.queryByText(/Разрешённые домены:/)).toBeNull();
});

test('tooltip — портал поверх интерфейса, не в потоке формы; список из ответа backend', async () => {
  const { container } = render(<RegisterForm onSuccess={jest.fn()} />);
  await screen.findByText(SHORT_HINT);
  fireEvent.mouseEnter(infoButton());

  const tip = tooltip();
  expect(tip).toBeVisible();
  expect(container).not.toContainElement(tip);
  expect(document.body).toContainElement(tip);
  expect(tip).toHaveStyle({ zIndex: '2100' });
  expect(tip).toHaveTextContent('Разрешённые домены');
  expect(domainsOf(tip)).toEqual(['@a.example', '@b.example']);
  // Без отдельных плашек: обычный текст, не список элементов.
  expect(within(tip).queryAllByRole('listitem')).toHaveLength(0);
});

test('info-кнопка: доступное имя, aria-expanded/aria-controls/aria-describedby на tooltip', async () => {
  render(<RegisterForm onSuccess={jest.fn()} />);
  await screen.findByText(SHORT_HINT);

  const info = infoButton();
  expect(info).toHaveAttribute('type', 'button');
  expect(info).toHaveAttribute('aria-expanded', 'false');
  const tipId = info.getAttribute('aria-controls');
  expect(tipId).toBeTruthy();
  expect(info).toHaveAttribute('aria-describedby', tipId);
  // Список доступен скринридеру и при закрытом tooltip — как описание кнопки.
  expect(info).toHaveAccessibleDescription(/@a\.example.*@b\.example/);

  fireEvent.click(info);
  expect(info).toHaveAttribute('aria-expanded', 'true');
  expect(tooltip()).toHaveAttribute('id', tipId);
});

test('hover открывает tooltip, уход мыши закрывает', async () => {
  render(<RegisterForm onSuccess={jest.fn()} />);
  await screen.findByText(SHORT_HINT);
  const info = infoButton();

  fireEvent.mouseEnter(info);
  expect(tooltip()).toBeVisible();
  expect(info).toHaveAttribute('aria-expanded', 'true');

  fireEvent.mouseLeave(info);
  await waitFor(() => expect(tooltip()).toBeNull());
  expect(info).toHaveAttribute('aria-expanded', 'false');
});

test('указатель можно перевести с кнопки на tooltip — он не закрывается', async () => {
  render(<RegisterForm onSuccess={jest.fn()} />);
  await screen.findByText(SHORT_HINT);
  const info = infoButton();

  fireEvent.mouseEnter(info);
  fireEvent.mouseLeave(info);
  fireEvent.mouseEnter(tooltip());
  await act(async () => { await new Promise((resolve) => { setTimeout(resolve, 200); }); });
  expect(tooltip()).toBeVisible();

  fireEvent.mouseLeave(tooltip());
  await waitFor(() => expect(tooltip()).toBeNull());
});

test('фокус с клавиатуры открывает tooltip, blur закрывает', async () => {
  render(<RegisterForm onSuccess={jest.fn()} />);
  await screen.findByText(SHORT_HINT);
  const info = infoButton();

  fireEvent.focus(info);
  expect(tooltip()).toBeVisible();
  fireEvent.blur(info);
  expect(tooltip()).toBeNull();
});

test('tap/click открывает и закрепляет tooltip, повторный — закрывает', async () => {
  render(<RegisterForm onSuccess={jest.fn()} />);
  await screen.findByText(SHORT_HINT);
  const info = infoButton();

  // Первый tap: эмулированный mouseenter, mousedown (фокус не клавиатурный), click.
  fireEvent.mouseEnter(info);
  fireEvent.mouseDown(info);
  fireEvent.focus(info);
  fireEvent.click(info);
  expect(tooltip()).toBeVisible();
  // Закреплён: уход мыши его не закрывает.
  fireEvent.mouseLeave(info);
  await act(async () => { await new Promise((resolve) => { setTimeout(resolve, 200); }); });
  expect(tooltip()).toBeVisible();

  // Второй tap.
  fireEvent.mouseDown(info);
  fireEvent.click(info);
  expect(tooltip()).toBeNull();
  expect(info).toHaveAttribute('aria-expanded', 'false');
});

test('клик или tap снаружи закрывает tooltip, нажатие внутри — нет', async () => {
  render(<RegisterForm onSuccess={jest.fn()} />);
  await screen.findByText(SHORT_HINT);
  fireEvent.click(infoButton());

  fireEvent.mouseDown(tooltip());
  expect(tooltip()).toBeVisible();

  fireEvent.mouseDown(screen.getByLabelText('Пароль'));
  expect(tooltip()).toBeNull();

  fireEvent.click(infoButton());
  fireEvent.touchStart(screen.getByLabelText('Пароль'));
  expect(tooltip()).toBeNull();
});

test('Escape закрывает tooltip, не доходит до обработчика модалки, фокус остаётся на кнопке', async () => {
  const modalEscape = jest.fn();
  document.addEventListener('keydown', modalEscape);
  try {
    render(<RegisterForm onSuccess={jest.fn()} />);
    await screen.findByText(SHORT_HINT);
    const info = infoButton();
    act(() => { info.focus(); });                       // фокус с клавиатуры
    expect(tooltip()).toBeVisible();

    fireEvent.keyDown(info, { key: 'Escape' });
    expect(tooltip()).toBeNull();
    expect(info).toHaveAttribute('aria-expanded', 'false');
    expect(info).toHaveFocus();
    expect(modalEscape).not.toHaveBeenCalled();

    // Закрытый tooltip Escape не перехватывает — его получает модалка.
    fireEvent.keyDown(info, { key: 'Escape' });
    expect(modalEscape).toHaveBeenCalledTimes(1);
  } finally {
    document.removeEventListener('keydown', modalEscape);
  }
});

test('неподдерживаемый домен: короткая ошибка в той же строке и тот же tooltip', async () => {
  render(<RegisterForm onSuccess={jest.fn()} />);
  await screen.findByText(SHORT_HINT);
  const info = infoButton();

  fireEvent.change(emailInput(), { target: { value: 'someone@gmail.example' } });
  expect(screen.queryByText(DOMAIN_ERROR)).toBeNull();      // не во время ввода
  fireEvent.blur(emailInput());

  const error = screen.getByText(DOMAIN_ERROR);
  expect(error).toHaveAttribute('role', 'alert');
  expect(error).toHaveAttribute('id', 'r-email-domain-error');
  expect(screen.queryByText(SHORT_HINT)).toBeNull();        // ошибка вместо подсказки
  expect(emailInput()).toHaveAttribute('aria-invalid', 'true');
  expect(emailInput()).toHaveAttribute('aria-describedby', 'r-email-domain-error');
  // Отдельного раскрывающегося блока и второй кнопки нет — та же info-кнопка.
  expect(screen.getAllByRole('button', { name: INFO })).toHaveLength(1);
  expect(infoButton()).toBe(info);

  fireEvent.click(info);
  expect(domainsOf(tooltip())).toEqual(['@a.example', '@b.example']);

  // Правка адреса снимает ошибку до следующей проверки.
  fireEvent.change(emailInput(), { target: { value: 'someone@a.example' } });
  expect(screen.queryByText(DOMAIN_ERROR)).toBeNull();
  expect(screen.getByText(SHORT_HINT)).toBeInTheDocument();
  expect(emailInput()).not.toHaveAttribute('aria-invalid');
});

test('разрешённый домен (без учёта регистра и пробелов) ошибку не показывает', async () => {
  render(<RegisterForm onSuccess={jest.fn()} />);
  await screen.findByText(SHORT_HINT);
  fireEvent.change(emailInput(), { target: { value: '  Student@A.Example ' } });
  fireEvent.blur(emailInput());
  expect(screen.queryByText(DOMAIN_ERROR)).toBeNull();
  expect(screen.getByText(SHORT_HINT)).toBeInTheDocument();
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

// ── ФИО и ритм формы: подпись другая, проверка прежняя ──────────────────────

test('поле ФИО: подпись, placeholder и autocomplete="name"', async () => {
  render(<RegisterForm onSuccess={jest.fn()} />);
  await settled();
  const fio = screen.getByLabelText('ФИО');
  expect(fio).toHaveAttribute('placeholder', 'Введите ФИО');
  expect(fio).toHaveAttribute('autocomplete', 'name');
  expect(screen.queryByLabelText('Имя')).toBeNull();
});

test('проверка ФИО прежняя: не короче 2 символов, без требований к числу слов', async () => {
  render(<RegisterForm onSuccess={jest.fn()} />);
  await settled();
  const fio = screen.getByLabelText('ФИО');

  fireEvent.change(fio, { target: { value: ' И ' } });
  fireEvent.blur(fio);
  expect(fio).toHaveAttribute('aria-invalid', 'true');
  expect(fio).toHaveAccessibleDescription('Введите ФИО (минимум 2 символа)');

  // Одно слово — допустимо: фамилия и отчество не обязательны.
  fireEvent.change(fio, { target: { value: 'Иван' } });
  fireEvent.blur(fio);
  expect(fio).not.toHaveAttribute('aria-invalid');

  fireEvent.change(fio, { target: { value: 'Иван' } });
  fireEvent.change(emailInput(), { target: { value: EMAIL } });
  fireEvent.change(screen.getByLabelText('Пароль'), { target: { value: 'SecurePass42!' } });
  fireEvent.change(screen.getByLabelText('Повторите пароль'), { target: { value: 'SecurePass42!' } });
  fireEvent.click(screen.getByRole('checkbox'));
  fireEvent.click(screen.getByRole('button', { name: 'Продолжить' }));
  await screen.findByRole('group', { name: 'Код подтверждения' });
  expect(authApi.registerInit).toHaveBeenCalledWith({
    name: 'Иван', email: EMAIL, password: 'SecurePass42!',
  });
});

test('сила пароля и подсказка работают как прежде', async () => {
  render(<RegisterForm onSuccess={jest.fn()} />);
  await settled();
  const pass = screen.getByLabelText('Пароль');
  expect(pass).toHaveAttribute('aria-describedby', 'r-pass-hint r-pass-strength');
  const strength = document.getElementById('r-pass-strength');   // eslint-disable-line testing-library/no-node-access
  expect(strength).toHaveAttribute('aria-live', 'polite');
  expect(strength).toHaveTextContent('');

  fireEvent.change(pass, { target: { value: 'abc12' } });
  expect(strength).toHaveTextContent('Слабый');
  fireEvent.blur(pass);
  expect(pass).toHaveAttribute('aria-invalid', 'true');
  expect(screen.getByText('Минимум 8 символов', { selector: '#r-pass-hint' })).toBeInTheDocument();

  fireEvent.change(pass, { target: { value: 'SecurePass42!' } });
  expect(strength).toHaveTextContent('Надёжный');
});

test('без согласия заявка не отправляется (поток согласия прежний)', async () => {
  render(<RegisterForm onSuccess={jest.fn()} />);
  await settled();
  fireEvent.change(screen.getByLabelText('ФИО'), { target: { value: 'Иван Тестов' } });
  fireEvent.change(emailInput(), { target: { value: EMAIL } });
  fireEvent.change(screen.getByLabelText('Пароль'), { target: { value: 'SecurePass42!' } });
  fireEvent.change(screen.getByLabelText('Повторите пароль'), { target: { value: 'SecurePass42!' } });
  fireEvent.click(screen.getByRole('button', { name: 'Продолжить' }));
  expect(await screen.findByText('Необходимо принять политику персональных данных'))
    .toHaveAttribute('role', 'alert');
  expect(authApi.registerInit).not.toHaveBeenCalled();
});
