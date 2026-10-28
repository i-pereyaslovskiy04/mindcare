import { act, renderHook, waitFor } from '@testing-library/react';
import useClientAssignments from './useClientAssignments';
import {
  cancelAssignment, createClientAssignment, getClientAssignments,
} from '../../../api/assignments.api';

jest.mock('../../../api/assignments.api');

const page = (items, extra = {}) => ({ items, has_more: false, next_cursor: null, total: items.length, ...extra });
const item = (n, extra = {}) => ({ uuid: `a-${n}`, text: `T${n}`, status: 'active', can_cancel: true, ...extra });
const apiError = (status, body = {}) => Object.assign(new Error('x'), { status, code: body.code, body });

function deferred() {
  let resolve; let reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

beforeEach(() => {
  jest.clearAllMocks();
  getClientAssignments.mockResolvedValue(page([item(1)]));
});

describe('useClientAssignments', () => {
  it('без uuid запросов нет', () => {
    renderHook(() => useClientAssignments(null));
    expect(getClientAssignments).not.toHaveBeenCalled();
  });

  it.each([
    [404, 'unavailable'], [503, 'auditUnavailable'], [500, 'error'],
  ])('HTTP %s → %s без данных', async (status, expected) => {
    getClientAssignments.mockRejectedValue(apiError(status));
    const { result } = renderHook(() => useClientAssignments('s-1'));
    await waitFor(() => expect(result.current.status).toBe(expected));
    expect(result.current.list.items).toEqual([]);
  });

  it('создание: один запрос при двойном нажатии, затем список с первой страницы', async () => {
    const { result } = renderHook(() => useClientAssignments('s-1'));
    await waitFor(() => expect(result.current.status).toBe('ready'));
    const pending = deferred();
    createClientAssignment.mockReturnValue(pending.promise);
    getClientAssignments.mockResolvedValue(page([item(2), item(1)]));

    let first;
    act(() => { first = result.current.create({ text: 'Новое', dueDate: '', articleUuid: null }); });
    await act(async () => { await result.current.create({ text: 'Новое' }); });
    expect(createClientAssignment).toHaveBeenCalledTimes(1);
    expect(result.current.submitting).toBe(true);
    await act(async () => { pending.resolve({ uuid: 'a-2', status: 'active' }); await first; });
    await waitFor(() => expect(result.current.list.items.map(i => i.uuid)).toEqual(['a-2', 'a-1']));
    expect(getClientAssignments).toHaveBeenLastCalledWith('s-1', { before: undefined, size: 20 });
  });

  it('недоступный материал и ошибка текста — сообщения у полей', async () => {
    const { result } = renderHook(() => useClientAssignments('s-1'));
    await waitFor(() => expect(result.current.status).toBe('ready'));
    createClientAssignment.mockRejectedValueOnce(apiError(422, { code: 'assignment_material_unavailable' }));
    await act(async () => { await result.current.create({ text: 'x', articleUuid: 'm' }); });
    expect(result.current.formError.field).toBe('material');

    createClientAssignment.mockRejectedValueOnce(apiError(422, {
      code: 'assignment_invalid', errors: [{ field: 'text', code: 'too_long' }],
    }));
    await act(async () => { await result.current.create({ text: 'x' }); });
    expect(result.current.formError).toEqual({ field: 'text', message: expect.stringContaining('4000') });
  });

  it('отмена: 409 — понятная ошибка и перечитывание; сбой сети — без перечитывания', async () => {
    const { result } = renderHook(() => useClientAssignments('s-1'));
    await waitFor(() => expect(result.current.status).toBe('ready'));
    cancelAssignment.mockRejectedValueOnce(apiError(409, { code: 'assignment_finalized' }));
    getClientAssignments.mockClear();
    await act(async () => { await result.current.cancel('a-1'); });
    expect(result.current.actionError.message).toContain('уже выполнено');
    expect(getClientAssignments).toHaveBeenCalledTimes(1);

    cancelAssignment.mockRejectedValueOnce(new Error('Failed to fetch'));
    getClientAssignments.mockClear();
    await act(async () => { await result.current.cancel('a-1'); });
    expect(result.current.actionError.message).toContain('Не удалось отменить');
    expect(getClientAssignments).not.toHaveBeenCalled();
  });

  it('смена клиента: данные прежнего пропадают сразу', async () => {
    const { result, rerender } = renderHook(({ id }) => useClientAssignments(id), {
      initialProps: { id: 's-1' },
    });
    await waitFor(() => expect(result.current.list.items).toHaveLength(1));
    const next = deferred();
    getClientAssignments.mockReturnValueOnce(next.promise);
    rerender({ id: 's-2' });
    expect(result.current.list.items).toEqual([]);
    expect(result.current.status).toBe('loading');
    await act(async () => { next.resolve(page([item(7)])); });
    await waitFor(() => expect(result.current.list.items.map(i => i.uuid)).toEqual(['a-7']));
  });

  it('404 при догрузке — данные очищены, раздел недоступен', async () => {
    getClientAssignments.mockResolvedValueOnce(page([item(1)], { has_more: true, next_cursor: 'c1', total: 2 }));
    const { result } = renderHook(() => useClientAssignments('s-1'));
    await waitFor(() => expect(result.current.list.items).toHaveLength(1));
    getClientAssignments.mockRejectedValueOnce(apiError(404, { code: 'assignment_not_available' }));
    await act(async () => { await result.current.list.loadMore(); });
    expect(result.current.status).toBe('unavailable');
    expect(result.current.list.items).toEqual([]);
    expect(result.current.list.hasMore).toBe(false);
    expect(result.current.list.loadMoreError).toBeNull();
  });

  it('сетевая ошибка догрузки — данные остаются, повтор догружает', async () => {
    getClientAssignments.mockResolvedValueOnce(page([item(1)], { has_more: true, next_cursor: 'c1', total: 2 }));
    const { result } = renderHook(() => useClientAssignments('s-1'));
    await waitFor(() => expect(result.current.list.items).toHaveLength(1));
    getClientAssignments.mockRejectedValueOnce(new Error('Failed to fetch'));
    await act(async () => { await result.current.list.loadMore(); });
    expect(result.current.status).toBe('ready');
    expect(result.current.list.items.map(i => i.uuid)).toEqual(['a-1']);
    expect(result.current.list.loadMoreError).toBeTruthy();
    expect(result.current.list.hasMore).toBe(true);

    getClientAssignments.mockResolvedValueOnce(page([item(2)], { total: 2 }));
    await act(async () => { await result.current.list.loadMore(); });
    expect(result.current.list.items.map(i => i.uuid)).toEqual(['a-1', 'a-2']);
    expect(result.current.list.loadMoreError).toBeNull();
    expect(getClientAssignments).toHaveBeenLastCalledWith('s-1', { before: 'c1', size: 20 });
  });
});
