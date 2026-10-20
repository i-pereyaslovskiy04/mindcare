import { useCallback, useEffect, useRef, useState } from 'react';
import { getAdminArticles } from '../../../../api/articles.api';
import { useDebounce } from '../../../../hooks/useDebounce';

export function useAdminArticles() {
  const [items, setItems]     = useState([]);
  const [total, setTotal]     = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState(null);
  const [page, setPage]       = useState(1);
  const [query, setQueryRaw]  = useState('');
  const [filters, setFilters] = useState({ is_published: null, category_id: null });

  const debouncedQuery = useDebounce(query, 300);
  const requestId = useRef(0);

  const fetch = useCallback(async (p, q, f) => {
    const id = ++requestId.current;
    setLoading(true);
    setError(null);
    try {
      const data = await getAdminArticles({
        page: p,
        size: 20,
        search: q || undefined,
        is_published: f.is_published,
        category_id: f.category_id || undefined,
      });
      if (id !== requestId.current) return;
      setItems(data.items);
      setTotal(data.total);
    } catch (err) {
      if (id !== requestId.current) return;
      setError(err.message);
    } finally {
      if (id === requestId.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetch(page, debouncedQuery, filters);
  }, [page, debouncedQuery, filters, fetch]);

  function setQuery(val) {
    setQueryRaw(val);
    setPage(1);
  }

  function updateFilters(next) {
    setFilters(prev => ({ ...prev, ...next }));
    setPage(1);
  }

  const refetch = () => fetch(page, debouncedQuery, filters);

  return {
    items, loading, error, total,
    page, setPage,
    query, setQuery,
    filters, setFilters: updateFilters,
    refetch,
  };
}
