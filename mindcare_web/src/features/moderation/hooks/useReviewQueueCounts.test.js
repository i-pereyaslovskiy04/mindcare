import { act, renderHook, waitFor } from '@testing-library/react';
import useReviewQueueCounts, { REVIEW_POLL_MS, reviewBadge } from './useReviewQueueCounts';
import { getReviewArticlesPendingCount } from '../../../api/articles.api';
import { getTestsPendingCount } from '../../../api/tests.api';
import { notifyReviewQueueChanged } from '../lib/reviewQueueEvents';

jest.mock('../../../api/articles.api', () => ({ getReviewArticlesPendingCount: jest.fn() }));
jest.mock('../../../api/tests.api', () => ({ getTestsPendingCount: jest.fn() }));

beforeEach(() => {
  jest.clearAllMocks();
  jest.useRealTimers();
});

test('загружает оба счётчика; enabled=false — без запросов и null', async () => {
  getReviewArticlesPendingCount.mockResolvedValue({ count: 2 });
  getTestsPendingCount.mockResolvedValue({ count: 7 });
  const { result, rerender } = renderHook(({ on }) => useReviewQueueCounts(on, 'u1'), {
    initialProps: { on: true },
  });
  await waitFor(() => expect(result.current).toEqual({ articles: 2, tests: 7 }));
  rerender({ on: false });
  expect(result.current).toEqual({ articles: null, tests: null });
});

test('ошибка не подменяет значение нулём; шина и опрос перечитывают', async () => {
  jest.useFakeTimers();
  getReviewArticlesPendingCount.mockResolvedValueOnce({ count: 3 })
    .mockRejectedValueOnce(new Error('network'))
    .mockResolvedValue({ count: 1 });
  getTestsPendingCount.mockRejectedValue(new Error('network'));
  const { result } = renderHook(() => useReviewQueueCounts(true, 'u1'));
  await waitFor(() => expect(result.current.articles).toBe(3));
  expect(result.current.tests).toBeNull();

  act(() => { notifyReviewQueueChanged(); });          // ошибка — остаётся 3
  await waitFor(() => expect(getReviewArticlesPendingCount).toHaveBeenCalledTimes(2));
  expect(result.current.articles).toBe(3);

  act(() => { jest.advanceTimersByTime(REVIEW_POLL_MS); });
  await waitFor(() => expect(result.current.articles).toBe(1));
});

test('reviewBadge: 99+ и точное число в подписи; ноль и неизвестно — без бейджа', () => {
  expect(reviewBadge(150)).toEqual({ badge: '99+', badgeLabel: 'ожидают проверки: 150' });
  expect(reviewBadge(4)).toEqual({ badge: '4', badgeLabel: 'ожидают проверки: 4' });
  expect(reviewBadge(0)).toEqual({});
  expect(reviewBadge(null)).toEqual({});
});
