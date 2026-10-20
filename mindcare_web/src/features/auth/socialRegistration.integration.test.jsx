/**
 * Сквозной сценарий регистрации через внешний провайдер (Stage Social Auth 4,
 * VK-1B, UX hotfix): технический `/auth/callback` → память приложения
 * (НАСТОЯЩИЙ AuthProvider) → replace на `/` → существующая AuthModal главной
 * показывает шаг email и шаг кода.
 *
 * Не подменяются: AuthProvider, OAuthCallbackPage, Home, AuthModal, шаги
 * регистрации, api/auth.api и api/client — считаются ФИЗИЧЕСКИЕ вызовы fetch.
 * Всё рендерится в React StrictMode. react-router-dom в jest не резолвится
 * (как во всех тестах проекта), поэтому вместо него — маленький роутер в
 * памяти: navigate меняет location и адресную строку и записывает вызовы.
 */
import { StrictMode } from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
// eslint-disable-next-line import/no-unresolved
import { useLocation } from 'react-router-dom';
import { AuthProvider, useAuth } from './AuthContext';
import OAuthCallbackPage from './pages/OAuthCallbackPage';
import Home from '../../pages/home/Home';

const mockRouter = {
  location: { pathname: '/', search: '', key: 'k0', state: null },
  listeners: new Set(),
  calls: [],        // все вызовы navigate: [to, options]
  states: [],       // все router state, когда-либо побывавшие в location
  seq: 0,
  subscribe(listener) {
    mockRouter.listeners.add(listener);
    return () => mockRouter.listeners.delete(listener);
  },
  getLocation: () => mockRouter.location,
  navigate(to, options = {}) {
    mockRouter.calls.push([to, options]);
    mockRouter.seq += 1;
    window.history.replaceState(null, '', to);   // адресная строка — как у настоящего роутера
    mockRouter.location = {
      pathname: to.split('?')[0], search: '', key: `k${mockRouter.seq}`, state: options.state ?? null,
    };
    mockRouter.states.push(mockRouter.location.state);
    mockRouter.listeners.forEach((listener) => listener());
  },
  /** «Открыть страницу» по адресу (в т.ч. перезагрузка): история роутера пуста. */
  open(url) {
    window.history.replaceState(null, '', url);
    mockRouter.location = {
      pathname: url.split('#')[0], search: '', key: `k${mockRouter.seq += 1}`, state: null,
    };
    mockRouter.calls = [];
    mockRouter.states = [];
  },
};

jest.mock('react-router-dom', () => ({
  useNavigate: () => mockRouter.navigate,
  useLocation: () => {
    // eslint-disable-next-line global-require
    const React = require('react');
    return React.useSyncExternalStore(mockRouter.subscribe, mockRouter.getLocation);
  },
  Link: ({ to, children, ...rest }) => <a href={to} {...rest}>{children}</a>,
}), { virtual: true });
// Тяжёлые/сетевые части главной не участвуют в сценарии входа.
jest.mock('../../components/Navbar/Navbar', () => ({ onOpenAuth }) => (
  <button type="button" onClick={onOpenAuth}>NAVBAR-ВОЙТИ</button>
));
jest.mock('../../pages/home/components/Hero', () => () => null);
jest.mock('../../pages/home/components/QuickActions', () => () => null);
jest.mock('../news/components/NewsSection', () => () => null);
jest.mock('../../components/Footer/Footer', () => () => null);
jest.mock('../../components/CookieBanner/CookieBanner', () => () => null);
jest.mock('./forgot-password/ForgotPasswordModal', () => () => null);

const TICKET = 'tkt_REG_E2E_0123456789abcdefghijklmn';
const LOGIN_TICKET = 'tkt_LOGIN_E2E_0123456789abcdefghijk';
const SESSION = 'session-token-synthetic';
const NEW_EMAIL = 'student.new@donnu.ru';
const PROVIDER_KEY = 'mindcare_oauth_provider';

