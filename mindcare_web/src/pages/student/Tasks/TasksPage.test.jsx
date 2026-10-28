import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import TasksPage from './TasksPage';
import useMyAssignments from '../../../features/assignments/hooks/useMyAssignments';
import { UNAVAILABLE_NOTE } from './components/TaskItem';

jest.mock('../../../features/assignments/hooks/useMyAssignments');
jest.mock('react-router-dom', () => ({
  Link: ({ to, children, ...props }) => <a href={to} {...props}>{children}</a>,
}), { virtual: true });

const list = (items, extra = {}) => ({
  items, total: items.length, hasMore: false, loading: false, loadingMore: false,
  error: null, loadMoreError: null, loadMore: jest.fn(), reset: jest.fn(), ...extra,
});

const TASK = {
  uuid: 'a-1', text: 'Прочитать материал и записать мысли', status: 'active',
  due_date: '2026-10-30', is_overdue: false, created_at: '2026-10-20T09:00:00Z',
  completed_at: null, cancelled_at: null, engagement_active: true, can_complete: true,
  psychologist_name: 'Иванова Ирина', material: { uuid: 'm-1', title: 'Сон и учёба' },
  material_unavailable: false,
};

function mockHook(overrides = {}) {
  const value = {
    open: list([TASK]),
    history: list([]),
    summary: { open_count: 1, completed_count: 2, total_count: 3 },
    refetch: jest.fn(),
    complete: jest.fn().mockResolvedValue(true),
    pendingUuid: null,
    actionError: null,
    clearActionError: jest.fn(),
    ...overrides,
  };
  useMyAssignments.mockReturnValue(value);
  return value;
}

beforeEach(() => jest.clearAllMocks());

describe('TasksPage', () => {
  it('реальные данные: без INITIAL_TASKS, комментариев и «дней до сессии»', () => {
    mockHook();
    render(<TasksPage />);
    expect(screen.getByText('Прочитать материал и записать мысли')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Сон и учёба' })).toHaveAttribute('href', '/student/materials/m-1');
    expect(screen.getByText(/30 октября 2026/)).toBeInTheDocument();
    expect(screen.queryByText(/До следующей сессии/)).toBeNull();
    expect(screen.queryByText(/Мария Ковалёва/)).toBeNull();
    expect(screen.queryByText(/Дневник эмоций/)).toBeNull();
    expect(screen.getByRole('group', { name: 'Активных заданий' })).toHaveTextContent('1');
    expect(screen.getByRole('group', { name: 'Выполнено' })).toHaveTextContent('2 из 3');
  });

  it('выполнение — только после подтверждения', async () => {
    const hook = mockHook();
    render(<TasksPage />);
    userEvent.click(screen.getByRole('button', { name: 'Отметить выполненным' }));
    expect(hook.complete).not.toHaveBeenCalled();
    const dialog = screen.getByRole('dialog', { name: 'Отметить задание выполненным?' });
    userEvent.click(within(dialog).getByRole('button', { name: 'Да, выполнено' }));
    expect(hook.complete).toHaveBeenCalledWith('a-1');
    await waitFor(() => expect(
      screen.queryByRole('dialog', { name: 'Отметить задание выполненным?' }),
    ).toBeNull());
  });

  it('ошибка сохранения показывается у задания и связана с кнопкой', () => {
    mockHook({ actionError: { uuid: 'a-1', message: 'Не удалось сохранить отметку.' } });
    render(<TasksPage />);
    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent('Не удалось сохранить отметку.');
    expect(screen.getByRole('button', { name: 'Отметить выполненным' }))
      .toHaveAttribute('aria-describedby', alert.id);
    expect(screen.queryByText('Выполнено', { selector: 'span' })).toBeNull();
  });

  it('пока идёт запрос — кнопка заблокирована', () => {
    mockHook({ pendingUuid: 'a-1' });
    render(<TasksPage />);
    expect(screen.getByRole('button', { name: 'Сохраняем…' })).toBeDisabled();
  });

  it('задание завершённого сопровождения: без кнопки, с пояснением про возобновление', () => {
    mockHook({
      open: list([]),
      history: list([{ ...TASK, engagement_active: false, can_complete: false }]),
    });
    render(<TasksPage />);
    expect(screen.getByText('Недоступно')).toBeInTheDocument();
    expect(screen.getByText(UNAVAILABLE_NOTE)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Отметить выполненным' })).toBeNull();
    expect(screen.getByText('Активных заданий нет.')).toBeInTheDocument();
  });

  it('после реактивации задание снова в «Активных» с кнопкой', () => {
    mockHook({ open: list([TASK]), history: list([]) });
    render(<TasksPage />);
    const active = screen.getByRole('region', { name: /Активные/ });
    expect(within(active).getByRole('button', { name: 'Отметить выполненным' })).toBeInTheDocument();
    expect(screen.queryByText(UNAVAILABLE_NOTE)).toBeNull();
  });

  it('загрузка, ошибка с повтором и «Показать ещё»', () => {
    const loadMore = jest.fn();
    const hook = mockHook({
      open: list([], { loading: true }),
      history: list([TASK], { hasMore: true, loadMore }),
    });
    const { rerender } = render(<TasksPage />);
    expect(screen.getByRole('status')).toHaveTextContent('Загружаем задания');
    userEvent.click(screen.getByRole('button', { name: 'Показать ещё' }));
    expect(loadMore).toHaveBeenCalledTimes(1);

    mockHook({ ...hook, open: list([], { error: new Error('x') }) });
    rerender(<TasksPage />);
    userEvent.click(screen.getByRole('button', { name: 'Повторить' }));
    expect(useMyAssignments.mock.results.at(-1).value.refetch).toHaveBeenCalled();
  });
});
