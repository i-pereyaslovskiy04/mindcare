import { fireEvent, render, screen, within } from '@testing-library/react';
import UsersPage from './UsersPage';
import { useAdminUsers } from '../hooks/useAdminUsers';

jest.mock('react-router-dom', () => ({ useNavigate: () => jest.fn() }), { virtual: true });
jest.mock('../../../auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1 }, impersonate: jest.fn() }),
}));
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

beforeEach(() => {
  jest.clearAllMocks();
  useAdminUsers.mockReturnValue({
    items: [ITEM], loading: false, error: null, total: 45,
    page: 2, setPage, size: 20,
    query: 'псих', setQuery: jest.fn(),
    filters: { role: '', showDisabled: false }, setFilters,
    refetch: jest.fn(),
  });
});

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
