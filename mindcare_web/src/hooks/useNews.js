import { useState, useEffect, useCallback } from 'react';
import { getNews } from '../api/news.api';

export function useNews(page = 1, limit = 9) {
  const [items, setItems] = useState([]);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetch = useCallback(() => {
    setLoading(true);
    setError(null);

    getNews(page, limit)
      .then((data) => {
        const news = Array.isArray(data) ? data : (data.items || []);
        const total = data.total ?? news.length;
        setItems(news);
        setTotalPages(Math.max(1, Math.ceil(total / limit)));
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [page, limit]);

  useEffect(() => { fetch(); }, [fetch]);

  return { items, totalPages, loading, error, refetch: fetch };
}
