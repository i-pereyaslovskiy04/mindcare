import { useCallback, useEffect, useRef, useState } from 'react';
import { getMyVerification } from '../../../api/studentVerification.api';

const LOAD_ERROR_MESSAGE = 'Не удалось загрузить статус подтверждения';

/**
 * Собственный статус подтверждения студента ДонГУ (ADR-029).
 * Контракт: { data, loading, error, refetch }.
 *
 * enabled=false (staff, режим «под именем») — запрос не выполняется: backend
 * всё равно ответил бы 403. «Побеждает последний запрос»: устаревший ответ не
 * перезапишет более свежий статус (например, после подачи заявки).
 */
export default function useMyStudentVerification(enabled = true) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(Boolean(enabled));
  const [error, setError] = useState(null);
  const latestRequest = useRef(0);

  const refetch = useCallback(() => {
    const requestId = latestRequest.current + 1;
    latestRequest.current = requestId;
    const isLatest = () => latestRequest.current === requestId;

    if (!enabled) {
      setData(null);
      setError(null);
      setLoading(false);
      return Promise.resolve();
    }
    setLoading(true);
    setError(null);
    return getMyVerification()
      .then((response) => {
        if (isLatest()) setData(response);
      })
      .catch((err) => {
        if (isLatest()) setError(err?.message || LOAD_ERROR_MESSAGE);
      })
      .finally(() => {
        if (isLatest()) setLoading(false);
      });
  }, [enabled]);

  useEffect(() => {
    refetch();
    return () => { latestRequest.current += 1; };
  }, [refetch]);

  return { data, loading, error, refetch, setData };
}
