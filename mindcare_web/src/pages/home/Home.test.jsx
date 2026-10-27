/**
 * Канонический вход: главная `/` + AuthModal. Router state `openAuth`
 * ('login' | 'register') открывает модалку на нужной вкладке — так приходят
 * guards, истечение сессии, совместимые `/login` и `/register` и OAuth callback.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import Home from './Home';
import * as AuthContext from '../../features/auth/AuthContext';
import * as configApi from '../../api/config.api';
import * as authApi from '../../api/auth.api';

const mockNavigate = jest.fn();
let mockLocation;
jest.mock('react-router-dom', () => ({
  useNavigate: () => mockNavigate,
  useLocation: () => mockLocation,
  Link: ({ to, children, ...rest }) => <a href={to} {...rest}>{children}</a>,
}), { virtual: true });
jest.mock('../../features/auth/AuthContext', () => ({ useAuth: jest.fn() }));
jest.mock('../../api/auth.api', () => ({
  oauthStart: jest.fn(), registerInit: jest.fn(), registerConfirm: jest.fn(),
  oauthRegistrationInit: jest.fn(), oauthRegistrationPreview: jest.fn(),
  oauthRegistrationResume: jest.fn(),
}));
jest.mock('../../api/config.api', () => ({
  ...jest.requireActual('../../api/config.api'),
  getPublicConfig: jest.fn(),
}));
// Открытая AuthModal монтирует RegisterForm, а он читает публичный список доменов;
// здесь он не важен — пустой. Обычная функция, а не jest.fn(): resetMocks (CRA)
// обнулил бы её реализацию.
jest.mock('../../api/domains.api', () => ({
  ...jest.requireActual('../../api/domains.api'),
  getPublicEmailDomains: () => Promise.resolve({ domains: [] }),
}));
// Тяжёлые/сетевые части главной не участвуют в сценарии входа.
jest.mock('../../components/Navbar/Navbar', () => ({ onOpenAuth }) => (
  <button type="button" onClick={onOpenAuth}>NAVBAR-ВОЙТИ</button>
));
jest.mock('./components/Hero', () => () => null);
jest.mock('./components/QuickActions', () => () => null);
jest.mock('../../features/news/components/NewsSection', () => () => null);
jest.mock('../../components/Footer/Footer', () => () => null);
jest.mock('../../components/CookieBanner/CookieBanner', () => () => null);
jest.mock('../../features/auth/forgot-password/ForgotPasswordModal', () => () => null);

function at(state, key = 'k1') {
  mockLocation = { pathname: '/', search: '', key, state };
}

beforeEach(() => {
  jest.clearAllMocks();
  at(null);
  AuthContext.useAuth.mockReturnValue({
    loading: false, isAuthenticated: false, login: jest.fn(),
  });
  configApi.getPublicConfig.mockResolvedValue({ social_providers: ['yandex'] });
});

const dialog = () => screen.queryByRole('dialog', { name: 'Вход и регистрация' });
const selectedTab = () => screen.getByRole('tab', { selected: true });

async function settled() {
  // Дождаться списка провайдеров (SocialButtons), чтобы не было act-предупреждений.
  await waitFor(() => expect(configApi.getPublicConfig).toHaveBeenCalled());
  // Закрытая модалка — aria-hidden, поэтому ищем и среди скрытых узлов.
  await screen.findAllByRole('button', { name: /Яндекс/, hidden: true });
}

test('openAuth=login → модалка открыта на вкладке «Вход», router state очищен', async () => {
  at({ openAuth: 'login' });
  render(<Home />);
  await settled();
  expect(dialog()).toBeInTheDocument();
  expect(selectedTab()).toHaveTextContent('Вход');
  expect(screen.getByRole('tabpanel', { name: 'Вход' })).toBeVisible();
  expect(mockNavigate).toHaveBeenCalledWith('/', { replace: true, state: null });
});

test('openAuth=register → модалка открыта на вкладке «Регистрация»', async () => {
  at({ openAuth: 'register' });
  render(<Home />);
  await settled();
  expect(dialog()).toBeInTheDocument();
  expect(selectedTab()).toHaveTextContent('Регистрация');
  expect(within(screen.getByRole('tabpanel', { name: 'Регистрация' })).getByLabelText('Имя'))
    .toBeInTheDocument();
});

test('openAuth=login + message → сообщение над формой входа', async () => {
  at({ openAuth: 'login', message: 'Сессия истекла. Войдите снова.' });
  render(<Home />);
  await settled();
  expect(screen.getByText('Сессия истекла. Войдите снова.')).toBeInTheDocument();
});

test('неизвестное значение openAuth модалку не открывает', async () => {
  at({ openAuth: 'admin', message: 'x' });
  render(<Home />);
  await settled();
  expect(dialog()).toBeNull();
  expect(mockNavigate).not.toHaveBeenCalled();
});

test('без router state модалка закрыта; Navbar открывает её на вкладке «Вход»', async () => {
  render(<Home />);
  await settled();
  expect(dialog()).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'NAVBAR-ВОЙТИ' }));
  expect(dialog()).toBeInTheDocument();
  expect(selectedTab()).toHaveTextContent('Вход');
});

test('внутри модалки вкладки «Вход» ↔ «Регистрация» переключаются', async () => {
  at({ openAuth: 'login' });
  render(<Home />);
  await settled();
  fireEvent.click(screen.getByRole('tab', { name: 'Регистрация' }));
  expect(selectedTab()).toHaveTextContent('Регистрация');
  fireEvent.click(screen.getByRole('tab', { name: 'Вход' }));
  expect(selectedTab()).toHaveTextContent('Вход');
});

test('новая навигация на смонтированную главную открывает нужную вкладку без устаревшего состояния', async () => {
  at({ openAuth: 'register' }, 'k1');
  const { rerender } = render(<Home />);
  await settled();
  expect(selectedTab()).toHaveTextContent('Регистрация');
  fireEvent.click(screen.getByRole('button', { name: 'Закрыть' }));
  expect(dialog()).toBeNull();

  at(null, 'k2');                               // router state очищен
  rerender(<Home />);
  expect(dialog()).toBeNull();

  at({ openAuth: 'login' }, 'k3');              // например, guard вернул на `/`
  rerender(<Home />);
  expect(dialog()).toBeInTheDocument();
  expect(selectedTab()).toHaveTextContent('Вход');
});

test('Navbar после открытия на «Регистрации» снова открывает «Вход»', async () => {
  at({ openAuth: 'register' });
  render(<Home />);
  await settled();
  fireEvent.click(screen.getByRole('button', { name: 'Закрыть' }));
  fireEvent.click(screen.getByRole('button', { name: 'NAVBAR-ВОЙТИ' }));
  expect(selectedTab()).toHaveTextContent('Вход');
});

test('вошедшему пользователю модалка не показывается даже с openAuth', async () => {
  AuthContext.useAuth.mockReturnValue({ loading: false, isAuthenticated: true });
  at({ openAuth: 'login' });
  render(<Home />);
  expect(dialog()).toBeNull();
});

// ── системное сообщение: тон, роли, отсутствие «залипания» ──────────────────

const DISABLED = 'Доступ к аккаунту сейчас недоступен. Обратитесь к администратору.';
const EXPIRED = 'Сессия истекла. Войдите снова.';

test('messageTone=error → «Вход», сообщение — alert в стиле ошибки', async () => {
  at({ openAuth: 'login', message: DISABLED, messageTone: 'error' });
  render(<Home />);
  await settled();
  expect(selectedTab()).toHaveTextContent('Вход');
  // Ровно один узел с текстом — значит, одно объявление для скринридера.
  const box = screen.getByText(DISABLED);
  expect(box).toHaveAttribute('role', 'alert');
  expect(box).toHaveClass('errorMessage');
  expect(box).not.toHaveClass('infoMessage');
});

test('истекшая сессия (без тона) → info: status в нейтральном стиле', async () => {
  at({ openAuth: 'login', message: EXPIRED });
  render(<Home />);
  await settled();
  const box = screen.getByText(EXPIRED);
  expect(box).toHaveAttribute('role', 'status');
  expect(box).toHaveClass('infoMessage');
  expect(box).not.toHaveClass('errorMessage');
});

test.each([['warning'], ['errorMessage'], [{ x: 1 }], [42]])(
  'неизвестный messageTone %p → безопасный info',
  async (tone) => {
    at({ openAuth: 'login', message: EXPIRED, messageTone: tone });
    render(<Home />);
    await settled();
    const box = screen.getByText(EXPIRED);
    expect(box).toHaveAttribute('role', 'status');
    expect(box).toHaveClass('infoMessage');
  },
);

test('закрыли модалку с ошибкой и открыли снова — старого сообщения нет', async () => {
  at({ openAuth: 'login', message: DISABLED, messageTone: 'error' });
  render(<Home />);
  await settled();
  expect(screen.getByText(DISABLED)).toHaveAttribute('role', 'alert');

  fireEvent.click(screen.getByRole('button', { name: 'Закрыть' }));
  expect(dialog()).toBeNull();
  expect(screen.queryByText(DISABLED)).toBeNull();

  fireEvent.click(screen.getByRole('button', { name: 'NAVBAR-ВОЙТИ' }));
  expect(dialog()).toBeInTheDocument();
  expect(selectedTab()).toHaveTextContent('Вход');
  expect(screen.queryByText(DISABLED)).toBeNull();
  expect(screen.queryByText(EXPIRED)).toBeNull();
});

test('новая навигация без сообщения не показывает прежнюю ошибку', async () => {
  at({ openAuth: 'login', message: DISABLED, messageTone: 'error' }, 'k1');
  const { rerender } = render(<Home />);
  await settled();
  at({ openAuth: 'register' }, 'k2');
  rerender(<Home />);
  expect(selectedTab()).toHaveTextContent('Регистрация');
  expect(screen.queryByText(DISABLED)).toBeNull();
});

// ── регистрация через провайдера: продолжение из памяти приложения ──────────
//
// `/auth/callback` кладёт ticket в AuthContext (только память) и делает
// replace на `/` БЕЗ router state. Главная открывает ту же AuthModal в
// social-режиме. Здесь AuthContext подменён маленьким хранилищем в памяти
// теста: clearSocialRegistration действительно забывает ticket.

describe('регистрация через провайдера внутри AuthModal', () => {
  const TICKET = 'tkt_REG_HOME_0123456789abcdefghijk';
  const TICKET_GONE = 'Время на завершение регистрации истекло. Начните заново через VK.';
  let social;
  let clearSocialRegistration;
  let completeOAuthRegistration;

  function mockAuthWithSocial(over = {}) {
    AuthContext.useAuth.mockImplementation(() => ({
      loading: false,
      isAuthenticated: false,
      login: jest.fn(),
      completeOAuthRegistration,
      socialRegistration: social,
      clearSocialRegistration,
      ...over,
    }));
  }

  beforeEach(() => {
    social = Object.freeze({ ticket: TICKET, provider: 'vk', emailStep: true });
    clearSocialRegistration = jest.fn(() => { social = null; });
    completeOAuthRegistration = jest.fn().mockResolvedValue({ roles: ['student'] });
    authApi.oauthRegistrationPreview.mockResolvedValue({
      provider: 'vk', email_masked: null, email_allowed: false, email_editable: true,
    });
    authApi.oauthRegistrationInit.mockResolvedValue({ message: 'ok', email_masked: 's***@donnu.ru' });
    mockAuthWithSocial();
  });

  const emailTitle = () => screen.findByRole('heading', { name: 'Почта для регистрации' });
  const entryReady = () => screen.findByRole('button', { name: 'Войти через Яндекс' });

  test('новая VK identity: модалка открыта без router state, шаг email внутри неё, вкладок нет', async () => {
    render(<Home />);                                 // router state пуст (at(null))
    const heading = await emailTitle();

    expect(dialog()).toBeInTheDocument();
    expect(within(dialog()).getByRole('heading', { name: 'Почта для регистрации' })).toBe(heading);
    expect(within(dialog()).getByLabelText('Электронная почта')).toBeInTheDocument();
    expect(screen.queryByRole('tablist')).toBeNull();
    expect(screen.queryByLabelText('Пароль')).toBeNull();           // LoginForm не смонтирован
    expect(authApi.oauthRegistrationPreview).toHaveBeenCalledTimes(1);
    expect(authApi.oauthRegistrationPreview).toHaveBeenCalledWith({ ticket: TICKET });
    // Ни навигации, ни ticket в router state/DOM/storage.
    expect(mockNavigate).not.toHaveBeenCalled();
    expect(document.body.innerHTML).not.toContain(TICKET);
    expect(JSON.stringify({ ...localStorage, ...sessionStorage })).not.toContain(TICKET);
  });

  test('шаг кода — в той же модалке, вкладок нет', async () => {
    render(<Home />);
    await emailTitle();
    fireEvent.change(screen.getByLabelText('Электронная почта'), { target: { value: 'student@donnu.ru' } });
    fireEvent.click(screen.getByRole('button', { name: 'Получить код' }));

    const group = await screen.findByRole('group', { name: 'Код подтверждения' });
    expect(within(dialog()).getByRole('group', { name: 'Код подтверждения' })).toBe(group);
    expect(within(dialog()).getByRole('heading', { name: 'Подтверждение регистрации' }))
      .toBeInTheDocument();
    expect(screen.getAllByRole('dialog')).toHaveLength(1);
    expect(screen.queryByRole('tablist')).toBeNull();
    expect(clearSocialRegistration).not.toHaveBeenCalled();
  });

  test('«Начать заново» забывает ticket и возвращает обычную модалку на «Регистрации»', async () => {
    render(<Home />);
    await emailTitle();
    fireEvent.click(screen.getByRole('button', { name: 'Начать заново' }));

    expect(clearSocialRegistration).toHaveBeenCalledTimes(1);
    expect(social).toBeNull();                                      // ticket в памяти не остался
    await entryReady();
    expect(dialog()).toBeInTheDocument();
    expect(selectedTab()).toHaveTextContent('Регистрация');
    expect(screen.queryByRole('heading', { name: 'Почта для регистрации' })).toBeNull();
    expect(screen.queryByText(TICKET_GONE)).toBeNull();             // выход без сообщения
    expect(authApi.oauthRegistrationInit).not.toHaveBeenCalled();
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  test('терминальная ошибка (ticket истёк) → ticket забыт, обычная модалка «Вход» с ошибкой', async () => {
    authApi.oauthRegistrationPreview.mockRejectedValue(
      Object.assign(new Error('RAW'), { status: 400, code: 'oauth_ticket_invalid' }),
    );
    render(<Home />);

    const box = await screen.findByText(TICKET_GONE);
    expect(box).toHaveAttribute('role', 'alert');
    expect(box).toHaveClass('errorMessage');
    expect(clearSocialRegistration).toHaveBeenCalledTimes(1);
    expect(social).toBeNull();
    await entryReady();
    expect(selectedTab()).toHaveTextContent('Вход');
    expect(screen.queryByRole('heading', { name: 'Почта для регистрации' })).toBeNull();
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  test('закрыли модалку посреди регистрации → ticket забыт; Navbar открывает обычный вход', async () => {
    render(<Home />);
    await emailTitle();
    fireEvent.click(screen.getByRole('button', { name: 'Закрыть' }));

    expect(clearSocialRegistration).toHaveBeenCalledTimes(1);
    expect(social).toBeNull();
    expect(dialog()).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'NAVBAR-ВОЙТИ' }));
    await entryReady();
    expect(dialog()).toBeInTheDocument();
    expect(selectedTab()).toHaveTextContent('Вход');
    expect(screen.queryByRole('heading', { name: 'Почта для регистрации' })).toBeNull();
    expect(authApi.oauthRegistrationPreview).toHaveBeenCalledTimes(1);   // повторно не запрашивается
  });

  test('после «обновления страницы» продолжения нет: модалка закрыта, backend не вызывается', async () => {
    social = null;                                    // память приложения пуста
    render(<Home />);
    await settled();
    expect(dialog()).toBeNull();
    expect(screen.queryByRole('heading', { name: 'Почта для регистрации', hidden: true })).toBeNull();
    expect(authApi.oauthRegistrationPreview).not.toHaveBeenCalled();
    expect(authApi.oauthRegistrationInit).not.toHaveBeenCalled();
  });

  test('пока AuthContext восстанавливает сессию, шаг не показывается и preview не уходит', () => {
    mockAuthWithSocial({ loading: true });
    render(<Home />);
    expect(dialog()).toBeNull();
    expect(authApi.oauthRegistrationPreview).not.toHaveBeenCalled();
  });

  test('вошедшему пользователю продолжение регистрации не показывается', () => {
    mockAuthWithSocial({ isAuthenticated: true });
    render(<Home />);
    expect(dialog()).toBeNull();
    expect(authApi.oauthRegistrationPreview).not.toHaveBeenCalled();
  });
});

// ── /register/confirm#r=<reference>: шаг подтверждения задан маршрутом ───────

const REF = '8a62d590-71a1-4b17-90f7-4a5ff0c9d782';
const REG_EMAIL = 'student@donnu.ru';
const confirmHeading = () => screen.queryByRole('heading', { name: 'Подтверждение регистрации' });
const codeGroup = () => screen.queryByRole('group', { name: 'Код подтверждения' });

function atConfirmRoute({ key = 'c1', hash = `#r=${REF}`, state = null } = {}) {
  mockLocation = { pathname: '/register/confirm', search: '', hash, key, state };
}

function typeCode(digits) {
  within(codeGroup()).getAllByRole('textbox').forEach((input, i) => {
    fireEvent.change(input, { target: { value: digits[i] } });
  });
}

function mockAuthHandoff(over = {}) {
  const handoff = {
    rememberRegisteredEmail: jest.fn(),
    clearRegisteredEmail: jest.fn(),
    registeredEmail: null,
    ...over,
  };
  AuthContext.useAuth.mockReturnValue({
    loading: false, isAuthenticated: false, login: jest.fn(), ...handoff,
  });
  return handoff;
}

test('прямое открытие ссылки → шаг кода без поля email, адрес не меняется', async () => {
  atConfirmRoute();
  render(<Home routeAuth="confirm" />);
  await settled();
  expect(dialog()).toBeInTheDocument();
  expect(confirmHeading()).toBeInTheDocument();
  expect(codeGroup()).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Подтвердить' })).toBeInTheDocument();
  expect(screen.queryByRole('textbox', { name: 'Email' })).toBeNull();
  expect(screen.queryByRole('tablist')).toBeNull();
  expect(dialog()).not.toHaveTextContent(REF);
  // Ни редиректа, ни очистки: адрес с fragment остаётся.
  expect(mockNavigate).not.toHaveBeenCalled();
});

test('повторное открытие ссылки (F5) снова показывает шаг кода', async () => {
  atConfirmRoute({ key: 'c1' });
  const { unmount } = render(<Home routeAuth="confirm" />);
  await settled();
  expect(codeGroup()).toBeInTheDocument();
  unmount();

  // Перезагрузка: новый монтаж той же страницы, fragment в адресе тот же.
  atConfirmRoute({ key: 'c2' });
  render(<Home routeAuth="confirm" />);
  await settled();
  expect(codeGroup()).toBeInTheDocument();
  expect(mockNavigate).not.toHaveBeenCalled();
});

test('код уходит в POST { registrationReference, code }; reference не в storage и не в адресе', async () => {
  const setItem = jest.spyOn(Storage.prototype, 'setItem');
  mockAuthHandoff();
  authApi.registerConfirm.mockReturnValue(new Promise(() => {}));
  atConfirmRoute();
  render(<Home routeAuth="confirm" />);
  await settled();
  typeCode('012345');
  await waitFor(() => expect(authApi.registerConfirm).toHaveBeenCalledWith({
    registrationReference: REF, code: '012345',
  }));
  expect(authApi.registerConfirm).toHaveBeenCalledTimes(1);
  expect(setItem.mock.calls.flat().join(' ')).not.toMatch(new RegExp(`${REF}|012345`));
  expect(mockNavigate).not.toHaveBeenCalled();
  setItem.mockRestore();
});

test('успех → email в память (AuthContext) и replace на главную', async () => {
  const handoff = mockAuthHandoff();
  authApi.registerConfirm.mockResolvedValue({ message: 'Регистрация завершена', email: REG_EMAIL });
  atConfirmRoute();
  render(<Home routeAuth="confirm" />);
  await settled();
  typeCode('482915');
  await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/', { replace: true }));
  expect(handoff.rememberRegisteredEmail).toHaveBeenCalledWith(REG_EMAIL);
  // Email не передаётся ни через router state, ни через адрес.
  expect(JSON.stringify(mockNavigate.mock.calls)).not.toContain(REG_EMAIL);
  expect(handoff.clearRegisteredEmail).not.toHaveBeenCalled();
});

test('главная после успеха → «Вход» с сообщением и подставленным email; передача одноразовая', async () => {
  const handoff = mockAuthHandoff({ registeredEmail: REG_EMAIL });
  render(<Home />);
  await settled();
  expect(selectedTab()).toHaveTextContent('Вход');
  expect(screen.getByRole('status')).toHaveTextContent(
    'Регистрация завершена. Войдите в свою учётную запись.',
  );
  const loginPanel = screen.getByRole('tabpanel', { name: 'Вход' });
  expect(within(loginPanel).getByLabelText('Email')).toHaveValue(REG_EMAIL);
  expect(within(loginPanel).getByLabelText('Пароль')).toHaveValue('');
  expect(handoff.clearRegisteredEmail).toHaveBeenCalled();
});

test('«Начать регистрацию заново» → replace на главную с вкладкой «Регистрация»', async () => {
  atConfirmRoute();
  render(<Home routeAuth="confirm" />);
  await settled();
  fireEvent.click(screen.getByRole('button', { name: 'Начать регистрацию заново' }));
  expect(mockNavigate).toHaveBeenCalledWith('/', { replace: true, state: { openAuth: 'register' } });
});

test('закрытие шага подтверждения уводит на главную (replace)', async () => {
  atConfirmRoute();
  render(<Home routeAuth="confirm" />);
  await settled();
  fireEvent.click(screen.getByRole('button', { name: 'Закрыть' }));
  expect(mockNavigate).toHaveBeenCalledWith('/', { replace: true });
});

test.each([
  ['без fragment', ''],
  ['без r', '#x=1'],
  ['не UUID', '#r=not-a-uuid'],
  ['не UUIDv4', '#r=8a62d590-71a1-1b17-90f7-4a5ff0c9d782'],
])('ссылка %s → объяснение и «Начать регистрацию заново», без поля email и кода', async (_, hash) => {
  atConfirmRoute({ hash });
  render(<Home routeAuth="confirm" />);
  await settled();
  expect(screen.getByText(
    'Эта ссылка не содержит данных для продолжения регистрации. Начните регистрацию заново.',
  )).toBeInTheDocument();
  expect(codeGroup()).toBeNull();
  expect(screen.queryByRole('textbox', { name: 'Email' })).toBeNull();
  expect(screen.getByRole('button', { name: 'Начать регистрацию заново' })).toBeInTheDocument();
});

test('очистка router state сохраняет fragment ссылки', async () => {
  atConfirmRoute({ state: { openAuth: 'login' } });
  render(<Home routeAuth="confirm" />);
  await settled();
  expect(mockNavigate).toHaveBeenCalledWith(
    `/register/confirm#r=${REF}`, { replace: true, state: null },
  );
});

test('явная ссылка важнее незавершённой регистрации через провайдера', async () => {
  AuthContext.useAuth.mockReturnValue({
    loading: false, isAuthenticated: false, login: jest.fn(),
    socialRegistration: Object.freeze({ ticket: 'tkt_HIDDEN_0123456789abcdefghijk', provider: 'vk', emailStep: true }),
    clearSocialRegistration: jest.fn(),
  });
  atConfirmRoute();
  render(<Home routeAuth="confirm" />);
  await settled();
  expect(codeGroup()).toBeInTheDocument();
  expect(screen.getByTestId('auth-modal-body')).toHaveAttribute('data-mode', 'confirm');
  expect(screen.queryByRole('heading', { name: 'Почта для регистрации' })).toBeNull();
  expect(authApi.oauthRegistrationPreview).not.toHaveBeenCalled();
});

test('главная без routeAuth и router state — модалка закрыта (обычный /)', async () => {
  render(<Home />);
  await settled();
  expect(dialog()).toBeNull();
  expect(confirmHeading()).toBeNull();
});

test('неизвестный routeAuth модалку не открывает', async () => {
  atConfirmRoute();
  render(<Home routeAuth="admin" />);
  await settled();
  expect(dialog()).toBeNull();
});

test('смена fragment в той же вкладке: ошибка прежней ссылки не остаётся без F5', async () => {
  authApi.registerConfirm.mockRejectedValueOnce(Object.assign(
    new Error('любой текст'), { status: 400, code: 'registration_reference_invalid' },
  ));
  atConfirmRoute({ key: 'a' });
  const { rerender } = render(<Home routeAuth="confirm" />);
  await settled();
  typeCode('111111');
  const invalid = 'Ссылка недействительна или срок её действия истёк. Начните регистрацию заново.';
  await screen.findByText(invalid);

  atConfirmRoute({ key: 'b', hash: '#r=0f8f2f44-2a8e-4c1e-9d55-0c3b1d1e2a77' });
  rerender(<Home routeAuth="confirm" />);
  expect(screen.queryByText(invalid)).toBeNull();
  expect(codeGroup()).toBeInTheDocument();
  expect(mockNavigate).not.toHaveBeenCalled();
});

// ── /register/social: продолжение регистрации через провайдера из письма ────

describe('/register/social', () => {
  let social;
  let resumeSocialRegistration;
  let clearSocialRegistration;

  function mockAuth(over = {}) {
    AuthContext.useAuth.mockImplementation(() => ({
      loading: false, isAuthenticated: false, login: jest.fn(),
      completeOAuthRegistration: jest.fn(),
      socialRegistration: social, resumeSocialRegistration, clearSocialRegistration,
      ...over,
    }));
  }

  beforeEach(() => {
    social = null;
    resumeSocialRegistration = jest.fn(() => {
      social = Object.freeze({ ticket: null, provider: null, emailStep: false, resume: true });
    });
    clearSocialRegistration = jest.fn(() => { social = null; });
    mockLocation = { pathname: '/register/social', search: '', hash: '', key: 's1', state: null };
    mockAuth();
  });

  test('открытие ссылки → один resume; модалка не на «Входе», код не отправляется', async () => {
    authApi.oauthRegistrationResume.mockReturnValue(new Promise(() => {}));
    const { rerender } = render(<Home routeAuth="social" />);
    expect(resumeSocialRegistration).toHaveBeenCalledTimes(1);
    rerender(<Home routeAuth="social" />);
    expect(await screen.findByText('Восстанавливаем регистрацию…')).toBeInTheDocument();
    expect(resumeSocialRegistration).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('tablist')).toBeNull();
    expect(authApi.oauthRegistrationInit).not.toHaveBeenCalled();
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  test('вошедшему пользователю resume не нужен', () => {
    mockAuth({ isAuthenticated: true });
    render(<Home routeAuth="social" />);
    expect(resumeSocialRegistration).not.toHaveBeenCalled();
  });

  test('нет cookie этого браузера → replace на главную: «Вход» с понятным сообщением', async () => {
    authApi.oauthRegistrationResume.mockRejectedValue(Object.assign(
      new Error('x'), { status: 400, code: 'oauth_registration_not_found' },
    ));
    const { rerender } = render(<Home routeAuth="social" />);
    rerender(<Home routeAuth="social" />);
    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/', {
      replace: true,
      state: {
        openAuth: 'login',
        message: 'Продолжить регистрацию можно только в браузере, где вы начинали вход '
          + 'через Яндекс или VK. Начните заново.',
        messageTone: 'error',
      },
    }));
    expect(clearSocialRegistration).toHaveBeenCalled();
  });

  test('закрытие модалки на /register/social уводит на главную', async () => {
    authApi.oauthRegistrationResume.mockReturnValue(new Promise(() => {}));
    const { rerender } = render(<Home routeAuth="social" />);
    rerender(<Home routeAuth="social" />);
    await screen.findByText('Восстанавливаем регистрацию…');
    fireEvent.click(screen.getByRole('button', { name: 'Закрыть' }));
    expect(mockNavigate).toHaveBeenCalledWith('/', { replace: true });
    expect(clearSocialRegistration).toHaveBeenCalled();
    // Закрытая модалка возвращается в обычный режим — дождаться его загрузки.
    await settled();
  });
});
