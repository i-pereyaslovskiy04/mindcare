import { useCallback, useEffect, useRef, useState } from 'react';
import { getCampaignResults } from '../../../api/campaigns.api';

export const EMPTY_FILTERS = { faculty_code: '', gender: '', validity: '', type: '' };

/**
 * Первичная обработка результатов кампании (ADR-036): баллы, уровни, типы
 * участников и сводка. Фильтрация — на сервере. Каждый запрос с непустой
 * кампанией фиксируется в журнале аудита (ФИО). Контракт:
 * { data, loading, error, filters, setFilters, refetch }.
 * Запоздалый ответ прежних фильтров/кампании отбрасывается. ФИО не логировать.
 */
export default function useCampaignResults(campaignUuid, enabled = true) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(Boolean(enabled));
  const [error, setError] = useState(null);
  const [filters, setFiltersState] = useState(EMPTY_FILTERS);
  const generation = useRef(0);

  const load = useCallback(() => {
    if (!enabled) return;
    const current = ++generation.current;
    setLoading(true);
    setError(null);
    getCampaignResults(campaignUuid, filters)
      .then((res) => {
        if (current !== generation.current) return;
        setData(res);
        setLoading(false);
      })
      .catch((err) => {
        if (current !== generation.current) return;
        setData(null);
        setError(err?.message || 'Не удалось загрузить результаты');
        setLoading(false);
      });
  }, [campaignUuid, enabled, filters]);

  useEffect(() => {
    load();
    return () => { generation.current += 1; };
  }, [load]);

  const setFilters = useCallback((patch) => {
    setFiltersState((prev) => ({ ...prev, ...patch }));
  }, []);

  return { data, loading, error, filters, setFilters, refetch: load };
}
