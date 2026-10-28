import { act, renderHook, waitFor } from '@testing-library/react';
import useMyAssignments, { SUMMARY_POLL_MS } from './useMyAssignments';
import {
  completeMyAssignment, getMyAssignments, getMyAssignmentsSummary,
} from '../../../api/assignments.api';
import { ASSIGNMENTS_CHANGED_EVENT } from '../lib/assignmentEvents';

jest.mock('../../../api/assignments.api');

const task = (n, extra = {}) => ({
  uuid: `a-${n}`, text: `Задание ${n}`, status: 'active', engagement_active: true,
  can_complete: true, ...extra,
});
const page = (items, { hasMore = false, cursor = null, total } = {}) => ({
  items, has_more: hasMore, next_cursor: cursor, total: total ?? items.length,
});
const SUMMARY = { open_count: 2, completed_count: 0, total_count: 2 };
const apiError = (status, code) => Object.assign(new Error('x'), { status, code, body: { code } });

function deferred() {
  let resolve; let reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

function byView(open, history = page([])) {
  getMyAssignments.mockImplementation(({ view }) => Promise.resolve(view === 'open' ? open : history));
}

beforeEach(() => {
  jest.clearAllMocks();
  getMyAssignmentsSummary.mockResolvedValue(SUMMARY);
  byView(page([task(1), task(2)]));
});

describe('useMyAssignments', () => {
  it('грузит активные, историю и сводку', async () => {
    byView(page([task(1)]), page([task(9, { status: 'completed', can_complete: false })]));
    const { result } = renderHook(() => useMyAssignments());
    await waitFor(() => expect(result.current.open.items).toHaveLength(1));
    await waitFor(() => expect(result.current.history.items).toHaveLength(1));
    await waitFor(() => expect(result.current.summary).toEqual(SUMMARY));
    expect(getMyAssignments).toHaveBeenCalledWith({ view: 'open', before: undefined, size: 20 });
    expect(getMyAssignments).toHaveBeenCalledWith({ view: 'history', before: undefined, size: 20 });
  });

  it('ошибка сохранения не выглядит как выполнение: статус не меняется', async () => {
    const { result } = renderHook(() => useMyAssignments());
    await waitFor(() => expect(result.current.open.items).toHaveLength(2));
    completeMyAssignment.mockRejectedValue(new Error('Failed to fetch'));
    getMyAssignments.mockClear();

    let ok;
    await act(async () => { ok = await result.current.complete('a-1'); });
    expect(ok).toBe(false);
    expect(result.current.open.items.map(t => t.status)).toEqual(['active', 'active']);
    expect(result.current.actionError).toEqual({
      uuid: 'a-1', message: expect.stringContaining('Не удалось сохранить отметку'),
    });
    expect(getMyAssignments).not.toHaveBeenCalled();     // сетевой сбой — без сброса
  });

  it('двойное нажатие во время запроса — один запрос', async () => {
    const { result } = renderHook(() => useMyAssignments());
    await waitFor(() => expect(result.current.open.items).toHaveLength(2));
    const pending = deferred();
    completeMyAssignment.mockReturnValue(pending.promise);

    let first;
    act(() => { first = result.current.complete('a-1'); });
    await act(async () => { await result.current.complete('a-1'); });
    expect(completeMyAssignment).toHaveBeenCalledTimes(1);
    expect(result.current.pendingUuid).toBe('a-1');
    await act(async () => { pending.resolve({ uuid: 'a-1', status: 'completed', changed: true }); await first; });
    expect(result.current.pendingUuid).toBeNull();
  });

  it('успех: оба списка перечитываются, бейдж получает сигнал', async () => {
    const { result } = renderHook(() => useMyAssignments());
    await waitFor(() => expect(result.current.open.items).toHaveLength(2));
    const listener = jest.fn();
    window.addEventListener(ASSIGNMENTS_CHANGED_EVENT, listener);
    completeMyAssignment.mockResolvedValue({ uuid: 'a-1', status: 'completed', changed: true });
    byView(page([task(2)]), page([task(1, { status: 'completed', can_complete: false })]));
    getMyAssignments.mockClear();

    await act(async () => { await result.current.complete('a-1'); });
    await waitFor(() => expect(result.current.open.items.map(t => t.uuid)).toEqual(['a-2']));
    await waitFor(() => expect(result.current.history.items.map(t => t.uuid)).toEqual(['a-1']));
    expect(getMyAssignments).toHaveBeenCalledWith(expect.objectContaining({ view: 'open', before: undefined }));
    expect(getMyAssignments).toHaveBeenCalledWith(expect.objectContaining({ view: 'history', before: undefined }));
    expect(listener).toHaveBeenCalledTimes(1);
    window.removeEventListener(ASSIGNMENTS_CHANGED_EVENT, listener);
  });

  it.each([
    ['assignment_engagement_inactive', 'Сопровождение завершено'],
    ['assignment_finalized', 'уже отменено'],
  ])('409 %s — понятная ошибка и сброс обоих списков', async (code, text) => {
    const { result } = renderHook(() => useMyAssignments());
    await waitFor(() => expect(result.current.open.items).toHaveLength(2));
    completeMyAssignment.mockRejectedValue(apiError(409, code));
    getMyAssignments.mockClear();
    await act(async () => { await result.current.complete('a-1'); });
    expect(result.current.actionError.message).toContain(text);
    expect(getMyAssignments).toHaveBeenCalledWith(expect.objectContaining({ view: 'open', before: undefined }));
    expect(getMyAssignments).toHaveBeenCalledWith(expect.objectContaining({ view: 'history', before: undefined }));
  });

  describe('опрос состава (30 с)', () => {
    beforeEach(() => jest.useFakeTimers());
    afterEach(() => jest.useRealTimers());

    async function tick() {
      await act(async () => { jest.advanceTimersByTime(SUMMARY_POLL_MS); });
      await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    }

    it('те же счётчики, но другой состав (передача/реактивация) — список заменяется', async () => {
      byView(page([task(1), task(2)]));
      const { result } = renderHook(() => useMyAssignments());
      await waitFor(() => expect(result.current.open.items.map(t => t.uuid)).toEqual(['a-1', 'a-2']));

      // сводка та же (2 активных из 2), но задания — другого сопровождения
      byView(page([task(3), task(4)]), page([
        task(1, { engagement_active: false, can_complete: false }),
        task(2, { engagement_active: false, can_complete: false }),
      ]));
      await tick();
      await waitFor(() => expect(result.current.open.items.map(t => t.uuid)).toEqual(['a-3', 'a-4']));
      await waitFor(() => expect(result.current.history.items.map(t => t.uuid)).toEqual(['a-1', 'a-2']));
      expect(getMyAssignmentsSummary).toHaveBeenCalledTimes(2);
      expect(result.current.summary).toEqual(SUMMARY);
    });

    it('тот же состав — загруженные страницы не сбрасываются', async () => {
      const first = page([task(1), task(2)], { hasMore: true, cursor: 'c1', total: 3 });
      getMyAssignments.mockImplementation(({ view, before }) => {
        if (view === 'history') return Promise.resolve(page([]));
        return Promise.resolve(before === 'c1' ? page([task(3)], { total: 3 }) : first);
      });
      const { result } = renderHook(() => useMyAssignments());
      await waitFor(() => expect(result.current.open.items).toHaveLength(2));
      await act(async () => { await result.current.open.loadMore(); });
      expect(result.current.open.items.map(t => t.uuid)).toEqual(['a-1', 'a-2', 'a-3']);

      await tick();
      expect(result.current.open.items.map(t => t.uuid)).toEqual(['a-1', 'a-2', 'a-3']);
      expect(result.current.open.hasMore).toBe(false);
    });

    it('смена статуса без смены uuid (реактивация: снова можно выполнить) — замена', async () => {
      byView(page([]), page([task(1, { engagement_active: false, can_complete: false })]));
      const { result } = renderHook(() => useMyAssignments());
      await waitFor(() => expect(result.current.history.items).toHaveLength(1));
      byView(page([task(1)]), page([]));
      await tick();
      await waitFor(() => expect(result.current.open.items.map(t => t.can_complete)).toEqual([true]));
      expect(result.current.history.items).toEqual([]);
    });

    it('проба, начатая до своего выполнения, отбрасывается', async () => {
      byView(page([task(1), task(2)]));
      const { result } = renderHook(() => useMyAssignments());
      await waitFor(() => expect(result.current.open.items).toHaveLength(2));

      const staleOpen = deferred();
      getMyAssignments.mockImplementation(({ view }) => (view === 'open'
        ? staleOpen.promise : Promise.resolve(page([]))));
      await act(async () => { jest.advanceTimersByTime(SUMMARY_POLL_MS); });   // проба в полёте

      completeMyAssignment.mockResolvedValue({ uuid: 'a-1', status: 'completed', changed: true });
      byView(page([task(2)]), page([task(1, { status: 'completed', can_complete: false })]));
      await act(async () => { await result.current.complete('a-1'); });
      await waitFor(() => expect(result.current.open.items.map(t => t.uuid)).toEqual(['a-2']));

      // устаревшая проба вернула прежний состав — он не должен вернуться
      await act(async () => { staleOpen.resolve(page([task(1), task(2)])); });
      expect(result.current.open.items.map(t => t.uuid)).toEqual(['a-2']);
    });

    it('сбой пробы ничего не меняет', async () => {
      const { result } = renderHook(() => useMyAssignments());
      await waitFor(() => expect(result.current.open.items).toHaveLength(2));
      getMyAssignments.mockRejectedValue(new Error('down'));
      await tick();
      expect(result.current.open.items.map(t => t.uuid)).toEqual(['a-1', 'a-2']);
      expect(result.current.open.error).toBeNull();
    });
  });

  it('догрузка, начатая до сброса, отбрасывается; переход open → history без пропуска и дубля', async () => {
    byView(page([task(1), task(2)], { hasMore: true, cursor: 'c1', total: 3 }));
    const { result } = renderHook(() => useMyAssignments());
    await waitFor(() => expect(result.current.open.items).toHaveLength(2));

    // догрузка «старой» второй страницы зависла
    const stale = deferred();
    getMyAssignments.mockImplementation(({ view, before }) => {
      if (view === 'open' && before === 'c1') return stale.promise;
      // после выполнения a-1: open = [a-2, a-3], history = [a-1]
      if (view === 'open') return Promise.resolve(page([task(2), task(3)]));
      return Promise.resolve(page([task(1, { status: 'completed', can_complete: false })]));
    });
    act(() => { result.current.open.loadMore(); });

    completeMyAssignment.mockResolvedValue({ uuid: 'a-1', status: 'completed', changed: true });
    await act(async () => { await result.current.complete('a-1'); });
    await waitFor(() => expect(result.current.open.items.map(t => t.uuid)).toEqual(['a-2', 'a-3']));

    // устаревший ответ догрузки приходит после сброса и игнорируется
    await act(async () => { stale.resolve(page([task(3)], { total: 3 })); });
    expect(result.current.open.items.map(t => t.uuid)).toEqual(['a-2', 'a-3']);
    await waitFor(() => expect(result.current.history.items.map(t => t.uuid)).toEqual(['a-1']));
    const all = [...result.current.open.items, ...result.current.history.items].map(t => t.uuid);
    expect(new Set(all).size).toBe(all.length);
    expect(all.sort()).toEqual(['a-1', 'a-2', 'a-3']);
  });

  it('догрузка по курсору дополняет список; дубль по uuid отбрасывается', async () => {
    byView(page([task(1), task(2)], { hasMore: true, cursor: 'c1', total: 3 }));
    const { result } = renderHook(() => useMyAssignments());
    await waitFor(() => expect(result.current.open.items).toHaveLength(2));
    getMyAssignments.mockImplementation(({ before }) =>
      Promise.resolve(before === 'c1' ? page([task(2), task(3)], { total: 3 }) : page([])));
    await act(async () => { await result.current.open.loadMore(); });
    expect(result.current.open.items.map(t => t.uuid)).toEqual(['a-1', 'a-2', 'a-3']);
    expect(result.current.open.hasMore).toBe(false);
  });
});
