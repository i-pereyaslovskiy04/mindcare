import { render, screen, fireEvent, within } from '@testing-library/react';
import AdminLayout from './AdminLayout';
import { ThemeProvider } from '../theme/ThemeContext';
import { A11yProvider } from '../a11y/A11yContext';
import * as AuthContext from '../auth/AuthContext';

let mockPathname = '/admin/users';

jest.mock('react-router-dom', () => ({
  useLocation: () => ({ pathname: mockPathname }),
  useNavigate: () => jest.fn(),
  Outlet: () => <div>OUTLET</div>,
  NavLink: ({ children, to, 'aria-label': ariaLabel, className, onClick }) => {
    const isActive = to === mockPathname;
    const cls = typeof className === 'function' ? className({ isActive }) : className;
    return (
      <a
        href={to}
        aria-label={ariaLabel}
        className={cls}
        onClick={(e) => { e.preventDefault(); onClick?.(e); }}
      >
        {children}
      </a>
    );
  },
  Link: ({ children, to, 'aria-label': ariaLabel, className, title, onClick }) => (
    <a
      href={to}
      aria-label={ariaLabel}
      className={className}
      title={title}
      onClick={(e) => { e.preventDefault(); onClick?.(e); }}
    >
      {children}
    </a>
  ),
}), { virtual: true });
const mockLogout = jest.fn();
jest.mock('../auth/AuthContext', () => ({
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

test('renders the audit log link in the "Система" group', () => {
  mockAuth({ roles: ['admin'], activeRole: 'admin' });
  render(<AdminLayout />);

  const auditLink = screen.getByRole('link', { name: 'Журнал действий' });
  expect(auditLink).toHaveAttribute('href', '/admin/audit');

  // Пункт стоит именно в группе «Система», а не где-то ещё в sidebar.
  // Структура групп и есть предмет проверки, поэтому обращение к DOM здесь
  // осознанное (тот же приём, что в тестах chat-компонентов).
  // eslint-disable-next-line testing-library/no-node-access
  const group = screen.getByText('Система').parentElement;
  expect(group).toContainElement(auditLink);
});

test('audit link is active on /admin/audit and drives the breadcrumb', () => {
  mockPathname = '/admin/audit';
  mockAuth({ roles: ['admin'], activeRole: 'admin' });
  render(<AdminLayout />);

  expect(screen.getByRole('link', { name: 'Журнал действий' })).toHaveClass('active');
  expect(screen.getByRole('link', { name: 'Пользователи' })).not.toHaveClass('active');

  // Breadcrumb берёт подпись из того же ADMIN_NAV_GROUPS: подпись встречается
  // дважды — в sidebar и в хлебных крошках, а дефолтная «Панель» исчезает.
  expect(screen.getAllByText('Журнал действий')).toHaveLength(2);
  expect(screen.queryByText('Панель')).toBeNull();
});

test('renders links to the new email-domains and settings pages', () => {
  mockAuth({ roles: ['admin'], activeRole: 'admin' });
  render(<AdminLayout />);

  const domainsLink = screen.getByRole('link', { name: 'Домены регистрации' });
  expect(domainsLink).toHaveAttribute('href', '/admin/email-domains');

  const securityLink = screen.getByRole('link', { name: 'Безопасность' });
  expect(securityLink).toHaveAttribute('href', '/admin/settings');
});

// Отдельная home-иконка на публичный «/» удалена: на главную панели ведёт
// текстовый brand (а «Главная» в крошках — туда же).
test('brand «Панель управления» ведёт на /admin; ссылки на публичный «/» нет', () => {
  mockAuth({ roles: ['admin'], activeRole: 'admin' });
  render(<AdminLayout />);

  const brand = screen.getByRole('link', {
    name: 'Психология ДонГУ, панель управления — на главную',
  });
  expect(brand).toHaveAttribute('href', '/admin');
  expect(brand).toHaveTextContent('Панель управления');
  // Монограмма свёрнутого sidebar — «ПД» внутри той же ссылки; legacy «М» нет.
  expect(within(brand).getByText('ПД')).toHaveAttribute('aria-hidden', 'true');
  expect(within(brand).queryByText('М')).toBeNull();

  expect(screen.queryByRole('link', { name: 'На главную' })).toBeNull();
  expect(screen.queryAllByRole('link').filter((a) => a.getAttribute('href') === '/')).toHaveLength(0);
});

test('admin использует общий CabinetHeader: крошки, поиск, оформление, выход; без колокольчика', () => {
  mockAuth({ roles: ['admin', 'supervisor'], activeRole: 'admin' });
  render(
    <ThemeProvider>
      <A11yProvider>
        <AdminLayout />
      </A11yProvider>
    </ThemeProvider>,
  );

  const nav = screen.getByRole('navigation', { name: 'Навигационная цепочка' });
  expect(within(nav).getByRole('link', { name: 'Главная' })).toHaveAttribute('href', '/admin');
  expect(within(nav).getByText('Пользователи')).toHaveAttribute('aria-current', 'page');

  expect(screen.getByRole('searchbox', { name: 'Поиск — будет доступен позже' })).toBeDisabled();
  // Колокольчик — только student/psychologist; заглушки «скоро» больше нет.
  expect(screen.queryByRole('button', { name: /Уведомления/ })).toBeNull();
  expect(screen.getByRole('button', { name: 'Оформление и версия для слабовидящих' })).toBeInTheDocument();
  // Отдельных кнопок «глаз» и почты в шапке нет.
  expect(screen.queryByRole('button', { name: 'Версия для слабовидящих' })).toBeNull();
  expect(screen.queryByRole('button', { name: 'Почта' })).toBeNull();
  // Multi-role: topbar-копия переключателя кабинета на месте.
  expect(screen.getAllByRole('button', { name: /Администратор/ }).length).toBeGreaterThanOrEqual(1);

  fireEvent.click(screen.getByRole('button', { name: 'Выйти' }));
  expect(mockLogout).toHaveBeenCalledTimes(1);
});

test('страница теста: «Главная / Тесты / Тест»', () => {
  mockPathname = '/admin/tests/abc';
  mockAuth({ roles: ['admin'], activeRole: 'admin' });
  render(<AdminLayout />);

  const nav = screen.getByRole('navigation', { name: 'Навигационная цепочка' });
  expect(within(nav).getByRole('link', { name: 'Тесты' })).toHaveAttribute('href', '/admin/tests');
  expect(within(nav).getByText('Тест')).toHaveAttribute('aria-current', 'page');
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

describe('mobile drawer админки (<=600px — та же модель, что у кабинетов)', () => {
  const openDrawer = () => {
    fireEvent.click(screen.getByRole('button', { name: 'Открыть меню' }));
    return screen.getByRole('dialog', { name: 'Меню панели управления' });
  };

  test('по умолчанию drawer закрыт: навигация — в sidebar (rail/полный), hamburger есть', () => {
    mockAuth({ roles: ['admin'], activeRole: 'admin' });
    render(<AdminLayout />);
    expect(screen.queryByRole('dialog')).toBeNull();
    // Sidebar с той же навигацией остаётся основным механизмом шире 600px.
    expect(screen.getAllByRole('link', { name: 'Пользователи' })).toHaveLength(1);
    expect(screen.getByRole('button', { name: 'Открыть меню' }))
      .toHaveAttribute('aria-expanded', 'false');
  });

  test('drawer содержит полный brand → /admin, пользователя и ту же admin-навигацию', () => {
    mockAuth({ roles: ['admin', 'supervisor'], activeRole: 'admin' });
    render(<AdminLayout />);
    const drawer = openDrawer();

    const brand = within(drawer).getByRole('link', {
      name: 'Психология ДонГУ, панель управления — на главную',
    });
    expect(brand).toHaveAttribute('href', '/admin');
    expect(brand).toHaveTextContent('Панель управления');

    ['Пользователи', 'Материалы', 'Новости', 'Тесты', 'Баннер', 'Карточки услуг',
      'Типы материалов', 'Темы', 'Типы встреч', 'Домены регистрации',
      'Журнал действий', 'Безопасность'].forEach((name) => {
      expect(within(drawer).getByRole('link', { name })).toBeInTheDocument();
    });
    expect(within(drawer).getByText('Система')).toBeInTheDocument();
    // Переключатель кабинета и поддержка — как в sidebar.
    expect(within(drawer).getByRole('button', { name: /Администратор/ })).toBeInTheDocument();
    expect(within(drawer).getByRole('link', { name: 'support@donnu.ru' })).toBeInTheDocument();
  });

  test('фокус в drawer на «Закрыть меню»; Escape закрывает и возвращает фокус', () => {
    mockAuth({ roles: ['admin'], activeRole: 'admin' });
    render(<AdminLayout />);
    const burger = screen.getByRole('button', { name: 'Открыть меню' });
    const drawer = openDrawer();
    expect(within(drawer).getByRole('button', { name: 'Закрыть меню' })).toHaveFocus();

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(burger).toHaveFocus();
  });

  test('переход по пункту навигации закрывает drawer', () => {
    mockAuth({ roles: ['admin'], activeRole: 'admin' });
    render(<AdminLayout />);
    const drawer = openDrawer();
    fireEvent.click(within(drawer).getByRole('link', { name: 'Журнал действий' }));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  test('клик по brand в drawer закрывает drawer', () => {
    mockAuth({ roles: ['admin'], activeRole: 'admin' });
    render(<AdminLayout />);
    const drawer = openDrawer();
    fireEvent.click(within(drawer).getByRole('link', {
      name: 'Психология ДонГУ, панель управления — на главную',
    }));
    expect(screen.queryByRole('dialog')).toBeNull();
  });
});
