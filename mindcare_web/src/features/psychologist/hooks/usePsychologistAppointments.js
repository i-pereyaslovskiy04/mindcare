import { useCallback, useEffect, useRef, useState } from 'react';
import { getPsychologistAppointments } from '../../../api/appointments.api';

export function usePsychologistAppointments({ size = 20 } = {}) {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState('');
  const reqId = useRef(0);

  const fetchData = useCallback(async (p, st) => {
    const id = ++reqId.current;
    setLoading(true);
    setError(null);
    try {
      const data = await getPsychologistAppointments({
        page: p,
        size,
        status: st || undefined,
      });
      if (id !== reqId.current) return;
      setItems(data.items || []);
      setTotal(data.total || 0);
    } catch (e) {
      if (id !== reqId.current) return;
      setError(e.message || 'Ошибка загрузки');
    } finally {
      if (id === reqId.current) setLoading(false);
    }
  }, [size]);

  useEffect(() => { fetchData(page, statusFilter); }, [page, statusFilter, fetchData]);

  function setFilter(val) {
    setStatusFilter(val);
    setPage(1);
  }

  const refetch = () => fetchData(page, statusFilter);

  return { items, total, loading, error, page, setPage, statusFilter, setFilter, refetch };
}
