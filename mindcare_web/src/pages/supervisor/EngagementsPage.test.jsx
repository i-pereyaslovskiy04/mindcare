import fs from 'fs';
import path from 'path';
import { render, screen, fireEvent, within } from '@testing-library/react';
import EngagementsPage from './EngagementsPage';
import { useStudents } from '../../features/supervisor/hooks/useStudents';
import useUserContacts from '../../features/contacts/hooks/useUserContacts';

jest.mock('../../features/supervisor/hooks/useStudents');
jest.mock('../../features/contacts/hooks/useUserContacts');
jest.mock('../../features/supervisor/components/AssignModal', () => function AssignStub({ mode, student }) {
  return <div role="dialog" aria-label="Связь">{mode}:{student.uuid}</div>;
});
jest.mock('../../features/tests/ui/StudentTestResults', () => () => null);
jest.mock('../../api/supervisor.api');

const STUDENTS = [
  { id: 1, uuid: 'uuid-1', full_name: 'Анна Первая', email: 'a@x.test', current_engagement: null },
  { id: 2, uuid: 'uuid-2', full_name: 'Борис Второй', email: 'b@x.test',
    current_engagement: { id: 20, status: 'active', psychologist: { id: 7, full_name: 'Смирнова Ольга', email: 's@x.test' } } },
];
const refetch = jest.fn();

function mockStudents(overrides = {}) {
  useStudents.mockReturnValue({
    items: STUDENTS, loading: false, error: null, total: 2, page: 1,
    setPage: jest.fn(), query: '', setQuery: jest.fn(), refetch, ...overrides,
  });
}

beforeEach(() => {
  jest.clearAllMocks();
  mockStudents();
  useUserContacts.mockReturnValue({
    status: 'ready',
    data: { primary_phone: '+79001234567', items: [], catalog: null },
    error: null,
    refetch: jest.fn(),
  });
});

// jsdom не применяет CSS: обе раскладки ResponsiveTable в DOM.
const table = () => screen.getByRole('table', { name: 'Студенты и назначенные психологи' });
const list = () => screen.getByRole('list', { name: 'Студенты и назначенные психологи' });
const row = (name) => within(table()).getAllByRole('row').find((r) => within(r).queryByText(name));
const record = (name) => within(list()).getAllByRole('listitem')
  .find((li) => within(li).queryByRole('heading', { name }));
const openMenu = (scope, name) => fireEvent.click(
  within(scope).getByRole('button', { name: `Другие действия: ${name}` }),
);
const menuItems = () => screen.getAllByRole('menuitem').map((i) => i.textContent);

test('shared ResponsiveTable: колонки Студент, Психолог и статус, Действия', () => {
  render(<EngagementsPage />);
  expect(within(table()).getAllByRole('columnheader').map((th) => th.textContent))
    .toEqual(['Студент', 'Психолог и статус', 'Действия']);
  expect(within(row('Борис Второй')).getByText('Смирнова Ольга')).toBeInTheDocument();
  expect(within(row('Борис Второй')).getByText('Активна')).toBeInTheDocument();
  expect(within(row('Анна Первая')).getByText('Не назначен')).toBeInTheDocument();
});

describe.each([
  ['таблица', (name) => row(name)],
  ['список', (name) => record(name)],
])('матрица действий (%s)', (_, scopeOf) => {
  test('без связи: «Назначить» кнопкой; в меню результаты и контакты', () => {
    render(<EngagementsPage />);
    fireEvent.click(within(scopeOf('Анна Первая')).getByRole('button', { name: 'Назначить: Анна Первая' }));
    expect(screen.getByRole('dialog', { name: 'Связь' })).toHaveTextContent('assign:uuid-1');
    openMenu(scopeOf('Анна Первая'), 'Анна Первая');
    expect(menuItems()).toEqual(['Результаты тестов', 'Контакты']);
  });

  test('со связью: «Переназначить» кнопкой; «Закрыть связь» в меню', () => {
    render(<EngagementsPage />);
    expect(within(scopeOf('Борис Второй')).queryByRole('button', { name: /^Назначить/ })).toBeNull();
    fireEvent.click(within(scopeOf('Борис Второй')).getByRole('button', { name: 'Переназначить: Борис Второй' }));
    expect(screen.getByRole('dialog', { name: 'Связь' })).toHaveTextContent('transfer:uuid-2');
  });

  test('«Закрыть связь» из меню открывает тот же диалог в режиме close', () => {
    render(<EngagementsPage />);
    openMenu(scopeOf('Борис Второй'), 'Борис Второй');
    expect(menuItems()).toEqual(['Результаты тестов', 'Контакты', 'Закрыть связь']);
    fireEvent.click(screen.getByRole('menuitem', { name: 'Закрыть связь' }));
    expect(screen.getByRole('dialog', { name: 'Связь' })).toHaveTextContent('close:uuid-2');
  });

  test('«Результаты тестов» из меню открывает результаты выбранного студента', () => {
    render(<EngagementsPage />);
    openMenu(scopeOf('Анна Первая'), 'Анна Первая');
    fireEvent.click(screen.getByRole('menuitem', { name: 'Результаты тестов' }));
    expect(screen.getByRole('dialog', { name: 'Результаты тестов: Анна Первая' })).toBeInTheDocument();
  });
});

