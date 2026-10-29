import fs from 'fs';
import path from 'path';
import { render, screen, within, fireEvent, waitFor } from '@testing-library/react';
import AdminTestsPage from './AdminTestsPage';
import { useAdminTests } from '../hooks/useAdminTests';
import { getAdminTest, publishTest, returnTest, updateTest, deleteTest } from '../../../../api/tests.api';

const mockNavigate = jest.fn();
// react-router-dom v7 не резолвится в jest CRA — мокаем, как в остальных тестах
jest.mock('react-router-dom', () => ({ useNavigate: () => mockNavigate }), { virtual: true });
jest.mock('../hooks/useAdminTests');
jest.mock('../../../../api/tests.api');
jest.mock('../components/TestPreviewModal', () => function PreviewStub({ title }) {
  return <div role="dialog" aria-label="Предпросмотр теста">{title}</div>;
});

const cat = (id, name) => ({ id, name });
const TESTS = [
  {
    uuid: 't-1', title: 'Шкала тревоги', scoring: 'weighted', version: 1, is_active: true,
    status: 'in_review', question_count: 120, categories: [cat(5, 'Диагностика'), cat(3, 'Чек-лист'), cat(1, 'Статья')],
    tags: [], created_at: '2026-10-28T09:30:00Z', created_by_name: 'Кузнецова Мария',
  },
  {
    uuid: 't-2', title: 'Сон', scoring: 'sum', version: 1, is_active: false, status: 'draft',
    question_count: 3, categories: [], tags: [], created_at: '2026-10-27T09:30:00Z', created_by_name: null,
  },
  {
    uuid: 't-3', title: 'Шкала стресса', scoring: 'average', version: 1, is_active: true, status: 'published',
    question_count: 10, categories: [cat(5, 'Диагностика')], tags: [], created_at: '2026-10-26T09:30:00Z',
    created_by_name: 'Кузнецова Мария',
  },
  {
    uuid: 't-4', title: 'Опросник выгорания', scoring: 'sum', version: 1, is_active: true, status: 'needs_changes',
    question_count: 22, categories: [], tags: [], created_at: '2026-10-25T09:30:00Z', created_by_name: null,
  },
];

const setPage = jest.fn();
const setFilters = jest.fn();
const setQuery = jest.fn();
const refetch = jest.fn();

function mockTests(overrides = {}) {
  useAdminTests.mockReturnValue({
    items: TESTS, loading: false, error: null, total: 4, page: 1, setPage,
    query: '', setQuery, filters: { status: null, is_active: null }, setFilters, refetch, ...overrides,
  });
}

beforeEach(() => {
  jest.clearAllMocks();
  mockTests();
});

// jsdom не применяет CSS: обе раскладки ResponsiveTable в DOM.
const table = () => screen.getByRole('table', { name: 'Тесты' });
const list = () => screen.getByRole('list', { name: 'Тесты' });
const row = (title) => within(table()).getAllByRole('row')
  .find((r) => within(r).queryByText(title, { selector: '.primary' }));
const record = (title) => within(list()).getAllByRole('listitem')
  .find((li) => within(li).queryByRole('heading', { level: 2, name: title }));
const primaryOf = (scope) => within(scope).getAllByRole('button')
  .filter((b) => !/^Другие действия/.test(b.getAttribute('aria-label') || '') && !/^\+\d/.test(b.textContent))
  .map((b) => b.textContent);
const openMenu = (scope, title) => fireEvent.click(
  within(scope).getByRole('button', { name: `Другие действия: «${title}»` }),
);
const menuItems = () => screen.getAllByRole('menuitem').map((i) => i.textContent);

