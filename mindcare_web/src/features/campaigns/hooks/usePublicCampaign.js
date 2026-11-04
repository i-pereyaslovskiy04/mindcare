import { useCallback, useEffect, useRef, useState } from 'react';
import { getPublicCampaign } from '../../../api/campaigns.api';

/**
 * Анкета кампании по токену ссылки (без входа). Контракт: { data, loading,
 * error, refetch }. error — { status, message }: 404 — ссылка недействительна
 * или опрос завершён. Запоздалый ответ прежнего токена отбрасывается.
 */
export default function usePublicCampaign(token) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const generation = useRef(0);

  const load = useCallback(() => {
    const current = ++generation.current;
    setLoading(true);
    setError(null);
    return getPublicCampaign(token)
      .then((response) => {
        if (current !== generation.current) return;
        setData(response);
      })
      .catch((err) => {
        if (current !== generation.current) return;
        setData(null);
        setError({ status: err?.status ?? null, message: err?.message || '' });
      })
      .finally(() => {
        if (current === generation.current) setLoading(false);
      });
  }, [token]);

  useEffect(() => {
    load();
    return () => { generation.current += 1; };
  }, [load]);

  return { data, loading, error, refetch: load };
}
