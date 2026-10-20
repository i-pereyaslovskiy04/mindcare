import { useEffect, useState } from 'react';
import { getFaculties } from '../../../api/studentVerification.api';

/**
 * Каталог факультетов ДонГУ — единственный источник backend (ADR-029).
 * Контракт: { data, loading, error }. data — [{ value, label }] для shared Select.
 */
export default function useFaculties(enabled = true) {
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
    setError(null);
    getFaculties()
      .then((response) => {
        if (cancelled) return;
        const items = Array.isArray(response?.items) ? response.items : [];
        setData(items
          .filter((i) => typeof i?.code === 'string' && i.code)
          .map((i) => ({ value: i.code, label: i.label || i.code })));
      })
      .catch((err) => {
        if (!cancelled) setError(err?.message || 'Не удалось загрузить список факультетов');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [enabled]);

  return { data, loading, error };
}
