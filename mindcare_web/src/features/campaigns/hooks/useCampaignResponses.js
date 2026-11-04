import { useCallback, useEffect, useRef, useState } from 'react';
import { deleteCampaignResponse, getCampaignResponses } from '../../../api/campaigns.api';

const PAGE_SIZE = 50;

/**
 * Участники кампании (ФИО — каждая страница фиксируется в журнале аудита на
 * backend). Загрузка — только когда панель открыта (enabled). Контракт:
 * { items, loading, loadingMore, error, hasMore, loadMore, remove }.
 * Смена кампании или закрытие панели отбрасывает запоздалые ответы.
 * ФИО не логировать.
 */
export default function useCampaignResponses(campaignUuid, enabled) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState(null);
  const [hasMore, setHasMore] = useState(false);
  const generation = useRef(0);

  useEffect(() => {
    const current = ++generation.current;
    setItems([]);
    setHasMore(false);
    setError(null);
    if (!enabled) {
      setLoading(false);
      return undefined;
    }
    setLoading(true);
    getCampaignResponses(campaignUuid, { size: PAGE_SIZE })
      .then((res) => {
        if (current !== generation.current) return;
        setItems(res?.items ?? []);
        setHasMore(Boolean(res?.has_more));
      })
      .catch((err) => {
        if (current === generation.current) {
          setError(err?.message || 'Не удалось загрузить участников');
        }
      })
      .finally(() => {
        if (current === generation.current) setLoading(false);
      });
    return () => { generation.current += 1; };
  }, [campaignUuid, enabled]);

  const loadMore = useCallback(() => {
    if (!enabled || loadingMore || !items.length) return;
    const current = generation.current;
    setLoadingMore(true);
    getCampaignResponses(campaignUuid, { size: PAGE_SIZE, after: items[items.length - 1].uuid })
      .then((res) => {
        if (current !== generation.current) return;
        setItems((prev) => [...prev, ...(res?.items ?? [])]);
        setHasMore(Boolean(res?.has_more));
      })
      .catch((err) => {
        if (current === generation.current) {
          setError(err?.message || 'Не удалось загрузить участников');
        }
      })
      .finally(() => setLoadingMore(false));
  }, [campaignUuid, enabled, items, loadingMore]);

  /** Удаляет ответ; бросает ошибку вызывающему (без оптимистичного успеха). */
  const remove = useCallback(async (responseUuid) => {
    await deleteCampaignResponse(campaignUuid, responseUuid);
    setItems((prev) => prev.filter((i) => i.uuid !== responseUuid));
  }, [campaignUuid]);

  return { items, loading, loadingMore, error, hasMore, loadMore, remove };
}
