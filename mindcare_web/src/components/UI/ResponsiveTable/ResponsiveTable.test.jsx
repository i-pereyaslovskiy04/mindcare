import fs from 'fs';
import path from 'path';
import { render, screen, within } from '@testing-library/react';
import ResponsiveTable from './ResponsiveTable';

const ITEMS = [
  { id: 'a', title: 'Первая запись', sub: 'a@x.ru', tag: 'Метка А', date: '01.01.2026', off: false },
  { id: 'b', title: 'Вторая запись', sub: 'b@x.ru', tag: 'Метка Б', date: '02.01.2026', off: true },
];

function renderTable(props = {}) {
  return render(
    <ResponsiveTable
      label="Записи"
      items={ITEMS}
      getKey={(i) => i.id}
      emptyText="Пусто"
      isMuted={(i) => i.off}
      identity={{ header: 'Запись', primary: (i) => i.title, secondary: (i) => i.sub }}
      status={{ header: 'Метки', render: (i) => <span>{i.tag}</span> }}
      columns={[{ key: 'date', header: 'Дата', render: (i) => i.date }]}
      meta={(i) => [{ label: 'Дата', value: i.date }]}
      actions={{
        primary: (i) => <button type="button">Открыть {i.title}</button>,
        menu: (i) => <button type="button">Меню {i.title}</button>,
      }}
      {...props}
    />,
  );
}

const table = () => screen.getByRole('table', { name: 'Записи' });
const list = () => screen.getByRole('list', { name: 'Записи' });

test('wide — семантическая таблица: caption, th scope=col, колонки по конфигу и «Действия»', () => {
  renderTable();
  const headers = within(table()).getAllByRole('columnheader');
  expect(headers.map((th) => th.textContent)).toEqual(['Запись', 'Метки', 'Дата', 'Действия']);
  headers.forEach((th) => expect(th).toHaveAttribute('scope', 'col'));
  const first = within(table()).getAllByRole('row')[1];
  expect(within(first).getAllByRole('cell').map((td) => td.textContent))
    .toEqual(['Первая записьa@x.ru', 'Метка А', '01.01.2026', 'Открыть Первая записьМеню Первая запись']);
});

test('compact/mobile — семантический список: li, заголовок записи h2, детали в dl, действия', () => {
  renderTable();
  const items = within(list()).getAllByRole('listitem');
  expect(items).toHaveLength(2);
  expect(within(items[0]).getByRole('heading', { level: 2, name: 'Первая запись' })).toBeInTheDocument();
  expect(within(items[0]).getByText('a@x.ru')).toBeInTheDocument();
  expect(within(items[0]).getByRole('term')).toHaveTextContent('Дата');
  expect(within(items[0]).getByRole('definition')).toHaveTextContent('01.01.2026');
  expect(within(items[0]).getByRole('button', { name: 'Открыть Первая запись' })).toBeInTheDocument();
  expect(within(items[0]).getByRole('button', { name: 'Меню Первая запись' })).toBeInTheDocument();
});

test('isMuted помечает строку таблицы и запись списка', () => {
  renderTable();
  expect(within(table()).getAllByRole('row')[2]).toHaveClass('muted');
  expect(within(list()).getAllByRole('listitem')[1]).toHaveClass('muted');
  expect(within(list()).getAllByRole('listitem')[0]).not.toHaveClass('muted');
});

test('без меню (actions.menu не передан) слот «⋮» в записях не резервируется', () => {
  const { unmount } = renderTable();
  expect(list()).not.toHaveClass('noMenu');
  unmount();
  renderTable({ actions: { primary: (i) => <button type="button">Открыть {i.title}</button> } });
  expect(list()).toHaveClass('noMenu');
  expect(screen.queryByRole('button', { name: /^Меню/ })).toBeNull();
});

