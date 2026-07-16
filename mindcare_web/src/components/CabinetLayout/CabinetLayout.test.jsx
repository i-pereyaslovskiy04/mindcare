import { render } from '@testing-library/react';
import CabinetLayout from './CabinetLayout';
import * as AuthContext from '../../features/auth/AuthContext';

// react-router-dom (v7) не резолвится jest-резолвером в этом проекте — как и
// во всех существующих тестах, мокаем виртуально.
jest.mock('react-router-dom', () => ({
  useLocation: () => ({ pathname: '/psychologist' }),
  useNavigate: () => jest.fn(),
  Outlet: () => <div>OUTLET</div>,
  NavLink: ({ children }) => <div>{children}</div>,
}), { virtual: true });
jest.mock('../../features/auth/AuthContext', () => ({
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

test('direct entry (reload/URL) into a membership cabinet syncs activeRole', () => {
  mockAuth({ roles: ['admin', 'psychologist'], activeRole: 'admin' });
  render(
    <CabinetLayout cabinetRole="psychologist" navSections={[]} crumbLabels={{}} />,
  );
  expect(setActiveRole).toHaveBeenCalledWith('psychologist');
});

test('already-synced activeRole does not re-trigger setActiveRole', () => {
  mockAuth({ roles: ['psychologist'], activeRole: 'psychologist' });
  render(
    <CabinetLayout cabinetRole="psychologist" navSections={[]} crumbLabels={{}} />,
  );
  expect(setActiveRole).not.toHaveBeenCalled();
});

test('cabinetRole outside membership does not call setActiveRole', () => {
  mockAuth({ roles: ['psychologist'], activeRole: null });
  render(
    <CabinetLayout cabinetRole="admin" navSections={[]} crumbLabels={{}} />,
  );
  expect(setActiveRole).not.toHaveBeenCalled();
});
