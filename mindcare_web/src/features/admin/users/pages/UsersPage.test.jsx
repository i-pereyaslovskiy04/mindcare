import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import UsersPage from './UsersPage';
import { useAuth } from '../../../auth/AuthContext';
import { useAdminUsers } from '../hooks/useAdminUsers';

const mockNavigate = jest.fn();
jest.mock('react-router-dom', () => ({ useNavigate: () => mockNavigate }), { virtual: true });
jest.mock('../../../auth/AuthContext', () => ({ useAuth: jest.fn() }));
jest.mock('../hooks/useAdminUsers', () => ({ useAdminUsers: jest.fn() }));
// Диалоги — заглушки: проверяем, что они одни на страницу и получают цель.
jest.mock('../components/UserCreateModal', () => () => null);
jest.mock('../components/UserEditModal', () => function EditStub({ open, uuid }) {
  return open ? <div role="dialog" aria-label="Редактирование">{uuid}</div> : null;
});
jest.mock('../components/UserLifecycleDialog', () => function LifecycleStub({ open, mode, userInfo }) {
  return open ? <div role="dialog" aria-label="Жизненный цикл">{mode}:{userInfo.uuid}</div> : null;
});

const ITEM = {
  id: 2, uuid: 'active', full_name: 'Активный Психолог', email: 'psy@donnu.ru',
  roles: ['psychologist'], is_active: true, deleted_at: null,
  created_at: '2026-01-01T00:00:00Z', last_login: null,
};
const setPage = jest.fn();
const setFilters = jest.fn();
let impersonate;

beforeEach(() => {
  jest.clearAllMocks();
  impersonate = jest.fn().mockResolvedValue(undefined);
  useAuth.mockReturnValue({ user: { id: 1 }, impersonate });
  useAdminUsers.mockReturnValue({
    items: [ITEM], loading: false, error: null, total: 45,
    page: 2, setPage, size: 20,
    query: 'псих', setQuery: jest.fn(),
    filters: { role: '', showDisabled: false }, setFilters,
    refetch: jest.fn(),
  });
});

// ── Один источник данных для таблицы и компактного списка ───────────────────

test('один источник данных: hook вызывается один раз на рендер, обе раскладки получают его items', () => {
  render(<UsersPage />);
  expect(useAdminUsers).toHaveBeenCalledTimes(1);
  expect(within(screen.getByRole('table')).getByText('Активный Психолог')).toBeInTheDocument();
  expect(within(screen.getByRole('list', { name: 'Пользователи' })).getByText('Активный Психолог')).toBeInTheDocument();
});

test('«Редактировать» из таблицы и из списка открывает один и тот же диалог', () => {
  render(<UsersPage />);
  fireEvent.click(within(screen.getByRole('table')).getByRole('button', { name: 'Редактировать Активный Психолог' }));
  expect(screen.getAllByRole('dialog', { name: 'Редактирование' })).toHaveLength(1);
  expect(screen.getByRole('dialog', { name: 'Редактирование' })).toHaveTextContent('active');
});

test('отключение из компактного списка — тот же lifecycle-диалог страницы', () => {
  render(<UsersPage />);
  const list = screen.getByRole('list', { name: 'Пользователи' });
  fireEvent.click(within(list).getByRole('button', { name: 'Другие действия: Активный Психолог' }));
  fireEvent.click(screen.getByRole('menuitem', { name: 'Отключить аккаунт' }));
  expect(screen.getByRole('dialog', { name: 'Жизненный цикл' })).toHaveTextContent('deactivate:active');
});

test('фильтры и пагинация — вне раскладок данных и прежние', () => {
  render(<UsersPage />);
  expect(screen.getByDisplayValue('псих')).toBeInTheDocument();
  expect(screen.getByText('Стр. 2 из 3')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Вперёд →' }));
  expect(setPage).toHaveBeenCalledWith(3);
  // Пагинация и фильтры не внутри таблицы/списка.
  expect(within(screen.getByRole('table')).queryByText(/Стр\./)).toBeNull();
  expect(within(screen.getByRole('list', { name: 'Пользователи' })).queryByDisplayValue('псих')).toBeNull();
});

// ── Вход под именем через подтверждение ─────────────────────────────────────

const openImpersonateDialog = () => {
  const table = screen.getByRole('table');
  userEvent.click(within(table).getByRole('button', { name: `Другие действия: ${ITEM.full_name}` }));
  userEvent.click(screen.getByRole('menuitem', { name: 'Зайти под именем' }));
};

test('«Зайти» открывает подтверждение и не вызывает API', () => {
  render(<UsersPage />);
  openImpersonateDialog();
  const dialog = screen.getByRole('dialog', { name: 'Войти под именем пользователя?' });
  expect(dialog).toHaveTextContent(ITEM.full_name);
  expect(dialog).toHaveTextContent(/журнал аудита/);
  expect(impersonate).not.toHaveBeenCalled();
});

test('«Отмена» закрывает диалог без вызова API', () => {
  render(<UsersPage />);
  openImpersonateDialog();
  userEvent.click(screen.getByRole('button', { name: 'Отмена' }));
  expect(impersonate).not.toHaveBeenCalled();
  expect(mockNavigate).not.toHaveBeenCalled();
});

test('«Войти» вызывает API один раз и переходит в кабинет', async () => {
  render(<UsersPage />);
  openImpersonateDialog();
  userEvent.click(screen.getByRole('button', { name: 'Войти' }));
  await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/dashboard', { replace: true }));
  expect(impersonate).toHaveBeenCalledTimes(1);
  expect(impersonate).toHaveBeenCalledWith('active');
});

test('ошибка API показывается в диалоге, а не дублируется на странице', async () => {
  impersonate.mockRejectedValue(new Error('Нельзя войти под этим пользователем'));
  render(<UsersPage />);
  openImpersonateDialog();
  userEvent.click(screen.getByRole('button', { name: 'Войти' }));
  const dialog = screen.getByRole('dialog', { name: 'Войти под именем пользователя?' });
  expect(await within(dialog).findByRole('alert')).toHaveTextContent('Нельзя войти под этим пользователем');
  expect(screen.getAllByText('Нельзя войти под этим пользователем')).toHaveLength(1);
  expect(mockNavigate).not.toHaveBeenCalled();
});
