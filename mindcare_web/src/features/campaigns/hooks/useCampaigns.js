import { useCallback, useEffect, useRef, useState } from 'react';
import { getCampaigns } from '../../../api/campaigns.api';

const PAGE_SIZE = 20;

/**
 * Кампании супервизора: keyset-список «новые сверху» + «Показать ещё».
 * Контракт: { items, loading, loadingMore, error, hasMore, loadMore, refetch,
 * replaceItem, removeItem }. enabled=false (режим «под именем») — без запросов.
 * Запоздалый ответ прежнего поколения (refetch) отбрасывается.
 */
export default function useCampaigns(enabled = true) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(Boolean(enabled));
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState(null);
  const [hasMore, setHasMore] = useState(false);
  const generation = useRef(0);

  const refetch = useCallback(() => {
    if (!enabled) return;
    const current = ++generation.current;
    setLoading(true);
    setError(null);
    getCampaigns({ size: PAGE_SIZE })
      .then((res) => {
        if (current !== generation.current) return;
        setItems(res?.items ?? []);
        setHasMore(Boolean(res?.has_more));
      })
      .catch((err) => {
        if (current === generation.current) {
          setError(err?.message || 'Не удалось загрузить кампании');
        }
      })
      .finally(() => {
        if (current === generation.current) setLoading(false);
      });
  }, [enabled]);

  const loadMore = useCallback(() => {
    if (!enabled || loadingMore || !items.length) return;
    const current = generation.current;
    setLoadingMore(true);
    getCampaigns({ size: PAGE_SIZE, before: items[items.length - 1].uuid })
      .then((res) => {
        if (current !== generation.current) return;
        setItems((prev) => {
          const known = new Set(prev.map((i) => i.uuid));
          return [...prev, ...(res?.items ?? []).filter((i) => !known.has(i.uuid))];
        });
        setHasMore(Boolean(res?.has_more));
      })
      .catch((err) => {
        if (current === generation.current) {
          setError(err?.message || 'Не удалось загрузить кампании');
        }
      })
      .finally(() => setLoadingMore(false));
  }, [enabled, items, loadingMore]);

  const replaceItem = useCallback((campaign) => {
    setItems((prev) => {
      const exists = prev.some((i) => i.uuid === campaign.uuid);
      return exists
        ? prev.map((i) => (i.uuid === campaign.uuid ? campaign : i))
        : [campaign, ...prev];
    });
  }, []);

  const removeItem = useCallback((uuid) => {
    setItems((prev) => prev.filter((i) => i.uuid !== uuid));
  }, []);

  useEffect(() => {
    refetch();
    return () => { generation.current += 1; };
  }, [refetch]);

  return {
    items, loading, loadingMore, error, hasMore, loadMore, refetch,
    replaceItem, removeItem,
  };
}
