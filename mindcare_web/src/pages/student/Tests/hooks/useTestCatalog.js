import { useState, useEffect, useCallback, useRef } from 'react';
import { getTests } from '../../../../api/tests.api';

const PAGE_SIZE = 12;

/**
 * Каталог активных тестов с серверным поиском и пагинацией («загрузить ещё»).
 * Возвращает плоский список (накопительно) + total/loading/error.
 */
export function useTestCatalog() {
  const [items, setItems]   = useState([]);
  const [total, setTotal]   = useState(0);
  const [page, setPage]     = useState(1);
  const [query, setQueryRaw] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(null);

  const reqId = useRef(0);

  useEffect(() => {
    const id = ++reqId.current;
    setLoading(true);
    setError(null);

    getTests({ page, size: PAGE_SIZE, search: query.trim() || undefined })
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
  }, [page, query]);

  const setQuery = useCallback((q) => {
    setQueryRaw(q);
    setPage(1);
  }, []);

  const hasMore = items.length < total;
  const loadMore = () => setPage((p) => p + 1);

  return { items, total, loading, error, query, setQuery, hasMore, loadMore };
}
