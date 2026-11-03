import fs from 'fs';
import path from 'path';
import { render, screen, within, fireEvent, waitFor } from '@testing-library/react';
import ArticlesPage from './ArticlesPage';
import { useAdminArticles } from '../hooks/useAdminArticles';
import { deleteArticle, getAdminArticleItem } from '../../../../api/articles.api';

jest.mock('../hooks/useAdminArticles');
jest.mock('../../../../api/articles.api');
jest.mock('../components/ArticleFormModal', () => function ArticleFormStub({ article }) {
  return <div role="dialog" aria-label="Форма материала">{article ? article.uuid : 'new'}</div>;
});

const tag = (name) => ({ uuid: `t-${name}`, name });
const cat = (id, name) => ({ id, name, slug: `c${id}` });
const ARTICLES = [
  {
    uuid: 'a-1', title: 'Как справиться с тревогой', excerpt: 'Кратко', cover_image_url: '/media/cover-1.jpg',
    categories: [cat(1, 'Статья'), cat(2, 'Видео'), cat(3, 'Чек-лист')],
    tags: [tag('Стресс'), tag('Тревожность'), tag('Сон'), tag('Сессия'), tag('Семья')],
    is_published: true, status: 'published', published_at: '2026-10-20T09:30:00Z',
    created_at: '2026-10-01T09:30:00Z', created_by_name: 'Кузнецова Мария',
  },
  {
    uuid: 'a-2', title: 'Сон', excerpt: null, cover_image_url: null, categories: [], tags: [],
    is_published: false, status: 'draft', published_at: null, created_at: '2026-10-09T09:30:00Z',
    created_by_name: null,
  },
  {
    uuid: 'a-3', title: 'Памятка куратору', excerpt: null, cover_image_url: null,
    categories: [cat(1, 'Статья')], tags: [tag('Стресс')],
    is_published: false, status: 'in_review', published_at: null, created_at: '2026-10-05T09:30:00Z',
    created_by_name: 'Кузнецова Мария',
  },
  {
    uuid: 'a-4', title: 'На доработке', excerpt: null, cover_image_url: null, categories: [], tags: [tag('Сон')],
    is_published: false, status: 'needs_changes', published_at: null, created_at: '2026-10-04T09:30:00Z',
    created_by_name: null,
  },
];

const setPage = jest.fn();
const setFilters = jest.fn();
const setQuery = jest.fn();
const refetch = jest.fn();

function mockArticles(overrides = {}) {
  useAdminArticles.mockReturnValue({
    items: ARTICLES, loading: false, error: null, total: 4, page: 1, setPage,
    query: '', setQuery, filters: { is_published: null, category_id: null }, setFilters, refetch,
    ...overrides,
  });
}

beforeEach(() => {
  jest.clearAllMocks();
  mockArticles();
});

// jsdom не применяет CSS: обе раскладки ResponsiveTable в DOM.
const table = () => screen.getByRole('table', { name: 'Материалы' });
const list = () => screen.getByRole('list', { name: 'Материалы' });
const row = (title) => within(table()).getAllByRole('row')
  .find((r) => within(r).queryByText(title, { selector: '.primary' }));
const record = (title) => within(list()).getAllByRole('listitem')
  .find((li) => within(li).queryByRole('heading', { level: 2, name: title }));
const labels = (scope, name) => within(within(scope).getByRole('list', { name }))
  .getAllByRole('listitem').map((li) => li.textContent);

test('wide: Материал | Статус | Тип и темы | Действия на shared ResponsiveTable', () => {
  render(<ArticlesPage />);
  expect(within(table()).getAllByRole('columnheader').map((th) => th.textContent))
    .toEqual(['Материал', 'Статус', 'Тип и темы', 'Действия']);
  const r = row('Как справиться с тревогой');
  expect(within(r).getByText(/Кузнецова Мария/)).toBeInTheDocument();
  expect(within(r).getByText('20.10.2026')).toBeInTheDocument();
  expect(within(row('Сон')).getByText('09.10.2026')).toBeInTheDocument();
});

test('все статусы модерации — подписью бейджа', () => {
  render(<ArticlesPage />);
  expect(within(row('Как справиться с тревогой')).getByText('Опубликовано')).toBeInTheDocument();
  expect(within(row('Сон')).getByText('Черновик')).toBeInTheDocument();
  expect(within(row('Памятка куратору')).getByText('На проверке')).toBeInTheDocument();
  expect(within(record('На доработке')).getByText('На доработке', { selector: 'span:not(.primary)' }))
    .toBeInTheDocument();
});

test('обложка — identity.media; без обложки картинки нет', () => {
  render(<ArticlesPage />);
  const imgs = within(row('Как справиться с тревогой')).getAllByRole('presentation');
  expect(imgs[0]).toHaveAttribute('src', '/media/cover-1.jpg');
  expect(within(row('Сон')).queryAllByRole('presentation')).toHaveLength(0);
});

test('тип и темы: TagList «Тип» (category) и «Темы» с «+N»; пусто — «—»', () => {
  render(<ArticlesPage />);
  const r = row('Как справиться с тревогой');
  expect(labels(r, 'Тип')).toEqual(['Статья', 'Видео']);
  expect(within(within(r).getByRole('list', { name: 'Тип' })).getByText('Статья')).toHaveClass('category');
  expect(labels(r, 'Темы')).toEqual(['Стресс', 'Тревожность']);
  fireEvent.click(within(r).getByRole('button', { name: '+3: показать все, всего 5' }));
  expect(labels(r, 'Темы')).toHaveLength(5);
  expect(within(r).getByRole('button', { name: '+1: показать все, всего 3' })).toBeInTheDocument();

  expect(within(row('Сон')).getByText('—')).toBeInTheDocument();
  expect(within(row('На доработке')).queryByRole('list', { name: 'Тип' })).toBeNull();
  expect(labels(row('На доработке'), 'Темы')).toEqual(['Сон']);
});

