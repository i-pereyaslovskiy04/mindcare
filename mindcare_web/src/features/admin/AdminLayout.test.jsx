import { render } from '@testing-library/react';
import AdminLayout from './AdminLayout';
import * as AuthContext from '../auth/AuthContext';

jest.mock('react-router-dom', () => ({
  useLocation: () => ({ pathname: '/admin/users' }),
  useNavigate: () => jest.fn(),
  Outlet: () => <div>OUTLET</div>,
  NavLink: ({ children }) => <div>{children}</div>,
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

beforeEach(() => jest.clearAllMocks());

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
