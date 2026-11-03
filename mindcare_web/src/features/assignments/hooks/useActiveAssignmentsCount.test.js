import { act, renderHook } from '@testing-library/react';
import useActiveAssignmentsCount, { ASSIGNMENTS_POLL_MS } from './useActiveAssignmentsCount';
import { getMyAssignmentsSummary } from '../../../api/assignments.api';
import { notifyAssignmentsChanged } from '../lib/assignmentEvents';

jest.mock('../../../api/assignments.api', () => ({
  getMyAssignmentsSummary: jest.fn(),
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
  getMyAssignmentsSummary.mockResolvedValue({ open_count: 2, completed_count: 1, total_count: 4 });
});

afterEach(() => {
  jest.useRealTimers();
});

async function flush() {
  await act(async () => { await Promise.resolve(); });
}

test('бейдж — доступные активные задания (open_count), не все задания', async () => {
  const { result } = renderHook(() => useActiveAssignmentsCount(true, 1));
  expect(result.current).toBeNull();
  await flush();
  expect(result.current).toBe(2);
});

test('опрос раз в 30 с только при видимой вкладке', async () => {
  renderHook(() => useActiveAssignmentsCount(true, 1));
  await flush();
  await act(async () => { jest.advanceTimersByTime(ASSIGNMENTS_POLL_MS); });
  expect(getMyAssignmentsSummary).toHaveBeenCalledTimes(2);
  visibility = 'hidden';
  await act(async () => { jest.advanceTimersByTime(ASSIGNMENTS_POLL_MS * 2); });
  expect(getMyAssignmentsSummary).toHaveBeenCalledTimes(2);
});

test('обновляется сразу после выполнения задания (шина событий)', async () => {
  const { result } = renderHook(() => useActiveAssignmentsCount(true, 1));
  await flush();
  getMyAssignmentsSummary.mockResolvedValue({ open_count: 1, completed_count: 2, total_count: 4 });
  act(() => { notifyAssignmentsChanged(); });
  await flush();
  expect(result.current).toBe(1);
});

test('ошибка не превращается в 0: остаётся последнее известное значение', async () => {
  const { result } = renderHook(() => useActiveAssignmentsCount(true, 1));
  await flush();
  getMyAssignmentsSummary.mockRejectedValue(new Error('down'));
  await act(async () => { jest.advanceTimersByTime(ASSIGNMENTS_POLL_MS); });
  await flush();
  expect(result.current).toBe(2);
});

test('enabled=false (impersonation / нет роли) — запросов нет', async () => {
  const { result } = renderHook(() => useActiveAssignmentsCount(false, 1));
  await flush();
  expect(result.current).toBeNull();
  expect(getMyAssignmentsSummary).not.toHaveBeenCalled();
});
