import { render, screen, waitFor } from '@testing-library/react';
import SupervisorLayout from './SupervisorLayout';
import { useAuth } from '../../features/auth/AuthContext';
import { getPendingVerificationsCount } from '../../api/studentVerification.api';

// react-router-dom (v7) не резолвится jest-резолвером — мокаем виртуально,
// как в CabinetLayout.test.jsx; NavLink пробрасывает доступное имя.
jest.mock('react-router-dom', () => ({
  useLocation: () => ({ pathname: '/supervisor' }),
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
jest.mock('../../api/studentVerification.api', () => ({
  getPendingVerificationsCount: jest.fn(),
}));

function mockAuth({ roles = ['supervisor', 'student'], isImpersonating = false } = {}) {
  useAuth.mockReturnValue({
    user: { id: '5', name: 'Пётр Супервизоров', roles },
    activeRole: 'supervisor',
    setActiveRole: jest.fn(),
    isImpersonating,
  });
}

beforeEach(() => {
  jest.clearAllMocks();
});

test('бейдж ожидающих заявок и понятное доступное имя пункта меню', async () => {
  mockAuth();
  getPendingVerificationsCount.mockResolvedValue({ count: 3 });
  render(<SupervisorLayout />);
  const link = await screen.findByRole('link', {
    name: 'Подтверждение студентов, ожидают проверки: 3',
  });
  expect(link).toHaveAttribute('href', '/supervisor/student-verifications');
  expect(link).toHaveTextContent('3');
  expect(getPendingVerificationsCount).toHaveBeenCalledTimes(1);   // один таймер/запрос
});

test('большое число — «99+», в доступном имени точное число', async () => {
  mockAuth();
  getPendingVerificationsCount.mockResolvedValue({ count: 1000 });
  render(<SupervisorLayout />);
  const link = await screen.findByRole('link', {
    name: 'Подтверждение студентов, ожидают проверки: 1000',
  });
  expect(link).toHaveTextContent('99+');
});

test('при нуле бейджа нет', async () => {
  mockAuth();
  getPendingVerificationsCount.mockResolvedValue({ count: 0 });
  render(<SupervisorLayout />);
  await waitFor(() => expect(getPendingVerificationsCount).toHaveBeenCalled());
  // Точное имя без числа: бейджа нет, aria-label не задан.
  const link = screen.getByRole('link', { name: 'Подтверждение студентов' });
  expect(link).not.toHaveAttribute('aria-label');
});

test('ошибка загрузки — бейджа нет (неизвестное значение не показывается нулём)', async () => {
  mockAuth();
  getPendingVerificationsCount.mockRejectedValue(new Error('network'));
  render(<SupervisorLayout />);
  await waitFor(() => expect(getPendingVerificationsCount).toHaveBeenCalled());
  expect(screen.getByRole('link', { name: 'Подтверждение студентов' }))
    .not.toHaveAttribute('aria-label');
});

test('в режиме «под именем» и без роли supervisor счётчик не запрашивается', async () => {
  mockAuth({ isImpersonating: true });
  const { unmount } = render(<SupervisorLayout />);
  unmount();
  mockAuth({ roles: ['admin', 'student'] });
  render(<SupervisorLayout />);
  await new Promise((r) => setTimeout(r, 0));
  expect(getPendingVerificationsCount).not.toHaveBeenCalled();
});
