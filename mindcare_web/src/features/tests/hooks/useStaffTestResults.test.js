import { act, renderHook, waitFor } from '@testing-library/react';
import useStaffTestResults from './useStaffTestResults';
import { getStudentTestResults } from '../../../api/tests.api';

jest.mock('../../../api/tests.api');

const apiError = (status) => Object.assign(new Error('x'), { status });
const row = (n) => ({ uuid: `r-${n}`, test_title: `Тест ${n}`, submitted_at: '2026-10-01T10:00:00Z' });
const page = (from, to, total) => ({
  items: Array.from({ length: to - from + 1 }, (_, i) => row(from + i)), total, page: 1, size: 20,
});

function deferred() {
  let resolve; let reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

beforeEach(() => jest.resetAllMocks());

describe('useStaffTestResults', () => {
  it('больше 20 прохождений: «Показать ещё» дописывает следующую страницу', async () => {
    getStudentTestResults
      .mockResolvedValueOnce(page(1, 20, 22))
      .mockResolvedValueOnce(page(21, 22, 22));
    const { result } = renderHook(() => useStaffTestResults('c-1', 'psychologist'));
    await waitFor(() => expect(result.current.status).toBe('ready'));
    expect(result.current.items).toHaveLength(20);
    expect(result.current.hasMore).toBe(true);
    expect(getStudentTestResults).toHaveBeenLastCalledWith('c-1', 'psychologist', { page: 1, size: 20 });

    await act(async () => { await result.current.loadMore(); });
    expect(getStudentTestResults).toHaveBeenLastCalledWith('c-1', 'psychologist', { page: 2, size: 20 });
    expect(result.current.items.map(i => i.uuid)).toEqual(
      Array.from({ length: 22 }, (_, i) => `r-${i + 1}`),
    );
    expect(result.current.hasMore).toBe(false);
  });

  it('новое прохождение сдвинуло страницы — дубли не появляются', async () => {
    getStudentTestResults
      .mockResolvedValueOnce(page(1, 20, 21))
      .mockResolvedValueOnce({ items: [row(20), row(21)], total: 22 });
    const { result } = renderHook(() => useStaffTestResults('c-1', 'psychologist'));
    await waitFor(() => expect(result.current.status).toBe('ready'));
    await act(async () => { await result.current.loadMore(); });
    const uuids = result.current.items.map(i => i.uuid);
    expect(new Set(uuids).size).toBe(uuids.length);
    expect(uuids).toHaveLength(21);
  });

  it('смена клиента: прежний список очищается, запоздалый ответ прежнего клиента отбрасывается', async () => {
    const first = deferred();
    getStudentTestResults.mockReturnValueOnce(first.promise);
    const { result, rerender } = renderHook(
      ({ id, role }) => useStaffTestResults(id, role),
      { initialProps: { id: 'c-1', role: 'psychologist' } },
    );
    const second = deferred();
    getStudentTestResults.mockReturnValueOnce(second.promise);
    rerender({ id: 'c-2', role: 'psychologist' });
    await act(async () => { second.resolve({ items: [row(99)], total: 1 }); });
    await act(async () => { first.resolve({ items: [row(1)], total: 1 }); });
    expect(result.current.items.map(i => i.uuid)).toEqual(['r-99']);
  });

  it('смена роли перезагружает список и отбрасывает догрузку прежней роли', async () => {
    getStudentTestResults.mockResolvedValueOnce(page(1, 20, 25));
    const { result, rerender } = renderHook(
      ({ role }) => useStaffTestResults('c-1', role),
      { initialProps: { role: 'psychologist' } },
    );
    await waitFor(() => expect(result.current.status).toBe('ready'));
    const more = deferred();
    getStudentTestResults.mockReturnValueOnce(more.promise);
    act(() => { result.current.loadMore(); });
    getStudentTestResults.mockResolvedValueOnce({ items: [row(500)], total: 1 });
    rerender({ role: 'supervisor' });
    await waitFor(() => expect(result.current.items.map(i => i.uuid)).toEqual(['r-500']));
    await act(async () => { more.resolve(page(21, 25, 25)); });
    expect(result.current.items.map(i => i.uuid)).toEqual(['r-500']);
  });

  it('404 при догрузке — доступ потерян, загруженное очищается', async () => {
    getStudentTestResults
      .mockResolvedValueOnce(page(1, 20, 30))
      .mockRejectedValueOnce(apiError(404));
    const { result } = renderHook(() => useStaffTestResults('c-1', 'psychologist'));
    await waitFor(() => expect(result.current.status).toBe('ready'));
    await act(async () => { await result.current.loadMore(); });
    expect(result.current.status).toBe('unavailable');
    expect(result.current.items).toEqual([]);
  });

  it('сетевая ошибка догрузки нефатальна: загруженное остаётся', async () => {
    getStudentTestResults
      .mockResolvedValueOnce(page(1, 20, 30))
      .mockRejectedValueOnce(apiError(500));
    const { result } = renderHook(() => useStaffTestResults('c-1', 'psychologist'));
    await waitFor(() => expect(result.current.status).toBe('ready'));
    await act(async () => { await result.current.loadMore(); });
    expect(result.current.items).toHaveLength(20);
    expect(result.current.loadMoreError.status).toBe(500);
  });

  it('invalidate (сигнал детали) очищает список и отбрасывает летящую догрузку', async () => {
    getStudentTestResults.mockResolvedValueOnce(page(1, 20, 30));
    const { result } = renderHook(() => useStaffTestResults('c-1', 'psychologist'));
    await waitFor(() => expect(result.current.status).toBe('ready'));
    const more = deferred();
    getStudentTestResults.mockReturnValueOnce(more.promise);
    act(() => { result.current.loadMore(); });
    act(() => { result.current.invalidate(apiError(404)); });
    await act(async () => { more.resolve(page(21, 30, 30)); });
    expect(result.current.status).toBe('unavailable');
    expect(result.current.items).toEqual([]);
  });
});
