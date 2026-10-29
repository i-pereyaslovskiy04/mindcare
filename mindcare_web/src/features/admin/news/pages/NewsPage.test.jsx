import fs from 'fs';
import path from 'path';
import { render, screen, within, fireEvent, waitFor } from '@testing-library/react';
import NewsPage from './NewsPage';
import { useAdminNews } from '../hooks/useAdminNews';
import { deleteNews, getAdminNewsItem } from '../../../../api/news.api';

jest.mock('../hooks/useAdminNews');
jest.mock('../../../../api/news.api');
jest.mock('../components/NewsFormModal', () => function NewsFormStub({ news }) {
  return <div role="dialog" aria-label="Форма новости">{news ? news.uuid : 'new'}</div>;
});

const tag = (name) => ({ uuid: `t-${name}`, name });
const NEWS = [
  {
    uuid: 'n-1', title: 'Неделя психологического здоровья', cover_image_url: '/media/cover-1.jpg',
    tags: [tag('Стресс'), tag('Тревожность'), tag('Сон'), tag('Сессия'), tag('Семья')],
    is_published: true, published_at: '2026-10-20T09:30:00Z', created_at: '2026-10-01T09:30:00Z',
    created_by_name: 'Супервизор Демо',
  },
  {
    uuid: 'n-2', title: 'Итоги недели', cover_image_url: null, tags: [],
    is_published: false, published_at: null, created_at: '2026-10-09T09:30:00Z', created_by_name: null,
  },
];

const setPage = jest.fn();
const setFilters = jest.fn();
const setQuery = jest.fn();
const refetch = jest.fn();

function mockNews(overrides = {}) {
  useAdminNews.mockReturnValue({
    items: NEWS, loading: false, error: null, total: 2, page: 1, setPage,
    query: '', setQuery, filters: { is_published: null }, setFilters, refetch, ...overrides,
  });
}

beforeEach(() => {
  jest.clearAllMocks();
  mockNews();
});

// jsdom не применяет CSS: обе раскладки ResponsiveTable в DOM.
const table = () => screen.getByRole('table', { name: 'Новости' });
const list = () => screen.getByRole('list', { name: 'Новости' });
const row = (title) => within(table()).getAllByRole('row').find((r) => within(r).queryByText(title));
const record = (title) => within(list()).getAllByRole('listitem')
  .find((li) => within(li).queryByRole('heading', { level: 2, name: title }));

test('wide: Новость | Статус | Темы | Действия на shared ResponsiveTable', () => {
  render(<NewsPage />);
  expect(within(table()).getAllByRole('columnheader').map((th) => th.textContent))
    .toEqual(['Новость', 'Статус', 'Темы', 'Действия']);
  const r = row('Неделя психологического здоровья');
  expect(within(r).getByText('Опубликовано')).toBeInTheDocument();
  expect(within(r).getByText(/Супервизор Демо/)).toBeInTheDocument();
  expect(within(r).getByText('20.10.2026')).toBeInTheDocument();
  expect(within(row('Итоги недели')).getByText('Черновик')).toBeInTheDocument();
  expect(within(row('Итоги недели')).getByText('09.10.2026')).toBeInTheDocument();
});

test('обложка — identity.media; без обложки картинки нет (плашка ResponsiveTable)', () => {
  render(<NewsPage />);
  // alt="" — декоративная картинка, роль presentation
  const imgs = within(row('Неделя психологического здоровья')).getAllByRole('presentation');
  expect(imgs[0]).toHaveAttribute('src', '/media/cover-1.jpg');
  expect(within(row('Итоги недели')).queryAllByRole('presentation')).toHaveLength(0);
  expect(within(record('Итоги недели')).queryAllByRole('presentation')).toHaveLength(0);
});

test('темы: две видимых и «+N»; без тем — «—» в таблице и нет строки в записи', () => {
  render(<NewsPage />);
  const topics = within(row('Неделя психологического здоровья')).getByRole('list', { name: 'Темы' });
  expect(within(topics).getAllByRole('listitem').map((li) => li.textContent)).toEqual(['Стресс', 'Тревожность']);
  fireEvent.click(within(row('Неделя психологического здоровья'))
    .getByRole('button', { name: '+3: показать все, всего 5' }));
  expect(within(topics).getAllByRole('listitem')).toHaveLength(5);

  expect(within(row('Итоги недели')).getByText('—')).toBeInTheDocument();
  expect(within(record('Итоги недели')).queryByRole('term')).toBeNull();
  expect(within(record('Неделя психологического здоровья')).getByRole('term')).toHaveTextContent('Темы');
});

