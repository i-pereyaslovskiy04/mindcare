import { useCallback, useEffect, useRef, useState } from 'react';
import { getMyTests } from '../../../api/tests.api';
import { useDebounce } from '../../../hooks/useDebounce';

/**
 * Список СВОИХ тестов психолога (Этап F2) — все статусы, без is_active-фильтра
 * (он не имеет значения для психолога: видимость решает публикация). Отдельный
 * от useAdminTests лёгкий хук — не обобщение admin-пути ради небольшого
 * дублирования (~40 строк), чтобы не задевать протестированный admin-код.
 */
export function useMyTests() {
  const [items, setItems]     = useState([]);
  const [total, setTotal]     = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState(null);
  const [page, setPage]       = useState(1);
  const [query, setQueryRaw]  = useState('');
  const [filters, setFilters] = useState({ status: null });

  const debouncedQuery = useDebounce(query, 300);
  const requestId = useRef(0);

  const fetch = useCallback(async (p, q, f) => {
    const id = ++requestId.current;
    setLoading(true);
    setError(null);
    try {
      const data = await getMyTests({
        page: p, size: 20, search: q || undefined, status: f.status || undefined,
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
    setFilters((prev) => ({ ...prev, ...next }));
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
