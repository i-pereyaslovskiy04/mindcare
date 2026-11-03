import fs from 'fs';
import path from 'path';
import { render, screen, within, fireEvent, waitFor } from '@testing-library/react';
import CategoriesPage from './CategoriesPage';
import { useAdminCategories } from '../hooks/useAdminCategories';
import { deleteCategory } from '../../../../api/categories.api';

jest.mock('../hooks/useAdminCategories');
jest.mock('../../../../api/categories.api');
jest.mock('../components/CategoryFormModal', () => function CategoryFormStub({ category }) {
  return <div role="dialog" aria-label="Форма типа">{category ? category.id : 'new'}</div>;
});

const SLUG = 'metodicheskie-rekomendacii-dlya-kuratorov-akademicheskih-grupp-pervogo-kursa';
const CATS = [
  { id: 1, name: 'Методические рекомендации', slug: SLUG, description: null, display_order: 1, is_active: true, article_count: 1240, created_at: '2026-10-15T09:30:00Z' },
  { id: 2, name: 'Подкаст', slug: 'podcast', description: null, display_order: 120, is_active: false, article_count: 0, created_at: '2026-10-11T09:30:00Z' },
];
const setPage = jest.fn();
const setFilters = jest.fn();
const refetch = jest.fn();

function mockCats(overrides = {}) {
  useAdminCategories.mockReturnValue({
    items: CATS, loading: false, error: null, total: 2, page: 1, setPage, size: 50,
    query: '', setQuery: jest.fn(), filters: { is_active: null }, setFilters, refetch, ...overrides,
  });
}

beforeEach(() => {
  jest.clearAllMocks();
  mockCats();
});

const table = () => screen.getByRole('table', { name: 'Типы материалов' });
const list = () => screen.getByRole('list', { name: 'Типы материалов' });
const row = (name) => within(table()).getAllByRole('row').find((r) => within(r).queryByText(name, { selector: '.primary' }));
const record = (name) => within(list()).getAllByRole('listitem')
  .find((li) => within(li).queryByRole('heading', { level: 2, name }));

test('wide: Тип материала (название + slug) | Статус | Параметры | Действия', () => {
  render(<CategoriesPage />);
  expect(within(table()).getAllByRole('columnheader').map((th) => th.textContent))
    .toEqual(['Тип материала', 'Статус', 'Параметры', 'Действия']);
  const r = row('Методические рекомендации');
  expect(within(r).getByText(SLUG).tagName).toBe('CODE');
  expect(within(r).getByText('Активна')).toBeInTheDocument();
  expect(within(r).getByText('Порядок 1')).toBeInTheDocument();
  expect(within(r).getByText('Материалов 1240')).toBeInTheDocument();
  expect(within(row('Подкаст')).getByText('Скрыта')).toBeInTheDocument();
  expect(within(record('Подкаст')).getAllByRole('term').map((t) => t.textContent))
    .toEqual(['Порядок', 'Материалов', 'Создана']);
});

test('«Редактировать» открывает форму строки; «Деактивировать» в меню — с подтверждением', async () => {
  deleteCategory.mockResolvedValue(null);
  render(<CategoriesPage />);
  fireEvent.click(within(record('Подкаст')).getByRole('button', { name: 'Редактировать «Подкаст»' }));
  expect(screen.getByRole('dialog', { name: 'Форма типа' })).toHaveTextContent('2');

  fireEvent.click(within(row('Подкаст')).getByRole('button', { name: 'Другие действия: «Подкаст»' }));
  expect(screen.getAllByRole('menuitem').map((i) => i.textContent)).toEqual(['Деактивировать']);
  fireEvent.click(screen.getByRole('menuitem', { name: 'Деактивировать' }));
  expect(screen.getByText('Скрыть тип материалов?')).toBeInTheDocument();
  expect(deleteCategory).not.toHaveBeenCalled();
});

test('пагинация — через хук, как прежде', () => {
  mockCats({ total: 120, page: 2 });
  render(<CategoriesPage />);
  expect(screen.getByText('2 / 3')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '›' }));
  expect(setPage).toHaveBeenCalledTimes(1);
});

test('загрузка, ошибка и пусто — состояния ResponsiveTable', async () => {
  mockCats({ loading: true, items: [] });
  const { rerender } = render(<CategoriesPage />);
  expect(list()).toHaveAttribute('aria-busy', 'true');
  mockCats({ error: 'Сбой', items: [] });
  rerender(<CategoriesPage />);
  expect(screen.getAllByText('Ошибка загрузки: Сбой')).toHaveLength(2);
  mockCats({ items: [], total: 0 });
  rerender(<CategoriesPage />);
  await waitFor(() => expect(screen.getAllByText('Типов материалов пока нет')).toHaveLength(2));
});

test('нет локальной табличной и responsive-механики', () => {
  const dir = path.join(__dirname, '..', 'components');
  expect(fs.readFileSync(path.join(dir, 'CategoriesTable.jsx'), 'utf8')).not.toMatch(/<table|<thead|<tr/);
  expect(fs.readFileSync(path.join(dir, 'CategoriesTable.module.css'), 'utf8')).not.toMatch(/@container|@media|overflow-x|\.table/);
});
