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

function renderTable(handlers = {}) {
  render(
    <UsersTable
      items={ITEMS}
      loading={false}
      error={null}
      currentUserId={1}
      onEdit={jest.fn()}
      onImpersonate={jest.fn()}
      {...handlers}
    />,
  );
}

function row(name) {
  return screen.getByText(name).closest('tr');
}

test('own admin account has no "deactivate" action', () => {
  renderTable();
  expect(within(row('Я Админ')).queryByRole('button', { name: /Отключить аккаунт/ })).toBeNull();
  expect(within(row('Я Админ')).getByRole('button', { name: /Редактировать/ })).toBeInTheDocument();
});

test('active user can be deactivated; disabled and deleted can be restored', () => {
  const onDeactivate = jest.fn();
  const onRestore = jest.fn();
  renderTable({ onDeactivate, onRestore });

  fireEvent.click(within(row('Активный Психолог')).getByRole('button', { name: /Отключить аккаунт/ }));
  expect(onDeactivate).toHaveBeenCalledWith(expect.objectContaining({ uuid: 'active' }));

  fireEvent.click(within(row('Сам Отключился')).getByRole('button', { name: /Восстановить/ }));
  fireEvent.click(within(row('Удалён Ранее')).getByRole('button', { name: /Восстановить/ }));
  expect(onRestore.mock.calls.map(([u]) => u.uuid)).toEqual(['self-off', 'deleted']);
});

test('disabled (not deleted) stays editable; deleted is not editable; statuses shown', () => {
  renderTable();
  const selfOff = row('Сам Отключился');
  expect(within(selfOff).getByRole('button', { name: /Редактировать/ })).toBeInTheDocument();
  expect(within(selfOff).queryByRole('button', { name: /Зайти под именем/ })).toBeNull();
  expect(within(selfOff).getByText('Отключён')).toBeInTheDocument();
  expect(within(selfOff).getByText('по запросу пользователя')).toBeInTheDocument();

  const deleted = row('Удалён Ранее');
  expect(within(deleted).queryByRole('button', { name: /Редактировать/ })).toBeNull();
  expect(within(deleted).getByText('Отключён (удалён ранее)')).toBeInTheDocument();
});
