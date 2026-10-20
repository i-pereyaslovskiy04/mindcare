import { useEffect, useState } from 'react';
import { getAvailableSlots } from '../../../api/appointments.api';

/**
 * Слоты для выбранного типа встречи + формата + даты (schedule v2).
 * Запрос уходит только когда заданы все три параметра.
 */
export function useAvailableSlots({ date, meetingTypeId, modality } = {}) {
  const [slots, setSlots] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!date || !meetingTypeId || !modality) {
      setSlots([]);
      setError(null);
      return undefined;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    setSlots([]);
    getAvailableSlots(date, { meetingTypeId, modality })
      .then((data) => { if (!cancelled) setSlots(data.slots || []); })
      .catch((e) => {
        if (!cancelled) setError(e.message || 'Ошибка загрузки слотов');
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [date, meetingTypeId, modality]);

  return { slots, loading, error };
}
