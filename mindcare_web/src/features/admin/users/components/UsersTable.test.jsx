import { render, screen, within, fireEvent } from '@testing-library/react';
import UsersTable from './UsersTable';

const base = {
  email: 'x@donnu.ru', roles: ['psychologist', 'student'], role: 'psychologist',
  created_at: '2026-01-01T00:00:00Z', last_login: null, deleted_at: null,
  deactivation_source: null, deactivated_at: null,
};
const ITEMS = [
  { ...base, id: 1, uuid: 'me', full_name: 'Я Админ', roles: ['admin', 'student'], is_active: true },
  { ...base, id: 2, uuid: 'active', full_name: 'Активный Психолог', is_active: true },
  { ...base, id: 3, uuid: 'self-off', full_name: 'Сам Отключился', roles: ['student'],
    is_active: false, deactivation_source: 'self', deactivated_at: '2026-10-01T00:00:00Z' },
  { ...base, id: 4, uuid: 'deleted', full_name: 'Удалён Ранее', is_active: false,
    deleted_at: '2025-01-01T00:00:00Z' },
];

function renderTable(handlers = {}, props = {}) {
  render(
    <UsersTable
      items={ITEMS}
      loading={false}
      error={null}
      actionContext={{ currentUserId: 1, onEdit: jest.fn(), onImpersonate: jest.fn(), ...handlers }}
      {...props}
    />,
  );
}

// eslint-disable-next-line testing-library/no-node-access
const row = (name) => screen.getByText(name).closest('tr');
const openMenu = (name) => fireEvent.click(
  within(row(name)).getByRole('button', { name: `Другие действия: ${name}` }),
);

test('семантическая таблица: пользователь (ФИО + email), роли и статус, активность', () => {
  renderTable();
  const table = screen.getByRole('table', { name: 'Пользователи' });
  expect(within(table).getAllByRole('columnheader').map((th) => th.textContent))
    .toEqual(['Пользователь', 'Роли и статус', 'Активность', 'Действия']);
  const active = row('Активный Психолог');
  expect(within(active).getByText('x@donnu.ru')).toBeInTheDocument();
  expect(within(active).getByText('Психолог')).toBeInTheDocument();
  expect(within(active).getByText('Активен')).toBeInTheDocument();
  expect(within(active).getByText('Регистрация')).toBeInTheDocument();
  expect(within(active).getByText('01.01.2026')).toBeInTheDocument();
});

test('own admin account: только «Редактировать», меню нет', () => {
  renderTable();
  expect(within(row('Я Админ')).getByRole('button', { name: 'Редактировать Я Админ' })).toBeInTheDocument();
  expect(within(row('Я Админ')).queryByRole('button', { name: /Другие действия/ })).toBeNull();
});

test('active user is deactivated via the menu; disabled and deleted can be restored', () => {
  const onDeactivate = jest.fn();
  const onRestore = jest.fn();
  renderTable({ onDeactivate, onRestore });

  openMenu('Активный Психолог');
  fireEvent.click(screen.getByRole('menuitem', { name: 'Отключить аккаунт' }));
  expect(onDeactivate).toHaveBeenCalledWith(expect.objectContaining({ uuid: 'active' }));

  openMenu('Сам Отключился');
  fireEvent.click(screen.getByRole('menuitem', { name: 'Восстановить' }));
  fireEvent.click(within(row('Удалён Ранее')).getByRole('button', { name: 'Восстановить Удалён Ранее' }));
  expect(onRestore.mock.calls.map(([u]) => u.uuid)).toEqual(['self-off', 'deleted']);
});

test('impersonation via the menu for an active non-admin', () => {
  const onImpersonate = jest.fn();
  renderTable({ onImpersonate });
  openMenu('Активный Психолог');
  fireEvent.click(screen.getByRole('menuitem', { name: 'Зайти под именем' }));
  expect(onImpersonate).toHaveBeenCalledWith(expect.objectContaining({ uuid: 'active' }));
});

test('disabled (not deleted) stays editable; deleted is not editable; statuses shown', () => {
  renderTable();
  const selfOff = row('Сам Отключился');
  expect(within(selfOff).getByRole('button', { name: /Редактировать/ })).toBeInTheDocument();
  openMenu('Сам Отключился');
  expect(screen.queryByRole('menuitem', { name: 'Зайти под именем' })).toBeNull();
  expect(within(selfOff).getByText('Отключён')).toBeInTheDocument();
  expect(within(selfOff).getByText('по запросу пользователя')).toBeInTheDocument();

  const deleted = row('Удалён Ранее');
  expect(within(deleted).queryByRole('button', { name: /Редактировать/ })).toBeNull();
  expect(within(deleted).queryByRole('button', { name: /Другие действия/ })).toBeNull();
  expect(within(deleted).getByText('Отключён (удалён ранее)')).toBeInTheDocument();
});

test('состояния: ошибка и пусто — строкой на всю ширину', () => {
  const { unmount } = render(
    <UsersTable items={[]} loading={false} error="Сбой" actionContext={{}} />,
  );
  expect(screen.getByRole('cell', { name: 'Ошибка загрузки: Сбой' })).toHaveAttribute('colspan', '4');
  unmount();
  render(<UsersTable items={[]} loading={false} error={null} actionContext={{}} />);
  expect(screen.getByRole('cell', { name: 'Пользователи не найдены' })).toBeInTheDocument();
});
