import { act, renderHook, waitFor } from '@testing-library/react';
import { useAdminUsers, visibilityParams } from './useAdminUsers';
import { getUsers } from '../../../../api/users.api';

jest.mock('../../../../api/users.api', () => ({ getUsers: jest.fn() }));
// Без задержки debounce: поиск в этих тестах не проверяется.
jest.mock('../../../../hooks/useDebounce', () => ({ useDebounce: (v) => v }));

const user = (n) => ({ uuid: `u-${n}`, full_name: `U${n}` });

beforeEach(() => {
  jest.clearAllMocks();
  getUsers.mockResolvedValue({ items: [user(1)], total: 1 });
});

test('visibilityParams: существующие параметры API, смысл include_deleted не меняется', () => {
  expect(visibilityParams(false)).toEqual({ is_active: 'true', include_deleted: false });
  expect(visibilityParams(true)).toEqual({ is_active: '', include_deleted: true });
});

test('по умолчанию — только активные (is_active=true без include_deleted)', async () => {
  renderHook(() => useAdminUsers());
  await waitFor(() => expect(getUsers).toHaveBeenCalled());
  expect(getUsers).toHaveBeenLastCalledWith(expect.objectContaining({
    page: 1, is_active: 'true', include_deleted: false,
  }));
});

test('галочка включена — без ограничения is_active и с include_deleted; страница сбрасывается', async () => {
  getUsers.mockResolvedValue({ items: Array.from({ length: 20 }, (_, i) => user(i)), total: 60 });
  const { result } = renderHook(() => useAdminUsers());
  await waitFor(() => expect(result.current.loading).toBe(false));
  act(() => result.current.setPage(2));
  await waitFor(() => expect(getUsers).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 })));

  act(() => result.current.setFilters({ ...result.current.filters, showDisabled: true }));
  await waitFor(() => expect(getUsers).toHaveBeenLastCalledWith(expect.objectContaining({
    page: 1, is_active: '', include_deleted: true,
  })));
  expect(result.current.page).toBe(1);
});

test('опустевшая последняя страница после отключения → последняя существующая', async () => {
  getUsers.mockResolvedValue({ items: Array.from({ length: 20 }, (_, i) => user(i)), total: 41 });
  const { result } = renderHook(() => useAdminUsers());
  await waitFor(() => expect(result.current.loading).toBe(false));
  act(() => result.current.setPage(3));
  await waitFor(() => expect(result.current.loading).toBe(false));

  // Последнего пользователя на 3-й странице отключили: страница 3 пуста, total=40.
  getUsers.mockImplementation(({ page }) => Promise.resolve(
    page === 3 ? { items: [], total: 40 } : { items: [user(page)], total: 40 },
  ));
  act(() => result.current.refetch());
  await waitFor(() => expect(result.current.page).toBe(2));
  await waitFor(() => expect(result.current.items).toEqual([user(2)]));
  expect(result.current.total).toBe(40);
});

test('все записи исчезли (total=0) на странице > 1 → страница 1', async () => {
  getUsers.mockResolvedValue({ items: [user(1)], total: 50 });
  const { result } = renderHook(() => useAdminUsers());
  await waitFor(() => expect(result.current.loading).toBe(false));
  act(() => result.current.setPage(3));
  await waitFor(() => expect(result.current.loading).toBe(false));

  getUsers.mockResolvedValue({ items: [], total: 0 });
  act(() => result.current.refetch());
  await waitFor(() => expect(result.current.page).toBe(1));
  await waitFor(() => expect(result.current.loading).toBe(false));
  expect(result.current.items).toEqual([]);
  expect(result.current.total).toBe(0);
});
