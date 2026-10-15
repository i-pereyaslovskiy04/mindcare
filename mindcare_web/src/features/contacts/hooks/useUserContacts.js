import { useCallback, useEffect, useRef, useState } from 'react';
import { getUserContacts } from '../../../api/contacts.api';

const IDLE = { key: null, status: 'idle', data: null, error: null };

function kindOf(err) {
  if (err?.status === 404) return 'unavailable';
  if (err?.status === 403) return 'forbidden';
  if (err?.status === 503) return 'auditUnavailable';
  return 'error';
}

/**
 * Контакты пользователя для сотрудника (ADR-031), только чтение.
 *
 * Данные привязаны к uuid, под который загружены: при смене uuid, потере
 * доступа (404/403/503) и размонтировании прежние данные сразу исчезают, ответ
 * устаревшего запроса отбрасывается. Статусы: idle|loading|ready|unavailable|
 * forbidden|auditUnavailable|error. Контракт: { status, data, error, refetch }.
 * Значения контактов не логируются.
 */
export default function useUserContacts(userUuid) {
  const [state, setState] = useState(IDLE);
  const requestId = useRef(0);

  const load = useCallback(() => {
    const id = ++requestId.current;
    if (!userUuid) {
      setState(IDLE);
      return Promise.resolve();
    }
    setState({ key: userUuid, status: 'loading', data: null, error: null });
    return getUserContacts(userUuid)
      .then((data) => {
        if (id === requestId.current) {
          setState({ key: userUuid, status: 'ready', data, error: null });
        }
      })
      .catch((err) => {
        if (id === requestId.current) {
          setState({ key: userUuid, status: kindOf(err), data: null, error: err?.message || null });
        }
      });
  }, [userUuid]);

  useEffect(() => {
    load();
    return () => { requestId.current += 1; };
  }, [load]);

  // Состояние чужого uuid не показываем даже на один кадр.
  const current = state.key === userUuid
    ? state
    : { ...IDLE, status: userUuid ? 'loading' : 'idle' };

  return { status: current.status, data: current.data, error: current.error, refetch: load };
}
