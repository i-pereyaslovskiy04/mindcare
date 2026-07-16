import { render, screen } from '@testing-library/react';
import AdminLayout from './AdminLayout';
import * as AuthContext from '../auth/AuthContext';

let mockPathname = '/admin/users';

jest.mock('react-router-dom', () => ({
  useLocation: () => ({ pathname: mockPathname }),
  useNavigate: () => jest.fn(),
  Outlet: () => <div>OUTLET</div>,
  NavLink: ({ children, to, 'aria-label': ariaLabel, className }) => {
    const isActive = to === mockPathname;
    const cls = typeof className === 'function' ? className({ isActive }) : className;
    return (
      <a href={to} aria-label={ariaLabel} className={cls}>
        {children}
      </a>
    );
  },
}), { virtual: true });
jest.mock('../auth/AuthContext', () => ({
  useAuth: jest.fn(),
  useLogout: () => jest.fn(),
}));

const setActiveRole = jest.fn();

function mockAuth({ roles, activeRole }) {
  AuthContext.useAuth.mockReturnValue({
    user: { roles },
    activeRole,
    setActiveRole,
  });
}

beforeEach(() => {
  jest.clearAllMocks();
  mockPathname = '/admin/users';
});

test('direct entry into /admin syncs activeRole to admin', () => {
  mockAuth({ roles: ['admin', 'supervisor'], activeRole: 'supervisor' });
  render(<AdminLayout />);
  expect(setActiveRole).toHaveBeenCalledWith('admin');
});

test('activeRole already admin does not re-trigger setActiveRole', () => {
  mockAuth({ roles: ['admin'], activeRole: 'admin' });
  render(<AdminLayout />);
  expect(setActiveRole).not.toHaveBeenCalled();
});

test('renders all four nav group headings', () => {
  mockAuth({ roles: ['admin'], activeRole: 'admin' });
  render(<AdminLayout />);
  expect(screen.getByText('Управление')).toBeInTheDocument();
  expect(screen.getByText('Контент')).toBeInTheDocument();
  expect(screen.getByText('Система')).toBeInTheDocument();
  expect(screen.getByText('Аккаунт')).toBeInTheDocument();
});

test('renders links to the new email-domains and settings pages', () => {
  mockAuth({ roles: ['admin'], activeRole: 'admin' });
  render(<AdminLayout />);

  const domainsLink = screen.getByRole('link', { name: 'Домены регистрации' });
  expect(domainsLink).toHaveAttribute('href', '/admin/email-domains');

  const securityLink = screen.getByRole('link', { name: 'Безопасность' });
  expect(securityLink).toHaveAttribute('href', '/admin/settings');
});

test('active link matches current pathname (/admin/users)', () => {
  mockAuth({ roles: ['admin'], activeRole: 'admin' });
  render(<AdminLayout />);
  expect(screen.getByRole('link', { name: 'Пользователи' })).toHaveClass('active');
  expect(screen.getByRole('link', { name: 'Новости' })).not.toHaveClass('active');
  expect(screen.getByRole('link', { name: 'Домены регистрации' })).not.toHaveClass('active');
});

test('active link matches current pathname (/admin/email-domains)', () => {
  mockPathname = '/admin/email-domains';
  mockAuth({ roles: ['admin'], activeRole: 'admin' });
  render(<AdminLayout />);
  expect(screen.getByRole('link', { name: 'Домены регистрации' })).toHaveClass('active');
  expect(screen.getByRole('link', { name: 'Пользователи' })).not.toHaveClass('active');
});
