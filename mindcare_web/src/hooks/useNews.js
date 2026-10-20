import { useState, useEffect, useCallback } from 'react';
import { getNews, normalizeNewsItem } from '../api/news.api';

export function useNews(page = 1, limit = 9) {
  const [items, setItems]           = useState([]);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading]       = useState(true);
  const [error, setError]           = useState(null);

  const fetch = useCallback(() => {
    setLoading(true);
    setError(null);
    getNews({ page, size: limit })
      .then((data) => {
        const raw   = Array.isArray(data) ? data : (data.items || []);
        const total = data.total ?? raw.length;
        setItems(raw.map(normalizeNewsItem));
        setTotalPages(Math.max(1, Math.ceil(total / limit)));
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [page, limit]);

  useEffect(() => { fetch(); }, [fetch]);

  return { items, totalPages, loading, error, refetch: fetch };
}
