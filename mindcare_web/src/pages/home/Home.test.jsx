/**
 * Канонический вход: главная `/` + AuthModal. Router state `openAuth`
 * ('login' | 'register') открывает модалку на нужной вкладке — так приходят
 * guards, истечение сессии, совместимые `/login` и `/register` и OAuth callback.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import Home from './Home';
import * as AuthContext from '../../features/auth/AuthContext';
import * as configApi from '../../api/config.api';

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