const PATH = Object.freeze({
  preview: '/api/auth/oauth/registration/preview',
  init: '/api/auth/oauth/registration/init',
  confirm: '/api/auth/oauth/registration/confirm',
  complete: '/api/auth/oauth/complete',
  me: '/api/auth/me',
  config: '/api/public/config',
});

const ok = (body) => ({ ok: true, status: 200, json: () => Promise.resolve(body) });
const fail = (status, body) => ({ ok: false, status, json: () => Promise.resolve(body) });

let responses;
let fetchSpy;
const originalFetch = global.fetch;
// Что сейчас лежит в памяти приложения (читает компонент внутри AuthProvider).
let memory;

function callsTo(pathname) {
  return fetchSpy.mock.calls.filter(([url]) => String(url) === pathname);
}
const bodyOf = (call) => JSON.parse(call[1].body);

function Memory() {
  memory = useAuth().socialRegistration;
  return null;
}

function TestApp() {
  const { pathname } = useLocation();
  if (pathname === '/auth/callback') return <OAuthCallbackPage />;
  if (pathname === '/dashboard') return <div>DASHBOARD</div>;
  return <Home />;
}

/** Открыть адрес «с нуля»: новая память приложения (как после перезагрузки). */
function openApp(url) {
  mockRouter.open(url);
  return render(
    <StrictMode>
      <AuthProvider>
        <Memory />
        <TestApp />
      </AuthProvider>
    </StrictMode>,
  );
}

beforeEach(() => {
  jest.clearAllMocks();
  localStorage.clear();
  sessionStorage.clear();
  memory = undefined;
  responses = {
    [PATH.preview]: () => ok({
      provider: 'vk', email_masked: null, email_allowed: false, email_editable: true,
    }),
    [PATH.init]: () => ok({ message: 'ok', email_masked: 's***@donnu.ru' }),
    [PATH.confirm]: () => ok({ session_token: SESSION, roles: ['student'] }),
    [PATH.complete]: () => ok({ session_token: SESSION, roles: ['student'] }),
    [PATH.me]: () => ok({ id: 'u1', name: 'Студент', roles: ['student'] }),
    [PATH.config]: () => ok({ social_providers: ['yandex', 'vk'] }),
  };
  fetchSpy = jest.fn((url) => {
    const handler = responses[String(url)];
    return Promise.resolve(handler ? handler() : ok({}));
  });
  global.fetch = fetchSpy;
});

afterEach(() => {
  global.fetch = originalFetch;
  window.history.replaceState(null, '', '/');
});

const dialog = () => screen.queryByRole('dialog', { name: 'Вход и регистрация' });
const emailTitle = () => screen.findByRole('heading', { name: 'Почта для регистрации' });
const codeGroup = () => screen.findByRole('group', { name: 'Код подтверждения' });
// Даём StrictMode-повторам и микрозадачам шанс отправить лишний запрос.
const settle = () => new Promise((resolve) => { setTimeout(resolve, 50); });

function typeCode(value = '123456') {
  fireEvent.paste(screen.getByLabelText('Цифра 1'), {
    clipboardData: { getData: () => value },
  });
}

/** Ticket не виден нигде, кроме памяти приложения и тел запросов к backend. */
function expectTicketOnlyInMemory(ticket = TICKET) {
  expect(window.location.href).not.toContain(ticket);
  expect(JSON.stringify(window.history.state ?? null)).not.toContain(ticket);
  expect(JSON.stringify(mockRouter.calls)).not.toContain(ticket);      // ни адрес, ни router state
  expect(JSON.stringify(mockRouter.states)).not.toContain(ticket);
  expect(JSON.stringify(mockRouter.location)).not.toContain(ticket);
  expect(JSON.stringify({ ...localStorage })).not.toContain(ticket);
  expect(JSON.stringify({ ...sessionStorage })).not.toContain(ticket);
  expect(document.body.innerHTML).not.toContain(ticket);
  // В URL запросов ticket тоже не бывает — только в теле POST.
  expect(fetchSpy.mock.calls.map(([url]) => String(url)).join(' ')).not.toContain(ticket);
}

/**
 * Следит за КАЖДЫМ состоянием DOM: где был пользователь, когда на экране были
 * шаг email или шаг кода, и находились ли они внутри AuthModal.
 */
