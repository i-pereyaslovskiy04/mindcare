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
