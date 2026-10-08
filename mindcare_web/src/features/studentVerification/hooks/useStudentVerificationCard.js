import { useCallback, useEffect, useRef, useState } from 'react';
import { getStudentVerification } from '../../../api/studentVerification.api';

/**
 * Карточка заявки для supervisor — содержит ПОЛНЫЙ номер билета (backend
 * пишет аудит чтения; при сбое аудита — 503 без номера). Загружается только
 * при открытии (uuid задан). Контракт: { data, loading, error, refetch }.
 */
export default function useStudentVerificationCard(uuid) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(Boolean(uuid));
  const [error, setError] = useState(null);
  const latestRequest = useRef(0);

  const refetch = useCallback(() => {
    const requestId = latestRequest.current + 1;
    latestRequest.current = requestId;
    const isLatest = () => latestRequest.current === requestId;
    setData(null);
    if (!uuid) {
      setLoading(false);
      setError(null);
      return Promise.resolve();
    }
    setLoading(true);
    setError(null);
    return getStudentVerification(uuid)
      .then((response) => { if (isLatest()) setData(response); })
      .catch((err) => { if (isLatest()) setError(err); })
      .finally(() => { if (isLatest()) setLoading(false); });
  }, [uuid]);

  useEffect(() => {
    refetch();
    return () => { latestRequest.current += 1; };
  }, [refetch]);

  return { data, loading, error, refetch };
}
