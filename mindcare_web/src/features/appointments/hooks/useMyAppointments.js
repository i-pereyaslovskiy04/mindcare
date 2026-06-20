import { useCallback, useEffect, useRef, useState } from 'react';
import { getMyAppointments } from '../../../api/appointments.api';

export function useMyAppointments({ size = 50 } = {}) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const reqId = useRef(0);

  const fetch = useCallback(async () => {
    const id = ++reqId.current;
    setLoading(true);
    setError(null);
    try {
      const data = await getMyAppointments({ size });
      if (id !== reqId.current) return;
      setItems(data.items || []);
    } catch (e) {
      if (id !== reqId.current) return;
      setError(e.message || 'Ошибка загрузки');
    } finally {
      if (id === reqId.current) setLoading(false);
    }
  }, [size]);

  useEffect(() => { fetch(); }, [fetch]);

  return { items, loading, error, refetch: fetch };
}
