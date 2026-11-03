import { useCallback, useRef, useState } from 'react';
import { markAppointmentOutcome } from '../../../api/appointments.api';

const FALLBACK = 'Не удалось сохранить итог встречи. Повторите попытку.';
const AUDIT_UNAVAILABLE = 'Итог не сохранён: не удалось зафиксировать действие в журнале. Повторите попытку позже.';

function messageFor(err) {
  switch (err?.status) {
    case 409: return `${err.message || 'Итог отметить нельзя'}. Список встреч обновлён.`;
    case 403: return 'Итог встречи отмечает только проводивший её психолог.';
    case 404: return 'Встреча не найдена. Список встреч обновлён.';
    case 503: return AUDIT_UNAVAILABLE;
    default:  return FALLBACK;
  }
}

/**
 * Отметка итога индивидуальной встречи (ADR-035): «Состоялась» / «Неявка».
 * Время окончания проверяет сервер; успех — только по ответу сервера (без
 * оптимистичного обновления). Двойная отправка исключена ref-lock'ом.
 * onDone вызывается после успеха, а также после 409/404 — состояние встречи
 * изменилось, связанные списки нужно перечитать.
 */
export default function useAppointmentOutcome({ onDone } = {}) {
  const [pending, setPending] = useState(null);  // { uuid, outcome }
  const [error, setError] = useState(null);      // { uuid, message }
  const lock = useRef(false);
  const onDoneRef = useRef(onDone);
  onDoneRef.current = onDone;

  const mark = useCallback(async (uuid, outcome) => {
    if (lock.current) return false;
    lock.current = true;
    setPending({ uuid, outcome });
    setError(null);
    try {
      await markAppointmentOutcome(uuid, outcome);
      onDoneRef.current?.();
      return true;
    } catch (err) {
      setError({ uuid, message: messageFor(err) });
      if (err?.status === 409 || err?.status === 404) onDoneRef.current?.();
      return false;
    } finally {
      lock.current = false;
      setPending(null);
    }
  }, []);

  const clearError = useCallback(() => setError(null), []);

  return { mark, pending, error, clearError };
}
