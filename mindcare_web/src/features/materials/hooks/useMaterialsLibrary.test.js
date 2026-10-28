import { act, renderHook, waitFor } from '@testing-library/react';
import { useMaterialsLibrary } from './useMaterialsLibrary';
import { getArticles, getPublicCategories } from '../../../api/articles.api';

jest.mock('../../../api/articles.api');

const article = (n, extra = {}) => ({
  uuid: `uuid-${n}`,
  title: `Материал ${n}`,
  excerpt: `Описание ${n}`,
  published_at: '2026-10-01T09:00:00Z',
  created_at: '2026-09-30T09:00:00Z',
  cover_image_url: null,
  categories: [{ id: 3, name: 'Статья' }],
  tags: [{ uuid: 't1', name: 'Тревога' }],
  ...extra,
});

function deferred() {
  let resolve; let reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

beforeEach(() => {
  jest.clearAllMocks();
  getPublicCategories.mockResolvedValue([{ id: 3, name: 'Статья' }, { id: 4, name: 'Гид' }]);
});

describe('useMaterialsLibrary', () => {
  it('первая страница: серверные параметры и нормализация без времени чтения', async () => {
    getArticles.mockResolvedValue({ items: [article(1)], total: 1 });
    const { result } = renderHook(() => useMaterialsLibrary({ pageSize: 2 }));
    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(getArticles).toHaveBeenCalledWith({
      page: 1, size: 2, search: undefined, category_id: undefined,
    });
    expect(result.current.items).toEqual([{
      id: 'uuid-1',
      title: 'Материал 1',
      description: 'Описание 1',
      date: '1 октября 2026 г.',
      dateTime: '2026-10-01T09:00:00Z',
      image: null,
      category: 'Статья',
      topics: ['Тревога'],
    }]);
    expect(result.current.hasMore).toBe(false);
    await waitFor(() => expect(result.current.categoryOptions).toEqual([
      { value: 3, label: 'Статья' }, { value: 4, label: 'Гид' },
    ]));
  });

  it('поиск и категория уходят на сервер и сбрасывают страницу', async () => {
    getArticles.mockResolvedValue({ items: [article(1), article(2)], total: 4 });
    const { result } = renderHook(() => useMaterialsLibrary({ pageSize: 2 }));
    await waitFor(() => expect(result.current.loading).toBe(false));

    act(() => result.current.loadMore());
    await waitFor(() => expect(getArticles).toHaveBeenLastCalledWith(
      expect.objectContaining({ page: 2 }),
    ));
    await waitFor(() => expect(result.current.loading).toBe(false));

    act(() => result.current.setQuery('  сон '));
    await waitFor(() => expect(getArticles).toHaveBeenLastCalledWith({
      page: 1, size: 2, search: 'сон', category_id: undefined,
    }));
    await waitFor(() => expect(result.current.loading).toBe(false));

    act(() => result.current.setCategory(4));
    await waitFor(() => expect(getArticles).toHaveBeenLastCalledWith({
      page: 1, size: 2, search: 'сон', category_id: 4,
    }));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.category).toBe(4);
  });

  it('«Загрузить ещё» дополняет список, hasMore — по total сервера', async () => {
    getArticles
      .mockResolvedValueOnce({ items: [article(1), article(2)], total: 3 })
      .mockResolvedValueOnce({ items: [article(3)], total: 3 });
    const { result } = renderHook(() => useMaterialsLibrary({ pageSize: 2 }));
    await waitFor(() => expect(result.current.items).toHaveLength(2));
    expect(result.current.hasMore).toBe(true);

    act(() => result.current.loadMore());
    await waitFor(() => expect(result.current.items).toHaveLength(3));
    expect(result.current.items.map(i => i.id)).toEqual(['uuid-1', 'uuid-2', 'uuid-3']);
    expect(result.current.hasMore).toBe(false);
  });

  it('запоздавший ответ прежнего запроса отбрасывается', async () => {
    const slow = deferred();
    getArticles
      .mockReturnValueOnce(slow.promise)
      .mockResolvedValueOnce({ items: [article(9)], total: 1 });
    const { result } = renderHook(() => useMaterialsLibrary());

    act(() => result.current.setQuery('новый'));
    await waitFor(() => expect(result.current.items.map(i => i.id)).toEqual(['uuid-9']));
    await act(async () => { slow.resolve({ items: [article(1)], total: 1 }); });
    expect(result.current.items.map(i => i.id)).toEqual(['uuid-9']);
  });

  it('ошибка → error; refetch повторяет ту же страницу', async () => {
    getArticles
      .mockRejectedValueOnce(new Error('Network down'))
      .mockResolvedValueOnce({ items: [article(1)], total: 1 });
    const { result } = renderHook(() => useMaterialsLibrary());
    await waitFor(() => expect(result.current.error).toBe('Network down'));
    expect(result.current.items).toEqual([]);

    act(() => result.current.refetch());
    await waitFor(() => expect(result.current.items).toHaveLength(1));
    expect(result.current.error).toBeNull();
    expect(getArticles).toHaveBeenCalledTimes(2);
    expect(getArticles.mock.calls[1][0]).toEqual(expect.objectContaining({ page: 1 }));
  });

  it('сбой загрузки категорий: фильтра нет, список работает', async () => {
    getPublicCategories.mockRejectedValue(new Error('x'));
    getArticles.mockResolvedValue({ items: [article(1)], total: 1 });
    const { result } = renderHook(() => useMaterialsLibrary());
    await waitFor(() => expect(result.current.items).toHaveLength(1));
    expect(result.current.categoryOptions).toEqual([]);
  });

  it('повтор того же запроса (в т.ч. после trim) и той же категории не очищает список', async () => {
    getArticles.mockResolvedValue({ items: [article(1), article(2)], total: 4 });
    const { result } = renderHook(() => useMaterialsLibrary({ pageSize: 2 }));
    await waitFor(() => expect(result.current.items).toHaveLength(2));

    act(() => result.current.setQuery('сон'));
    await waitFor(() => expect(result.current.loading).toBe(false));
    act(() => result.current.loadMore());
    await waitFor(() => expect(result.current.items).toHaveLength(4));
    const calls = getArticles.mock.calls.length;

    act(() => result.current.setQuery('сон'));
    act(() => result.current.setQuery('  сон '));
    act(() => result.current.setCategory(null));
    expect(result.current.items).toHaveLength(4);       // ничего не очищено
    expect(result.current.loading).toBe(false);
    expect(getArticles).toHaveBeenCalledTimes(calls);    // и ничего не запрошено

    act(() => result.current.setCategory(3));
    await waitFor(() => expect(result.current.loading).toBe(false));
    const afterCategory = getArticles.mock.calls.length;
    act(() => result.current.setCategory(3));
    expect(result.current.items).toHaveLength(2);
    expect(getArticles).toHaveBeenCalledTimes(afterCategory);
  });
});

