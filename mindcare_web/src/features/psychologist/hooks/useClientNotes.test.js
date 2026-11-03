import { act, renderHook, waitFor } from '@testing-library/react';
import useClientNotes from './useClientNotes';
import { createClientNote, getClientNotes, updateClientNote } from '../../../api/sessionNotes.api';

jest.mock('../../../api/sessionNotes.api');

const apiError = (status) => Object.assign(new Error('x'), { status });
const note = (uuid, extra = {}) => ({
  uuid, note_type: 'general', content: `Текст ${uuid}`, version: 1,
  created_at: '2026-10-01T10:00:00Z', updated_at: '2026-10-01T10:00:00Z', appointment: null, ...extra,
});
const page = (items) => ({ items, has_more: false, next_cursor: null });

function deferred() {
  let resolve; let reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

beforeEach(() => jest.resetAllMocks());

describe('useClientNotes', () => {
  it('создание: без оптимистичного успеха, после ответа список перечитывается', async () => {
    getClientNotes.mockResolvedValueOnce(page([]));
    const { result } = renderHook(() => useClientNotes('c-1'));
    await waitFor(() => expect(result.current.status).toBe('ready'));
    getClientNotes.mockResolvedValueOnce(page([note('n1')]));
    let out;
    await act(async () => {
      out = await result.current.create({ content: 'Текст', noteType: 'plan', appointmentUuid: 'a-9' });
    });
    expect(out).toEqual({ ok: true });
    expect(createClientNote).toHaveBeenCalledWith('c-1', { content: 'Текст', noteType: 'plan', appointmentUuid: 'a-9' });
    await waitFor(() => expect(result.current.list.items.map(i => i.uuid)).toEqual(['n1']));
  });

  it('двойная отправка исключена', async () => {
    getClientNotes.mockResolvedValue(page([]));
    const { result } = renderHook(() => useClientNotes('c-1'));
    await waitFor(() => expect(result.current.status).toBe('ready'));
    const save = deferred();
    createClientNote.mockReturnValueOnce(save.promise);
    let first;
    act(() => { first = result.current.create({ content: 'a', noteType: 'general' }); });
    let second;
    await act(async () => { second = await result.current.create({ content: 'b', noteType: 'general' }); });
    expect(second).toEqual({ ok: false });
    await act(async () => { save.resolve(note('n1')); await first; });
    expect(createClientNote).toHaveBeenCalledTimes(1);
  });

  it('409 правки заметки со второй страницы: черновик остаётся, актуальная версия найдена', async () => {
    getClientNotes.mockImplementation((uuid, { before }) => Promise.resolve(before
      ? { items: [note('p2', { content: 'Чужая правка', version: 2 })], has_more: false, next_cursor: null }
      : { items: [note('p1')], has_more: true, next_cursor: 'cur' }));
    const { result } = renderHook(() => useClientNotes('c-1'));
    await waitFor(() => expect(result.current.status).toBe('ready'));
    await act(async () => { await result.current.list.loadMore(); });
    const p2 = result.current.list.items.find(i => i.uuid === 'p2');
    act(() => { result.current.openDraft({ ...p2, version: 1 }); });
    act(() => { result.current.changeDraft('p2', { content: 'Моя правка' }); });
    updateClientNote.mockRejectedValueOnce(apiError(409));
    let out;
    await act(async () => { out = await result.current.update('p2'); });
    expect(out).toEqual({ ok: false, status: 409 });
    // reload заменил список первой страницей — строки p2 в нём нет, черновик жив
    await waitFor(() => expect(result.current.list.items.map(i => i.uuid)).toEqual(['p1']));
    const draft = result.current.drafts.p2;
    expect(draft.content).toBe('Моя правка');
    expect(draft.current.content).toBe('Чужая правка');
    expect(draft.baseVersion).toBe(2);
    expect(draft.error).toMatch(/Ваша правка сохранена/);

    // повторное сохранение — поверх актуальной версии
    updateClientNote.mockResolvedValueOnce({});
    await act(async () => { await result.current.update('p2'); });
    expect(updateClientNote).toHaveBeenLastCalledWith('c-1', 'p2', {
      content: 'Моя правка', noteType: 'general', version: 2,
    });
    expect(result.current.drafts.p2).toBeUndefined();
  });

  it('409, но актуальную версию загрузить не удалось: черновик остаётся, можно повторить загрузку', async () => {
    getClientNotes.mockResolvedValueOnce(page([note('n1')]));
    const { result } = renderHook(() => useClientNotes('c-1'));
    await waitFor(() => expect(result.current.status).toBe('ready'));
    act(() => { result.current.openDraft(result.current.list.items[0]); });
    act(() => { result.current.changeDraft('n1', { content: 'Правка' }); });
    updateClientNote.mockRejectedValueOnce(apiError(409));
    getClientNotes.mockRejectedValue(apiError(500));
    await act(async () => { await result.current.update('n1'); });
    expect(result.current.drafts.n1.content).toBe('Правка');
    expect(result.current.drafts.n1.needsRefresh).toBe(true);
    getClientNotes.mockReset();
    getClientNotes.mockResolvedValue(page([note('n1', { version: 3, content: 'Свежая' })]));
    await act(async () => { await result.current.refreshDraft('n1'); });
    expect(result.current.drafts.n1.current.content).toBe('Свежая');
    expect(result.current.drafts.n1.baseVersion).toBe(3);
    expect(result.current.drafts.n1.content).toBe('Правка');
  });

  it('размонтирование: успех create после unmount не перечитывает список и помечен stale', async () => {
    getClientNotes.mockResolvedValue(page([]));
    const { result, unmount } = renderHook(() => useClientNotes('c-1'));
    await waitFor(() => expect(result.current.status).toBe('ready'));
    const save = deferred();
    createClientNote.mockReturnValueOnce(save.promise);
    let pending;
    act(() => { pending = result.current.create({ content: 'a', noteType: 'general' }); });
    const calls = getClientNotes.mock.calls.length;
    unmount();
    let out;
    await act(async () => { save.resolve({}); out = await pending; });
    expect(out).toEqual({ ok: false, stale: true });
    expect(getClientNotes.mock.calls.length).toBe(calls);
  });

  it('A → B → A: ответы (успех и ошибка) старого запроса A не трогают новый контекст A', async () => {
    getClientNotes.mockResolvedValue(page([]));
    const { result, rerender } = renderHook(({ id }) => useClientNotes(id), { initialProps: { id: 'c-A' } });
    await waitFor(() => expect(result.current.status).toBe('ready'));
    const ok = deferred();
    const fail = deferred();
    createClientNote.mockReturnValueOnce(ok.promise);
    let first;
    act(() => { first = result.current.create({ content: 'a1', noteType: 'general' }); });
    rerender({ id: 'c-B' });
    rerender({ id: 'c-A' });
    await waitFor(() => expect(result.current.creating).toBe(false));
    await waitFor(() => expect(result.current.status).toBe('ready'));
    // новый контекст A может отправлять: блокировка старого запроса не мешает
    createClientNote.mockReturnValueOnce(fail.promise);
    let second;
    act(() => { second = result.current.create({ content: 'a2', noteType: 'general' }); });
    expect(result.current.creating).toBe(true);
    const calls = getClientNotes.mock.calls.length;
    let r1;
    await act(async () => { ok.resolve({}); r1 = await first; });
    expect(r1).toEqual({ ok: false, stale: true });
    expect(result.current.creating).toBe(true);           // старый успех не снял блокировку нового
    expect(getClientNotes.mock.calls.length).toBe(calls);
    let r2;
    await act(async () => { fail.reject(apiError(503)); r2 = await second; });
    expect(r2).toEqual({ ok: false, status: 503 });
    expect(result.current.createError).toMatch(/журнале/);
  });

  it('смена клиента во время сохранения: ответ прежнего клиента не трогает новое состояние', async () => {
    getClientNotes.mockResolvedValue(page([]));
    const { result, rerender } = renderHook(({ id }) => useClientNotes(id), {
      initialProps: { id: 'c-1' },
    });
    await waitFor(() => expect(result.current.status).toBe('ready'));
    const save = deferred();
    createClientNote.mockReturnValueOnce(save.promise);
    let pending;
    act(() => { pending = result.current.create({ content: 'Для A', noteType: 'general' }); });
    expect(result.current.creating).toBe(true);
    rerender({ id: 'c-2' });
    await waitFor(() => expect(result.current.creating).toBe(false));
    const callsAfterSwitch = getClientNotes.mock.calls.length;
    let out;
    await act(async () => { save.reject(apiError(503)); out = await pending; });
    expect(out).toEqual({ ok: false, stale: true });
    expect(result.current.createError).toBeNull();
    expect(getClientNotes.mock.calls.length).toBe(callsAfterSwitch);
    // новый клиент может сразу отправлять — блокировка прежнего снята
    createClientNote.mockResolvedValueOnce(note('b1'));
    await act(async () => {
      out = await result.current.create({ content: 'Для B', noteType: 'general' });
    });
    expect(out).toEqual({ ok: true });
    expect(createClientNote).toHaveBeenLastCalledWith('c-2', expect.objectContaining({ content: 'Для B' }));
  });

  it('запоздалый список прежнего клиента отбрасывается', async () => {
    const late = deferred();
    getClientNotes.mockImplementation((uuid) => (uuid === 'c-1' ? late.promise : Promise.resolve(page([note('b1')]))));
    const { result, rerender } = renderHook(({ id }) => useClientNotes(id), {
      initialProps: { id: 'c-1' },
    });
    rerender({ id: 'c-2' });
    await waitFor(() => expect(result.current.list.items.map(i => i.uuid)).toEqual(['b1']));
    await act(async () => { late.resolve(page([note('a1')])); });
    expect(result.current.list.items.map(i => i.uuid)).toEqual(['b1']);
  });
});