function watchSteps() {
  const seen = [];
  const snapshot = () => {
    const email = screen.queryByText('Почта для регистрации');
    const otp = screen.queryByText('Подтверждение регистрации');
    for (const [step, node] of [['email', email], ['otp', otp]]) {
      if (node) {
        seen.push({
          step,
          pathname: mockRouter.location.pathname,
          // eslint-disable-next-line testing-library/no-node-access
          inDialog: node.closest('[role="dialog"]') !== null,
        });
      }
    }
  };
  const observer = new MutationObserver(snapshot);
  observer.observe(document.body, { subtree: true, childList: true, characterData: true });
  return { seen, stop: () => { snapshot(); observer.disconnect(); } };
}

// ── VK ID: новая identity ────────────────────────────────────────────────────

describe('VK ID: новая identity', () => {
  const CALLBACK = `/auth/callback#result=registration&ticket=${TICKET}&step=email`;
  beforeEach(() => { sessionStorage.setItem(PROVIDER_KEY, 'vk'); });

  test('callback → техническая передача → `/` → AuthModal открыта → шаг email внутри неё', async () => {
    const steps = watchSteps();
    openApp(CALLBACK);
    const heading = await emailTitle();
    await settle();
    steps.stop();

    // Пользователь на главной; callback в истории заменён, fragment вычищен.
    expect(mockRouter.location.pathname).toBe('/');
    expect(window.location.pathname).toBe('/');
    expect(window.location.hash).toBe('');
    expect(mockRouter.calls).toEqual([['/', { replace: true }]]);     // один переход, без state
    expect(mockRouter.location.state).toBeNull();

    // Шаг — внутри существующей AuthModal, вкладок и обычных форм нет.
    expect(dialog()).toBeInTheDocument();
    expect(screen.getAllByRole('dialog')).toHaveLength(1);
    expect(within(dialog()).getByRole('heading', { name: 'Почта для регистрации' })).toBe(heading);
    expect(within(dialog()).getByLabelText('Электронная почта')).toHaveValue('');
    expect(screen.queryByRole('tablist')).toBeNull();
    expect(screen.queryByLabelText('Пароль')).toBeNull();
    expect(screen.getByTestId('auth-modal-body')).toHaveAttribute('data-mode', 'socialEmail');

    // На /auth/callback шаг не рисовался ни на один кадр — только в модалке на `/`.
    expect(steps.seen.length).toBeGreaterThan(0);
    expect(steps.seen.every((s) => s.pathname === '/' && s.inDialog)).toBe(true);
    expect(steps.seen.some((s) => s.step === 'otp')).toBe(false);

    // StrictMode: preview физически один, код сам не отправляется.
    expect(callsTo(PATH.preview)).toHaveLength(1);
    expect(bodyOf(callsTo(PATH.preview)[0])).toEqual({ ticket: TICKET });
    expect(callsTo(PATH.init)).toHaveLength(0);
    expect(callsTo(PATH.complete)).toHaveLength(0);

    // Ticket — только в памяти приложения.
    expect(memory).toEqual({ ticket: TICKET, provider: 'vk', emailStep: true });
    expectTicketOnlyInMemory();
    expect({ ...sessionStorage }).toEqual({ [PROVIDER_KEY]: 'vk' });   // только имя провайдера
    expect({ ...localStorage }).toEqual({});
  });

  test('шаг кода — в той же AuthModal, вкладок нет; init физически один на действие', async () => {
    const steps = watchSteps();
    openApp(CALLBACK);
    await emailTitle();
    fireEvent.change(screen.getByLabelText('Электронная почта'), { target: { value: NEW_EMAIL } });
    const submit = screen.getByRole('button', { name: 'Получить код' });
    fireEvent.click(submit);
    fireEvent.click(submit);                                           // двойной клик

    const group = await codeGroup();
    await settle();
    steps.stop();

    expect(mockRouter.location.pathname).toBe('/');
    expect(within(dialog()).getByRole('group', { name: 'Код подтверждения' })).toBe(group);
    expect(within(dialog()).getByRole('heading', { name: 'Подтверждение регистрации' }))
      .toBeInTheDocument();
    expect(within(dialog()).getByText('s***@donnu.ru')).toBeInTheDocument();
    expect(screen.getAllByRole('dialog')).toHaveLength(1);
    expect(screen.queryByRole('tablist')).toBeNull();
    expect(screen.queryByRole('heading', { name: 'Почта для регистрации' })).toBeNull();
    expect(screen.getByTestId('auth-modal-body')).toHaveAttribute('data-mode', 'socialOtp');
    expect(steps.seen.every((s) => s.pathname === '/' && s.inDialog)).toBe(true);

    expect(callsTo(PATH.init)).toHaveLength(1);
    expect(bodyOf(callsTo(PATH.init)[0])).toEqual({ ticket: TICKET, email: NEW_EMAIL });
    expect(callsTo(PATH.preview)).toHaveLength(1);

    // Ни ticket, ни введённый адрес не покидают память и тело запроса init.
    expectTicketOnlyInMemory();
    for (const blob of [
      window.location.href, JSON.stringify(mockRouter.calls), JSON.stringify(mockRouter.states),
      JSON.stringify({ ...localStorage }), JSON.stringify({ ...sessionStorage }),
      document.body.innerHTML,
    ]) {
      expect(blob).not.toContain(NEW_EMAIL);
    }
  });

  test('код + согласие → аккаунт и сессия → /dashboard; ticket из памяти убран', async () => {
    openApp(CALLBACK);
    await emailTitle();
    fireEvent.change(screen.getByLabelText('Электронная почта'), { target: { value: NEW_EMAIL } });
    fireEvent.click(screen.getByRole('button', { name: 'Получить код' }));
    await codeGroup();
    fireEvent.click(screen.getByRole('checkbox'));
    typeCode();

    expect(await screen.findByText('DASHBOARD')).toBeInTheDocument();
    await settle();
    expect(mockRouter.location.pathname).toBe('/dashboard');
    expect(callsTo(PATH.confirm)).toHaveLength(1);
    // Confirm не получает email — только ticket, код и согласие.
    expect(bodyOf(callsTo(PATH.confirm)[0])).toEqual({
      ticket: TICKET, code: '123456', consent_accepted: true,
    });
    expect(callsTo(PATH.init)).toHaveLength(1);
    expect(callsTo(PATH.preview)).toHaveLength(1);
    expect(localStorage.getItem('mindcare_session')).toBe(SESSION);
    expect(memory).toBeNull();
    expectTicketOnlyInMemory();
  });

  test('«Начать заново» очищает ticket в памяти и возвращает обычную AuthModal', async () => {
    openApp(CALLBACK);
    await emailTitle();
    expect(memory).not.toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Начать заново' }));

    await waitFor(() => expect(memory).toBeNull());                     // ticket забыт
    await screen.findByRole('button', { name: 'Войти через ВКонтакте' });
    expect(dialog()).toBeInTheDocument();
    expect(screen.getByRole('tablist')).toBeInTheDocument();
    expect(screen.getByRole('tab', { selected: true })).toHaveTextContent('Регистрация');
    expect(screen.queryByRole('heading', { name: 'Почта для регистрации' })).toBeNull();
    expect(screen.getByTestId('auth-modal-body')).toHaveAttribute('data-mode', 'entry');
    expect(mockRouter.location.pathname).toBe('/');
    await settle();
    expect(callsTo(PATH.init)).toHaveLength(0);                          // backend не трогаем
    expect(callsTo(PATH.preview)).toHaveLength(1);
    expectTicketOnlyInMemory();
  });

  test('закрытие модалки посреди регистрации тоже очищает ticket', async () => {
    openApp(CALLBACK);
    await emailTitle();
    fireEvent.click(screen.getByRole('button', { name: 'Закрыть' }));

    await waitFor(() => expect(memory).toBeNull());
    expect(dialog()).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'NAVBAR-ВОЙТИ' }));
    await screen.findByRole('button', { name: 'Войти через ВКонтакте' });
    expect(screen.getByRole('tab', { selected: true })).toHaveTextContent('Вход');
    expect(screen.queryByRole('heading', { name: 'Почта для регистрации' })).toBeNull();
    expect(callsTo(PATH.preview)).toHaveLength(1);
  });

  test('обновление `/` во время незавершённой регистрации: продолжение не восстанавливается', async () => {
    const view = openApp(CALLBACK);
    await emailTitle();
    expect(mockRouter.location.pathname).toBe('/');
    expect(memory).not.toBeNull();
    view.unmount();                                                    // страница выгружена

    openApp('/');                                                       // F5: тот же адрес, новая память
    // Дождаться загрузки главной (кнопки провайдеров в закрытой модалке).
    await screen.findAllByRole('button', { name: /ВКонтакте/, hidden: true });
    await settle();

    expect(memory).toBeNull();
    expect(dialog()).toBeNull();                                        // модалка закрыта
    expect(screen.queryByText('Почта для регистрации')).toBeNull();
    expect(screen.queryByText('Подтверждение регистрации')).toBeNull();
    expect(callsTo(PATH.preview)).toHaveLength(1);                      // новых запросов нет
    expect(callsTo(PATH.init)).toHaveLength(0);
    expect(mockRouter.calls).toEqual([]);
    expectTicketOnlyInMemory();
  });

  test('ticket истёк (preview 400) → обычная AuthModal «Вход» с ошибкой, ticket забыт', async () => {
    responses[PATH.preview] = () => fail(400, {
      detail: 'RAW server detail', code: 'oauth_ticket_invalid',
    });
    openApp(CALLBACK);

    const box = await screen.findByText(
      'Время на завершение регистрации истекло. Начните заново через VK.',
    );
    expect(box).toHaveAttribute('role', 'alert');
    expect(within(dialog()).getByText(box.textContent)).toBe(box);
    expect(screen.getByRole('tab', { selected: true })).toHaveTextContent('Вход');
    expect(screen.queryByText(/RAW server detail/)).toBeNull();
    await waitFor(() => expect(memory).toBeNull());
    await settle();
    expect(callsTo(PATH.preview)).toHaveLength(1);
    expect(mockRouter.location.pathname).toBe('/');
    expectTicketOnlyInMemory();
  });
});

