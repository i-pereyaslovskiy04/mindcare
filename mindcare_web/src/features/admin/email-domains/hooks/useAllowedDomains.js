import { useState, useEffect, useCallback } from 'react';
import {
  getEmailDomains,
  createEmailDomain,
  updateEmailDomain,
} from '../../../../api/domains.api';

/**
 * Список разрешённых почтовых доменов для админ-настроек.
 * Контракт: { items, loading, error, refetch, addDomain, setActive }.
 * Мутации возвращают Promise (компонент показывает ошибки inline).
 */
export function useAllowedDomains() {
  const [items, setItems]     = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(null);
  const [tick, setTick]       = useState(0);

  const refetch = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getEmailDomains()
      .then((data) => { if (!cancelled) setItems(data || []); })
      .catch((err) => { if (!cancelled) setError(err.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [tick]);

  const addDomain = useCallback(async (payload) => {
    const created = await createEmailDomain(payload);
    refetch();
    return created;
  }, [refetch]);

  const setActive = useCallback(async (id, isActive) => {
    const updated = await updateEmailDomain(id, { is_active: isActive });
    refetch();
    return updated;
  }, [refetch]);

  return { items, loading, error, refetch, addDomain, setActive };
}
