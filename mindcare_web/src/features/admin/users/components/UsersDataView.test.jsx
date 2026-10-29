import { fireEvent, render, screen, within } from '@testing-library/react';
import UsersDataView from './UsersDataView';

const ITEMS = [
  { id: 2, uuid: 'active', full_name: 'Активный Психолог', email: 'psy@donnu.ru',
    roles: ['psychologist', 'student'], is_active: true, deleted_at: null,
    created_at: '2026-01-01T00:00:00Z', last_login: '2026-02-01T00:00:00Z' },
  { id: 4, uuid: 'deleted', full_name: 'Удалён Ранее', email: 'old@donnu.ru',
    roles: ['student'], is_active: false, deleted_at: '2025-01-01T00:00:00Z',
    created_at: '2025-01-01T00:00:00Z', last_login: null },
];

function setup(props = {}) {
  const ctx = { currentUserId: 1, onEdit: jest.fn(), onRestore: jest.fn(), onDeactivate: jest.fn(), onImpersonate: jest.fn() };
  render(<UsersDataView items={ITEMS} loading={false} error={null} actionContext={ctx} {...props} />);
  return ctx;
}

// jsdom не применяет CSS: обе раскладки в DOM, выбор между ними — container query.
const table = () => screen.getByRole('table', { name: 'Пользователи' });
const list = () => screen.getByRole('list', { name: 'Пользователи' });

test('обе раскладки показывают одни и те же записи', () => {
  setup();
  // Первая ячейка строки: ФИО, затем email.
  const inTable = within(table()).getAllByRole('row').slice(1)
    .map((r) => within(r).getAllByRole('cell')[0].firstChild.textContent); // eslint-disable-line testing-library/no-node-access
  const inList = within(list()).getAllByRole('heading', { level: 2 }).map((h) => h.textContent);
  expect(inList).toEqual(['Активный Психолог', 'Удалён Ранее']);
  expect(inTable).toEqual(inList);
});

test('строка списка: ФИО (заголовок), email, роли и статус, даты «подпись — значение», действия', () => {
  setup();
  const item = within(list()).getAllByRole('listitem')[0];
  expect(within(item).getByRole('heading', { name: 'Активный Психолог' })).toBeInTheDocument();
  expect(within(item).getByText('psy@donnu.ru')).toBeInTheDocument();
  expect(within(item).getByText('Психолог')).toBeInTheDocument();
  expect(within(item).getByText('Активен')).toBeInTheDocument();
  expect(within(item).getAllByRole('term').map((t) => t.textContent))
    .toEqual(['Регистрация', 'Последний вход']);
  expect(within(item).getByRole('button', { name: 'Редактировать Активный Психолог' })).toBeInTheDocument();
  expect(within(item).getByRole('button', { name: 'Другие действия: Активный Психолог' })).toBeInTheDocument();
});

test('у удалённого ранее в строке только «Восстановить», меню нет', () => {
  setup();
  const deleted = within(list()).getAllByRole('listitem')[1];
  expect(within(deleted).getByRole('button', { name: 'Восстановить Удалён Ранее' })).toBeInTheDocument();
  expect(within(deleted).queryByRole('button', { name: /Другие действия/ })).toBeNull();
  expect(within(deleted).queryByRole('button', { name: /Редактировать/ })).toBeNull();
});

test('действия обеих раскладок вызывают один и тот же обработчик страницы', () => {
  const ctx = setup();
  fireEvent.click(within(table()).getByRole('button', { name: 'Редактировать Активный Психолог' }));
  fireEvent.click(within(list()).getByRole('button', { name: 'Редактировать Активный Психолог' }));
  expect(ctx.onEdit).toHaveBeenCalledTimes(2);
  expect(ctx.onEdit.mock.calls[0][0]).toBe(ctx.onEdit.mock.calls[1][0]);

  fireEvent.click(within(list()).getByRole('button', { name: 'Другие действия: Активный Психолог' }));
  fireEvent.click(screen.getByRole('menuitem', { name: 'Отключить аккаунт' }));
  expect(ctx.onDeactivate).toHaveBeenCalledWith(ITEMS[0]);

  fireEvent.click(within(list()).getByRole('button', { name: 'Восстановить Удалён Ранее' }));
  expect(ctx.onRestore).toHaveBeenCalledWith(ITEMS[1]);
});

test('состояния компактного списка: загрузка, ошибка, пусто', () => {
  const { rerender } = render(<UsersDataView items={[]} loading error={null} actionContext={{}} />);
  expect(screen.getByRole('list', { name: 'Пользователи' })).toHaveAttribute('aria-busy', 'true');
  rerender(<UsersDataView items={[]} loading={false} error="Сбой" actionContext={{}} />);
  expect(screen.getAllByText('Ошибка загрузки: Сбой')).toHaveLength(2);   // таблица + список
  rerender(<UsersDataView items={[]} loading={false} error={null} actionContext={{}} />);
  expect(screen.getAllByText('Пользователи не найдены')).toHaveLength(2);
});