// ── VK ID: известная identity ────────────────────────────────────────────────

test('известная VK identity: прямой вход → /dashboard, продолжения в модалке нет', async () => {
  sessionStorage.setItem(PROVIDER_KEY, 'vk');
  const steps = watchSteps();
  openApp(`/auth/callback#result=login&ticket=${LOGIN_TICKET}`);

  expect(await screen.findByText('DASHBOARD')).toBeInTheDocument();
  await settle();
  steps.stop();

  expect(mockRouter.calls).toEqual([['/dashboard', { replace: true }]]);
  expect(callsTo(PATH.complete)).toHaveLength(1);                       // StrictMode: один обмен
  expect(bodyOf(callsTo(PATH.complete)[0])).toEqual({ ticket: LOGIN_TICKET });
  expect(callsTo(PATH.preview)).toHaveLength(0);
  expect(callsTo(PATH.init)).toHaveLength(0);
  expect(callsTo(PATH.confirm)).toHaveLength(0);
  expect(steps.seen).toEqual([]);                                       // ни шага email, ни шага кода
  expect(dialog()).toBeNull();
  expect(memory).toBeNull();
  expect(localStorage.getItem('mindcare_session')).toBe(SESSION);
  expectTicketOnlyInMemory(LOGIN_TICKET);
});

