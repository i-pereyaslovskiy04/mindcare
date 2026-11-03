import { render, screen, fireEvent } from '@testing-library/react';
import NotFound from './NotFound';

jest.mock('react-router-dom', () => ({
  Link: ({ to, children, ...props }) => <a href={to} {...props}>{children}</a>,
}), { virtual: true });
jest.mock('../../components/Navbar/Navbar', () => ({ onOpenAuth }) => (
  <button type="button" onClick={() => onOpenAuth?.()}>Войти в аккаунт</button>
));
jest.mock('../../components/Footer/Footer', () => () => null);
jest.mock('../../features/auth/ui/AuthModal', () => ({ isOpen }) => (
  isOpen ? <div role="dialog" aria-label="Вход" /> : null
));

test('404: содержимое в main, заголовок вкладки, h1', () => {
  render(<NotFound />);
  expect(screen.getByRole('main')).toHaveAttribute('id', 'main-content');
  expect(screen.getByRole('heading', { level: 1, name: 'Страница не найдена' })).toBeInTheDocument();
  expect(document.title).toBe('Страница не найдена — Психология ДонГУ');
});

test('404: «Войти в аккаунт» открывает AuthModal, как на остальных публичных страницах', () => {
  render(<NotFound />);
  expect(screen.queryByRole('dialog', { name: 'Вход' })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Войти в аккаунт' }));
  expect(screen.getByRole('dialog', { name: 'Вход' })).toBeInTheDocument();
});