describe.each(['admin', 'supervisor'])('кабинет %s — context moderator', (cabinetRole) => {
  test('wide: Тест | Модерация и видимость | Параметры | Действия', () => {
    render(<AdminTestsPage cabinetRole={cabinetRole} />);
    expect(within(table()).getAllByRole('columnheader').map((th) => th.textContent))
      .toEqual(['Тест', 'Модерация и видимость', 'Параметры', 'Действия']);
    const r = row('Шкала тревоги');
    expect(within(r).getByText(/Кузнецова Мария/)).toBeInTheDocument();
    expect(within(r).getByText('создан 28.10.2026')).toBeInTheDocument();
    expect(within(r).getByText('На проверке')).toBeInTheDocument();
    expect(within(r).getByText('Активен')).toBeInTheDocument();
    expect(within(r).getByText('Вопросов: 120')).toBeInTheDocument();
    expect(within(r).getByText('Взвешенная сумма')).toBeInTheDocument();
    expect(within(row('Сон')).getByText('Черновик')).toBeInTheDocument();
    expect(within(row('Сон')).getByText('Скрыт')).toBeInTheDocument();
  });

  test('основное действие и меню по статусу (как в матрице testActions)', () => {
    render(<AdminTestsPage cabinetRole={cabinetRole} />);
    expect(primaryOf(row('Шкала тревоги'))).toEqual(['Опубликовать']);
    openMenu(row('Шкала тревоги'), 'Шкала тревоги');
    expect(menuItems()).toEqual(['Вернуть на доработку', 'Предпросмотр', 'Скрыть из каталога', 'Редактировать', 'Удалить']);
    fireEvent.keyDown(screen.getAllByRole('menuitem')[0], { key: 'Escape' });

    expect(primaryOf(record('Сон'))).toEqual(['Редактировать']);
    openMenu(record('Сон'), 'Сон');
    expect(menuItems()).toEqual(['Опубликовать', 'Предпросмотр', 'Показать в каталоге', 'Удалить']);
  });

  test('«Редактировать» ведёт в форму своего кабинета', () => {
    render(<AdminTestsPage cabinetRole={cabinetRole} />);
    fireEvent.click(within(row('Шкала стресса')).getByRole('button', { name: 'Редактировать «Шкала стресса»' }));
    expect(mockNavigate).toHaveBeenCalledWith(`/${cabinetRole}/tests/t-3`);
  });
});

test('«Опубликовать»: запрос один раз, кнопка строки недоступна до ответа, потом refetch', async () => {
  let resolve;
  publishTest.mockReturnValue(new Promise((r) => { resolve = r; }));
  render(<AdminTestsPage />);
  const btn = within(row('Шкала тревоги')).getByRole('button', { name: 'Опубликовать «Шкала тревоги»' });
  fireEvent.click(btn);
  expect(btn).toBeDisabled();
  fireEvent.click(btn);
  expect(publishTest).toHaveBeenCalledTimes(1);
  expect(publishTest).toHaveBeenCalledWith('t-1');
  // у другой строки «Опубликовать» доступно
  openMenu(row('Сон'), 'Сон');
  expect(screen.getByRole('menuitem', { name: 'Опубликовать' })).toBeEnabled();
  resolve({});
  await waitFor(() => expect(refetch).toHaveBeenCalledTimes(1));
  expect(btn).toBeEnabled();
});

test('«Вернуть на доработку» — диалог с комментарием, затем запрос', async () => {
  returnTest.mockResolvedValue({});
  render(<AdminTestsPage />);
  openMenu(row('Шкала тревоги'), 'Шкала тревоги');
  fireEvent.click(screen.getByRole('menuitem', { name: 'Вернуть на доработку' }));
  expect(screen.getByText('Вернуть на доработку?')).toBeInTheDocument();
  expect(returnTest).not.toHaveBeenCalled();
  fireEvent.change(screen.getByPlaceholderText('Комментарий автору (необязательно)'), { target: { value: 'Уточнить шкалы' } });
  fireEvent.click(screen.getByRole('button', { name: 'Вернуть на доработку' }));
  await waitFor(() => expect(returnTest).toHaveBeenCalledWith('t-1', 'Уточнить шкалы'));
});

test('«Показать в каталоге» — PATCH is_active, пункт недоступен до ответа', async () => {
  let resolve;
  updateTest.mockReturnValue(new Promise((r) => { resolve = r; }));
  render(<AdminTestsPage />);
  openMenu(row('Сон'), 'Сон');
  fireEvent.click(screen.getByRole('menuitem', { name: 'Показать в каталоге' }));
  expect(updateTest).toHaveBeenCalledWith('t-2', { is_active: true });
  openMenu(row('Сон'), 'Сон');
  expect(screen.getByRole('menuitem', { name: 'Показать в каталоге' })).toBeDisabled();
  resolve({});
  await waitFor(() => expect(refetch).toHaveBeenCalled());
});