// ── Яндекс: продуктовое поведение прежнее ────────────────────────────────────

describe('Яндекс: регрессия', () => {
  const CALLBACK = `/auth/callback#result=registration&ticket=${TICKET}`;
  beforeEach(() => {
    sessionStorage.setItem(PROVIDER_KEY, 'yandex');
    responses[PATH.init] = () => ok({ message: 'ok', email_masked: 'i***@yandex.ru' });
  });

  test('новая identity: код уходит автоматически (один раз), шаг кода в AuthModal, шага email нет', async () => {
    const steps = watchSteps();
    openApp(CALLBACK);
    const group = await codeGroup();
    await settle();
    steps.stop();

    expect(mockRouter.location.pathname).toBe('/');
    expect(mockRouter.calls).toEqual([['/', { replace: true }]]);
    expect(within(dialog()).getByRole('group', { name: 'Код подтверждения' })).toBe(group);
    expect(within(dialog()).getByText('i***@yandex.ru')).toBeInTheDocument();
    expect(screen.queryByRole('tablist')).toBeNull();
    expect(screen.getByTestId('auth-modal-body')).toHaveAttribute('data-mode', 'socialOtp');

    // Автоматический init — физически один; preview и шага email у Яндекса нет.
    expect(callsTo(PATH.init)).toHaveLength(1);
    expect(bodyOf(callsTo(PATH.init)[0])).toEqual({ ticket: TICKET });   // ни email, ни имени
    expect(callsTo(PATH.preview)).toHaveLength(0);
    expect(steps.seen.some((s) => s.step === 'email')).toBe(false);
    expect(steps.seen.every((s) => s.pathname === '/' && s.inDialog)).toBe(true);
    expect(screen.queryByLabelText('Электронная почта')).toBeNull();
    // Адрес фиксирован: изменить нельзя, только начать заново.
    expect(screen.getByRole('button', { name: 'Начать заново' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Изменить email' })).toBeNull();
    expect(screen.queryByRole('button', { name: /Указать другую/ })).toBeNull();
    expect(screen.getByRole('checkbox')).not.toBeChecked();              // согласие MindCare
    expectTicketOnlyInMemory();
  });

  test('код + согласие → /dashboard', async () => {
    openApp(CALLBACK);
    await codeGroup();
    fireEvent.click(screen.getByRole('checkbox'));
    typeCode();

    expect(await screen.findByText('DASHBOARD')).toBeInTheDocument();
    expect(callsTo(PATH.confirm)).toHaveLength(1);
    expect(bodyOf(callsTo(PATH.confirm)[0])).toEqual({
      ticket: TICKET, code: '123456', consent_accepted: true,
    });
    expect(callsTo(PATH.init)).toHaveLength(1);
    expect(memory).toBeNull();
  });

  test('email занят (init 409) → обычная AuthModal «Вход» с тем же текстом, что и раньше', async () => {
    responses[PATH.init] = () => fail(409, { detail: 'RAW', code: 'email_already_exists' });
    openApp(CALLBACK);

    const box = await screen.findByText(
      'Аккаунт с таким email уже существует. Войдите по email и паролю.',
    );
    expect(box).toHaveAttribute('role', 'alert');
    expect(screen.getByRole('tab', { selected: true })).toHaveTextContent('Вход');
    await waitFor(() => expect(memory).toBeNull());
    await settle();
    expect(callsTo(PATH.init)).toHaveLength(1);
    expect(screen.queryByRole('group', { name: 'Код подтверждения' })).toBeNull();
  });

  test('известная identity: прямой вход, как и раньше', async () => {
    openApp(`/auth/callback#result=login&ticket=${LOGIN_TICKET}`);
    expect(await screen.findByText('DASHBOARD')).toBeInTheDocument();
    expect(mockRouter.calls).toEqual([['/dashboard', { replace: true }]]);
    expect(callsTo(PATH.complete)).toHaveLength(1);
    expect(callsTo(PATH.init)).toHaveLength(0);
    expect(dialog()).toBeNull();
  });

  test('ошибка во fragment → AuthModal «Вход» с сообщением через router state (как раньше)', async () => {
    openApp('/auth/callback#error=oauth_cancelled');
    const box = await screen.findByText('Вход через Яндекс отменён.');
    expect(box).toHaveAttribute('role', 'status');
    expect(mockRouter.calls[0]).toEqual(['/', {
      replace: true,
      state: { openAuth: 'login', message: 'Вход через Яндекс отменён.', messageTone: 'info' },
    }]);
    expect(memory).toBeNull();
  });
});
