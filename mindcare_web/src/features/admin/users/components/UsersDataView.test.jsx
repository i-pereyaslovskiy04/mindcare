import { fireEvent, render, screen, within } from '@testing-library/react';
import UsersDataView from './UsersDataView';

const base = {
  email: 'x@donnu.ru', role: 'psychologist', created_at: '2026-01-01T00:00:00Z',
  last_login: '2026-02-01T00:00:00Z', deleted_at: null, deactivation_source: null,
};
const ITEMS = [
  { ...base, id: 1, uuid: 'me', full_name: 'Я Админ', roles: ['admin', 'student'], is_active: true },
  { ...base, id: 2, uuid: 'active', full_name: 'Активный Психолог', email: 'psy@donnu.ru',
    roles: ['psychologist', 'student'], is_active: true },
  { ...base, id: 3, uuid: 'self-off', full_name: 'Сам Отключился', roles: ['student'],
    is_active: false, deactivation_source: 'self', last_login: null },
  { ...base, id: 4, uuid: 'deleted', full_name: 'Удалён Ранее', roles: ['student'],
    is_active: false, deleted_at: '2025-01-01T00:00:00Z' },
];

function setup(props = {}) {
  const ctx = {
    currentUserId: 1, onEdit: jest.fn(), onRestore: jest.fn(),
    onDeactivate: jest.fn(), onImpersonate: jest.fn(),
  };
  render(<UsersDataView items={ITEMS} loading={false} error={null} actionContext={ctx} {...props} />);
  return ctx;
}

// jsdom не применяет CSS: обе раскладки ResponsiveTable в DOM.
const table = () => screen.getByRole('table', { name: 'Пользователи' });
const list = () => screen.getByRole('list', { name: 'Пользователи' });
const row = (name) => within(table()).getAllByRole('row').find((r) => within(r).queryByText(name));
const record = (name) => within(list()).getAllByRole('listitem')
  .find((li) => within(li).queryByRole('heading', { name }));
const openMenu = (scope, name) => fireEvent.click(
  within(scope).getByRole('button', { name: `Другие действия: ${name}` }),
);

test('таблица: Пользователь (ФИО + email), Роли и статус, Активность, Действия', () => {
  setup();
  expect(within(table()).getAllByRole('columnheader').map((th) => th.textContent))
    .toEqual(['Пользователь', 'Роли и статус', 'Активность', 'Действия']);
  const active = row('Активный Психолог');
  expect(within(active).getByText('psy@donnu.ru')).toBeInTheDocument();
  expect(within(active).getByText('Психолог')).toBeInTheDocument();
  expect(within(active).getByText('Активен')).toBeInTheDocument();
  expect(within(active).getByText('Регистрация')).toBeInTheDocument();
  expect(within(active).getByText('01.01.2026')).toBeInTheDocument();
});

test('строка списка: ФИО (h2), email, роли и статус, даты «подпись — значение», действия', () => {
  setup();
  const item = record('Активный Психолог');
  expect(within(item).getByText('psy@donnu.ru')).toBeInTheDocument();
  expect(within(item).getByText('Психолог')).toBeInTheDocument();
  expect(within(item).getAllByRole('term').map((t) => t.textContent))
    .toEqual(['Регистрация', 'Последний вход']);
  expect(within(item).getByRole('button', { name: 'Редактировать Активный Психолог' })).toBeInTheDocument();
  expect(within(item).getByRole('button', { name: 'Другие действия: Активный Психолог' })).toBeInTheDocument();
});

test('обе раскладки показывают одни и те же записи в том же порядке', () => {
  setup();
  const names = ITEMS.map((u) => u.full_name);
  expect(within(list()).getAllByRole('heading', { level: 2 }).map((h) => h.textContent)).toEqual(names);
  expect(within(table()).getAllByRole('row').slice(1).map((r) => names.find((n) => within(r).queryByText(n))))
    .toEqual(names);
});

