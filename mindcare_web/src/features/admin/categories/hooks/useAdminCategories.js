import { useCallback, useEffect, useRef, useState } from 'react';
import { getAdminCategories } from '../../../../api/categories.api';
import { useDebounce } from '../../../../hooks/useDebounce';

export const CATEGORIES_PAGE_SIZE = 50;

export function useAdminCategories() {
  const [items, setItems]     = useState([]);
  const [total, setTotal]     = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState(null);
  const [page, setPage]       = useState(1);
  const [query, setQueryRaw]  = useState('');
  const [filters, setFilters] = useState({ is_active: null });

  const debouncedQuery = useDebounce(query, 300);

  // requestId защищает от race condition: если быстро меняем search/page,
  // только последний запрос обновляет state — устаревшие ответы игнорируются.
  const requestId = useRef(0);

  const fetch = useCallback(async (p, q, f) => {
    const id = ++requestId.current;
    setLoading(true);
    setError(null);
    try {
      const data = await getAdminCategories({
        page: p,
        size: CATEGORIES_PAGE_SIZE,
        search: q || undefined,
        is_active: f.is_active,
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
    setPage(1); // сброс на первую страницу при новом поиске
  }

  function updateFilters(next) {
    setFilters(prev => ({ ...prev, ...next }));
    setPage(1); // сброс на первую страницу при смене фильтра
  }

  const refetch = () => fetch(page, debouncedQuery, filters);

  return {
    items, loading, error, total,
    page, setPage,
    size: CATEGORIES_PAGE_SIZE,
    query, setQuery,
    filters, setFilters: updateFilters,
    refetch,
  };
}