test('список: тип и темы — строками деталей; пустые не выводятся', () => {
  render(<ArticlesPage />);
  expect(within(record('Как справиться с тревогой')).getAllByRole('term').map((t) => t.textContent))
    .toEqual(['Тип', 'Темы']);
  expect(within(record('Памятка куратору')).getAllByRole('term').map((t) => t.textContent))
    .toEqual(['Тип', 'Темы']);
  expect(within(record('На доработке')).getAllByRole('term').map((t) => t.textContent)).toEqual(['Темы']);
  expect(within(record('Сон')).queryByRole('term')).toBeNull();
});

test('действия: «Редактировать» видно, «Удалить» — в меню ⋮ (в обеих раскладках)', () => {
  render(<ArticlesPage />);
  [row('Сон'), record('Сон')].forEach((scope) => {
    expect(within(scope).getByRole('button', { name: 'Редактировать «Сон»' })).toBeInTheDocument();
    expect(within(scope).queryByRole('button', { name: /^Удалить/ })).toBeNull();
    expect(within(scope).getByRole('button', { name: 'Другие действия: «Сон»' })).toBeInTheDocument();
  });
});

test('«Редактировать» загружает полный материал один раз и открывает форму', async () => {
  getAdminArticleItem.mockResolvedValue({ ...ARTICLES[1], content: '<p>x</p>' });
  render(<ArticlesPage />);
  fireEvent.click(within(record('Сон')).getByRole('button', { name: 'Редактировать «Сон»' }));
  expect(await screen.findByRole('dialog', { name: 'Форма материала' })).toHaveTextContent('a-2');
  expect(getAdminArticleItem).toHaveBeenCalledTimes(1);
  expect(getAdminArticleItem).toHaveBeenCalledWith('a-2');
});

test('ошибка загрузки полного материала — сообщение над таблицей', async () => {
  getAdminArticleItem.mockRejectedValue(new Error('сбой'));
  render(<ArticlesPage />);
  fireEvent.click(within(row('Сон')).getByRole('button', { name: 'Редактировать «Сон»' }));
  expect(await screen.findByText('Не удалось загрузить материал: сбой')).toBeInTheDocument();
});

test('«Удалить» из меню — подтверждение, затем DELETE и перезагрузка списка', async () => {
  deleteArticle.mockResolvedValue(null);
  render(<ArticlesPage />);
  fireEvent.click(within(row('Сон')).getByRole('button', { name: 'Другие действия: «Сон»' }));
  expect(screen.getAllByRole('menuitem').map((i) => i.textContent)).toEqual(['Удалить']);
  fireEvent.click(screen.getByRole('menuitem', { name: 'Удалить' }));
  expect(screen.getByText('Удалить материал?')).toBeInTheDocument();
  expect(deleteArticle).not.toHaveBeenCalled();

  fireEvent.click(screen.getByRole('button', { name: 'Удалить' }));
  await waitFor(() => expect(deleteArticle).toHaveBeenCalledWith('a-2'));
  await waitFor(() => expect(refetch).toHaveBeenCalledTimes(1));
});

test('загрузка, ошибка и пусто — состояния ResponsiveTable', () => {
  mockArticles({ loading: true, items: [] });
  const { rerender } = render(<ArticlesPage />);
  expect(list()).toHaveAttribute('aria-busy', 'true');

  mockArticles({ error: 'Сервис недоступен', items: [] });
  rerender(<ArticlesPage />);
  expect(screen.getAllByText('Ошибка загрузки: Сервис недоступен')).toHaveLength(2);

  mockArticles({ items: [], total: 0 });
  rerender(<ArticlesPage />);
  expect(screen.getAllByText('Материалов пока нет')).toHaveLength(2);
});

test('пагинация, поиск и фильтр статуса работают через хук, как прежде', () => {
  mockArticles({ total: 45, page: 2, filters: { is_published: false, category_id: null } });
  render(<ArticlesPage />);
  expect(screen.getByText('2 / 3')).toBeInTheDocument();
  expect(screen.getByText('Черновики')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '›' }));
  fireEvent.click(screen.getByRole('button', { name: '‹' }));
  expect(setPage).toHaveBeenCalledTimes(2);

  fireEvent.change(screen.getByPlaceholderText('Поиск по заголовку...'), { target: { value: 'сон' } });
  expect(setQuery).toHaveBeenCalledWith('сон');
});

test('права: страница только в кабинете admin; без ролевых веток и локальной responsive-механики', () => {
  const router = fs.readFileSync(path.join(__dirname, '..', '..', '..', '..', 'app', 'router.jsx'), 'utf8');
  expect(router.match(/<AdminArticlesPage \/>/g)).toHaveLength(1);
  expect(router).toMatch(/path="articles"\s+element=\{<AdminArticlesPage \/>\}/);

  const dir = path.join(__dirname, '..', 'components');
  const tableSrc = fs.readFileSync(path.join(dir, 'ArticlesTable.jsx'), 'utf8');
  const tableCss = fs.readFileSync(path.join(dir, 'ArticlesTable.module.css'), 'utf8');
  expect(tableSrc).not.toMatch(/useAuth|activeRole|'supervisor'|'admin'/);
  expect(tableSrc).toMatch(/ResponsiveTable/);
  expect(tableSrc).not.toMatch(/<table|<thead|<tr/);
  expect(tableCss).not.toMatch(/@container|@media|overflow-x/);
});
