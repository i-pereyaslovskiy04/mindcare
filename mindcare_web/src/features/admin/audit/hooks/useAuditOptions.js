import { useCallback, useEffect, useRef, useState } from 'react';
import { getAuditOptions } from '../../../../api/audit.api';

/**
 * Справочник фильтров журналов (`GET /api/admin/audit/options`).
 *
 * Живёт отдельным hook'ом намеренно: его ошибка не должна подменять ошибку
 * списка и наоборот. При недоступном справочнике страница остаётся рабочей на
 * базовых фильтрах (период, порядок, участник, страница), а registry-зависимые
 * селекты просто отключаются.
 *
 * Контракт короткого объекта: { data, loading, error, refetch }.
 */
export function useAuditOptions() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [tick, setTick] = useState(0);
  const latest = useRef(0);

  const refetch = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    let cancelled = false;
    const reqId = latest.current + 1;
    latest.current = reqId;

    setLoading(true);
    setError(null);

    getAuditOptions()
      .then((payload) => {
        if (cancelled || latest.current !== reqId) return;
        setData(payload);
      })
      .catch((err) => {
        if (cancelled || latest.current !== reqId) return;
        setData(null);
        setError(err.message);
      })
      .finally(() => {
        if (cancelled || latest.current !== reqId) return;
        setLoading(false);
      });

    return () => { cancelled = true; };
  }, [tick]);

  return { data, loading, error, refetch };
}
