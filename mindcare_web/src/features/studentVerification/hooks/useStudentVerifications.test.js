import { act, renderHook, waitFor } from '@testing-library/react';
import useStudentVerifications from './useStudentVerifications';
import { getStudentVerifications } from '../../../api/studentVerification.api';

jest.mock('../../../api/studentVerification.api', () => ({
  getStudentVerifications: jest.fn(),
}));

const rows = (n, offset = 0) => Array.from({ length: n }, (_, i) => ({ uuid: `r-${offset + i}` }));

/** Каждый вызов API — отдельный отложенный Promise. */
function deferredServer() {
  const calls = [];
  getStudentVerifications.mockImplementation(({ page }) => new Promise((resolve, reject) => {
    calls.push({
      page,
      respond: (items, total) => act(async () => { resolve({ items, total }); }),
      fail: (message) => act(async () => { reject(new Error(message)); }),
    });
  }));
  return calls;
}

async function loaded(calls, items = rows(20), total = 60) {
  const view = renderHook(() => useStudentVerifications(true));
  await waitFor(() => expect(calls).toHaveLength(1));
  await calls[0].respond(items, total);
  await waitFor(() => expect(view.result.current.pageLoading).toBe(false));
  return view;
}

beforeEach(() => {
  jest.clearAllMocks();
});

test('запрашивает только pending по 20, без поиска', async () => {
  const calls = deferredServer();
  await loaded(calls);
  expect(getStudentVerifications).toHaveBeenCalledWith({ page: 1, size: 20, status: 'pending' });
});

test('до первого ответа строк нет и pageLoading=true', async () => {
  const calls = deferredServer();
  const { result } = renderHook(() => useStudentVerifications(true));
  expect(result.current.pageLoading).toBe(true);
  expect(result.current.items).toEqual([]);
  await waitFor(() => expect(calls).toHaveLength(1));
});

test('смена страницы: page меняется сразу, строки прежней страницы не выдаются за новые', async () => {
  const calls = deferredServer();
  const { result } = await loaded(calls);
  expect(result.current.items).toHaveLength(20);

  act(() => result.current.setPage(2));
  // Сразу после смены страницы (до ответа) — уже пусто и «идёт загрузка».
  expect(result.current.page).toBe(2);
  expect(result.current.items).toEqual([]);
  expect(result.current.pageLoading).toBe(true);
  await waitFor(() => expect(calls).toHaveLength(2));
  expect(result.current.items).toEqual([]);
  expect(result.current.loading).toBe(true);

  await calls[1].respond(rows(20, 20), 60);
  expect(result.current.items.map((i) => i.uuid)[0]).toBe('r-20');
  expect(result.current.pageLoading).toBe(false);
  expect(result.current.loading).toBe(false);
});

test('refetch той же страницы строки не скрывает', async () => {
  const calls = deferredServer();
  const { result } = await loaded(calls);
  act(() => { result.current.refetch(); });
  await waitFor(() => expect(calls).toHaveLength(2));
  expect(result.current.items).toHaveLength(20);
  expect(result.current.pageLoading).toBe(false);
  expect(result.current.loading).toBe(true);
  await calls[1].respond(rows(19), 59);
  expect(result.current.items).toHaveLength(19);
  expect(result.current.total).toBe(59);
});

test('устаревший ответ (раньше пришёл ответ более новой страницы) отбрасывается', async () => {
  const calls = deferredServer();
  const { result } = await loaded(calls);

  act(() => result.current.setPage(2));
  await waitFor(() => expect(calls).toHaveLength(2));
  act(() => result.current.setPage(3));
  await waitFor(() => expect(calls).toHaveLength(3));

  await calls[2].respond(rows(20, 40), 60);                  // страница 3
  expect(result.current.items[0].uuid).toBe('r-40');
  await calls[1].respond(rows(20, 20), 60);                  // запоздавшая страница 2
  expect(result.current.page).toBe(3);
  expect(result.current.items[0].uuid).toBe('r-40');
  expect(result.current.pageLoading).toBe(false);
});

test('пустая страница > 1: строки сброшены, загрузка существующей страницы, затем её строки', async () => {
  const calls = deferredServer();
  const { result } = await loaded(calls);
  act(() => result.current.setPage(3));
  await waitFor(() => expect(calls).toHaveLength(2));
  await calls[1].respond([], 40);                            // страница 3 пуста, total=40

  await waitFor(() => expect(calls).toHaveLength(3));
  expect(calls[2].page).toBe(2);
  expect(result.current.page).toBe(2);
  expect(result.current.items).toEqual([]);
  expect(result.current.pageLoading).toBe(true);
  expect(result.current.total).toBe(40);

  await calls[2].respond(rows(20, 20), 40);
  expect(result.current.items).toHaveLength(20);
  expect(result.current.pageLoading).toBe(false);
});

test('возврат на уже загруженную страницу после пустого ответа не показывает её устаревшие строки', async () => {
  const calls = deferredServer();
  const { result } = await loaded(calls);
  act(() => result.current.setPage(2));
  await waitFor(() => expect(calls).toHaveLength(2));
  await calls[1].respond(rows(20, 20), 60);
  act(() => result.current.setPage(3));
  await waitFor(() => expect(calls).toHaveLength(3));
  await calls[2].respond([], 40);                            // 3 пуста → назад на 2

  await waitFor(() => expect(calls).toHaveLength(4));
  expect(calls[3].page).toBe(2);
  expect(result.current.items).toEqual([]);                  // прежние строки 2-й страницы устарели
  expect(result.current.pageLoading).toBe(true);
  await calls[3].respond(rows(20, 20), 40);
  expect(result.current.items).toHaveLength(20);
});

test('total=0 на странице > 1 → страница 1, затем пустая очередь', async () => {
  const calls = deferredServer();
  const { result } = await loaded(calls);
  act(() => result.current.setPage(4));
  await waitFor(() => expect(calls).toHaveLength(2));
  await calls[1].respond([], 0);

  await waitFor(() => expect(calls).toHaveLength(3));
  expect(calls[2].page).toBe(1);
  expect(result.current.pageLoading).toBe(true);
  await calls[2].respond([], 0);
  expect(result.current.page).toBe(1);
  expect(result.current.items).toEqual([]);
  expect(result.current.total).toBe(0);
  expect(result.current.pageLoading).toBe(false);
  expect(result.current.loading).toBe(false);
});

test('ошибка принадлежит странице, на которой возникла; на другой странице её нет', async () => {
  const calls = deferredServer();
  const { result } = await loaded(calls);
  act(() => result.current.setPage(2));
  await waitFor(() => expect(calls).toHaveLength(2));
  await calls[1].fail('Сервер недоступен');

  expect(result.current.error).toBe('Сервер недоступен');
  expect(result.current.items).toEqual([]);
  expect(result.current.pageLoading).toBe(false);            // не «вечная загрузка»

  act(() => result.current.setPage(1));
  expect(result.current.error).toBeNull();                   // чужая ошибка не прилипает
  await waitFor(() => expect(calls).toHaveLength(3));
  await calls[2].respond(rows(20), 60);
  expect(result.current.items).toHaveLength(20);
});

test('enabled=false — запросов нет и «загрузки» нет', async () => {
  const { result } = renderHook(() => useStudentVerifications(false));
  expect(getStudentVerifications).not.toHaveBeenCalled();
  expect(result.current.pageLoading).toBe(false);
  expect(result.current.items).toEqual([]);
});
