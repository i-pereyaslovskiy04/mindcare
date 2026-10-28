import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ClientAssignments from './ClientAssignments';
import useClientAssignments from '../hooks/useClientAssignments';
import { useMaterialsLibrary } from '../../materials/hooks/useMaterialsLibrary';

jest.mock('../hooks/useClientAssignments');
jest.mock('../../materials/hooks/useMaterialsLibrary');
jest.mock('react-router-dom', () => ({
  Link: ({ to, children, ...props }) => <a href={to} {...props}>{children}</a>,
}), { virtual: true });

const ITEM = {
  uuid: 'a-1', text: 'Дыхательная практика', status: 'active', due_date: null,
  is_overdue: false, created_at: '2026-10-20T09:00:00Z', completed_at: null,
  cancelled_at: null, engagement_active: true, can_cancel: true,
  material: null, material_unavailable: true,
};

function mockHook(overrides = {}) {
  const value = {
    list: {
      items: [ITEM], total: 1, hasMore: false, loading: false, loadingMore: false,
      error: null, loadMoreError: null, loadMore: jest.fn(), reset: jest.fn(),
    },
    status: 'ready',
    reload: jest.fn(),
    create: jest.fn().mockResolvedValue(true),
    submitting: false,
    formError: null,
    clearFormError: jest.fn(),
    cancel: jest.fn().mockResolvedValue(true),
    pendingUuid: null,
    actionError: null,
    ...overrides,
  };
  useClientAssignments.mockReturnValue(value);
  return value;
}

beforeEach(() => {
  jest.clearAllMocks();
  useMaterialsLibrary.mockReturnValue({
    items: [{ id: 'm-1', title: 'Сон и учёба', category: 'Статья' }],
    loading: false, error: null, hasMore: false,
    setQuery: jest.fn(), loadMore: jest.fn(), refetch: jest.fn(),
  });
});

describe('ClientAssignments', () => {
  it('создание с материалом из библиотеки', async () => {
    const hook = mockHook();
    render(<ClientAssignments studentUuid="s-1" />);
    expect(useMaterialsLibrary).not.toHaveBeenCalled();     // библиотека — только при выборе

    userEvent.type(screen.getByLabelText('Текст задания'), 'Прочитать главу');
    userEvent.click(screen.getByRole('button', { name: 'Выбрать из библиотеки' }));
    // выбор — встроенная панель формы, не вложенное модальное окно
    const picker = screen.getByRole('region', { name: 'Материал из библиотеки' });
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(within(picker).getByRole('searchbox', { name: 'Поиск по названию' })).toHaveFocus();
    userEvent.click(within(picker).getByRole('button', { name: 'Выбрать «Сон и учёба»' }));
    expect(screen.queryByRole('region', { name: 'Материал из библиотеки' })).toBeNull();
    expect(screen.getByText('Сон и учёба')).toBeInTheDocument();

    userEvent.click(screen.getByRole('button', { name: 'Выдать задание' }));
    expect(hook.create).toHaveBeenCalledWith({
      text: 'Прочитать главу', dueDate: '', articleUuid: 'm-1',
    });
    // успешная выдача очищает форму
    await waitFor(() => expect(screen.getByLabelText('Текст задания')).toHaveValue(''));
  });

  it('пустой текст — кнопка выдачи заблокирована; во время отправки — loading', () => {
    mockHook();
    const { rerender } = render(<ClientAssignments studentUuid="s-1" />);
    expect(screen.getByRole('button', { name: 'Выдать задание' })).toBeDisabled();
    mockHook({ submitting: true });
    rerender(<ClientAssignments studentUuid="s-1" />);
    expect(screen.getByLabelText('Текст задания')).toBeDisabled();
  });

  it('ошибка поля связана с textarea', () => {
    mockHook({ formError: { field: 'text', message: 'Введите текст задания.' } });
    render(<ClientAssignments studentUuid="s-1" />);
    const textarea = screen.getByLabelText('Текст задания');
    expect(textarea).toHaveAttribute('aria-invalid', 'true');
    const alert = screen.getByRole('alert');
    expect(textarea.getAttribute('aria-describedby')).toContain(alert.id);
  });

  it('статус, недоступный материал и отмена с подтверждением', async () => {
    const hook = mockHook();
    render(<ClientAssignments studentUuid="s-1" />);
    const [row] = within(screen.getByRole('list', { name: 'Выданные задания' })).getAllByRole('listitem');
    expect(within(row).getByText('Дыхательная практика')).toBeInTheDocument();
    expect(within(row).getByText('В работе')).toBeInTheDocument();
    expect(within(row).getByText('Прикреплённый материал больше недоступен.')).toBeInTheDocument();
    userEvent.click(within(row).getByRole('button', { name: 'Отменить' }));
    expect(hook.cancel).not.toHaveBeenCalled();
    const dialog = screen.getByRole('dialog', { name: 'Отменить задание?' });
    userEvent.click(within(dialog).getByRole('button', { name: 'Отменить задание' }));
    expect(hook.cancel).toHaveBeenCalledWith('a-1');
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Отменить задание?' })).toBeNull());
  });

  it('выполненное задание — статус, без кнопки отмены', () => {
    mockHook({
      list: { ...mockHook().list, items: [{ ...ITEM, status: 'completed', can_cancel: false,
        completed_at: '2026-10-21T10:00:00Z' }] },
    });
    render(<ClientAssignments studentUuid="s-1" />);
    expect(screen.getByText('Выполнено')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Отменить' })).toBeNull();
  });

  it('сбой обязательного аудита чтения: список не показан, есть повтор', () => {
    const hook = mockHook({ status: 'auditUnavailable', list: { ...mockHook().list, items: [] } });
    render(<ClientAssignments studentUuid="s-1" />);
    expect(screen.getByRole('alert')).toHaveTextContent('Не удалось зафиксировать просмотр');
    userEvent.click(screen.getByRole('button', { name: 'Повторить' }));
    expect(hook.reload).toHaveBeenCalled();
  });

  it('сопровождение неактивно — нейтральный текст без формы', () => {
    mockHook({ status: 'unavailable' });
    render(<ClientAssignments studentUuid="s-1" />);
    expect(screen.getByText(/сопровождение не активно/)).toBeInTheDocument();
    expect(screen.queryByLabelText('Текст задания')).toBeNull();
  });

  it('Escape в панели выбора закрывает только панель и возвращает фокус на кнопку', async () => {
    mockHook();
    render(<ClientAssignments studentUuid="s-1" />);
    const trigger = screen.getByRole('button', { name: 'Выбрать из библиотеки' });
    userEvent.click(trigger);
    const search = screen.getByRole('searchbox', { name: 'Поиск по названию' });
    userEvent.type(search, '{esc}');
    expect(screen.queryByRole('region', { name: 'Материал из библиотеки' })).toBeNull();
    await waitFor(() => expect(trigger).toHaveFocus());
  });
});
