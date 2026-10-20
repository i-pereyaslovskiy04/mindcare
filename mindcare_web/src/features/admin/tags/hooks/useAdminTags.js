import { useState, useEffect } from 'react';
import { useDebounce } from '../../../../hooks/useDebounce';
import { getTags } from '../../../../api/tags.api';

export function useAdminTags() {
  const [items, setItems]     = useState([]);
  const [total, setTotal]     = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(null);
  const [page, setPage]       = useState(1);
  const [size]                = useState(50);
  const [query, setQueryRaw]  = useState('');
  const [tick, setTick]       = useState(0);

  const debouncedQuery = useDebounce(query, 300);

  function setQuery(val) {
    setQueryRaw(val);
    setPage(1);
  }

  function refetch() {
    setTick((t) => t + 1);
  }

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    getTags({ page, size, search: debouncedQuery })
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
  }, [debouncedQuery, page, size, tick]);

  return { items, loading, error, total, page, setPage, size, query, setQuery, refetch };
}
