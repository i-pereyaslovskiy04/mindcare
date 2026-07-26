import { render, screen } from '@testing-library/react';
import { RoleRoute, DashboardRedirect } from './guards';
import * as AuthContext from '../features/auth/AuthContext';

// react-router-dom (v7) не резолвится jest-резолвером в этом проекте — как и во
// всех существующих тестах, мокаем виртуально. Navigate рендерит свой `to`,
// чтобы можно было проверить цель редиректа.
jest.mock('react-router-dom', () => ({
  Navigate: ({ to }) => <div>NAV:{to}</div>,
  useNavigate: () => jest.fn(),
}), { virtual: true });
jest.mock('../features/auth/AuthContext', () => ({ useAuth: jest.fn() }));

function mockAuth(value) {
  AuthContext.useAuth.mockReturnValue({ loading: false, ...value });
}

beforeEach(() => jest.clearAllMocks());

// ── RoleRoute ────────────────────────────────────────────────────────────────

test('RoleRoute grants access when a membership role intersects allowed', () => {
  mockAuth({ user: { roles: ['admin', 'supervisor', 'psychologist'] } });
  render(<RoleRoute roles={['admin']}><div>GRANTED</div></RoleRoute>);
  expect(screen.getByText('GRANTED')).toBeInTheDocument();
});

test('RoleRoute grants supervisor+psychologist to a psychologist route', () => {
  mockAuth({ user: { roles: ['supervisor', 'psychologist'] } });
  render(<RoleRoute roles={['psychologist']}><div>GRANTED</div></RoleRoute>);
  expect(screen.getByText('GRANTED')).toBeInTheDocument();
});

test('RoleRoute redirects to /profile without membership', () => {
  mockAuth({ user: { roles: ['supervisor', 'psychologist'] } });
  render(<RoleRoute roles={['admin']}><div>GRANTED</div></RoleRoute>);
  expect(screen.getByText('NAV:/profile')).toBeInTheDocument();
  expect(screen.queryByText('GRANTED')).toBeNull();
});

// ── DashboardRedirect ────────────────────────────────────────────────────────

test('single role redirects straight to its cabinet', () => {
  mockAuth({ user: { roles: ['psychologist'] }, activeRole: null });
  render(<DashboardRedirect />);
  expect(screen.getByText('NAV:/psychologist')).toBeInTheDocument();
});

test('multi-role with valid activeRole redirects to that cabinet', () => {
  mockAuth({ user: { roles: ['admin', 'supervisor'] }, activeRole: 'supervisor' });
  render(<DashboardRedirect />);
  expect(screen.getByText('NAV:/supervisor')).toBeInTheDocument();
});

test('multi-role without valid activeRole shows the cabinet chooser', () => {
  mockAuth({ user: { roles: ['admin', 'supervisor'] }, activeRole: null });
  render(<DashboardRedirect />);
  expect(screen.getByText('Выберите кабинет')).toBeInTheDocument();
});

test('multi-role with an invalid stored activeRole falls back to chooser', () => {
  mockAuth({ user: { roles: ['supervisor', 'psychologist'] }, activeRole: 'admin' });
  render(<DashboardRedirect />);
  expect(screen.getByText('Выберите кабинет')).toBeInTheDocument();
});

test('no roles redirects to /profile', () => {
  mockAuth({ user: { roles: [] }, activeRole: null });
  render(<DashboardRedirect />);
  expect(screen.getByText('NAV:/profile')).toBeInTheDocument();
});
