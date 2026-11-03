import { render, screen, waitFor } from '@testing-library/react';
import StudentLayout from './StudentLayout';
import { useAuth } from '../../features/auth/AuthContext';
import { getMyAssignmentsSummary } from '../../api/assignments.api';

// react-router-dom (v7) не резолвится jest-резолвером — мокаем виртуально,
// как в SupervisorLayout.test.jsx; NavLink пробрасывает доступное имя.
jest.mock('react-router-dom', () => ({
  useLocation: () => ({ pathname: '/student' }),
  useNavigate: () => jest.fn(),
  Outlet: () => <div>OUTLET</div>,
  NavLink: ({ children, to, 'aria-label': ariaLabel }) => (
    <a href={to} aria-label={ariaLabel}>{children}</a>
  ),
  Link: ({ children, to, 'aria-label': ariaLabel }) => (
    <a href={to} aria-label={ariaLabel}>{children}</a>
  ),
}), { virtual: true });
jest.mock('../../features/auth/AuthContext', () => ({
  useAuth: jest.fn(),
  useLogout: () => jest.fn(),
}));
jest.mock('../../features/chat/hooks/useMessagesBadge', () => ({
  useMessagesBadge: () => 0,
}));
jest.mock('../../api/assignments.api', () => ({
  getMyAssignmentsSummary: jest.fn(),
}));

function mockAuth({ roles = ['student'], isImpersonating = false } = {}) {
  useAuth.mockReturnValue({
    user: { id: '9', name: 'Анна Клиентова', roles },
    activeRole: 'student',
    setActiveRole: jest.fn(),
    isImpersonating,
  });
}

beforeEach(() => jest.clearAllMocks());

test('бейдж заданий — реальное число доступных активных заданий', async () => {
  mockAuth();
  getMyAssignmentsSummary.mockResolvedValue({ open_count: 3, completed_count: 1, total_count: 5 });
  render(<StudentLayout />);
  const link = await screen.findByRole('link', { name: 'Задания психолога, активных заданий: 3' });
  expect(link).toHaveAttribute('href', '/student/tasks');
  expect(link).toHaveTextContent('3');
  expect(getMyAssignmentsSummary).toHaveBeenCalledTimes(1);
});

test('нет активных — бейджа нет (не «2» по умолчанию)', async () => {
  mockAuth();
  getMyAssignmentsSummary.mockResolvedValue({ open_count: 0, completed_count: 4, total_count: 4 });
  render(<StudentLayout />);
  await waitFor(() => expect(getMyAssignmentsSummary).toHaveBeenCalled());
  const link = screen.getAllByRole('link').find(a => a.getAttribute('href') === '/student/tasks');
  expect(link).not.toHaveTextContent(/\d/);
});

test('impersonation — счётчик не запрашивается', () => {
  mockAuth({ isImpersonating: true });
  render(<StudentLayout />);
  expect(getMyAssignmentsSummary).not.toHaveBeenCalled();
});

test('роль student проверяется по membership roles[]', () => {
  mockAuth({ roles: ['psychologist'] });
  render(<StudentLayout />);
  expect(getMyAssignmentsSummary).not.toHaveBeenCalled();
});
