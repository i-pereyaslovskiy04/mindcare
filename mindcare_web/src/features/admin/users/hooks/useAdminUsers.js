import { useState, useEffect } from 'react';
import { useDebounce } from '../../../../hooks/useDebounce';
import { getUsers } from '../../../../api/users.api';

export function useAdminUsers() {
  const [items, setItems]   = useState([]);
  const [total, setTotal]   = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError]   = useState(null);
  const [page, setPage]     = useState(1);
  const [query, setQueryRaw]   = useState('');
  const [filters, setFiltersRaw] = useState({ role: '', is_active: '' });
  const [tick, setTick]     = useState(0);

  const debouncedQuery = useDebounce(query, 300);

  function setQuery(val) {
    setQueryRaw(val);
    setPage(1);
  }

  function setFilters(val) {
    setFiltersRaw(val);
    setPage(1);
  }

  function refetch() {
    setTick((t) => t + 1);
  }

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    getUsers({
      page,
      search:    debouncedQuery,
      role:      filters.role,
      is_active: filters.is_active,
    })
      .then((data) => {
        if (!cancelled) {
          setItems(data.items);
          setTotal(data.total);
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, [debouncedQuery, filters, page, tick]);

  return {
    items,
    loading,
    error,
    total,
    page,
    setPage,
    query,
    setQuery,
    filters,
    setFilters,
    refetch,
  };
}
