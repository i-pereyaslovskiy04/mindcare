import { render, screen, fireEvent, within } from '@testing-library/react';
import CabinetLayout from './CabinetLayout';
import { ThemeProvider } from '../../features/theme/ThemeContext';
import { A11yProvider } from '../../features/a11y/A11yContext';
import * as AuthContext from '../../features/auth/AuthContext';

let mockPathname = '/psychologist';

// react-router-dom (v7) не резолвится jest-резолвером в этом проекте — как и
// во всех существующих тестах, мокаем виртуально.
jest.mock('react-router-dom', () => ({
  useLocation: () => ({ pathname: mockPathname }),
  useNavigate: () => jest.fn(),
  Outlet: () => <div>OUTLET</div>,
  NavLink: ({ children }) => <div>{children}</div>,
  Link: ({ children, to, className, 'aria-label': ariaLabel, title, onClick }) => (
    <a
      href={to}
      className={className}
      aria-label={ariaLabel}
      title={title}
      onClick={(e) => { e.preventDefault(); onClick?.(e); }}
    >
      {children}
    </a>
  ),
}), { virtual: true });

const mockLogout = jest.fn();
jest.mock('../../features/auth/AuthContext', () => ({
  useAuth: jest.fn(),
  useLogout: () => mockLogout,
}));

const setActiveRole = jest.fn();

function mockAuth({ roles, activeRole }) {
  AuthContext.useAuth.mockReturnValue({
    user: { roles },
    activeRole,
    setActiveRole,
  });
}

const PSY_CRUMBS = {
  '/psychologist': 'Главная',
  '/psychologist/students': 'Мои студенты',
};
const PSY_DYNAMIC = [
  { prefix: '/psychologist/students/', label: 'Карточка студента', parent: '/psychologist/students' },
];

beforeEach(() => {
  jest.clearAllMocks();
  mockPathname = '/psychologist';
});

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

test.each([
  ['student', '/student'],
  ['psychologist', '/psychologist'],
  ['supervisor', '/supervisor'],
])('текстовый brand кабинета %s ведёт на %s', (role, home) => {
  mockPathname = home;
  mockAuth({ roles: [role], activeRole: role });
  render(<CabinetLayout cabinetRole={role} navSections={[]} crumbLabels={{}} />);

  const brand = screen.getByRole('link', { name: 'Психология ДонГУ, личный кабинет — на главную' });
  expect(brand).toHaveAttribute('href', home);
  expect(brand).toHaveTextContent('Личный кабинет');

  // Монограмма свёрнутого sidebar — «ПД» внутри той же ссылки; legacy «М» нет.
  expect(within(brand).getByText('ПД')).toHaveAttribute('aria-hidden', 'true');
  expect(within(brand).queryByText('М')).toBeNull();
});

test('шапка — общий CabinetHeader: крошки, «Оформление», выход; без home/почты', () => {
  mockPathname = '/psychologist/students';
  mockAuth({ roles: ['psychologist'], activeRole: 'psychologist' });
  render(
    <ThemeProvider>
      <A11yProvider>
        <CabinetLayout cabinetRole="psychologist" navSections={[]} crumbLabels={PSY_CRUMBS} />
      </A11yProvider>
    </ThemeProvider>,
  );

  const nav = screen.getByRole('navigation', { name: 'Навигационная цепочка' });
  expect(within(nav).getByRole('link', { name: 'Главная' })).toHaveAttribute('href', '/psychologist');
  expect(within(nav).getByText('Мои студенты')).toHaveAttribute('aria-current', 'page');

  expect(screen.getByRole('button', { name: 'Оформление и версия для слабовидящих' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Уведомления — скоро' })).toBeInTheDocument();
  expect(screen.queryByRole('link', { name: 'На главную' })).toBeNull();
  expect(screen.queryByRole('button', { name: 'Почта' })).toBeNull();

  fireEvent.click(screen.getByRole('button', { name: 'Выйти' }));
  expect(mockLogout).toHaveBeenCalledTimes(1);
});

test('динамическая страница: «Главная / Мои студенты / Карточка студента»', () => {
  mockPathname = '/psychologist/students/42';
  mockAuth({ roles: ['psychologist'], activeRole: 'psychologist' });
  render(
    <CabinetLayout
      cabinetRole="psychologist"
      navSections={[]}
      crumbLabels={PSY_CRUMBS}
      dynamicCrumbs={PSY_DYNAMIC}
    />,
  );

  const nav = screen.getByRole('navigation', { name: 'Навигационная цепочка' });
  expect(within(nav).getAllByRole('listitem').map((li) => li.textContent)).toEqual([
    'Главная', ' / Мои студенты', ' / Карточка студента',
  ]);
  expect(within(nav).getByRole('link', { name: 'Мои студенты' }))
    .toHaveAttribute('href', '/psychologist/students');
});

test('mobile drawer: brand в drawer ведёт на главную кабинета и закрывает меню', () => {
  mockPathname = '/psychologist/students';
  mockAuth({ roles: ['psychologist'], activeRole: 'psychologist' });
  render(<CabinetLayout cabinetRole="psychologist" navSections={[]} crumbLabels={PSY_CRUMBS} />);

  fireEvent.click(screen.getByRole('button', { name: 'Открыть меню' }));
  const drawer = screen.getByRole('dialog', { name: 'Меню кабинета' });
  const brand = within(drawer).getByRole('link', {
    name: 'Психология ДонГУ, личный кабинет — на главную',
  });
  expect(brand).toHaveAttribute('href', '/psychologist');

  fireEvent.click(brand);
  expect(screen.queryByRole('dialog', { name: 'Меню кабинета' })).toBeNull();
});

test('mobile drawer: фокус на «Закрыть меню», Escape закрывает и возвращает фокус на hamburger', () => {
  mockAuth({ roles: ['student'], activeRole: 'student' });
  mockPathname = '/student';
  render(<CabinetLayout cabinetRole="student" navSections={[]} crumbLabels={{}} />);

  const burger = screen.getByRole('button', { name: 'Открыть меню' });
  expect(burger).toHaveAttribute('aria-expanded', 'false');
  fireEvent.click(burger);

  const drawer = screen.getByRole('dialog', { name: 'Меню кабинета' });
  expect(burger).toHaveAttribute('aria-expanded', 'true');
  expect(burger).toHaveAttribute('aria-controls', drawer.id);
  expect(within(drawer).getByRole('button', { name: 'Закрыть меню' })).toHaveFocus();

  fireEvent.keyDown(window, { key: 'Escape' });
  expect(screen.queryByRole('dialog', { name: 'Меню кабинета' })).toBeNull();
  expect(burger).toHaveFocus();
});
