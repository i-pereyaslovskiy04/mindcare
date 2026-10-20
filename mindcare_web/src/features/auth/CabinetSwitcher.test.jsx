import { render, screen, fireEvent, act } from '@testing-library/react';
import CabinetSwitcher from './CabinetSwitcher';
import * as AuthContext from './AuthContext';

const mockNavigate = jest.fn();
jest.mock('react-router-dom', () => ({
  useNavigate: () => mockNavigate,
}), { virtual: true });
jest.mock('./AuthContext', () => ({ useAuth: jest.fn() }));

const setActiveRole = jest.fn();

function mockAuth(roles) {
  AuthContext.useAuth.mockReturnValue({
    user: { roles },
    setActiveRole,
  });
}

beforeEach(() => jest.clearAllMocks());

test('single-role renders a static label, no switcher button', () => {
  mockAuth(['supervisor']);
  render(<CabinetSwitcher currentRole="supervisor" />);
  expect(screen.getByText('Супервизор')).toBeInTheDocument();
  expect(screen.queryByRole('button')).toBeNull();
});

test('чистый пользователь: статичный лейбл «Пользователь», без «Студент» и без кнопки', () => {
  mockAuth(['student']);
  render(<CabinetSwitcher currentRole="student" />);
  expect(screen.getByText('Пользователь')).toBeInTheDocument();
  expect(screen.queryByText('Студент')).toBeNull();
  expect(screen.queryByRole('button')).toBeNull();
});

test('staff: пункт кабинета student подписан «Пользователь»; код роли и маршрут /student прежние', () => {
  mockAuth(['psychologist', 'student']);
  render(<CabinetSwitcher currentRole="psychologist" />);

  fireEvent.click(screen.getByRole('button', { name: /Психолог/ }));
  expect(screen.queryByRole('button', { name: 'Студент' })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Пользователь' }));

  expect(setActiveRole).toHaveBeenCalledWith('student');
  expect(mockNavigate).toHaveBeenCalledWith('/student');
});

test('currentRole=null renders "Выбрать кабинет"', () => {
  mockAuth(['admin', 'supervisor']);
  render(<CabinetSwitcher currentRole={null} />);
  expect(screen.getByRole('button', { name: /Выбрать кабинет/ })).toBeInTheDocument();
});

test('multi-role: opens panel, aria-expanded toggles, choosing switches + closes', () => {
  mockAuth(['admin', 'supervisor']);
  render(<CabinetSwitcher currentRole="admin" />);

  const trigger = screen.getByRole('button', { name: /Администратор/ });
  expect(trigger).toHaveAttribute('aria-expanded', 'false');

  fireEvent.click(trigger);
  expect(trigger).toHaveAttribute('aria-expanded', 'true');
  expect(screen.getByText('Перейти в кабинет')).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: 'Супервизор' }));
  expect(setActiveRole).toHaveBeenCalledWith('supervisor');
  expect(mockNavigate).toHaveBeenCalledWith('/supervisor');
  // панель закрылась
  expect(screen.queryByText('Перейти в кабинет')).toBeNull();
});

test('outside click closes the panel', () => {
  mockAuth(['admin', 'supervisor']);
  render(
    <div>
      <CabinetSwitcher currentRole="admin" />
      <button type="button">outside</button>
    </div>,
  );

  fireEvent.click(screen.getByRole('button', { name: /Администратор/ }));
  expect(screen.getByText('Перейти в кабинет')).toBeInTheDocument();

  fireEvent.mouseDown(screen.getByRole('button', { name: 'outside' }));
  expect(screen.queryByText('Перейти в кабинет')).toBeNull();
});

test('window resize while open recomputes position without closing the panel', () => {
  mockAuth(['admin', 'supervisor']);
  render(<CabinetSwitcher currentRole="admin" />);

  fireEvent.click(screen.getByRole('button', { name: /Администратор/ }));
  expect(screen.getByText('Перейти в кабинет')).toBeInTheDocument();

  act(() => { window.dispatchEvent(new Event('resize')); });
  // Панель остаётся открытой — resize пересчитывает координаты, а не закрывает.
  expect(screen.getByText('Перейти в кабинет')).toBeInTheDocument();
});

test('orientationchange while open recomputes position without closing the panel', () => {
  mockAuth(['admin', 'supervisor']);
  render(<CabinetSwitcher currentRole="admin" />);

  fireEvent.click(screen.getByRole('button', { name: /Администратор/ }));
  act(() => { window.dispatchEvent(new Event('orientationchange')); });
  expect(screen.getByText('Перейти в кабинет')).toBeInTheDocument();
});

test('scrolling the page closes the panel', () => {
  mockAuth(['admin', 'supervisor']);
  render(<CabinetSwitcher currentRole="admin" />);

  fireEvent.click(screen.getByRole('button', { name: /Администратор/ }));
  expect(screen.getByText('Перейти в кабинет')).toBeInTheDocument();

  act(() => { window.dispatchEvent(new Event('scroll')); });
  expect(screen.queryByText('Перейти в кабинет')).toBeNull();
});

