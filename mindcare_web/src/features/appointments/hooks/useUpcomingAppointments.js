import { useEffect, useState } from 'react';
import { getMyUpcomingAppointments } from '../../../api/appointments.api';

/**
 * Ближайшие встречи клиента для главной кабинета: запрос уже отдаёт
 * отфильтрованные (ожидает подтверждения/подтверждена, starts_at в будущем)
 * и отсортированные по возрастанию starts_at записи — лимит применяется на
 * сервере после фильтрации, а не к первой странице общего списка.
 */
export default function useUpcomingAppointments({ limit = 3 } = {}) {
  const [state, setState] = useState({ items: [], loading: true, error: false });

  useEffect(() => {
    let alive = true;
    getMyUpcomingAppointments({ limit })
      .then((items) => {
        if (!alive) return;
        setState({ items: Array.isArray(items) ? items : [], loading: false, error: false });
      })
      .catch(() => {
        if (alive) setState({ items: [], loading: false, error: true });
      });
    return () => { alive = false; };
  }, [limit]);

  return state;
}
