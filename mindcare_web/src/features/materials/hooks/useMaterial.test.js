import { act, renderHook, waitFor } from '@testing-library/react';
import { useMaterial } from './useMaterial';
import { getArticleById } from '../../../api/articles.api';

jest.mock('../../../api/articles.api');

const apiError = (status, message = 'x') => Object.assign(new Error(message), { status });

beforeEach(() => jest.clearAllMocks());

describe('useMaterial', () => {
  it('загружает материал по uuid', async () => {
    getArticleById.mockResolvedValue({ uuid: 'a-1', title: 'T' });
    const { result } = renderHook(() => useMaterial('a-1'));
    expect(result.current.status).toBe('loading');
    await waitFor(() => expect(result.current.status).toBe('ready'));
    expect(result.current.item).toEqual({ uuid: 'a-1', title: 'T' });
    expect(getArticleById).toHaveBeenCalledWith('a-1');
  });

  it('404 → notFound (снят с публикации, удалён или не существует)', async () => {
    getArticleById.mockRejectedValue(apiError(404));
    const { result } = renderHook(() => useMaterial('a-1'));
    await waitFor(() => expect(result.current.status).toBe('notFound'));
    expect(result.current.item).toBeNull();
  });

  it('сетевой сбой → error, refetch повторяет запрос', async () => {
    getArticleById
      .mockRejectedValueOnce(apiError(undefined, 'Failed to fetch'))
      .mockResolvedValueOnce({ uuid: 'a-1', title: 'T' });
    const { result } = renderHook(() => useMaterial('a-1'));
    await waitFor(() => expect(result.current.status).toBe('error'));

    act(() => result.current.refetch());
    await waitFor(() => expect(result.current.status).toBe('ready'));
    expect(getArticleById).toHaveBeenCalledTimes(2);
  });

  it('без uuid запроса нет', () => {
    const { result } = renderHook(() => useMaterial(undefined));
    expect(result.current.status).toBe('notFound');
    expect(getArticleById).not.toHaveBeenCalled();
  });
});
