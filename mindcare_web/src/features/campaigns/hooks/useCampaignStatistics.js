import { useCallback, useEffect, useRef, useState } from 'react';
import { getCampaignStatistics } from '../../../api/campaigns.api';

/**
 * Статистика кампании (ТЗ редактора методик, этап 2, §7) по тем же фильтрам,
 * что экран результатов. Загружается только когда enabled (вкладка открыта).
 * Контракт: { data, loading, error, refetch }. Запоздалый ответ отбрасывается.
 */
export default function useCampaignStatistics(campaignUuid, filters, enabled) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const generation = useRef(0);

  const load = useCallback(() => {
    if (!enabled) return;
    const current = ++generation.current;
    setLoading(true);
    setError(null);
    getCampaignStatistics(campaignUuid, filters)
      .then((res) => {
        if (current !== generation.current) return;
        setData(res);
      })
      .catch((err) => {
        if (current !== generation.current) return;
        setData(null);
        setError(err?.message || 'Не удалось загрузить статистику');
      })
      .finally(() => {
        if (current === generation.current) setLoading(false);
      });
  }, [campaignUuid, filters, enabled]);

  useEffect(() => {
    load();
    return () => { generation.current += 1; };
  }, [load]);

  return { data, loading, error, refetch: load };
}
