import { act, renderHook } from '@testing-library/react';
import usePendingVerificationsCount, { PENDING_POLL_MS } from './usePendingVerificationsCount';
import { getPendingVerificationsCount } from '../../../api/studentVerification.api';
import { notifyVerificationsChanged } from '../lib/verificationEvents';

jest.mock('../../../api/studentVerification.api', () => ({
  getPendingVerificationsCount: jest.fn(),
}));

let visibility = 'visible';

beforeAll(() => {
  Object.defineProperty(document, 'visibilityState', {
    configurable: true,
    get: () => visibility,
  });
});

beforeEach(() => {
  jest.useFakeTimers();
  jest.clearAllMocks();
  visibility = 'visible';
  getPendingVerificationsCount.mockResolvedValue({ count: 3 });
});

afterEach(() => {
  jest.useRealTimers();
});

async function flush() {
  await act(async () => { await Promise.resolve(); });
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

test('загружает число при монтировании', async () => {
  const { result } = renderHook(() => usePendingVerificationsCount(true, 1));
  expect(result.current).toBeNull();               // неизвестно до ответа
  await flush();
  expect(result.current).toBe(3);
  expect(getPendingVerificationsCount).toHaveBeenCalledTimes(1);
});

test('опрос каждые 30 с при видимой вкладке; при скрытой тик пропускается', async () => {
  renderHook(() => usePendingVerificationsCount(true, 1));
  await flush();
  await act(async () => { jest.advanceTimersByTime(PENDING_POLL_MS); });
  expect(getPendingVerificationsCount).toHaveBeenCalledTimes(2);

  visibility = 'hidden';
  await act(async () => { jest.advanceTimersByTime(PENDING_POLL_MS * 3); });
  expect(getPendingVerificationsCount).toHaveBeenCalledTimes(2);
});

test('обновляется при возвращении на вкладку и по сигналу после решения', async () => {
  const { result } = renderHook(() => usePendingVerificationsCount(true, 1));
  await flush();
  visibility = 'hidden';
  act(() => { document.dispatchEvent(new Event('visibilitychange')); });
  expect(getPendingVerificationsCount).toHaveBeenCalledTimes(1);

  visibility = 'visible';
  getPendingVerificationsCount.mockResolvedValue({ count: 2 });
  act(() => { document.dispatchEvent(new Event('visibilitychange')); });
  await flush();
  expect(result.current).toBe(2);

  getPendingVerificationsCount.mockResolvedValue({ count: 1 });
  act(() => { notifyVerificationsChanged(); });
  await flush();
  expect(result.current).toBe(1);
  expect(getPendingVerificationsCount).toHaveBeenCalledTimes(3);
});

test('устаревший ответ отбрасывается', async () => {
  const slow = deferred();
  const fast = deferred();
  getPendingVerificationsCount
    .mockReturnValueOnce(slow.promise)
    .mockReturnValueOnce(fast.promise);
  const { result } = renderHook(() => usePendingVerificationsCount(true, 1));
  act(() => { notifyVerificationsChanged(); });
  await act(async () => { fast.resolve({ count: 5 }); });
  expect(result.current).toBe(5);
  await act(async () => { slow.resolve({ count: 9 }); });
  expect(result.current).toBe(5);
});

test('ошибка не подменяет неизвестное значение нулём и не стирает известное', async () => {
  getPendingVerificationsCount.mockRejectedValueOnce(new Error('network'));
  const { result } = renderHook(() => usePendingVerificationsCount(true, 1));
  await flush();
  expect(result.current).toBeNull();

  getPendingVerificationsCount.mockResolvedValueOnce({ count: 4 });
  await act(async () => { jest.advanceTimersByTime(PENDING_POLL_MS); });
  expect(result.current).toBe(4);

  getPendingVerificationsCount.mockRejectedValueOnce(new Error('503'));
  await act(async () => { jest.advanceTimersByTime(PENDING_POLL_MS); });
  expect(result.current).toBe(4);
});

test('ноль — число 0 (бейдж решает показывать ли), некорректный ответ игнорируется', async () => {
  getPendingVerificationsCount.mockResolvedValueOnce({ count: 'x' });
  const { result } = renderHook(() => usePendingVerificationsCount(true, 1));
  await flush();
  expect(result.current).toBeNull();
  getPendingVerificationsCount.mockResolvedValueOnce({ count: 0 });
  act(() => { notifyVerificationsChanged(); });
  await flush();
  expect(result.current).toBe(0);
});

test('enabled=false — запросов нет', async () => {
  const { result } = renderHook(() => usePendingVerificationsCount(false, 1));
  await act(async () => { jest.advanceTimersByTime(PENDING_POLL_MS * 2); });
  act(() => { notifyVerificationsChanged(); });
  expect(getPendingVerificationsCount).not.toHaveBeenCalled();
  expect(result.current).toBeNull();
});

test('выключение (impersonation/выход) и unmount останавливают опрос', async () => {
  const { result, rerender, unmount } = renderHook(
    ({ enabled }) => usePendingVerificationsCount(enabled, 1),
    { initialProps: { enabled: true } },
  );
  await flush();
  expect(result.current).toBe(3);
  rerender({ enabled: false });
  expect(result.current).toBeNull();
  await act(async () => { jest.advanceTimersByTime(PENDING_POLL_MS * 2); });
  expect(getPendingVerificationsCount).toHaveBeenCalledTimes(1);

  rerender({ enabled: true });
  await flush();
  expect(getPendingVerificationsCount).toHaveBeenCalledTimes(2);
  unmount();
  await act(async () => { jest.advanceTimersByTime(PENDING_POLL_MS * 2); });
  act(() => { notifyVerificationsChanged(); });
  act(() => { document.dispatchEvent(new Event('visibilitychange')); });
  expect(getPendingVerificationsCount).toHaveBeenCalledTimes(2);
});

test('ответ, пришедший после unmount, не применяется', async () => {
  const pending = deferred();
  getPendingVerificationsCount.mockReturnValueOnce(pending.promise);
  const { result, unmount } = renderHook(() => usePendingVerificationsCount(true, 1));
  unmount();
  await act(async () => { pending.resolve({ count: 7 }); });
  expect(result.current).toBeNull();
});