test('scroll inside a nested scrollable container also closes the panel (capture)', () => {
  mockAuth(['admin', 'supervisor']);
  render(
    <div>
      <div data-testid="scrollable" style={{ overflow: 'auto' }}>
        <CabinetSwitcher currentRole="admin" />
      </div>
    </div>,
  );

  fireEvent.click(screen.getByRole('button', { name: /Администратор/ }));
  expect(screen.getByText('Перейти в кабинет')).toBeInTheDocument();

  fireEvent.scroll(screen.getByTestId('scrollable'));
  expect(screen.queryByText('Перейти в кабинет')).toBeNull();
});

test('Escape closes the panel and returns focus to the trigger', () => {
  mockAuth(['admin', 'supervisor']);
  render(<CabinetSwitcher currentRole="admin" />);

  const trigger = screen.getByRole('button', { name: /Администратор/ });
  fireEvent.click(trigger);
  expect(screen.getByText('Перейти в кабинет')).toBeInTheDocument();

  fireEvent.keyDown(trigger, { key: 'Escape' });
  expect(screen.queryByText('Перейти в кабинет')).toBeNull();
  expect(trigger).toHaveFocus();
});

// ── Заметность и состав кабинетов (доработка 2026-10-13) ─────────────────────

test('multi-role: видимая кнопка «Сменить кабинет» с текущей ролью и понятным доступным именем', () => {
  mockAuth(['supervisor', 'student']);
  render(<CabinetSwitcher currentRole="supervisor" />);
  const trigger = screen.getByRole('button', { name: 'Сменить кабинет (текущий: Супервизор)' });
  expect(trigger).toHaveTextContent('Сменить кабинет');
  expect(trigger).toHaveTextContent('Супервизор');
  expect(trigger).toHaveAttribute('aria-expanded', 'false');
});

test('compact-вариант (topbar) — то же доступное имя', () => {
  mockAuth(['psychologist', 'student']);
  render(<CabinetSwitcher currentRole="psychologist" variant="compact" />);
  expect(screen.getByRole('button', { name: 'Сменить кабинет (текущий: Психолог)' }))
    .toBeInTheDocument();
});

test('одна роль — без меню и без надписи «Сменить кабинет»', () => {
  mockAuth(['psychologist']);
  render(<CabinetSwitcher currentRole="psychologist" />);
  expect(screen.queryByRole('button')).toBeNull();
  expect(screen.queryByText('Сменить кабинет')).toBeNull();
});

test.each([
  [['psychologist', 'student'], ['Психолог', 'Пользователь']],
  [['supervisor', 'psychologist', 'student'], ['Супервизор', 'Психолог', 'Пользователь']],
  [['admin', 'supervisor', 'psychologist', 'student'],
    ['Администратор', 'Супервизор', 'Психолог', 'Пользователь']],
])('roles %j → все назначенные кабинеты, включая «Пользователь» (без selectableRoles)', (roles, labels) => {
  mockAuth(roles);
  render(<CabinetSwitcher currentRole={roles[0]} />);
  fireEvent.click(screen.getByRole('button', { name: /Сменить кабинет/ }));
  const options = screen.getAllByRole('button').filter((b) => !/Сменить кабинет/.test(b.getAttribute('aria-label') || ''));
  expect(options.map((b) => b.textContent)).toEqual(labels);
  expect(options[0]).toHaveAttribute('aria-current', 'true');
});

test.each([
  ['student', '/student'],
  ['psychologist', '/psychologist'],
  ['supervisor', '/supervisor'],
  ['admin', '/admin/users'],
])('переход в кабинет %s → %s без повторного входа', (role, path) => {
  mockAuth(['admin', 'supervisor', 'psychologist', 'student']);
  render(<CabinetSwitcher currentRole={role === 'admin' ? 'student' : 'admin'} />);
  fireEvent.click(screen.getByRole('button', { name: /Сменить кабинет/ }));
  const labels = { student: 'Пользователь', psychologist: 'Психолог', supervisor: 'Супервизор', admin: 'Администратор' };
  fireEvent.click(screen.getByRole('button', { name: labels[role] }));
  expect(setActiveRole).toHaveBeenCalledWith(role);
  expect(mockNavigate).toHaveBeenCalledWith(path);
});

test('клавиатура: Escape в панели закрывает её и возвращает фокус на кнопку', () => {
  mockAuth(['supervisor', 'student']);
  render(<CabinetSwitcher currentRole="supervisor" />);
  const trigger = screen.getByRole('button', { name: /Сменить кабинет/ });
  trigger.focus();
  fireEvent.keyDown(trigger, { key: 'Enter' });
  fireEvent.click(trigger);
  const option = screen.getByRole('button', { name: 'Пользователь' });
  option.focus();
  fireEvent.keyDown(option, { key: 'Escape' });
  expect(screen.queryByText('Перейти в кабинет')).toBeNull();
  expect(trigger).toHaveFocus();
});
