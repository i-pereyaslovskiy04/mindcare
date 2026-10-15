import { fireEvent, render, screen, within } from '@testing-library/react';
import CabinetLayout from './CabinetLayout';
import * as AuthContext from '../../features/auth/AuthContext';

// react-router-dom (v7) не резолвится jest-резолвером в этом проекте — как и
// во всех существующих тестах, мокаем виртуально.
jest.mock('react-router-dom', () => ({
  useLocation: () => ({ pathname: '/psychologist' }),
  useNavigate: () => jest.fn(),
  Outlet: () => <div>OUTLET</div>,
  NavLink: ({ children, to, 'aria-label': ariaLabel }) => (
    <a href={to} aria-label={ariaLabel}>{children}</a>
  ),
  Link: ({ children, to, 'aria-label': ariaLabel, title }) => (
    <a href={to} aria-label={ariaLabel} title={title}>{children}</a>
  ),
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


const NAV = [{
  label: 'Работа',
  items: [
    { key: 'queue', label: 'Подтверждение студентов', icon: 'check', to: '/q',
      badge: '3', badgeLabel: 'ожидают проверки: 3' },
    { key: 'chat', label: 'Сообщения', icon: 'chat', to: '/c', badge: '2' },
  ],
}];

test('badgeLabel даёт пункту понятное доступное имя; бейдж без подписи — как раньше', () => {
  mockAuth({ roles: ['supervisor', 'student'], activeRole: 'supervisor' });
  render(<CabinetLayout cabinetRole="supervisor" navSections={NAV} crumbLabels={{}} />);
  const link = screen.getByRole('link', { name: 'Подтверждение студентов, ожидают проверки: 3' });
  expect(link).toHaveAttribute('href', '/q');
  expect(within(link).getByText('3')).toHaveAttribute('aria-hidden', 'true');
  const chat = screen.getByRole('link', { name: /Сообщения/ });
  expect(chat).not.toHaveAttribute('aria-label');
  expect(within(chat).getByText('2')).not.toHaveAttribute('aria-hidden');
});

test('переключатель кабинета есть в sidebar, topbar и в мобильном меню', () => {
  mockAuth({ roles: ['supervisor', 'student'], activeRole: 'supervisor' });
  render(<CabinetLayout cabinetRole="supervisor" navSections={NAV} crumbLabels={{}} />);
  // sidebar + topbar-копия (CSS показывает одну из них по ширине экрана)
  expect(screen.getAllByRole('button', { name: 'Сменить кабинет (текущий: Супервизор)' }))
    .toHaveLength(2);
  fireEvent.click(screen.getByRole('button', { name: 'Открыть меню' }));
  const drawer = screen.getByRole('dialog', { name: 'Меню кабинета' });
  expect(within(drawer).getByRole('button', { name: 'Сменить кабинет (текущий: Супервизор)' }))
    .toBeInTheDocument();
  expect(within(drawer).getByRole('link', { name: /ожидают проверки: 3/ })).toBeInTheDocument();
  fireEvent.keyDown(window, { key: 'Escape' });
  expect(screen.queryByRole('dialog', { name: 'Меню кабинета' })).toBeNull();
});
