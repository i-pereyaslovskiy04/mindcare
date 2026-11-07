import { useCallback, useEffect, useRef, useState } from 'react';
import { getCampaign } from '../../../api/campaigns.api';

/**
 * Одна кампания супервизора (страница /supervisor/campaigns/:uuid).
 * Контракт: { data, loading, error, refetch, setData }. setData — обновить
 * карточку ответом backend после действия (без повторного запроса).
 * Запоздалый ответ прежнего uuid отбрасывается.
 */
export default function useCampaign(uuid) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const generation = useRef(0);

  const refetch = useCallback(() => {
    const current = ++generation.current;
    setLoading(true);
    setError(null);
    getCampaign(uuid)
      .then((res) => { if (current === generation.current) setData(res); })
      .catch((err) => {
        if (current !== generation.current) return;
        setData(null);
        setError(err?.status === 404
          ? 'Кампания не найдена — возможно, её удалили.'
          : err?.message || 'Не удалось загрузить кампанию');
      })
      .finally(() => { if (current === generation.current) setLoading(false); });
  }, [uuid]);

  useEffect(() => {
    setData(null);
    refetch();
    return () => { generation.current += 1; };
  }, [refetch]);

  return { data, loading, error, refetch, setData };
}