describe.each([
  ['таблица', (name) => row(name)],
  ['список', (name) => record(name)],
])('матрица действий (%s)', (_, scopeOf) => {
  test('свой аккаунт: только «Редактировать», меню нет', () => {
    setup();
    expect(within(scopeOf('Я Админ')).getByRole('button', { name: 'Редактировать Я Админ' })).toBeInTheDocument();
    expect(within(scopeOf('Я Админ')).queryByRole('button', { name: /Другие действия/ })).toBeNull();
  });

  test('активный не-админ: «Зайти под именем» и «Отключить аккаунт» в меню', () => {
    const ctx = setup();
    openMenu(scopeOf('Активный Психолог'), 'Активный Психолог');
    fireEvent.click(screen.getByRole('menuitem', { name: 'Зайти под именем' }));
    expect(ctx.onImpersonate).toHaveBeenCalledWith(ITEMS[1]);
    openMenu(scopeOf('Активный Психолог'), 'Активный Психолог');
    fireEvent.click(screen.getByRole('menuitem', { name: 'Отключить аккаунт' }));
    expect(ctx.onDeactivate).toHaveBeenCalledWith(ITEMS[1]);
  });

  test('отключённый: редактируется, восстанавливается через меню, без входа под именем', () => {
    const ctx = setup();
    const scope = scopeOf('Сам Отключился');
    expect(within(scope).getByRole('button', { name: 'Редактировать Сам Отключился' })).toBeInTheDocument();
    expect(within(scope).getByText('Отключён')).toBeInTheDocument();
    expect(within(scope).getByText('по запросу пользователя')).toBeInTheDocument();
    openMenu(scope, 'Сам Отключился');
    expect(screen.queryByRole('menuitem', { name: 'Зайти под именем' })).toBeNull();
    fireEvent.click(screen.getByRole('menuitem', { name: 'Восстановить' }));
    expect(ctx.onRestore).toHaveBeenCalledWith(ITEMS[2]);
  });

  test('удалённый ранее: только «Восстановить», не редактируется, меню нет', () => {
    const ctx = setup();
    const scope = scopeOf('Удалён Ранее');
    expect(within(scope).getByText('Отключён (удалён ранее)')).toBeInTheDocument();
    expect(within(scope).queryByRole('button', { name: /Редактировать/ })).toBeNull();
    expect(within(scope).queryByRole('button', { name: /Другие действия/ })).toBeNull();
    fireEvent.click(within(scope).getByRole('button', { name: 'Восстановить Удалён Ранее' }));
    expect(ctx.onRestore).toHaveBeenCalledWith(ITEMS[3]);
  });
});

test('«Редактировать» обеих раскладок вызывает один обработчик страницы с тем же пользователем', () => {
  const ctx = setup();
  fireEvent.click(within(table()).getByRole('button', { name: 'Редактировать Активный Психолог' }));
  fireEvent.click(within(list()).getByRole('button', { name: 'Редактировать Активный Психолог' }));
  expect(ctx.onEdit).toHaveBeenCalledTimes(2);
  expect(ctx.onEdit.mock.calls[0][0]).toBe(ctx.onEdit.mock.calls[1][0]);
});

test('состояния: загрузка, ошибка (с префиксом), пусто', () => {
  const { rerender } = render(<UsersDataView items={[]} loading error={null} actionContext={{}} />);
  expect(screen.getByRole('list', { name: 'Пользователи' })).toHaveAttribute('aria-busy', 'true');
  rerender(<UsersDataView items={[]} loading={false} error="Сбой" actionContext={{}} />);
  expect(screen.getAllByText('Ошибка загрузки: Сбой')).toHaveLength(2);   // таблица + список
  rerender(<UsersDataView items={[]} loading={false} error={null} actionContext={{}} />);
  expect(screen.getAllByText('Пользователи не найдены')).toHaveLength(2);
});
