import { StrictMode } from 'react';
import { act, renderHook, waitFor } from '@testing-library/react';
import useAllowedEmailDomains from './useAllowedEmailDomains';
import * as domainsApi from '../../../api/domains.api';

// emailDomainNamesOf остаётся настоящим (requireActual): автомок вернул бы undefined.
jest.mock('../../../api/domains.api', () => ({
  ...jest.requireActual('../../../api/domains.api'),
  getPublicEmailDomains: jest.fn(),
}));

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

// Макрозадача: к этому моменту отработала вся цепочка then/catch/finally.
const flush = () => new Promise((resolve) => { setTimeout(resolve, 0); });

test('загружает домены из ответа backend', async () => {
  domainsApi.getPublicEmailDomains.mockResolvedValue({ domains: ['a.example', 'b.example'] });
  const { result } = renderHook(() => useAllowedEmailDomains());

  expect(result.current.data).toEqual([]);
  expect(result.current.loading).toBe(true);
  await waitFor(() => expect(result.current.loading).toBe(false));
  expect(result.current.data).toEqual(['a.example', 'b.example']);
  expect(result.current.error).toBeNull();
  expect(domainsApi.getPublicEmailDomains).toHaveBeenCalledTimes(1);
});

test('ошибка запроса: пустой список и сообщение, исключение наружу не летит', async () => {
  domainsApi.getPublicEmailDomains.mockRejectedValue(new Error('network down'));
  const { result } = renderHook(() => useAllowedEmailDomains());

  await waitFor(() => expect(result.current.loading).toBe(false));
  expect(result.current.data).toEqual([]);
  expect(result.current.error).toBe('network down');
});

test('ошибка без текста получает безопасное сообщение по умолчанию', async () => {
  domainsApi.getPublicEmailDomains.mockRejectedValue({});
  const { result } = renderHook(() => useAllowedEmailDomains());

  await waitFor(() => expect(result.current.loading).toBe(false));
  expect(result.current.error).toBe('Не удалось загрузить список разрешённых доменов');
});

test.each([
  [{ domains: 'a.example' }],
  [{ domains: [null, 5, ''] }],
  [{}],
  [null],
])('мусор в ответе %j → пустой список', async (response) => {
  domainsApi.getPublicEmailDomains.mockResolvedValue(response);
  const { result } = renderHook(() => useAllowedEmailDomains());

  await waitFor(() => expect(result.current.loading).toBe(false));
  expect(result.current.data).toEqual([]);
  expect(result.current.error).toBeNull();
});

test('refetch перечитывает список', async () => {
  domainsApi.getPublicEmailDomains
    .mockResolvedValueOnce({ domains: ['a.example', 'b.example'] })
    .mockResolvedValueOnce({ domains: ['b.example'] });
  const { result } = renderHook(() => useAllowedEmailDomains());
  await waitFor(() => expect(result.current.data).toEqual(['a.example', 'b.example']));

  await act(async () => { await result.current.refetch(); });
  expect(result.current.data).toEqual(['b.example']);
  expect(domainsApi.getPublicEmailDomains).toHaveBeenCalledTimes(2);
});

describe('запоздавшие ответы не перезаписывают более свежее состояние', () => {
  test('старый запрос, ответивший ПОСЛЕ свежего, не перезаписывает список', async () => {
    const first = deferred();
    const second = deferred();
    domainsApi.getPublicEmailDomains
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);

    const { result } = renderHook(() => useAllowedEmailDomains());
    act(() => { result.current.refetch(); });             // второй, более свежий запрос
    expect(domainsApi.getPublicEmailDomains).toHaveBeenCalledTimes(2);

    await act(async () => { second.resolve({ domains: ['new.example'] }); await flush(); });
    expect(result.current.data).toEqual(['new.example']);
    expect(result.current.loading).toBe(false);

    await act(async () => { first.resolve({ domains: ['old.example'] }); await flush(); });
    expect(result.current.data).toEqual(['new.example']);  // запоздавший ответ проигнорирован
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
  });

  test('старая ошибка после свежего успеха не очищает список и не ставит ошибку', async () => {
    const first = deferred();
    const second = deferred();
    domainsApi.getPublicEmailDomains
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);

    const { result } = renderHook(() => useAllowedEmailDomains());
    act(() => { result.current.refetch(); });

    await act(async () => { second.resolve({ domains: ['new.example'] }); await flush(); });
    await act(async () => { first.reject(new Error('stale failure')); await flush(); });

    expect(result.current.data).toEqual(['new.example']);
    expect(result.current.error).toBeNull();
    expect(result.current.loading).toBe(false);
  });

  test('пока свежий запрос в полёте, ответ старого ничего не меняет (включая loading)', async () => {
    const first = deferred();
    const second = deferred();
    domainsApi.getPublicEmailDomains
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);

    const { result } = renderHook(() => useAllowedEmailDomains());
    act(() => { result.current.refetch(); });

    await act(async () => { first.resolve({ domains: ['old.example'] }); await flush(); });
    expect(result.current.data).toEqual([]);              // свежий ещё не ответил
    expect(result.current.loading).toBe(true);

    await act(async () => { second.resolve({ domains: ['new.example'] }); await flush(); });
    expect(result.current.data).toEqual(['new.example']);
    expect(result.current.loading).toBe(false);
  });

  test('ошибка свежего запроса убирает список: устаревшие домены не показываем', async () => {
    domainsApi.getPublicEmailDomains
      .mockResolvedValueOnce({ domains: ['a.example'] })
      .mockRejectedValueOnce(new Error('boom'));
    const { result } = renderHook(() => useAllowedEmailDomains());
    await waitFor(() => expect(result.current.data).toEqual(['a.example']));

    await act(async () => { await result.current.refetch(); });
    expect(result.current.data).toEqual([]);
    expect(result.current.error).toBe('boom');
  });

  test('StrictMode (двойной запуск эффекта): запрос первого запуска не перезаписывает второй', async () => {
    const first = deferred();
    const second = deferred();
    domainsApi.getPublicEmailDomains
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);

    const { result } = renderHook(() => useAllowedEmailDomains(), { wrapper: StrictMode });
    expect(domainsApi.getPublicEmailDomains).toHaveBeenCalledTimes(2);

    await act(async () => { second.resolve({ domains: ['fresh.example'] }); await flush(); });
    await act(async () => { first.resolve({ domains: ['stale.example'] }); await flush(); });

    expect(result.current.data).toEqual(['fresh.example']);
  });
});

test('ответ после размонтирования не применяется и ничего не ломает', async () => {
  const pending = deferred();
  domainsApi.getPublicEmailDomains.mockReturnValue(pending.promise);
  const errorSpy = jest.spyOn(console, 'error').mockImplementation(() => {});

  const { unmount } = renderHook(() => useAllowedEmailDomains());
  unmount();
  await act(async () => { pending.resolve({ domains: ['late.example'] }); await flush(); });

  expect(errorSpy).not.toHaveBeenCalled();
  errorSpy.mockRestore();
});
