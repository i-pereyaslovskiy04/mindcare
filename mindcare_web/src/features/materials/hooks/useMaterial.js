import { useCallback, useEffect, useRef, useState } from 'react';
import { getArticleById } from '../../../api/articles.api';

/**
 * Один опубликованный материал по uuid (публичный API /api/articles/{uuid}).
 *
 * status: 'loading' | 'ready' | 'notFound' | 'error'.
 * 404 — материал не опубликован, удалён или не существует (сервер их не
 * различает и скрытое содержимое не отдаёт); прочие сбои — 'error' с повтором.
 */
export function useMaterial(uuid) {
  const [state, setState] = useState({ status: 'loading', item: null, error: null });
  const [reloadKey, setReloadKey] = useState(0);
  const reqId = useRef(0);

  useEffect(() => {
    const id = ++reqId.current;
    if (!uuid) {
      setState({ status: 'notFound', item: null, error: null });
      return;
    }
    setState({ status: 'loading', item: null, error: null });
    getArticleById(uuid)
      .then(item => {
        if (id === reqId.current) setState({ status: 'ready', item, error: null });
      })
      .catch(err => {
        if (id !== reqId.current) return;
        if (err?.status === 404 || err?.status === 422) {
          setState({ status: 'notFound', item: null, error: null });
        } else {
          setState({
            status: 'error', item: null,
            error: err?.message || 'Не удалось загрузить материал',
          });
        }
      });
  }, [uuid, reloadKey]);

  const refetch = useCallback(() => setReloadKey(k => k + 1), []);

  return { ...state, refetch };
}