test('действия: «Редактировать» видно, «Удалить» — в меню ⋮ (в обеих раскладках)', () => {
  render(<NewsPage />);
  [row('Итоги недели'), record('Итоги недели')].forEach((scope) => {
    expect(within(scope).getByRole('button', { name: 'Редактировать «Итоги недели»' })).toBeInTheDocument();
    expect(within(scope).queryByRole('button', { name: /^Удалить/ })).toBeNull();
    expect(within(scope).getByRole('button', { name: 'Другие действия: «Итоги недели»' })).toBeInTheDocument();
  });
});

test('«Редактировать» загружает полную новость один раз и открывает форму', async () => {
  getAdminNewsItem.mockResolvedValue({ ...NEWS[1], content: '<p>x</p>' });
  render(<NewsPage />);
  fireEvent.click(within(record('Итоги недели')).getByRole('button', { name: 'Редактировать «Итоги недели»' }));
  expect(await screen.findByRole('dialog', { name: 'Форма новости' })).toHaveTextContent('n-2');
  expect(getAdminNewsItem).toHaveBeenCalledTimes(1);
  expect(getAdminNewsItem).toHaveBeenCalledWith('n-2');
});

test('ошибка загрузки полной новости — сообщение над таблицей', async () => {
  getAdminNewsItem.mockRejectedValue(new Error('сбой'));
  render(<NewsPage />);
  fireEvent.click(within(row('Итоги недели')).getByRole('button', { name: 'Редактировать «Итоги недели»' }));
  expect(await screen.findByText('Не удалось загрузить новость: сбой')).toBeInTheDocument();
});

test('«Удалить» из меню — подтверждение, затем DELETE и перезагрузка списка', async () => {
  deleteNews.mockResolvedValue(null);
  render(<NewsPage />);
  fireEvent.click(within(row('Итоги недели')).getByRole('button', { name: 'Другие действия: «Итоги недели»' }));
  expect(screen.getAllByRole('menuitem').map((i) => i.textContent)).toEqual(['Удалить']);
  fireEvent.click(screen.getByRole('menuitem', { name: 'Удалить' }));
  expect(screen.getByText('Удалить новость?')).toBeInTheDocument();
  expect(deleteNews).not.toHaveBeenCalled();

  fireEvent.click(screen.getByRole('button', { name: 'Удалить' }));
  await waitFor(() => expect(deleteNews).toHaveBeenCalledWith('n-2'));
  await waitFor(() => expect(refetch).toHaveBeenCalledTimes(1));
});

test('загрузка, ошибка и пусто — состояния ResponsiveTable', () => {
  mockNews({ loading: true, items: [] });
  const { rerender } = render(<NewsPage />);
  expect(list()).toHaveAttribute('aria-busy', 'true');

  mockNews({ error: 'Сервис недоступен', items: [] });
  rerender(<NewsPage />);
  expect(screen.getAllByText('Ошибка загрузки: Сервис недоступен')).toHaveLength(2);

  mockNews({ items: [], total: 0 });
  rerender(<NewsPage />);
  expect(screen.getAllByText('Новостей пока нет')).toHaveLength(2);
});

test('фильтр статуса и пагинация работают через хук, как прежде', () => {
  mockNews({ total: 45, page: 2 });
  render(<NewsPage />);
  expect(screen.getByText('2 / 3')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '›' }));
  fireEvent.click(screen.getByRole('button', { name: '‹' }));
  expect(setPage).toHaveBeenCalledTimes(2);

  fireEvent.change(screen.getByPlaceholderText('Поиск по заголовку...'), { target: { value: 'неделя' } });
  expect(setQuery).toHaveBeenCalledWith('неделя');
});

test('одна реализация для admin и supervisor: без ролевых веток и локальной responsive-механики', () => {
  const dir = path.join(__dirname, '..', 'components');
  const tableSrc = fs.readFileSync(path.join(dir, 'NewsTable.jsx'), 'utf8');
  const tableCss = fs.readFileSync(path.join(dir, 'NewsTable.module.css'), 'utf8');
  const pageSrc = fs.readFileSync(path.join(__dirname, 'NewsPage.jsx'), 'utf8');
  [tableSrc, pageSrc].forEach((src) => {
    expect(src).not.toMatch(/useAuth|activeRole|'supervisor'|'admin'/);
  });
  expect(tableSrc).toMatch(/ResponsiveTable/);
  expect(tableSrc).not.toMatch(/<table|<thead|<tr/);
  expect(tableCss).not.toMatch(/@container|@media|overflow-x/);
});
