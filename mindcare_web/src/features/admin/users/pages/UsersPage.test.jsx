import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import UsersPage from './UsersPage';
import { useAuth } from '../../../auth/AuthContext';
import { useAdminUsers } from '../hooks/useAdminUsers';

const mockNavigate = jest.fn();
jest.mock('react-router-dom', () => ({
  useNavigate: () => mockNavigate,
}), { virtual: true });
jest.mock('../../../auth/AuthContext', () => ({ useAuth: jest.fn() }));
jest.mock('../hooks/useAdminUsers', () => ({ useAdminUsers: jest.fn() }));
jest.mock('../components/UsersFilters', () => () => null);
jest.mock('../components/UserCreateModal', () => () => null);
jest.mock('../components/UserEditModal', () => () => null);
jest.mock('../components/UserLifecycleDialog', () => () => null);
jest.mock('../components/UsersTable', () => ({ items, onImpersonate }) => (
  <ul>
    {items.map((u) => (
      <li key={u.uuid}>
        <button type="button" onClick={() => onImpersonate(u)}>{`Зайти под именем ${u.full_name}`}</button>
      </li>
    ))}
  </ul>
));

const TARGET = { uuid: 'u-2', full_name: 'Иванова Анна Петровна' };
let impersonate;

beforeEach(() => {
  jest.clearAllMocks();
  impersonate = jest.fn().mockResolvedValue(undefined);
  useAuth.mockReturnValue({ user: { id: 1 }, impersonate });
  useAdminUsers.mockReturnValue({
    items: [TARGET], loading: false, error: null, total: 1,
    page: 1, setPage: jest.fn(), size: 20,
    query: '', setQuery: jest.fn(), filters: {}, setFilters: jest.fn(), refetch: jest.fn(),
  });
});

const openDialog = () => userEvent.click(
  screen.getByRole('button', { name: `Зайти под именем ${TARGET.full_name}` }),
);

test('«Зайти» открывает подтверждение и не вызывает API', () => {
  render(<UsersPage />);
  openDialog();
  const dialog = screen.getByRole('dialog', { name: 'Войти под именем пользователя?' });
  expect(dialog).toHaveTextContent(TARGET.full_name);
  expect(dialog).toHaveTextContent(/журнал аудита/);
  expect(impersonate).not.toHaveBeenCalled();
});

test('«Отмена» закрывает диалог без вызова API', () => {
  render(<UsersPage />);
  openDialog();
  userEvent.click(screen.getByRole('button', { name: 'Отмена' }));
  expect(impersonate).not.toHaveBeenCalled();
  expect(mockNavigate).not.toHaveBeenCalled();
});

test('«Войти» вызывает API один раз и переходит в кабинет', async () => {
  render(<UsersPage />);
  openDialog();
  userEvent.click(screen.getByRole('button', { name: 'Войти' }));
  await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/dashboard', { replace: true }));
  expect(impersonate).toHaveBeenCalledTimes(1);
  expect(impersonate).toHaveBeenCalledWith('u-2');
});

test('ошибка API показывается в диалоге', async () => {
  impersonate.mockRejectedValue(new Error('Нельзя войти под этим пользователем'));
  render(<UsersPage />);
  openDialog();
  userEvent.click(screen.getByRole('button', { name: 'Войти' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Нельзя войти под этим пользователем');
  expect(mockNavigate).not.toHaveBeenCalled();
});
