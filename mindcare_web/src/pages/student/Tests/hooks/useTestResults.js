import { useState, useEffect, useCallback, useRef } from 'react';
import { getTestResults } from '../../../../api/tests.api';

/**
 * История пройденных тестов студента (накопительная пагинация).
 *
 * @param {number} size — размер страницы; для дашборда передаётся маленький (последние N).
 */
export function useTestResults(size = 20) {
  const [items, setItems]   = useState([]);
  const [total, setTotal]   = useState(0);
  const [page, setPage]     = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(null);

  const reqId = useRef(0);

  const load = useCallback(() => {
    const id = ++reqId.current;
    setLoading(true);
    setError(null);

    getTestResults({ page, size })
      .then((data) => {
        if (id !== reqId.current) return;
        const next = data.items || [];
        setItems((prev) => (page === 1 ? next : [...prev, ...next]));
        setTotal(data.total ?? 0);
      })
      .catch((err) => {
        if (id !== reqId.current) return;
        setError(err.message);
      })
      .finally(() => {
        if (id !== reqId.current) return;
        setLoading(false);
      });
  }, [page, size]);

  useEffect(() => { load(); }, [load]);

  const hasMore = items.length < total;
  const loadMore = () => setPage((p) => p + 1);

  return { items, total, loading, error, hasMore, loadMore };
}