// ── Контакты (ADR-032): чтение фиксируется в журнале только при открытии ──

test('значения контактов не загружаются и не показываются, пока диалог не открыт', () => {
  render(<EngagementsPage />);
  expect(screen.getAllByRole('button', { name: /^Другие действия:/ })).toHaveLength(4); // 2 студента × 2 раскладки
  expect(useUserContacts).not.toHaveBeenCalled();
  expect(screen.queryByText('+79001234567')).toBeNull();
});

test('«Контакты» из меню открывает диалог выбранного студента и запрашивает его uuid', () => {
  render(<EngagementsPage />);
  openMenu(row('Борис Второй'), 'Борис Второй');
  fireEvent.click(screen.getByRole('menuitem', { name: 'Контакты' }));

  expect(useUserContacts).toHaveBeenCalledWith('uuid-2');
  expect(useUserContacts).not.toHaveBeenCalledWith('uuid-1');
  const dialog = screen.getByRole('dialog', { name: 'Контакты: Борис Второй' });
  expect(within(dialog).getByText('Основной телефон')).toBeInTheDocument();
  expect(within(dialog).getByText(/фиксируется в журнале/)).toBeInTheDocument();
});

test('закрытие диалога убирает контакты со страницы', () => {
  render(<EngagementsPage />);
  openMenu(record('Анна Первая'), 'Анна Первая');
  fireEvent.click(screen.getByRole('menuitem', { name: 'Контакты' }));
  fireEvent.click(screen.getByRole('button', { name: 'Закрыть' }));

  expect(screen.queryByRole('dialog', { name: 'Контакты: Анна Первая' })).toBeNull();
  expect(screen.queryByText('+79001234567')).toBeNull();
});

test('503 при фиксации в журнале — понятное сообщение, данных нет', () => {
  useUserContacts.mockReturnValue({ status: 'auditUnavailable', data: null, error: null, refetch: jest.fn() });
  render(<EngagementsPage />);
  openMenu(row('Анна Первая'), 'Анна Первая');
  fireEvent.click(screen.getByRole('menuitem', { name: 'Контакты' }));

  expect(screen.getByRole('alert')).toHaveTextContent('зафиксировать в журнале');
  expect(screen.queryByText('+79001234567')).toBeNull();
});

// ── Состояния страницы — прежние (вне таблицы) ──

test('загрузка, ошибка с «Повторить» и пустой результат поиска', () => {
  mockStudents({ loading: true, items: [] });
  const { rerender } = render(<EngagementsPage />);
  expect(screen.getByText('Загрузка…')).toBeInTheDocument();
  expect(screen.queryByRole('table')).toBeNull();

  mockStudents({ error: 'Сбой сети', items: [] });
  rerender(<EngagementsPage />);
  expect(screen.getByText('Сбой сети')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Повторить' }));
  expect(refetch).toHaveBeenCalled();

  mockStudents({ items: [], query: 'xyz' });
  rerender(<EngagementsPage />);
  expect(screen.getByText('Студенты по запросу «xyz» не найдены')).toBeInTheDocument();
});

test('своей responsive-механики таблицы на странице нет — только ResponsiveTable', () => {
  const css = fs.readFileSync(path.join(__dirname, 'EngagementsPage.module.css'), 'utf8');
  expect(css).not.toMatch(/@container|container-type|\.table\b|<table/);
  const jsx = fs.readFileSync(path.join(__dirname, 'EngagementsPage.jsx'), 'utf8');
  expect(jsx).toMatch(/components\/UI\/ResponsiveTable\/ResponsiveTable/);
  expect(jsx).not.toMatch(/<table/);
});
