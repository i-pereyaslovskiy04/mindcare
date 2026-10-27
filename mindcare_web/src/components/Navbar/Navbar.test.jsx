import { render, screen, fireEvent, within } from '@testing-library/react';
import Navbar from './Navbar';
import * as AuthContext from '../../features/auth/AuthContext';
import { ThemeProvider } from '../../features/theme/ThemeContext';
import { A11yProvider } from '../../features/a11y/A11yContext';

jest.mock('react-router-dom', () => ({
  Link: ({ to, children, ...props }) => <a href={to} {...props}>{children}</a>,
}), { virtual: true });
jest.mock('../../features/auth/AuthContext', () => ({ useAuth: jest.fn() }));

const APPEARANCE = 'Оформление и версия для слабовидящих';
const root = () => document.documentElement;

function renderNavbar() {
  return render(
    <ThemeProvider>
      <A11yProvider>
        <Navbar onOpenAuth={jest.fn()} />
      </A11yProvider>
    </ThemeProvider>,
  );
}

beforeEach(() => {
  AuthContext.useAuth.mockReturnValue({ isAuthenticated: false, loading: false });
});

afterEach(() => {
  localStorage.clear();
  ['data-a11y', 'data-a11y-scheme', 'data-a11y-spacing', 'data-a11y-leading',
    'data-a11y-font', 'data-a11y-images'].forEach((a) => root().removeAttribute(a));
  root().style.removeProperty('--a11y-font-scale');
});

test('authenticated cabinet link points to /dashboard (chooser decides cabinet)', () => {
  AuthContext.useAuth.mockReturnValue({ isAuthenticated: true, loading: false });
  render(<Navbar onOpenAuth={jest.fn()} />);
  const link = screen.getByLabelText('Личный кабинет');
  expect(link).toHaveAttribute('href', '/dashboard');
});

test('в шапке одна кнопка «Оформление» рядом с аккаунтом, отдельной кнопки версии для слабовидящих нет', () => {
  renderNavbar();
  expect(screen.getAllByRole('button', { name: APPEARANCE })).toHaveLength(1);
  expect(screen.queryByRole('button', { name: 'Версия для слабовидящих' })).toBeNull();
  expect(screen.getByRole('button', { name: 'Войти в аккаунт' })).toBeInTheDocument();
});

test('«Оформление» открывает панель: режим, цветовая тема и секция версии для слабовидящих', () => {
  renderNavbar();
  const trigger = screen.getByRole('button', { name: APPEARANCE });
  fireEvent.click(trigger);
  expect(trigger).toHaveAttribute('aria-expanded', 'true');

  const panel = screen.getByRole('dialog', { name: 'Оформление' });
  const appearance = within(panel).getByRole('group', { name: 'Оформление' });
  expect(within(appearance).getByRole('group', { name: 'Режим темы оформления' })).toBeInTheDocument();
  expect(within(appearance).getByRole('group', { name: 'Цветовая тема' })).toBeInTheDocument();
  const a11y = within(panel).getByRole('group', { name: 'Версия для слабовидящих' });
  expect(within(a11y).getByRole('button', { name: 'Версия для слабовидящих' }))
    .toHaveAttribute('aria-pressed', 'false');
});

test('версия для слабовидящих из панели включается, панель закрывается, A11yPanel открывается', () => {
  renderNavbar();
  const trigger = screen.getByRole('button', { name: APPEARANCE });
  expect(screen.queryByRole('region', { name: 'Настройки версии для слабовидящих' })).toBeNull();

  fireEvent.click(trigger);
  fireEvent.click(screen.getByRole('button', { name: 'Версия для слабовидящих' }));

  expect(root().getAttribute('data-a11y')).toBe('on');
  expect(screen.queryByRole('dialog', { name: 'Оформление' })).toBeNull();
  expect(trigger).toHaveFocus();
  expect(screen.getByRole('region', { name: 'Настройки версии для слабовидящих' })).toBeInTheDocument();

  // Выключение — та же секция панели.
  fireEvent.click(trigger);
  fireEvent.click(screen.getByRole('button', { name: 'Обычная версия сайта' }));
  expect(root().hasAttribute('data-a11y')).toBe(false);
});

test('выбор режима темы в панели работает', () => {
  renderNavbar();
  fireEvent.click(screen.getByRole('button', { name: APPEARANCE }));
  fireEvent.click(screen.getByRole('button', { name: 'Тёмная тема' }));
  expect(root().getAttribute('data-theme')).toMatch(/-dark$/);
});