test('identity.media — картинка слева от текста в таблице и в записи списка', () => {
  renderTable({
    identity: {
      header: 'Запись',
      media: (i) => (i.off ? null : <img src={`/${i.id}.png`} alt="" data-testid={`media-${i.id}`} />),
      primary: (i) => i.title,
      secondary: (i) => i.sub,
    },
  });
  const firstRow = within(table()).getAllByRole('row')[1];
  const cell = within(firstRow).getAllByRole('cell')[0];
  expect(cell).toHaveTextContent('Первая записьa@x.ru');
  // eslint-disable-next-line testing-library/no-node-access
  expect(cell.querySelector('.withMedia > .media > img')).not.toBeNull();
  // eslint-disable-next-line testing-library/no-node-access
  expect(cell.querySelector('.withMedia > .identityText > .primary')).toHaveTextContent('Первая запись');

  const [first, second] = within(list()).getAllByRole('listitem');
  const heading = within(first).getByRole('heading', { level: 2, name: 'Первая запись' });
  expect(heading).toHaveClass('primary');
  // eslint-disable-next-line testing-library/no-node-access
  expect(heading.closest('.identity .withMedia')).not.toBeNull();
  // media вернул null — пустая плашка того же размера (заголовки в одну вертикаль)
  // eslint-disable-next-line testing-library/no-node-access
  const emptyMedia = second.querySelector('.media');
  expect(emptyMedia).toBeEmptyDOMElement();
  expect(screen.getAllByTestId('media-a')).toHaveLength(2);
  expect(screen.queryByTestId('media-b')).toBeNull();
});

test('без identity.media место под картинку не резервируется (разметка прежняя)', () => {
  const { container } = renderTable();
  // eslint-disable-next-line testing-library/no-container, testing-library/no-node-access
  expect(container.querySelector('.withMedia, .media, .identityText')).toBeNull();
  const cell = within(within(table()).getAllByRole('row')[1]).getAllByRole('cell')[0];
  // eslint-disable-next-line testing-library/no-node-access
  expect([...cell.children].map((el) => el.className)).toEqual(['primary', 'secondary']);
});

test('без status, columns и actions — только колонка identity', () => {
  renderTable({ status: undefined, columns: [], actions: {} });
  expect(within(table()).getAllByRole('columnheader').map((th) => th.textContent)).toEqual(['Запись']);
  expect(screen.queryByRole('button')).toBeNull();
});

test('состояния: загрузка (скелет), ошибка и пусто — в обеих раскладках', () => {
  const { rerender } = renderTable({ loading: true });
  expect(list()).toHaveAttribute('aria-busy', 'true');
  expect(within(table()).getAllByRole('row')).toHaveLength(1 + 7);

  rerender(
    <ResponsiveTable label="Записи" items={[]} getKey={(i) => i.id} error="Сбой" emptyText="Пусто"
      identity={{ header: 'Запись', primary: (i) => i.title }} />,
  );
  expect(screen.getAllByText('Сбой')).toHaveLength(2);
  expect(within(table()).getByRole('cell', { name: 'Сбой' })).toHaveAttribute('colspan', '1');

  rerender(
    <ResponsiveTable label="Записи" items={[]} getKey={(i) => i.id} emptyText="Пусто"
      identity={{ header: 'Запись', primary: (i) => i.title }} />,
  );
  expect(screen.getAllByText('Пусто')).toHaveLength(2);
});

test('shared-слой не зависит от фич (направление зависимостей)', () => {
  ['ResponsiveTable.jsx', 'ResponsiveTable.module.css'].forEach((file) => {
    const src = fs.readFileSync(path.join(__dirname, file), 'utf8');
    expect(src).not.toMatch(/features\//);
  });
});

test('границы режимов заданы только в ResponsiveTable.module.css (56rem / 39rem)', () => {
  const css = fs.readFileSync(path.join(__dirname, 'ResponsiveTable.module.css'), 'utf8');
  expect(css).toMatch(/container-type:\s*inline-size/);
  expect(css).toMatch(/@container \(min-width: 56rem\)/);
  expect(css).toMatch(/@container \(min-width: 39rem\)/);
});
