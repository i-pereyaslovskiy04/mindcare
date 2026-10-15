import { act, renderHook, waitFor } from '@testing-library/react';
import useUserContacts from './useUserContacts';
import { getUserContacts } from '../../../api/contacts.api';

jest.mock('../../../api/contacts.api');

const DATA = { primary_phone: '+79001234567', items: [], updated_at: null, catalog: null };
const apiError = (status) => Object.assign(new Error('x'), { status });

function deferred() {
  let resolve; let reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

describe('useUserContacts', () => {
  it('без uuid запросов нет', () => {
    const { result } = renderHook(() => useUserContacts(null));
    expect(result.current.status).toBe('idle');
    expect(getUserContacts).not.toHaveBeenCalled();
  });

  it('загружает контакты по uuid', async () => {
    getUserContacts.mockResolvedValue(DATA);
    const { result } = renderHook(() => useUserContacts('u-1'));
    expect(result.current.status).toBe('loading');
    await waitFor(() => expect(result.current.status).toBe('ready'));
    expect(result.current.data).toBe(DATA);
    expect(getUserContacts).toHaveBeenCalledWith('u-1');
  });

  it.each([
    [404, 'unavailable'],
    [403, 'forbidden'],
    [503, 'auditUnavailable'],
    [500, 'error'],
  ])('HTTP %s → %s без данных', async (status, expected) => {
    getUserContacts.mockRejectedValue(apiError(status));
    const { result } = renderHook(() => useUserContacts('u-1'));
    await waitFor(() => expect(result.current.status).toBe(expected));
    expect(result.current.data).toBeNull();
  });

  it('при смене uuid данные прежнего пользователя пропадают сразу', async () => {
    getUserContacts.mockResolvedValueOnce(DATA);
    const { result, rerender } = renderHook(({ id }) => useUserContacts(id), {
      initialProps: { id: 'u-1' },
    });
    await waitFor(() => expect(result.current.status).toBe('ready'));
    const pending = deferred();
    getUserContacts.mockReturnValueOnce(pending.promise);
    rerender({ id: 'u-2' });
    expect(result.current.status).toBe('loading');
    expect(result.current.data).toBeNull();
    await act(async () => { pending.resolve({ ...DATA, primary_phone: '+79990000000' }); });
    await waitFor(() => expect(result.current.data.primary_phone).toBe('+79990000000'));
  });

  it('запоздавший ответ прежнего uuid отбрасывается', async () => {
    const first = deferred();
    const second = deferred();
    getUserContacts.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
    const { result, rerender } = renderHook(({ id }) => useUserContacts(id), {
      initialProps: { id: 'u-1' },
    });
    rerender({ id: 'u-2' });
    await act(async () => { second.resolve({ ...DATA, primary_phone: '+70000000002' }); });
    await act(async () => { first.resolve({ ...DATA, primary_phone: '+70000000001' }); });
    await waitFor(() => expect(result.current.status).toBe('ready'));
    expect(result.current.data.primary_phone).toBe('+70000000002');
  });

  it('потеря доступа при повторной загрузке убирает данные', async () => {
    getUserContacts.mockResolvedValueOnce(DATA);
    const { result } = renderHook(() => useUserContacts('u-1'));
    await waitFor(() => expect(result.current.status).toBe('ready'));
    getUserContacts.mockRejectedValueOnce(apiError(404));
    await act(async () => { await result.current.refetch(); });
    expect(result.current.status).toBe('unavailable');
    expect(result.current.data).toBeNull();
  });
});
