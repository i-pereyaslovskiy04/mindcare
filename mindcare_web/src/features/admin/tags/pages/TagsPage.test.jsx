import fs from 'fs';
import path from 'path';
import { render, screen, within, fireEvent, waitFor } from '@testing-library/react';
import TagsPage from './TagsPage';
import { useAdminTags } from '../hooks/useAdminTags';
import { deleteTag } from '../../../../api/tags.api';

jest.mock('../hooks/useAdminTags');
jest.mock('../../../../api/tags.api');
jest.mock('../components/TagFormModal', () => function TagFormStub({ mode, tag }) {
  return <div role="dialog" aria-label="Форма темы">{mode}:{tag?.uuid}</div>;
});

const LONG = 'Психологическая поддержка студентов в период адаптации к дистанционному обучению и сессии';
const TAGS = [
  { uuid: 'tg-1', name: LONG, article_count: 1240, news_count: 385, test_count: 0, created_at: '2026-10-20T09:30:00Z' },
  { uuid: 'tg-2', name: 'Тревожность', article_count: 0, news_count: 0, test_count: 0, created_at: '2026-10-18T09:30:00Z' },
];
const refetch = jest.fn();

function mockTags(overrides = {}) {
  useAdminTags.mockReturnValue({
    items: TAGS, loading: false, error: null, total: 2, page: 1, setPage: jest.fn(), size: 50,
    query: '', setQuery: jest.fn(), refetch, ...overrides,
  });
}

beforeEach(() => {
  jest.clearAllMocks();
  mockTags();
});

const table = () => screen.getByRole('table', { name: 'Темы' });
const list = () => screen.getByRole('list', { name: 'Темы' });
const row = (name) => within(table()).getAllByRole('row').find((r) => within(r).queryByText(name, { selector: '.primary' }));
const record = (name) => within(list()).getAllByRole('listitem')
  .find((li) => within(li).queryByRole('heading', { level: 2, name }));

test('wide: Тема | Использование | Действия; название полностью, без Tag-обрезки', () => {
  render(<TagsPage />);
  expect(within(table()).getAllByRole('columnheader').map((th) => th.textContent))
    .toEqual(['Тема', 'Использование', 'Действия']);
  expect(within(row(LONG)).getByText(LONG)).toHaveClass('primary');
  expect(within(row(LONG)).getByText('создана 20.10.2026')).toBeInTheDocument();
  expect(within(row(LONG)).getByText('Статьи 1240')).toBeInTheDocument();
  expect(within(row(LONG)).getByText('Новости 385')).toBeInTheDocument();
  expect(within(row(LONG)).queryByText(/Тесты/)).toBeNull();
  expect(within(row('Тревожность')).getByText('Не используется')).toBeInTheDocument();
});

test('список: ненулевые счётчики — деталями; без связей — «Использование: нет»', () => {
  render(<TagsPage />);
  expect(within(record(LONG)).getAllByRole('term').map((t) => t.textContent)).toEqual(['Статьи', 'Новости']);
  expect(within(record('Тревожность')).getByRole('term')).toHaveTextContent('Использование');
  expect(within(record('Тревожность')).getByRole('definition')).toHaveTextContent('нет');
});

test('«Переименовать» открывает форму; «Удалить» в меню — с предупреждением о связях', async () => {
  deleteTag.mockResolvedValue(null);
  render(<TagsPage />);
  fireEvent.click(within(record('Тревожность')).getByRole('button', { name: 'Переименовать Тревожность' }));
  expect(screen.getByRole('dialog', { name: 'Форма темы' })).toHaveTextContent('tg-2');

  fireEvent.click(within(row(LONG)).getByRole('button', { name: `Другие действия: ${LONG}` }));
  expect(screen.getAllByRole('menuitem').map((i) => i.textContent)).toEqual(['Удалить']);
  fireEvent.click(screen.getByRole('menuitem', { name: 'Удалить' }));
  expect(screen.getByText(/Тема используется в 1625/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Удалить' }));
  await waitFor(() => expect(deleteTag).toHaveBeenCalledWith('tg-1'));
});

test('загрузка, ошибка и пусто — состояния ResponsiveTable', () => {
  mockTags({ loading: true, items: [] });
  const { rerender } = render(<TagsPage />);
  expect(list()).toHaveAttribute('aria-busy', 'true');
  mockTags({ error: 'Сбой', items: [] });
  rerender(<TagsPage />);
  expect(screen.getAllByText('Ошибка загрузки: Сбой')).toHaveLength(2);
  mockTags({ items: [], total: 0 });
  rerender(<TagsPage />);
  expect(screen.getAllByText('Темы не найдены')).toHaveLength(2);
});

test('нет локальной табличной и responsive-механики', () => {
  const dir = path.join(__dirname, '..', 'components');
  expect(fs.readFileSync(path.join(dir, 'TagsTable.jsx'), 'utf8')).not.toMatch(/<table|<thead|<tr/);
  expect(fs.readFileSync(path.join(dir, 'TagsTable.module.css'), 'utf8')).not.toMatch(/@container|@media|overflow-x|\.table/);
});
