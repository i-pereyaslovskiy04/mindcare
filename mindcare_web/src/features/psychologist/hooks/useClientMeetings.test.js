import { act, renderHook, waitFor } from '@testing-library/react';
import useClientMeetings from './useClientMeetings';
import { getClientAppointments, markAppointmentOutcome } from '../../../api/appointments.api';

jest.mock('../../../api/appointments.api');

const apiError = (status, message = 'x') => Object.assign(new Error(message), { status });
const meeting = (uuid, extra = {}) => ({
  uuid, starts_at: '2026-10-01T10:00:00+03:00', ends_at: '2026-10-01T10:50:00+03:00',
  status: 'confirmed', meeting_type_name: null, modality: 'in_person', via_card: false,
  can_mark_outcome: false, ...extra,
});
const page = (items, nextCursor = null) => ({
  items, has_more: Boolean(nextCursor), next_cursor: nextCursor,
});

function deferred() {
  let resolve; let reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

function byView(map) {
  getClientAppointments.mockImplementation((uuid, { view, before }) => {
    const key = `${uuid}:${view}:${before || ''}`;
    const value = map[key];
    if (value instanceof Error) return Promise.reject(value);
    return value && typeof value.then === 'function' ? value : Promise.resolve(value || page([]));
  });
}

beforeEach(() => jest.resetAllMocks());

describe('useClientMeetings', () => {
  it('грузит предстоящие и историю по uuid клиента, история — с догрузкой', async () => {
    byView({
      'c-1:upcoming:': page([meeting('u1')]),
      'c-1:history:': page([meeting('h1')], 'cur-1'),
      'c-1:history:cur-1': page([meeting('h2')]),
    });
    const { result } = renderHook(() => useClientMeetings('c-1'));
    await waitFor(() => expect(result.current.historyStatus).toBe('ready'));
    expect(result.current.upcoming.items.map(i => i.uuid)).toEqual(['u1']);
    expect(result.current.history.hasMore).toBe(true);
    await act(async () => { await result.current.history.loadMore(); });
    expect(result.current.history.items.map(i => i.uuid)).toEqual(['h1', 'h2']);
    expect(getClientAppointments).toHaveBeenCalledWith('c-1', { view: 'history', before: 'cur-1', size: 20 });
  });

  it('итог сохранён — оба списка перечитываются; без оптимистичного успеха', async () => {
    byView({
      'c-1:upcoming:': page([]),
      'c-1:history:': page([meeting('h1', { can_mark_outcome: true })]),
    });
    const { result } = renderHook(() => useClientMeetings('c-1'));
    await waitFor(() => expect(result.current.historyStatus).toBe('ready'));
    const save = deferred();
    markAppointmentOutcome.mockReturnValueOnce(save.promise);
    byView({
      'c-1:upcoming:': page([]),
      'c-1:history:': page([meeting('h1', { status: 'completed' })]),
    });
    let done;
    act(() => { done = result.current.outcome.mark('h1', 'completed'); });
    expect(result.current.history.items[0].status).toBe('confirmed');   // ещё не сохранено
    await act(async () => { save.resolve({ uuid: 'h1', status: 'completed', changed: true }); await done; });
    await waitFor(() => expect(result.current.history.items[0].status).toBe('completed'));
    expect(markAppointmentOutcome).toHaveBeenCalledWith('h1', 'completed');
  });

  it('двойная отправка итога исключена', async () => {
    byView({ 'c-1:history:': page([meeting('h1', { can_mark_outcome: true })]) });
    const { result } = renderHook(() => useClientMeetings('c-1'));
    await waitFor(() => expect(result.current.historyStatus).toBe('ready'));
    const save = deferred();
    markAppointmentOutcome.mockReturnValueOnce(save.promise);
    let first;
    act(() => { first = result.current.outcome.mark('h1', 'completed'); });
    let second;
    act(() => { second = result.current.outcome.mark('h1', 'no_show'); });
    await act(async () => { save.resolve({}); await first; });
    expect(await second).toBe(false);
    expect(markAppointmentOutcome).toHaveBeenCalledTimes(1);
  });

  it('409 — сообщение сервера и перечитывание списков', async () => {
    byView({ 'c-1:history:': page([meeting('h1', { can_mark_outcome: true })]) });
    const { result } = renderHook(() => useClientMeetings('c-1'));
    await waitFor(() => expect(result.current.historyStatus).toBe('ready'));
    const calls = getClientAppointments.mock.calls.length;
    markAppointmentOutcome.mockRejectedValueOnce(apiError(409, 'Итог встречи уже отмечен'));
    await act(async () => { await result.current.outcome.mark('h1', 'no_show'); });
    expect(result.current.outcome.error).toEqual({
      uuid: 'h1', message: 'Итог встречи уже отмечен. Список встреч обновлён.',
    });
    await waitFor(() => expect(getClientAppointments.mock.calls.length).toBe(calls + 2));
  });

  it('смена клиента: прежние встречи пропадают, запоздалый ответ отбрасывается', async () => {
    const late = deferred();
    byView({ 'c-1:upcoming:': late.promise, 'c-2:upcoming:': page([meeting('b1')]) });
    const { result, rerender } = renderHook(({ id }) => useClientMeetings(id), {
      initialProps: { id: 'c-1' },
    });
    rerender({ id: 'c-2' });
    await waitFor(() => expect(result.current.upcoming.items.map(i => i.uuid)).toEqual(['b1']));
    await act(async () => { late.resolve(page([meeting('a1')])); });
    expect(result.current.upcoming.items.map(i => i.uuid)).toEqual(['b1']);
  });

  it('404 — раздел недоступен', async () => {
    byView({ 'c-1:upcoming:': apiError(404), 'c-1:history:': apiError(404) });
    const { result } = renderHook(() => useClientMeetings('c-1'));
    await waitFor(() => expect(result.current.status).toBe('unavailable'));
    expect(result.current.upcoming.items).toEqual([]);
  });
});