test('«Предпросмотр» загружает тест один раз и открывает модалку', async () => {
  getAdminTest.mockResolvedValue({ ...TESTS[2], description: '', questions: [], interpretations: [] });
  render(<AdminTestsPage />);
  openMenu(record('Шкала стресса'), 'Шкала стресса');
  fireEvent.click(screen.getByRole('menuitem', { name: 'Предпросмотр' }));
  expect(await screen.findByRole('dialog', { name: 'Предпросмотр теста' })).toHaveTextContent('Шкала стресса');
  expect(getAdminTest).toHaveBeenCalledTimes(1);
});

test('«Удалить» — подтверждение, затем DELETE', async () => {
  deleteTest.mockResolvedValue(null);
  render(<AdminTestsPage />);
  openMenu(row('Сон'), 'Сон');
  fireEvent.click(screen.getByRole('menuitem', { name: 'Удалить' }));
  expect(screen.getByText('Удалить тест?')).toBeInTheDocument();
  expect(deleteTest).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Удалить' }));
  await waitFor(() => expect(deleteTest).toHaveBeenCalledWith('t-2'));
});

test('тип материала — TagList «Тип» (category) с «+N»; без типа в списке строки «Тип» нет', () => {
  render(<AdminTestsPage />);
  const types = within(row('Шкала тревоги')).getByRole('list', { name: 'Тип' });
  expect(within(types).getAllByRole('listitem').map((li) => li.textContent)).toEqual(['Диагностика', 'Чек-лист']);
  expect(within(types).getByText('Диагностика')).toHaveClass('category');
  expect(within(row('Шкала тревоги')).getByRole('button', { name: '+1: показать все, всего 3' })).toBeInTheDocument();
  expect(within(record('Сон')).getAllByRole('term').map((t) => t.textContent)).toEqual(['Вопросов', 'Подсчёт']);
  expect(within(record('Шкала тревоги')).getAllByRole('term').map((t) => t.textContent))
    .toEqual(['Тип', 'Вопросов', 'Подсчёт']);
});

test('загрузка, ошибка и пусто — состояния ResponsiveTable', () => {
  mockTests({ loading: true, items: [] });
  const { rerender } = render(<AdminTestsPage />);
  expect(list()).toHaveAttribute('aria-busy', 'true');
  mockTests({ error: 'Сервис недоступен', items: [] });
  rerender(<AdminTestsPage />);
  expect(screen.getAllByText('Ошибка загрузки: Сервис недоступен')).toHaveLength(2);
  mockTests({ items: [], total: 0 });
  rerender(<AdminTestsPage />);
  expect(screen.getAllByText('Тестов пока нет')).toHaveLength(2);
});

test('пагинация и поиск — через хук, как прежде', () => {
  mockTests({ total: 45, page: 2, filters: { status: 'in_review', is_active: null } });
  render(<AdminTestsPage />);
  expect(screen.getByText('2 / 3')).toBeInTheDocument();
  expect(screen.getByText('На проверке', { selector: '[class*="value"]' })).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '›' }));
  expect(setPage).toHaveBeenCalledTimes(1);
  fireEvent.change(screen.getByPlaceholderText('Поиск по названию...'), { target: { value: 'шкала' } });
  expect(setQuery).toHaveBeenCalledWith('шкала');
});

test('нет локальной responsive-механики и ролевых веток в таблице', () => {
  const dir = path.join(__dirname, '..', 'components');
  const src = fs.readFileSync(path.join(dir, 'TestsTable.jsx'), 'utf8');
  const css = fs.readFileSync(path.join(dir, 'TestsTable.module.css'), 'utf8');
  expect(src).toMatch(/ResponsiveTable/);
  expect(src).toMatch(/getTestActions/);
  expect(src).not.toMatch(/<table|<thead|<tr|useAuth|activeRole|'admin'|'supervisor'|'psychologist'/);
  expect(css).not.toMatch(/@container|@media|overflow-x/);
});
