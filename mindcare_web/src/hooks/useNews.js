import { useState, useEffect, useCallback } from 'react';
import { getNews } from '../api/news.api';

function formatDate(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleDateString('ru-RU', {
    day: 'numeric', month: 'long', year: 'numeric',
  });
}

// Приводит ответ API к формату который ожидают FeaturedNews и NewsListItem
function normalize(item) {
  return {
    id:          item.uuid,
    uuid:        item.uuid,
    tag:         item.tags?.[0]?.name || '',
    title:       item.title,
    description: '',               // у новостей нет excerpt
    date:        formatDate(item.published_at || item.created_at),
    image:       item.cover_image_url || null,
    // сырые поля для NewsItemPage
    content:     item.content,
    tags:        item.tags,
  };
}

export function useNews(page = 1, limit = 9) {
  const [items, setItems]         = useState([]);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState(null);

  const fetch = useCallback(() => {
    setLoading(true);
    setError(null);
    getNews({ page, size: limit })
      .then((data) => {
        const raw = Array.isArray(data) ? data : (data.items || []);
        const total = data.total ?? raw.length;
        setItems(raw.map(normalize));
        setTotalPages(Math.max(1, Math.ceil(total / limit)));
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [page, limit]);

  useEffect(() => { fetch(); }, [fetch]);

  return { items, totalPages, loading, error, refetch: fetch };
}
