import { useEffect, useState } from 'react';
import { getCampaignTests } from '../../../api/campaigns.api';

/** Тесты для кампаний. Контракт: { data, loading, error }; data — [{ value, label }]. */
export default function useCampaignTests(enabled = true) {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(Boolean(enabled));
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return undefined;
    }
    let cancelled = false;
    setLoading(true);
    getCampaignTests()
      .then((items) => {
        if (cancelled) return;
        setData((Array.isArray(items) ? items : [])
          .map((t) => ({ value: t.uuid, label: t.title })));
      })
      .catch((err) => {
        if (!cancelled) setError(err?.message || 'Не удалось загрузить тесты');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [enabled]);

  return { data, loading, error };
}
