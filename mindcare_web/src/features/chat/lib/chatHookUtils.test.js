import {
  HISTORY_LIMIT,
  LIST_PAGE_SIZE,
  POLL_LIST_MS,
  POLL_MESSAGES_MS,
  SNAPSHOT_LIMIT,
  STATUS_FALLBACK,
  errText,
} from './chatHookUtils';

test('exports chat hook timing and paging constants', () => {
  expect(POLL_MESSAGES_MS).toBe(8000);
  expect(POLL_LIST_MS).toBe(30000);
  expect(LIST_PAGE_SIZE).toBe(100);
  expect(HISTORY_LIMIT).toBe(100);
  expect(SNAPSHOT_LIMIT).toBe(50);
});

test('errText returns fallback for empty error or unknown status', () => {
  expect(errText(null, 'fallback')).toBe('fallback');
  expect(errText(undefined, 'fallback')).toBe('fallback');
  expect(errText({ status: 500, message: 'HTTP 500' }, 'fallback')).toBe('fallback');
});

test('errText returns mapped fallback for known raw HTTP statuses', () => {
  expect(errText({ status: 403, message: 'HTTP 403' }, 'fallback')).toBe(STATUS_FALLBACK[403]);
  expect(errText({ status: 404, message: 'HTTP 404' }, 'fallback')).toBe(STATUS_FALLBACK[404]);
  expect(errText({ status: 409, message: 'HTTP 409' }, 'fallback')).toBe(STATUS_FALLBACK[409]);
  expect(errText({ status: 429, message: 'HTTP 429' }, 'fallback')).toBe(STATUS_FALLBACK[429]);
});
