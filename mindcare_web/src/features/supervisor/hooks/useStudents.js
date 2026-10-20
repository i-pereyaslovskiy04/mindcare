import { useCallback, useEffect, useRef, useState } from 'react';
import { getSupervisorStudents } from '../../../api/supervisor.api';
import { useDebounce } from '../../../hooks/useDebounce';

export function useStudents() {
  const [items, setItems]     = useState([]);
  const [total, setTotal]     = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState(null);
  const [page, setPage]       = useState(1);
  const [query, setQueryRaw]  = useState('');

  const debouncedQuery = useDebounce(query, 300);
  const requestId      = useRef(0);

  const fetchStudents = useCallback(async (p, q) => {
    const id = ++requestId.current;
    setLoading(true);
    setError(null);
    try {
      const data = await getSupervisorStudents({ page: p, size: 20, search: q || undefined });
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
    fetchStudents(page, debouncedQuery);
  }, [page, debouncedQuery, fetchStudents]);

  function setQuery(val) {
    setQueryRaw(val);
    setPage(1);
  }

  const refetch = () => fetchStudents(page, debouncedQuery);

  return { items, loading, error, total, page, setPage, query, setQuery, refetch };
}
