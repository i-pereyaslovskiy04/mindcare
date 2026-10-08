import { useCallback, useEffect, useRef, useState } from 'react';
import { getStudentVerifications } from '../../../api/studentVerification.api';
import { useDebounce } from '../../../hooks/useDebounce';

const PAGE_SIZE = 20;

/**
 * Список заявок для supervisor (ADR-029) — серверная пагинация, фильтр
 * статуса и поиск по ФИО/email на backend. Номер билета в списке не приходит.
 * Контракт: { items, loading, error, total, page, setPage, query, setQuery,
 * filters, setFilters, refetch }. enabled=false — запросов нет (режим «под
 * именем»: backend всё равно ответил бы 403).
 */
export default function useStudentVerifications(enabled = true) {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(Boolean(enabled));
  const [error, setError] = useState(null);
  const [page, setPage] = useState(1);
  const [query, setQueryRaw] = useState('');
  const [filters, setFiltersRaw] = useState({ status: 'pending' });

  const debouncedQuery = useDebounce(query, 300);
  const requestId = useRef(0);

  const fetchList = useCallback(async (p, q, f) => {
    const id = ++requestId.current;
    if (!enabled) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await getStudentVerifications({
        page: p, size: PAGE_SIZE, status: f.status, search: q || undefined,
      });
      if (id !== requestId.current) return;
      setItems(Array.isArray(data?.items) ? data.items : []);
      setTotal(data?.total ?? 0);
    } catch (err) {
      if (id !== requestId.current) return;
      setError(err?.message || 'Не удалось загрузить заявки');
    } finally {
      if (id === requestId.current) setLoading(false);
    }
  }, [enabled]);

  useEffect(() => {
    fetchList(page, debouncedQuery, filters);
  }, [page, debouncedQuery, filters, fetchList]);

  const setQuery = useCallback((value) => {
    setQueryRaw(value);
    setPage(1);
  }, []);

  const setFilters = useCallback((next) => {
    setFiltersRaw((prev) => ({ ...prev, ...next }));
    setPage(1);
  }, []);

  const refetch = useCallback(
    () => fetchList(page, debouncedQuery, filters),
    [fetchList, page, debouncedQuery, filters],
  );

  return {
    items, loading, error, total, page, setPage,
    query, setQuery, filters, setFilters, refetch,
    pageSize: PAGE_SIZE,
  };
}
