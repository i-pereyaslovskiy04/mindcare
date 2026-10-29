import { render, screen, within, fireEvent, waitFor } from '@testing-library/react';
import PsychologistTestsPage from './PsychologistTestsPage';
import { useMyTests } from '../../../features/psychologist/hooks/useMyTests';
import { submitTestForReview, deleteMyTest, getMyTest } from '../../../api/tests.api';

const mockNavigate = jest.fn();
// react-router-dom v7 не резолвится в jest CRA — мокаем, как в остальных тестах
jest.mock('react-router-dom', () => ({ useNavigate: () => mockNavigate }), { virtual: true });
jest.mock('../../../features/psychologist/hooks/useMyTests');
jest.mock('../../../api/tests.api');
jest.mock('../../../features/admin/tests/components/TestPreviewModal', () => function PreviewStub({ title }) {
  return <div role="dialog" aria-label="Предпросмотр теста">{title}</div>;
});

const mk = (uuid, title, status, extra = {}) => ({
  uuid, title, status, scoring: 'sum', version: 1, is_active: true, question_count: 10,
  categories: [], tags: [], created_at: '2026-10-20T09:30:00Z', created_by_name: 'Кузнецова Мария', ...extra,
});
const TESTS = [
  mk('p-1', 'Черновик теста', 'draft'),
  mk('p-2', 'На доработке', 'needs_changes'),
  mk('p-3', 'На проверке у супервизора', 'in_review'),
  mk('p-4', 'Опубликованный тест', 'published'),
];

const refetch = jest.fn();
function mockTests(overrides = {}) {
  useMyTests.mockReturnValue({
    items: TESTS, loading: false, error: null, total: 4, page: 1, setPage: jest.fn(),
    query: '', setQuery: jest.fn(), filters: { status: null }, setFilters: jest.fn(), refetch, ...overrides,
  });
}

beforeEach(() => {
  jest.clearAllMocks();
  mockTests();
});

const table = () => screen.getByRole('table', { name: 'Тесты' });
const row = (title) => within(table()).getAllByRole('row')
  .find((r) => within(r).queryByText(title, { selector: '.primary' }));
const menuButton = (title) => within(row(title)).queryByRole('button', { name: `Другие действия: «${title}»` });
const openMenu = (title) => fireEvent.click(menuButton(title));
const menuItems = () => screen.getAllByRole('menuitem').map((i) => i.textContent);
const primary = (title, label) => within(row(title)).getByRole('button', { name: `${label} «${title}»` });

test('context author: модерации и видимости нет ни в одной строке', () => {
  render(<PsychologistTestsPage />);
  TESTS.forEach(({ title }) => {
    expect(within(row(title)).queryByRole('button', { name: /^Опубликовать/ })).toBeNull();
  });
  // Меню есть у всех, кроме in_review (там только «Предпросмотр»).
  const labels = ['Черновик теста', 'На доработке', 'Опубликованный тест'].flatMap((title) => {
    openMenu(title);
    const items = menuItems();
    fireEvent.keyDown(screen.getAllByRole('menuitem')[0], { key: 'Escape' });
    return items;
  });
  expect(labels.filter((l) => /Опубликовать|каталог|Вернуть/.test(l))).toEqual([]);
});

test('draft / needs_changes: «Редактировать», в меню отправка, предпросмотр, удаление', () => {
  render(<PsychologistTestsPage />);
  ['Черновик теста', 'На доработке'].forEach((title) => {
    expect(primary(title, 'Редактировать')).toBeInTheDocument();
    openMenu(title);
    expect(menuItems()).toEqual(['Отправить на модерацию', 'Предпросмотр', 'Удалить']);
    fireEvent.keyDown(screen.getAllByRole('menuitem')[0], { key: 'Escape' });
  });
});

test('in_review: только «Предпросмотр», меню нет (ADR-016)', () => {
  render(<PsychologistTestsPage />);
  expect(primary('На проверке у супервизора', 'Предпросмотр')).toBeInTheDocument();
  expect(menuButton('На проверке у супервизора')).toBeNull();
});

test('published: «Предпросмотр»; «Редактировать» в меню — с предупреждением о снятии с публикации', () => {
  render(<PsychologistTestsPage />);
  expect(primary('Опубликованный тест', 'Предпросмотр')).toBeInTheDocument();
  openMenu('Опубликованный тест');
  expect(menuItems()).toEqual(['Редактировать']);
  fireEvent.click(screen.getByRole('menuitem', { name: 'Редактировать' }));
  expect(screen.getByText('Редактировать опубликованный тест?')).toBeInTheDocument();
  expect(mockNavigate).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Редактировать' }));
  expect(mockNavigate).toHaveBeenCalledWith('/psychologist/tests/p-4');
});

test('черновик: «Редактировать» сразу открывает форму', () => {
  render(<PsychologistTestsPage />);
  fireEvent.click(primary('Черновик теста', 'Редактировать'));
  expect(mockNavigate).toHaveBeenCalledWith('/psychologist/tests/p-1');
});

test('«Отправить на модерацию» — один запрос, пункт недоступен до ответа', async () => {
  let resolve;
  submitTestForReview.mockReturnValue(new Promise((r) => { resolve = r; }));
  render(<PsychologistTestsPage />);
  openMenu('Черновик теста');
  fireEvent.click(screen.getByRole('menuitem', { name: 'Отправить на модерацию' }));
  expect(submitTestForReview).toHaveBeenCalledWith('p-1');
  openMenu('Черновик теста');
  expect(screen.getByRole('menuitem', { name: 'Отправить на модерацию' })).toBeDisabled();
  fireEvent.keyDown(screen.getAllByRole('menuitem')[0], { key: 'Escape' });
  openMenu('На доработке');
  expect(screen.getByRole('menuitem', { name: 'Отправить на модерацию' })).toBeEnabled();
  resolve({});
  await waitFor(() => expect(refetch).toHaveBeenCalledTimes(1));
  expect(submitTestForReview).toHaveBeenCalledTimes(1);
});

test('«Предпросмотр» читает свой тест (/psychologist API)', async () => {
  getMyTest.mockResolvedValue({ ...TESTS[2], description: '', questions: [], interpretations: [] });
  render(<PsychologistTestsPage />);
  fireEvent.click(primary('На проверке у супервизора', 'Предпросмотр'));
  expect(await screen.findByRole('dialog', { name: 'Предпросмотр теста' })).toBeInTheDocument();
  expect(getMyTest).toHaveBeenCalledWith('p-3');
});

test('«Удалить» черновик — подтверждение, затем DELETE своего теста', async () => {
  deleteMyTest.mockResolvedValue(null);
  render(<PsychologistTestsPage />);
  openMenu('Черновик теста');
  fireEvent.click(screen.getByRole('menuitem', { name: 'Удалить' }));
  expect(screen.getByText('Удалить тест?')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Удалить' }));
  await waitFor(() => expect(deleteMyTest).toHaveBeenCalledWith('p-1'));
});

test('пусто и ошибка — состояния ResponsiveTable', () => {
  mockTests({ items: [], total: 0 });
  const { rerender } = render(<PsychologistTestsPage />);
  expect(screen.getAllByText('Тестов пока нет')).toHaveLength(2);
  mockTests({ items: [], error: 'Сбой' });
  rerender(<PsychologistTestsPage />);
  expect(screen.getAllByText('Ошибка загрузки: Сбой')).toHaveLength(2);
});
